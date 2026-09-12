"""Bounded, provider-neutral execution beneath the Deep Research Engine.

The executor can use injected adapters to discover or retrieve public material.
It never treats discovery as publication evidence and never calls an editorial
provider.  Fixture adapters make the state transitions deterministic in tests;
the optional HTTP adapter only executes direct fetch actions through DRAGON's
existing safe fetch/extract path.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Protocol
from urllib.parse import quote_plus, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

import yaml

from dragon.deep_research import advance_research_job
from dragon.discovery import DiscoveryError, default_transport, discover_rss, fetch_and_extract_source
from dragon.evidence_validation import validate_exact_page
from dragon.research_recovery import build_recovery_plan
from dragon.source_intelligence import build_source_intelligence, normalize_url
from dragon.publisher_profiles import PublisherProfileCache, publisher_profile_from_pages
from dragon.evidence_policy import candidate_evidence_policy


ACTION_TYPES = {
    "SEARCH_DISCOVERY", "FETCH_URL", "FETCH_CONFIGURED_SOURCE",
    "SEARCH_OFFICIAL_SOURCE", "SEARCH_INDEPENDENT_COVERAGE",
    "SEARCH_ARCHIVE_OR_CATALOG", "FOLLOW_REFERENCE", "EXTRACT_DOCUMENT",
    "CHECK_CONTRADICTION", "RECOVER_PRIMARY_SOURCE",
    "RECOVER_INDEPENDENT_SOURCE", "FIND_DISTINCT_EVENT",
}
SEARCH_ACTIONS = {
    "SEARCH_DISCOVERY", "SEARCH_OFFICIAL_SOURCE", "SEARCH_INDEPENDENT_COVERAGE",
    "SEARCH_ARCHIVE_OR_CATALOG", "CHECK_CONTRADICTION", "RECOVER_PRIMARY_SOURCE",
    "RECOVER_INDEPENDENT_SOURCE", "FIND_DISTINCT_EVENT",
}
FETCH_ACTIONS = {"FETCH_URL", "FETCH_CONFIGURED_SOURCE", "FOLLOW_REFERENCE", "EXTRACT_DOCUMENT"}
OBSERVATION_CLASSES = {
    "LEAD", "POTENTIAL_EVIDENCE", "CONTEXT", "CONTRADICTION", "DUPLICATE",
    "IRRELEVANT", "DEAD_END",
}

# These priorities govern finite *research* work only.  They deliberately do
# not alter the independent publication gate in research_recovery.
PRIORITY_ORDER = {
    "P0_BLOCKING_EVIDENCE": 0,
    "P1_BREADTH": 1,
    "P1_DISTINCT_EVENT": 1,
    "P2_CONTRADICTION": 2,
    "P3_CONTEXT": 3,
}

_SOCIAL_ORIGINS = {"facebook.com", "www.facebook.com", "x.com", "twitter.com", "www.twitter.com", "instagram.com", "www.instagram.com", "youtube.com", "www.youtube.com"}
_AGGREGATOR_MARKERS = {"google", "feed", "rss", "aggregator", "archive"}


def _registrable_domain(origin: str | None) -> str | None:
    """Return a conservative domain family without claiming publisher identity."""
    if not origin:
        return None
    labels = origin.casefold().strip(".").split(".")
    return ".".join(labels[-2:]) if len(labels) >= 2 else origin.casefold()


def _lead_source_profile(url: str | None, title: str, snippet: str = "") -> dict:
    """Classify cheap, deterministic routing signals before an expensive fetch.

    This identifies obvious social and aggregation routes for *selection*.  It
    deliberately never upgrades a page to an independent/primary source.
    """
    origin = (urlsplit(url or "").hostname or "").casefold()
    family = _registrable_domain(origin)
    haystack = f"{origin} {title} {snippet}".casefold()
    if origin in _SOCIAL_ORIGINS or any(origin.endswith(f".{item}") for item in _SOCIAL_ORIGINS):
        kind = "SOCIAL"
    elif any(marker in haystack for marker in _AGGREGATOR_MARKERS):
        kind = "AGGREGATOR"
    elif origin:
        kind = "PUBLISHER_UNRESOLVED"
    else:
        kind = "SOURCE_UNRESOLVED"
    return {
        "origin": origin or None,
        "origin_family": family,
        "routing_class": kind,
        "identity_state": "SOURCE_UNRESOLVED" if kind == "SOURCE_UNRESOLVED" else "SOURCE_IDENTITY_PENDING",
    }


def _lead_priority(observation: dict, action: dict) -> tuple[str, list[str], tuple]:
    """Categorical fetch priority, not a journalism-confidence score."""
    result = observation.get("search_result", {}) if isinstance(observation.get("search_result"), dict) else {}
    title = str(observation.get("title") or "")
    snippet = str(result.get("snippet") or observation.get("claim") or "")
    profile = _lead_source_profile(observation.get("url"), title, snippet)
    haystack = f"{title} {snippet}".casefold()
    expected = {
        item.casefold() for item in [
            *action.get("known_entities", []),
            *(action.get("event_context", {}).get("entities", []) if isinstance(action.get("event_context"), dict) else []),
            *(action.get("event_context", {}).get("event_terms", []) if isinstance(action.get("event_context"), dict) else []),
            *action.get("query", "").split(),
        ] if len(str(item)) > 2
    }
    overlap = sum(term in haystack for term in expected)
    reasons = []
    if overlap:
        reasons.append("ENTITY_OR_EVENT_OVERLAP")
    if result.get("published_at") or observation.get("published_at"):
        reasons.append("DATE_AVAILABLE")
    if profile["routing_class"] in {"SOCIAL", "AGGREGATOR", "SOURCE_UNRESOLVED"}:
        reasons.append(profile["routing_class"])
        return "LOW", reasons, (2, int(result.get("rank") or 10**6), str(observation.get("url") or ""))
    if overlap >= 2:
        reasons.append("PUBLISHER_CANDIDATE")
        return "HIGH", reasons, (0, int(result.get("rank") or 10**6), str(observation.get("url") or ""))
    reasons.append("LIMITED_CONTEXT_MATCH")
    return "MEDIUM", reasons, (1, int(result.get("rank") or 10**6), str(observation.get("url") or ""))


def rank_discovery_leads(observations: list[dict], actions_by_id: dict[str, dict]) -> list[dict]:
    """Annotate discovery-only leads with deterministic, explainable priority."""
    ranked = []
    for observation in observations:
        action = actions_by_id.get(str(observation.get("provenance", {}).get("action_id") or ""))
        if not action or action.get("action_type") not in SEARCH_ACTIONS or observation.get("observation_class") != "LEAD" or not observation.get("url"):
            continue
        priority, reasons, key = _lead_priority(observation, action)
        profile = _lead_source_profile(
            observation.get("url"), str(observation.get("title") or ""),
            str((observation.get("search_result") or {}).get("snippet") or ""),
        )
        observation["lead_priority"] = priority
        observation["lead_priority_reasons"] = reasons
        observation["source_identity"] = profile
        observation["lead_attrition_state"] = "DISCOVERED_NOT_SELECTED"
        observation["_lead_sort_key"] = key
        ranked.append(observation)
    return ranked


def select_leads_for_followup(observations: list[dict], actions_by_id: dict[str, dict], limits: dict) -> list[dict]:
    """Choose a bounded, publisher/event-diverse subset of ranked leads."""
    ranked = rank_discovery_leads(observations, actions_by_id)
    groups: dict[str, list[dict]] = {}
    for item in ranked:
        parent = actions_by_id[item["provenance"]["action_id"]]
        need = str(parent.get("recovery_need_id") or f"QUESTION:{parent['question_id']}")
        groups.setdefault(need, []).append(item)
    selected: list[dict] = []
    for need in sorted(groups, key=lambda value: (
        PRIORITY_ORDER.get(str(actions_by_id[groups[value][0]["provenance"]["action_id"]].get("priority_class") or "P3_CONTEXT"), 99), value
    )):
        items = groups[need]
        parent = actions_by_id[items[0]["provenance"]["action_id"]]
        allowance = int(limits.get(str(parent.get("priority_class") or "P3_CONTEXT"), 0))
        require_event_diversity = str(parent.get("priority_class") or "") == "P1_DISTINCT_EVENT"
        seen_families, seen_titles = set(), set()
        for item in sorted(items, key=lambda value: value["_lead_sort_key"]):
            profile = item["source_identity"]
            title_key = " ".join(re.findall(r"[\w\u0600-\u06ff]+", str(item.get("title") or "").casefold())[:8])
            if len([value for value in selected if value.get("_followup_need") == need]) >= allowance:
                continue
            if (
                profile["routing_class"] in {"SOCIAL", "AGGREGATOR", "SOURCE_UNRESOLVED"}
                or profile.get("origin") in set(parent.get("excluded_origins", []))
                or profile.get("origin_family") in set(parent.get("excluded_origin_families", []))
                or profile.get("origin_family") in seen_families
                or (require_event_diversity and title_key in seen_titles)
            ):
                continue
            item["lead_attrition_state"] = "SELECTED_FOR_FETCH"
            item["_followup_need"] = need
            selected.append(item)
            seen_families.add(profile.get("origin_family"))
            seen_titles.add(title_key)
            if len(selected) >= int(limits.get("total", 0)):
                return selected
    return selected


class _RejectLocalSearchRedirect(HTTPRedirectHandler):
    """Do not let a private search endpoint bounce the client elsewhere."""

    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        return None


def _local_searxng_transport(url: str, timeout_seconds: int, maximum_bytes: int):
    """Fetch only the explicitly configured loopback SearXNG JSON endpoint.

    This is intentionally separate from ``default_transport``: that transport
    must continue rejecting all private addresses for public source pages.
    """
    parsed = urlsplit(url)
    if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or parsed.username or parsed.password:
        raise DiscoveryError("SEARCH_BACKEND_UNAVAILABLE", "local SearXNG endpoint policy rejected URL")
    request = Request(url, headers={"User-Agent": "DRAGON/5 private-search (+local newsroom)"})
    opener = build_opener(_RejectLocalSearchRedirect())
    with opener.open(request, timeout=timeout_seconds) as response:  # noqa: S310 - literal loopback host above
        final_url = response.geturl()
        if final_url != url:
            raise DiscoveryError("SEARCH_BACKEND_UNAVAILABLE", "local SearXNG redirect rejected")
        body = response.read(maximum_bytes + 1)
        if len(body) > maximum_bytes:
            raise DiscoveryError("SEARCH_BACKEND_UNAVAILABLE", "local SearXNG response exceeds bound")
        from dragon.discovery import FetchResponse
        return FetchResponse(final_url, int(response.status), response.headers.get_content_type(), body)


def recovery_priority(need: dict | None) -> str:
    """Classify a need without confusing research priority with readiness."""
    if not need:
        return "P3_CONTEXT"
    kind = str(need.get("kind") or "")
    if kind in {"FIND_PRIMARY_ORIGINAL_EVIDENCE", "FIND_INDEPENDENT_CORROBORATION"}:
        return "P0_BLOCKING_EVIDENCE"
    if kind == "NEED_DISTINCT_EVENT":
        return "P1_DISTINCT_EVENT"
    if kind.startswith("NEED_"):
        return "P1_BREADTH"
    if kind in {"CONTRADICTION", "CHECK_CONTRADICTION"}:
        return "P2_CONTRADICTION"
    return "P3_CONTEXT"


def _query_words(values: list[object]) -> list[str]:
    """Return stable, meaningful query terms rather than provider prose."""
    ignored = {"the", "and", "for", "with", "from", "this", "that", "في", "من", "على", "عن", "إلى", "الى", "مع", "بعد", "قبل", "حول", "تغطية", "أعلنت", "اعلنت"}
    words: list[str] = []
    for value in values:
        for word in str(value or "").replace("/", " ").replace("|", " ").split():
            cleaned = "".join(char for char in word if char.isalnum() or char in {"-", "_"})
            if len(cleaned) > 1 and cleaned.casefold() not in ignored and cleaned not in words:
                words.append(cleaned)
    return words


def _research_month(need: dict, job: dict) -> str:
    value = str(need.get("query_context", {}).get("research_date") or job.get("lead", {}).get("observed_at") or "")
    return value[:7] if len(value) >= 7 else ""


def event_fingerprint(job: dict, need: dict | None) -> str:
    """Identify the event/claim being recovered, not a publisher URL.

    This is deliberately a routing identity only.  It is stable across query
    variants and lets a failed publisher route be avoided for the same need
    without treating that failure as a verdict on the event or the desk.
    """
    if not need:
        return _stable_id("EVENT", job["lead"].get("related_event_cluster") or "", job["lead"].get("topic") or "")
    context = need.get("query_context", {})
    return _stable_id(
        "EVENT",
        need.get("event_id") or "",
        need.get("candidate_id") or "",
        need.get("missing_evidence_role") or "",
        " ".join(_query_words([*context.get("entities", []), *context.get("event_terms", []), *context.get("geography", [])])),
        context.get("research_date") or "",
    )


def _unusable_route_memory(job: dict, fingerprint: str) -> list[dict]:
    return [
        item for item in job.get("executor_state", {}).get("route_memory", [])
        if isinstance(item, dict) and item.get("event_fingerprint") == fingerprint
        and item.get("state") == "CURRENTLY_UNUSABLE"
    ]


def _route_exclusions(job: dict, need: dict | None) -> tuple[set[str], set[str]]:
    memory = _unusable_route_memory(job, event_fingerprint(job, need))
    return (
        {str(item["origin"]).casefold() for item in memory if item.get("origin")},
        {str(item["origin_family"]).casefold() for item in memory if item.get("origin_family")},
    )


def query_fingerprint(query: str, *, intent: str, language: str | None = None) -> str:
    """Deduplicate word-order rewrites while preserving distinct strategies."""
    normalized = sorted(set(word.casefold() for word in _query_words([query])))
    # Language is part of the search intent.  An Arabic and a French query for
    # a Meknes event are not superficial rewrites, but their order still is.
    return f"{intent}:{str(language or '').casefold()}:{' '.join(normalized)}"


def _search_languages(job: dict, need: dict | None) -> list[str]:
    """Choose a small desk-aware language set rather than translating blindly."""
    context = (need or {}).get("query_context", {})
    values = " ".join(str(item) for item in [
        job.get("lead", {}).get("desk"),
        job.get("lead", {}).get("topic"),
        *context.get("entities", []), *context.get("geography", []),
    ]).casefold()
    desk = str(job.get("lead", {}).get("desk") or "")
    if desk in {"meknes_local", "siyasa_dawla", "service", "investigations"} or any(
        item in values for item in ("morocco", "maroc", "meknes", "المغرب", "مكناس")
    ):
        return ["ar", "fr"]
    if desk == "filastin_middle_east":
        return ["ar", "en"]
    return ["en"]


_DESK_SEARCH_TERMS = {
    "africa_sahel": "Africa Sahel Sudan news",
    "filastin_middle_east": "Palestine Gaza Middle East news",
    "world": "world international news",
    "meknes_local": "Meknes Morocco local news",
    "siyasa_dawla": "Morocco politics public institutions",
    "service": "Morocco Meknes public services",
    "investigations": "Morocco audit procurement public accountability",
    "technology": "technology business news",
    "sport": "Morocco sport news",
    "culture": "Morocco culture news",
}


def _desk_terms(values: list[object]) -> str:
    """Translate internal desk IDs to finite, reader-facing search vocabulary."""
    terms = [_DESK_SEARCH_TERMS.get(str(value), str(value).replace("_", " ")) for value in values]
    return " ".join(item for item in terms if item)[:180]


def _breadth_target_section(need: dict) -> str:
    """Pick one eligible desk deterministically for an edition-wide event hunt.

    A breadth need is not a request to repeat every active desk in one query.
    Cycling the finite eligible list gives parallel needs different editorial
    targets, while retaining a stable route for audit and replay.
    """
    sections = list(need.get("search_constraints", {}).get("eligible_section_ids", []))
    if not sections:
        sections = list(need.get("topic_identifiers", []))
    if not sections:
        return "front"
    match = re.search(r":(\d+)$", str(need.get("need_id") or ""))
    index = int(match.group(1)) - 1 if match else 0
    return str(sections[index % len(sections)])


def _breadth_event_queries(job: dict, need: dict, *, month: str, primary_language: str, alternate_language: str | None, route: dict | None) -> list[dict]:
    """Return an event-acquisition ladder without copying provider prose.

    The plan is structured by the recovery planner: editorial gap, proposed
    event themes, date and eligible desks.  Existing retrieval adapters remain
    unchanged; this only gives them inspectable, distinct search intents.
    """
    plan = need.get("event_acquisition_plan", {})
    target_section = _breadth_target_section(need)
    themes = list(plan.get("candidate_event_themes", [])) or ["public institutional action"]
    families = list(plan.get("query_families", [])) or ["institutional", "topical", "geographical"]
    match = re.search(r":(\d+)$", str(need.get("need_id") or ""))
    index = int(match.group(1)) - 1 if match else 0
    theme = str(themes[index % len(themes)])
    relaxed_theme = str(themes[(index + 1) % len(themes)])
    is_morocco = str(plan.get("editorial_gap") or "") == "MOROCCO_BREADTH"
    geography = "Morocco" if is_morocco else "international"
    desk = _desk_terms([target_section])
    base = " ".join((geography, theme, desk, month))
    relaxed = " ".join((geography, relaxed_theme, desk))
    prefix = "DISTINCT_EVENT" if str(need.get("kind") or "") == "NEED_DISTINCT_EVENT" else "BREADTH"
    action_type = "FIND_DISTINCT_EVENT" if prefix == "DISTINCT_EVENT" else "SEARCH_DISCOVERY"
    return [
        {
            "intent": f"{prefix}_{str(families[0]).upper()}_WINDOW", "variant": "EVENT_THEME_DATE",
            "query": base, "channel": "SEARXNG_GENERAL_SEARCH", "backends": ["searxng-general-search"],
            "language": primary_language, "target_desk": target_section, "candidate_event_theme": theme,
            "fallback": {"action_type": action_type, "channel": "GOOGLE_NEWS_RSS", "backends": ["public-rss-search"]},
        },
        {
            "intent": f"{prefix}_{str(families[1 % len(families)]).upper()}_RELAXED", "variant": "RELAX_THEME_DATE",
            "query": relaxed, "channel": "GOOGLE_NEWS_RSS", "backends": ["public-rss-search"],
            "language": alternate_language or primary_language, "target_desk": target_section,
            "candidate_event_theme": relaxed_theme,
        },
        {
            "intent": f"{prefix}_ALTERNATIVE_EVENT", "variant": "EVENT_ALTERNATIVE",
            "query": base, "channel": "GDELT_DOC", "backends": ["gdelt-doc"], "language": primary_language,
            "target_desk": target_section, "candidate_event_theme": theme,
        },
    ]


def query_ladder(job: dict, need: dict | None) -> list[dict]:
    """Build a bounded, date-aware strategy ladder from structured context."""
    if not need:
        return [{"intent": "CONTEXT", "variant": "CONTEXT", "query": str(job["lead"].get("topic") or "")}]
    context = need.get("query_context", {})
    event_words = _query_words([
        *context.get("entities", []), *context.get("geography", []),
        *context.get("event_terms", []), *need.get("topic_identifiers", []),
    ])
    # Keep a compact seed, with date context supplied by the immutable packet.
    seed = " ".join(event_words[:12])
    month = _research_month(need, job)
    kind = str(need.get("kind") or "")
    languages = _search_languages(job, need)
    primary_language = languages[0]
    alternate_language = languages[1] if len(languages) > 1 else None
    routes = need.get("search_constraints", {}).get("configured_source_routes", [])
    excluded_origins, excluded_families = _route_exclusions(job, need)
    routes = [
        item for item in routes
        if str(item.get("origin") or urlsplit(str(item.get("url") or "")).hostname or "").casefold() not in excluded_origins
        and _registrable_domain(str(item.get("origin") or urlsplit(str(item.get("url") or "")).hostname or "")) not in excluded_families
    ]
    if kind == "FIND_INDEPENDENT_CORROBORATION":
        independent = [item for item in routes if item.get("role") == "INDEPENDENT" and item.get("url")]
        route = independent[0] if independent else None
        return [
            {
                "intent": "INDEPENDENT_CONFIGURED_ROUTE", "variant": "CONFIGURED_ROUTE",
                "query": " ".join(item for item in (seed, month) if item),
                "action_type": "FETCH_CONFIGURED_SOURCE", "target": route.get("url") if route else None,
                "channel": "CONFIGURED_INDEPENDENT_LISTING",
                # A failed configured publisher route must pivot to a
                # different origin for the same event, not retry that route
                # through a search-result wrapper.  GDELT remains metadata
                # discovery only and has its own bounded unavailable state.
                "fallback": {"action_type": "RECOVER_INDEPENDENT_SOURCE", "channel": "GDELT_DOC", "backends": ["gdelt-doc"]},
            },
            {"intent": "ENTITY_DATE_TERMS", "variant": "EXACT", "query": " ".join(item for item in (seed, month) if item), "channel": "SEARXNG_GENERAL_SEARCH", "backends": ["searxng-general-search"], "language": primary_language, "fallback": {"action_type": "RECOVER_INDEPENDENT_SOURCE", "channel": "GOOGLE_NEWS_RSS", "backends": ["public-rss-search"]}},
            {"intent": "ENTITY_ACTION_GEOGRAPHY", "variant": "RELAX_ENTITY_DATE", "query": seed, "channel": "SEARXNG_GENERAL_SEARCH", "backends": ["searxng-general-search"], "language": alternate_language or primary_language, "fallback": {"action_type": "RECOVER_INDEPENDENT_SOURCE", "channel": "GOOGLE_NEWS_RSS", "backends": ["public-rss-search"]}},
            {"intent": "FIND_ALTERNATIVE_COVERAGE", "variant": "EVENT_ALTERNATIVE", "query": " ".join(item for item in (seed, month) if item), "channel": "GDELT_DOC", "backends": ["gdelt-doc"], "language": primary_language},
            {"intent": "INDEPENDENT_SOURCE_ROUTE", "variant": "SOURCE_SPECIFIC", "query": " ".join(item for item in (f"site:{route.get('origin')}" if route else "", seed[:100], month) if item), "channel": "GOOGLE_NEWS_RSS", "backends": ["public-rss-search"]},
            {"intent": "INDEPENDENT_TOPIC", "variant": "RELAX_TOPIC", "query": " ".join(event_words[:6]), "channel": "SEARXNG_GENERAL_SEARCH", "backends": ["searxng-general-search"], "language": primary_language},
        ]
    if kind == "FIND_PRIMARY_ORIGINAL_EVIDENCE":
        official = [item for item in routes if item.get("role") == "PRIMARY" and item.get("url")]
        route = official[0] if official else None
        return [
            {
                "intent": "OFFICIAL_CONFIGURED_ROUTE", "variant": "CONFIGURED_ROUTE",
                "query": " ".join(item for item in (seed, month, "official document") if item),
                "action_type": "FETCH_CONFIGURED_SOURCE", "target": route.get("url") if route else None,
                "channel": "CONFIGURED_OFFICIAL_LISTING",
                "fallback": {"action_type": "RECOVER_PRIMARY_SOURCE", "channel": "GDELT_DOC", "backends": ["gdelt-doc"]},
            },
            {"intent": "OFFICIAL_ENTITY_ACTION", "variant": "EXACT", "query": " ".join(item for item in (seed, month, "official document") if item), "channel": "SEARXNG_GENERAL_SEARCH", "backends": ["searxng-general-search"], "language": primary_language, "fallback": {"action_type": "RECOVER_PRIMARY_SOURCE", "channel": "GOOGLE_NEWS_RSS", "backends": ["public-rss-search"]}},
            {"intent": "OFFICIAL_INSTITUTION_DATE", "variant": "RELAX_ENTITY_DATE", "query": " ".join(item for item in (" ".join(event_words[:8]), month) if item), "channel": "SEARXNG_GENERAL_SEARCH", "backends": ["searxng-general-search"], "language": alternate_language or primary_language},
            {"intent": "FIND_ALTERNATIVE_PRIMARY", "variant": "EVENT_ALTERNATIVE", "query": " ".join(item for item in (seed, month, "official document") if item), "channel": "GDELT_DOC", "backends": ["gdelt-doc"], "language": primary_language},
            {"intent": "OFFICIAL_SOURCE_ROUTE", "variant": "SOURCE_SPECIFIC", "query": " ".join(item for item in (f"site:{route.get('origin')}" if route else "", " ".join(event_words[:8])) if item), "channel": "GOOGLE_NEWS_RSS", "backends": ["public-rss-search"]},
            {"intent": "OFFICIAL_BROAD_DISCOVERY", "variant": "RELAX_TOPIC", "query": " ".join(event_words[:6]), "channel": "SEARXNG_GENERAL_SEARCH", "backends": ["searxng-general-search"], "language": primary_language},
        ]
    sections = need.get("search_constraints", {}).get("eligible_section_ids", []) or need.get("topic_identifiers", [])
    desk = _desk_terms(list(sections[:3]))
    direct = [item for item in routes if item.get("url")]
    route = direct[0] if direct else None
    if need.get("event_acquisition_plan"):
        return _breadth_event_queries(
            job, need, month=month, primary_language=primary_language,
            alternate_language=alternate_language, route=route,
        )
    if kind == "NEED_DISTINCT_EVENT":
        base = f"{desk} news {month}".strip()
        return [
            {"intent": "DISTINCT_EVENT_DESK_WINDOW", "variant": "EXACT", "query": base, "channel": "SEARXNG_GENERAL_SEARCH", "backends": ["searxng-general-search"], "language": primary_language, "fallback": {"action_type": "FIND_DISTINCT_EVENT", "channel": "GOOGLE_NEWS_RSS", "backends": ["public-rss-search"]}},
            {"intent": "DISTINCT_EVENT_RELAXED", "variant": "RELAX_TOPIC", "query": f"{desk} news".strip(), "channel": "GOOGLE_NEWS_RSS", "backends": ["public-rss-search"]},
            {"intent": "DISTINCT_EVENT_ALTERNATIVE", "variant": "EVENT_ALTERNATIVE", "query": base, "channel": "GDELT_DOC", "backends": ["gdelt-doc"], "language": primary_language},
        ]
    # Breadth needs use desk/institutional vocabulary, not a copied headline.
    institutional = "Cour des comptes public procurement TGR Morocco" if "accountability" in kind.casefold() else "world international news"
    return [
        {
            "intent": "BREADTH_CONFIGURED_ROUTE", "variant": "CONFIGURED_ROUTE",
            "query": f"{institutional} {desk} {month}".strip(),
            "action_type": "FETCH_CONFIGURED_SOURCE", "target": route.get("url") if route else None,
            "channel": "CONFIGURED_LISTING",
            "fallback": {"action_type": "SEARCH_DISCOVERY", "channel": "GOOGLE_NEWS_RSS", "backends": ["public-rss-search"]},
        },
        {"intent": "BREADTH_DESK_WINDOW", "variant": "EXACT", "query": f"{institutional} {desk} {month}".strip(), "channel": "SEARXNG_GENERAL_SEARCH", "backends": ["searxng-general-search"], "language": primary_language, "fallback": {"action_type": "SEARCH_DISCOVERY", "channel": "GOOGLE_NEWS_RSS", "backends": ["public-rss-search"]}},
        {"intent": "BREADTH_RELAXED", "variant": "RELAX_TOPIC", "query": f"{institutional} {desk}".strip(), "channel": "GOOGLE_NEWS_RSS", "backends": ["public-rss-search"]},
        {"intent": "BREADTH_ALTERNATIVE", "variant": "EVENT_ALTERNATIVE", "query": f"{institutional} {desk} {month}".strip(), "channel": "GDELT_DOC", "backends": ["gdelt-doc"], "language": primary_language},
    ]


class ResearchExecutorError(RuntimeError):
    pass


class ResearchAdapter(Protocol):
    """A non-generative adapter that returns zero or more raw retrieval results."""

    def execute(self, action: dict) -> list[dict]: ...


def _stable_id(prefix: str, *parts: object) -> str:
    text = "\0".join(str(item) for item in parts)
    return f"{prefix}-{hashlib.sha256(text.encode('utf-8')).hexdigest()[:12].upper()}"


def _question(job: dict, question_id: str) -> dict:
    return next((item for item in job.get("question_tree", []) if item["question_id"] == question_id), {})


def _action_type(question: dict, need: dict | None) -> str:
    if need:
        return {
            "FIND_PRIMARY_ORIGINAL_EVIDENCE": "RECOVER_PRIMARY_SOURCE",
            "FIND_INDEPENDENT_CORROBORATION": "RECOVER_INDEPENDENT_SOURCE",
            "NEED_DISTINCT_EVENT": "FIND_DISTINCT_EVENT",
        }.get(str(need.get("kind")), "SEARCH_DISCOVERY")
    return {
        "CONTRADICTION": "CHECK_CONTRADICTION",
        "DISPUTE": "CHECK_CONTRADICTION",
        "EVIDENCE_GAP": "SEARCH_OFFICIAL_SOURCE",
        "HISTORY": "SEARCH_ARCHIVE_OR_CATALOG",
        "FOLLOW_UP": "FOLLOW_REFERENCE",
    }.get(question.get("kind"), "SEARCH_DISCOVERY")


def create_research_action(
    job: dict,
    branch: dict,
    *,
    action_type: str | None = None,
    recovery_need: dict | None = None,
    target: str | None = None,
    known_event_ids: list[str] | None = None,
    query_strategy: dict | None = None,
) -> dict:
    """Build one reproducible action without executing it."""
    question_id = branch["question_ids"][0]
    question = _question(job, question_id)
    action_type = action_type or _action_type(question, recovery_need)
    if query_strategy and query_strategy.get("action_type"):
        action_type = str(query_strategy["action_type"])
    if action_type not in ACTION_TYPES:
        raise ResearchExecutorError("RESEARCH_ACTION_TYPE_INVALID")
    seen_urls = list(job.get("executor_state", {}).get("seen_urls", []))
    seen_origins = list(job.get("executor_state", {}).get("seen_origins", []))
    excluded_origins, excluded_families = _route_exclusions(job, recovery_need)
    known_events = sorted(set(known_event_ids or []) | ({job["lead"].get("related_event_cluster")} - {None}))
    strategy = query_strategy or query_ladder(job, recovery_need)[0]
    query = str(strategy.get("query") or job["lead"].get("topic") or "")
    target = target or strategy.get("target")
    return {
        "schema_version": 1,
        "action_id": _stable_id(
            "ACT", job["job_id"], job.get("round", 0), branch["branch_id"],
            action_type, recovery_need.get("need_id") if recovery_need else "",
            target or query,
        ),
        "job_id": job["job_id"],
        "branch_id": branch["branch_id"],
        "question_id": question_id,
        "desk": str(strategy.get("target_desk") or job["lead"]["desk"]),
        "research_regime": job["regime"],
        "action_type": action_type,
        "query": query,
        "query_intent": str(strategy.get("intent") or "CONTEXT"),
        "query_variant": str(strategy.get("variant") or "CONTEXT"),
        "query_fingerprint": query_fingerprint(query, intent=str(strategy.get("intent") or "CONTEXT"), language=strategy.get("language")),
        "priority_class": recovery_priority(recovery_need),
        "discovery_channel": str(strategy.get("channel") or "GOOGLE_NEWS_RSS"),
        "discovery_backends": list(strategy.get("backends") or []),
        "search_language": strategy.get("language"),
        "search_categories": strategy.get("categories"),
        "search_time_range": strategy.get("time_range"),
        "search_page": strategy.get("page"),
        "candidate_event_theme": strategy.get("candidate_event_theme"),
        "target": target,
        "known_entities": list(job["lead"].get("event_entities", [])),
        "event_context": {
            "entities": list((recovery_need or {}).get("query_context", {}).get("entities", [])),
            "aliases": list((recovery_need or {}).get("query_context", {}).get("aliases", [])),
            "event_terms": list((recovery_need or {}).get("query_context", {}).get("event_terms", [])),
            "topic_terms": list((recovery_need or {}).get("topic_identifiers", [])),
            "geography": list((recovery_need or {}).get("query_context", {}).get("geography", [])),
            "research_date": (recovery_need or {}).get("query_context", {}).get("research_date"),
        },
        "known_event_ids": known_events,
        "known_event_fingerprints": list((recovery_need or {}).get("event_acquisition_plan", {}).get("excluded_event_fingerprints", [])),
        "event_fingerprint": event_fingerprint(job, recovery_need),
        "already_seen_urls": seen_urls,
        "already_seen_origins": seen_origins,
        # A failed route is scoped to this event/claim and run.  It prevents
        # repeat fetches and same-family substitutions, never marks the event
        # itself false and never changes publication eligibility.
        "excluded_origins": sorted(excluded_origins),
        "excluded_origin_families": sorted(excluded_families),
        "budget": {
            "class": job["budget_class"],
            "round": job.get("round", 0),
            "max_rounds": job["budget"]["max_followup_rounds"],
        },
        "timeout_seconds": 15,
        "expected_result_type": "EXTRACTED_SOURCE" if action_type in FETCH_ACTIONS else "DISCOVERY_RESULT",
        "provenance_requirements": {
            "read_only": True,
            "discovery_is_not_publication_evidence": True,
            "exact_source_page_required_for_evidence": True,
            "required_role": recovery_need.get("missing_evidence_role") if recovery_need else None,
            "must_be_distinct_event": bool(recovery_need and recovery_need.get("search_constraints", {}).get("must_be_distinct_event")),
            "science_strict": job["regime"] == "SCIENCE",
        },
        "recovery_need_id": recovery_need.get("need_id") if recovery_need else None,
        "recovery_candidate_id": recovery_need.get("candidate_id") if recovery_need else None,
        "channel_fallback": deepcopy(strategy.get("fallback")) if strategy.get("fallback") else None,
    }


def plan_research_actions(job: dict, config: dict, *, known_event_ids: list[str] | None = None) -> list[dict]:
    """Plan query ladders; the global scheduler chooses a fair bounded slice."""
    if job.get("status") == "STOPPED":
        return []
    branches = [item for item in job.get("branches", []) if item.get("status") == "PLANNED"]
    needs = sorted(
        (
            item for item in job.get("recovery_needs", [])
            if item.get("attempt_count", 0) < item.get("max_attempts", 1)
        ),
        key=lambda item: (PRIORITY_ORDER[recovery_priority(item)], str(item.get("need_id"))),
    )
    if needs and branches:
        pairs = [
            (branches[index % len(branches)], need)
            for index, need in enumerate(needs)
        ]
    else:
        pairs = [(branch, None) for branch in branches]
    actions = []
    seen_fingerprints: set[tuple[str, str]] = set()
    for branch, need in pairs:
        strategies = [
            item for item in query_ladder(job, need)
            if item.get("action_type") != "FETCH_CONFIGURED_SOURCE" or item.get("target")
        ]
        for strategy_index, strategy in enumerate(strategies):
            action = create_research_action(
                job, branch, recovery_need=need, known_event_ids=known_event_ids,
                query_strategy=strategy,
            )
            action["strategy_index"] = strategy_index
            action["strategy_count"] = len(strategies)
            fingerprint = (action["action_type"], action["query_fingerprint"])
            if fingerprint in seen_fingerprints:
                continue
            seen_fingerprints.add(fingerprint)
            action["timeout_seconds"] = config["executor"]["action_timeout_seconds"]
            actions.append(action)
    # A duplicate strategy was intentionally not emitted; it cannot keep a
    # recovery ladder permanently "in progress".
    counts: dict[str, int] = {}
    for action in actions:
        if action.get("recovery_need_id"):
            need_id = str(action["recovery_need_id"])
            counts[need_id] = counts.get(need_id, 0) + 1
    for action in actions:
        if action.get("recovery_need_id"):
            action["strategy_count"] = counts[str(action["recovery_need_id"])]
    return actions


def schedule_research_actions(jobs: list[dict], config: dict, *, known_event_ids: list[str] | None = None) -> dict:
    """Select a finite, fair cross-desk slice without starving P1 behind P0.

    A wave contains the first untried strategy for each need.  Priority orders
    the wave, while a round-robin pass ensures one dead-end cannot consume the
    whole round.  Later ladder variants wait until every eligible need has had
    an earlier strategy considered.
    """
    all_actions = [
        action for job in jobs
        for action in plan_research_actions(job, config, known_event_ids=known_event_ids)
    ]
    cap = int(config["executor"]["maximum_actions_per_round"])
    # Context is deliberately not allowed to consume a scarce recovery round.
    # P0/P1/P2 remain eligible together; only P3 is deferred under pressure.
    if any(item["priority_class"] != "P3_CONTEXT" for item in all_actions):
        eligible_actions = [item for item in all_actions if item["priority_class"] != "P3_CONTEXT"]
    else:
        eligible_actions = all_actions
    selected: list[dict] = []
    # Reserve one first-wave slot for each non-context edition-wide gap class.
    # This is the anti-starvation rule: a large set of P0 candidate repairs
    # still cannot leave World/breadth/distinct-event research at zero.
    first_wave = [item for item in eligible_actions if int(item.get("strategy_index", 0)) == 0]
    for priority in ("P0_BLOCKING_EVIDENCE", "P1_BREADTH", "P1_DISTINCT_EVENT", "P2_CONTRADICTION"):
        candidate = next((item for item in sorted(first_wave, key=lambda value: (str(value.get("recovery_need_id") or value["job_id"]), value["action_id"])) if item["priority_class"] == priority), None)
        if candidate is not None and len(selected) < cap:
            selected.append(candidate)
    for strategy_index in sorted({int(item.get("strategy_index", 0)) for item in eligible_actions}):
        for priority in sorted(PRIORITY_ORDER, key=PRIORITY_ORDER.get):
            pool = [item for item in eligible_actions if item["priority_class"] == priority]
            wave = sorted(
                (item for item in pool if int(item.get("strategy_index", 0)) == strategy_index),
                key=lambda item: (str(item.get("recovery_need_id") or item["job_id"]), item["action_id"]),
            )
            for action in wave:
                if len(selected) >= cap:
                    break
                if action["action_id"] in {item["action_id"] for item in selected}:
                    continue
                selected.append(action)
            if len(selected) >= cap:
                break
        if len(selected) >= cap:
            break
    selected_ids = {item["action_id"] for item in selected}
    return {
        "actions": selected,
        "deferred_actions": [
            {**item, "deferred_reason": "ROUND_BUDGET_PRIORITY_AND_FAIRNESS"}
            for item in all_actions if item["action_id"] not in selected_ids
        ],
    }


class FixtureResearchAdapter:
    """Deterministic read-only adapter keyed by action ID or action type."""

    def __init__(self, responses: dict[str, list[dict]]) -> None:
        self.responses = deepcopy(responses)
        self.executed_actions: list[str] = []

    def execute(self, action: dict) -> list[dict]:
        self.executed_actions.append(action["action_id"])
        return deepcopy(self.responses.get(action["action_id"], self.responses.get(action["action_type"], [])))


class HttpResearchAdapter:
    """Optional direct-fetch adapter; it intentionally has no search backend."""

    def execute(self, action: dict) -> list[dict]:
        if action["action_type"] not in FETCH_ACTIONS or not action.get("target"):
            raise ResearchExecutorError("RESEARCH_ACTION_ADAPTER_UNAVAILABLE")
        try:
            return [fetch_and_extract_source(action["target"], timeout_seconds=action["timeout_seconds"])]
        except DiscoveryError as exc:
            return [{"result_type": "DEAD_END", "reason": exc.code, "detail": exc.detail}]


class RssSearchAdapter:
    """Concrete, read-only public RSS search/discovery adapter.

    It intentionally returns discovery leads only.  Feed results may point to
    domains outside every configured seed list; they are retained for normal
    inspection/classification, never counted as verified evidence merely
    because a public search feed returned them.
    """

    def __init__(
        self,
        *,
        adapter_id: str,
        endpoint_template: str,
        timeout_seconds: int = 10,
        maximum_bytes: int = 1_000_000,
        maximum_results: int = 8,
        source_classes_by_origin: dict[str, str] | None = None,
        transport=default_transport,
    ) -> None:
        if "{query}" not in endpoint_template or not endpoint_template.startswith("https://"):
            raise ResearchExecutorError("RSS_SEARCH_CONFIG_INVALID")
        self.adapter_id = adapter_id
        self.endpoint_template = endpoint_template
        self.timeout_seconds = timeout_seconds
        self.maximum_bytes = maximum_bytes
        self.maximum_results = maximum_results
        # A configured origin is only a routing hint.  It affects the
        # provisional source class of an exact fetched page; it never turns a
        # discovery result into verified publication evidence.
        self.source_classes_by_origin = {
            str(origin).casefold(): str(source_class).casefold()
            for origin, source_class in (source_classes_by_origin or {}).items()
            if str(source_class).casefold() in {"official", "primary", "independent", "paper"}
        }
        self.transport = transport
        self.follow_discovery_leads = True
        self.publisher_profile_cache = PublisherProfileCache()

    def execute(self, action: dict) -> list[dict]:
        if action.get("action_type") in FETCH_ACTIONS and action.get("target"):
            try:
                fetched = fetch_and_extract_source(
                    str(action["target"]), timeout_seconds=action["timeout_seconds"]
                )
            except DiscoveryError as exc:
                return [{
                    "result_type": "DEAD_END", "reason": exc.code,
                    "detail": exc.detail, "discovery_channel": f"{self.adapter_id}-followup",
                }]
            origin = urlsplit(str(fetched.get("canonical_url") or "")).hostname or ""
            fetched["source_class"] = self.source_classes_by_origin.get(origin.casefold(), "unknown")
            profile = self.publisher_profile_cache.get(origin)
            if profile is None:
                profile = self.publisher_profile_cache.put(publisher_profile_from_pages(origin, [fetched]))
            fetched["publisher_profile"] = profile
            fetched["discovery_channel"] = f"{self.adapter_id}-followup"
            return [fetched]
        if action.get("action_type") not in SEARCH_ACTIONS:
            raise ResearchExecutorError("RESEARCH_ACTION_ADAPTER_UNAVAILABLE")
        endpoint = self.endpoint_template.replace("{query}", quote_plus(str(action.get("query") or "")))
        try:
            response = self.transport(endpoint, self.timeout_seconds, self.maximum_bytes)
            if not 200 <= response.status < 300:
                return [{"result_type": "DEAD_END", "reason": f"RSS_HTTP_{response.status}", "discovery_channel": self.adapter_id}]
            candidates = discover_rss(
                response.body, provider_id=self.adapter_id, endpoint=response.url
            )[: self.maximum_results]
        except (DiscoveryError, OSError, TimeoutError) as exc:
            return [{"result_type": "DEAD_END", "reason": getattr(exc, "code", type(exc).__name__), "discovery_channel": self.adapter_id}]
        timestamp = datetime.now(timezone.utc).isoformat()
        if not candidates:
            return [{"result_type": "DEAD_END", "reason": "RSS_NO_MATCHES", "discovery_channel": self.adapter_id}]
        return [
            {
                "result_type": "LEAD",
                "canonical_url": item["discovered_url"],
                "title": item["title"],
                "source_class": "unknown",
                "discovered_at": timestamp,
                "discovery_channel": self.adapter_id,
                "discovery_endpoint": response.url,
                "verification_provenance": "DISCOVERY_ONLY_RSS",
                "search_result": {
                    "query": str(action.get("query") or ""), "backend": self.adapter_id,
                    "result_url": item["discovered_url"], "title": item["title"],
                    "snippet": None, "published_at": None, "engine": "rss",
                    "rank": index, "discovered_at": timestamp,
                },
            }
            for index, item in enumerate(candidates, start=1)
        ]


def rss_search_adapter_from_config(path, *, source_coverage_path=None) -> RssSearchAdapter | None:
    """Load the optional built-in public RSS adapter without extra packages."""
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ResearchExecutorError("RSS_SEARCH_CONFIG_INVALID") from exc
    required = {
        "version", "enabled", "adapter_id", "endpoint_template",
        "timeout_seconds", "maximum_bytes", "maximum_results",
        "integration_test_status", "provenance_behavior",
    }
    if not isinstance(value, dict) or set(value) != required or value.get("version") != 1:
        raise ResearchExecutorError("RSS_SEARCH_CONFIG_INVALID")
    if not value["enabled"]:
        return None
    if (
        not isinstance(value["adapter_id"], str)
        or not isinstance(value["endpoint_template"], str)
        or not isinstance(value["timeout_seconds"], int)
        or not isinstance(value["maximum_bytes"], int)
        or not isinstance(value["maximum_results"], int)
        or value["integration_test_status"] not in {"PASS", "NOT_RUN"}
        or value["provenance_behavior"] != "DISCOVERY_ONLY_UNKNOWN_DOMAINS_ALLOWED"
    ):
        raise ResearchExecutorError("RSS_SEARCH_CONFIG_INVALID")
    source_classes_by_origin: dict[str, str] = {}
    if source_coverage_path is not None:
        try:
            coverage = yaml.safe_load(source_coverage_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, yaml.YAMLError) as exc:
            raise ResearchExecutorError("RSS_SEARCH_SOURCE_COVERAGE_INVALID") from exc
        if not isinstance(coverage, dict) or not isinstance(coverage.get("sources"), list):
            raise ResearchExecutorError("RSS_SEARCH_SOURCE_COVERAGE_INVALID")
        source_classes_by_origin = {
            str(item["origin"]): str(item["role"]).casefold()
            for item in coverage["sources"]
            if isinstance(item, dict)
            and item.get("enabled") is True
            and item.get("discovery_only") is False
            and isinstance(item.get("origin"), str)
            and item.get("role") in {"PRIMARY", "INDEPENDENT"}
        }
    return RssSearchAdapter(
        adapter_id=value["adapter_id"],
        endpoint_template=value["endpoint_template"],
        timeout_seconds=value["timeout_seconds"],
        maximum_bytes=value["maximum_bytes"],
        maximum_results=value["maximum_results"],
        source_classes_by_origin=source_classes_by_origin,
    )


class SearxngSearchAdapter:
    """Optional provider-neutral SearXNG JSON discovery adapter.

    It is disabled unless a deliberate HTTPS endpoint is configured. Results
    are normalized discovery leads and cannot supply evidence without the
    ordinary exact-page fetch and validation path.
    """

    def __init__(
        self,
        *,
        adapter_id: str,
        base_url: str,
        timeout_seconds: int,
        maximum_bytes: int,
        maximum_results: int,
        language: str | None = None,
        categories: str | None = None,
        time_range: str | None = None,
        page: int = 1,
        endpoint_policy: str = "HTTPS_ONLY",
        source_classes_by_origin: dict[str, str] | None = None,
        transport=default_transport,
    ) -> None:
        split = urlsplit(base_url)
        is_loopback = split.hostname == "127.0.0.1"
        if (
            split.query or split.fragment or split.username or split.password
            or endpoint_policy not in {"HTTPS_ONLY", "LOCAL_PRIVATE_ONLY"}
            or (endpoint_policy == "HTTPS_ONLY" and split.scheme != "https")
            or (endpoint_policy == "LOCAL_PRIVATE_ONLY" and not (split.scheme == "http" and is_loopback))
        ):
            raise ResearchExecutorError("SEARXNG_SEARCH_CONFIG_INVALID")
        self.adapter_id = adapter_id
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.maximum_bytes = maximum_bytes
        self.maximum_results = maximum_results
        self.language = language
        self.categories = categories
        self.time_range = time_range
        self.page = page
        self.endpoint_policy = endpoint_policy
        self.source_classes_by_origin = {
            str(origin).casefold(): str(source_class).casefold()
            for origin, source_class in (source_classes_by_origin or {}).items()
        }
        self.transport = _local_searxng_transport if endpoint_policy == "LOCAL_PRIVATE_ONLY" and transport is default_transport else transport
        self.follow_discovery_leads = True
        self.publisher_profile_cache = PublisherProfileCache()

    def _search_url(self, action: dict) -> str:
        params = {
            "q": str(action.get("query") or ""), "format": "json",
            "pageno": action.get("search_page") or self.page,
        }
        if action.get("search_language") or self.language:
            params["language"] = action.get("search_language") or self.language
        if action.get("search_categories") or self.categories:
            params["categories"] = action.get("search_categories") or self.categories
        if action.get("search_time_range") or self.time_range:
            params["time_range"] = action.get("search_time_range") or self.time_range
        return f"{self.base_url}/search?{urlencode(params)}"

    def execute(self, action: dict) -> list[dict]:
        if action.get("action_type") in FETCH_ACTIONS and action.get("target"):
            try:
                fetched = fetch_and_extract_source(str(action["target"]), timeout_seconds=action["timeout_seconds"])
            except DiscoveryError as exc:
                return [{"result_type": "DEAD_END", "reason": exc.code, "detail": exc.detail, "discovery_channel": f"{self.adapter_id}-followup"}]
            origin = urlsplit(str(fetched.get("canonical_url") or "")).hostname or ""
            fetched["source_class"] = self.source_classes_by_origin.get(origin.casefold(), "unknown")
            # Publisher identity is cached separately from source/evidence
            # role.  The exact article remains untrusted until normal
            # attribution, event, and role validation passes.
            profile = self.publisher_profile_cache.get(origin)
            if profile is None:
                profile = self.publisher_profile_cache.put(publisher_profile_from_pages(origin, [fetched]))
            fetched["publisher_profile"] = profile
            fetched["discovery_channel"] = f"{self.adapter_id}-followup"
            return [fetched]
        if action.get("action_type") not in SEARCH_ACTIONS:
            raise ResearchExecutorError("RESEARCH_ACTION_ADAPTER_UNAVAILABLE")
        try:
            response = self.transport(self._search_url(action), self.timeout_seconds, self.maximum_bytes)
            if not 200 <= response.status < 300:
                return [{"result_type": "DEAD_END", "reason": f"SEARXNG_HTTP_{response.status}", "discovery_channel": self.adapter_id}]
            payload = json.loads(response.body.decode("utf-8"))
        except (DiscoveryError, OSError, TimeoutError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            return [{
                "result_type": "DEAD_END", "reason": "SEARCH_BACKEND_UNAVAILABLE",
                "detail": getattr(exc, "code", type(exc).__name__), "discovery_channel": self.adapter_id,
            }]
        results = payload.get("results") if isinstance(payload, dict) else None
        if not isinstance(results, list):
            return [{"result_type": "DEAD_END", "reason": "SEARXNG_RESPONSE_INVALID", "discovery_channel": self.adapter_id}]
        normalized = []
        timestamp = datetime.now(timezone.utc).isoformat()
        for rank, item in enumerate(results[: self.maximum_results], start=1):
            if not isinstance(item, dict) or not isinstance(item.get("url"), str):
                continue
            url = item["url"].strip()
            if not url.startswith(("https://", "http://")):
                continue
            normalized.append({
                "result_type": "LEAD", "canonical_url": url,
                "title": str(item.get("title") or "Untitled search result"),
                "claim": str(item.get("content") or item.get("title") or ""),
                "published_at": item.get("publishedDate") or item.get("published_at"),
                "discovered_at": timestamp, "source_class": "unknown",
                "discovery_channel": self.adapter_id,
                "verification_provenance": "DISCOVERY_ONLY_SEARXNG",
                "search_result": {
                    "query": str(action.get("query") or ""), "backend": self.adapter_id,
                    "result_url": url, "title": str(item.get("title") or ""),
                    "snippet": str(item.get("content") or ""), "engine": item.get("engine"),
                    "rank": rank, "discovered_at": timestamp,
                    "language": item.get("language") or action.get("search_language"),
                },
                "language": item.get("language") or action.get("search_language"),
            })
        return normalized or [{"result_type": "DEAD_END", "reason": "SEARXNG_NO_MATCHES", "discovery_channel": self.adapter_id}]


class DiscoveryAdapterChain:
    """Route discovery to every configured backend and deduplicate before fetch."""

    def __init__(self, adapters: list[ResearchAdapter]) -> None:
        self.adapters = adapters
        self.follow_discovery_leads = any(getattr(item, "follow_discovery_leads", False) for item in adapters)

    def execute(self, action: dict) -> list[dict]:
        requested = {str(item) for item in action.get("discovery_backends", [])}
        adapters = [item for item in self.adapters if not requested or getattr(item, "adapter_id", None) in requested]
        if not adapters:
            return [{"result_type": "DEAD_END", "reason": "SEARCH_BACKEND_UNAVAILABLE", "discovery_channel": str(action.get("discovery_channel") or "UNKNOWN")}]
        # Lead follow-up keeps the parent backend identity.  The adapters use
        # the same hardened exact-page fetcher, but SearXNG-led pages must not
        # be misreported as RSS yield merely because RSS is first in the chain.
        if action.get("action_type") in FETCH_ACTIONS:
            return adapters[0].execute(action)
        results = [item for adapter in adapters for item in adapter.execute(action)]
        seen, deduplicated = set(), []
        for item in results:
            url = str(item.get("canonical_url") or item.get("url") or "")
            canonical = normalize_url(url) if url else None
            if canonical and canonical in seen:
                continue
            if canonical:
                seen.add(canonical)
            deduplicated.append(item)
        return deduplicated or [{"result_type": "DEAD_END", "reason": "ALL_DISCOVERY_BACKENDS_UNAVAILABLE"}]


class GdeltDocSearchAdapter:
    """Bounded GDELT DOC ArticleList discovery; metadata is always a lead.

    GDELT is an optional public index, not an evidence source and not a
    substitute for a fetched original page.  The adapter accepts only the
    documented public HTTPS endpoint and returns a clear unavailable state
    when that endpoint cannot be used.
    """

    def __init__(self, *, adapter_id: str, base_url: str, timeout_seconds: int,
                 maximum_bytes: int, maximum_results: int, transport=default_transport) -> None:
        split = urlsplit(base_url)
        if (split.scheme != "https" or split.hostname != "api.gdeltproject.org"
                or split.query or split.fragment or split.username or split.password):
            raise ResearchExecutorError("GDELT_DOC_CONFIG_INVALID")
        self.adapter_id = adapter_id
        self.base_url = base_url
        self.timeout_seconds = timeout_seconds
        self.maximum_bytes = maximum_bytes
        self.maximum_results = maximum_results
        self.transport = transport
        self.follow_discovery_leads = True
        self.publisher_profile_cache = PublisherProfileCache()

    def _search_url(self, action: dict) -> str:
        date = str(action.get("event_context", {}).get("research_date") or "")
        # DOC expects YYYYMMDDHHMMSS.  A packet date is intentionally bounded
        # to its calendar day instead of silently drifting to current news.
        compact = re.sub(r"[^0-9]", "", date)[:8]
        params = {
            "query": str(action.get("query") or ""), "mode": "ArtList",
            "format": "json", "maxrecords": min(self.maximum_results, 250),
        }
        if compact:
            params["startdatetime"] = f"{compact}000000"
            params["enddatetime"] = f"{compact}235959"
        if action.get("search_language"):
            params["sourcelang"] = str(action["search_language"])
        return f"{self.base_url}?{urlencode(params)}"

    def execute(self, action: dict) -> list[dict]:
        if action.get("action_type") in FETCH_ACTIONS and action.get("target"):
            # Exact pages use DRAGON's one safe fetch path; GDELT never grants
            # a privileged retrieval route.
            try:
                fetched = fetch_and_extract_source(str(action["target"]), timeout_seconds=action["timeout_seconds"])
            except DiscoveryError as exc:
                return [{"result_type": "DEAD_END", "reason": exc.code, "detail": exc.detail,
                         "discovery_channel": f"{self.adapter_id}-followup"}]
            origin = urlsplit(str(fetched.get("canonical_url") or "")).hostname or ""
            profile = self.publisher_profile_cache.get(origin)
            fetched["publisher_profile"] = profile or self.publisher_profile_cache.put(publisher_profile_from_pages(origin, [fetched]))
            fetched["source_class"] = "unknown"
            fetched["discovery_channel"] = f"{self.adapter_id}-followup"
            return [fetched]
        if action.get("action_type") not in SEARCH_ACTIONS:
            raise ResearchExecutorError("RESEARCH_ACTION_ADAPTER_UNAVAILABLE")
        endpoint = self._search_url(action)
        try:
            response = self.transport(endpoint, self.timeout_seconds, self.maximum_bytes)
            if not 200 <= response.status < 300:
                return [{"result_type": "DEAD_END", "reason": f"GDELT_HTTP_{response.status}", "discovery_channel": self.adapter_id}]
            payload = json.loads(response.body.decode("utf-8"))
        except (DiscoveryError, OSError, TimeoutError, UnicodeError, json.JSONDecodeError) as exc:
            return [{"result_type": "DEAD_END", "reason": getattr(exc, "code", "GDELT_UNAVAILABLE"), "discovery_channel": self.adapter_id}]
        articles = payload.get("articles", []) if isinstance(payload, dict) else []
        if not isinstance(articles, list) or not articles:
            return [{"result_type": "DEAD_END", "reason": "GDELT_NO_MATCHES", "discovery_channel": self.adapter_id}]
        timestamp = datetime.now(timezone.utc).isoformat()
        leads = []
        for rank, article in enumerate(articles[:self.maximum_results], start=1):
            if not isinstance(article, dict) or not isinstance(article.get("url"), str):
                continue
            leads.append({
                "result_type": "LEAD", "canonical_url": article["url"],
                "title": str(article.get("title") or "GDELT result"), "source_class": "unknown",
                "discovered_at": timestamp, "discovery_channel": self.adapter_id,
                "discovery_endpoint": response.url, "verification_provenance": "DISCOVERY_ONLY_GDELT",
                "search_result": {"query": str(action.get("query") or ""), "backend": self.adapter_id,
                                  "result_url": article["url"], "title": article.get("title"),
                                  "snippet": article.get("socialimage") or article.get("seendate"),
                                  "published_at": article.get("seendate"), "engine": "gdelt-doc",
                                  "rank": rank, "discovered_at": timestamp},
            })
        return leads or [{"result_type": "DEAD_END", "reason": "GDELT_NO_USABLE_URLS", "discovery_channel": self.adapter_id}]


def gdelt_doc_adapter_from_config(path) -> GdeltDocSearchAdapter | None:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ResearchExecutorError("GDELT_DOC_CONFIG_INVALID") from exc
    required = {"version", "enabled", "adapter_id", "base_url", "timeout_seconds", "maximum_bytes", "maximum_results", "integration_test_status", "provenance_behavior"}
    if not isinstance(value, dict) or set(value) != required or value.get("version") != 1:
        raise ResearchExecutorError("GDELT_DOC_CONFIG_INVALID")
    if value.get("enabled") is False:
        return None
    if (not isinstance(value.get("adapter_id"), str) or not isinstance(value.get("base_url"), str)
            or not all(isinstance(value.get(key), int) and value[key] > 0 for key in ("timeout_seconds", "maximum_bytes", "maximum_results"))
            or value.get("integration_test_status") not in {"PASS", "NOT_RUN"}
            or value.get("provenance_behavior") != "DISCOVERY_ONLY_EXACT_PAGE_REQUIRED"):
        raise ResearchExecutorError("GDELT_DOC_CONFIG_INVALID")
    return GdeltDocSearchAdapter(adapter_id=value["adapter_id"], base_url=value["base_url"],
                                 timeout_seconds=value["timeout_seconds"], maximum_bytes=value["maximum_bytes"],
                                 maximum_results=value["maximum_results"])


def publisher_discovery_states_from_config(path) -> dict[str, dict]:
    """Load explicit non-evidence statuses for feeds, sitemaps and Media Cloud.

    Declaring a capability ready is not permission to crawl a publisher.  The
    only routable states are future explicitly configured endpoints; until
    then these values make the absence visible in every rehearsal report.
    """
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ResearchExecutorError("PUBLISHER_DISCOVERY_CONFIG_INVALID") from exc
    if not isinstance(value, dict) or set(value) != {"version", "publisher_owned_rss_atom", "publisher_owned_sitemaps", "media_cloud"} or value.get("version") != 1:
        raise ResearchExecutorError("PUBLISHER_DISCOVERY_CONFIG_INVALID")
    routes = {
        "publisher_owned_rss_atom": "ADAPTER_READY_NO_CONFIGURED_FEEDS",
        "publisher_owned_sitemaps": "ADAPTER_READY_NO_CONFIGURED_SITEMAPS",
    }
    for name, expected in routes.items():
        item = value.get(name)
        if not isinstance(item, dict) or item.get("status") != expected or item.get("discovery_only") is not True or item.get("exact_page_validation_required") is not True:
            raise ResearchExecutorError("PUBLISHER_DISCOVERY_CONFIG_INVALID")
    media = value.get("media_cloud")
    if not isinstance(media, dict) or media != {"status": "ADAPTER_READY_AUTH_NOT_CONFIGURED", "enabled": False}:
        raise ResearchExecutorError("PUBLISHER_DISCOVERY_CONFIG_INVALID")
    return deepcopy({name: value[name] for name in (*routes, "media_cloud")})


def searxng_search_adapter_from_config(path, *, source_classes_by_origin: dict[str, str] | None = None) -> SearxngSearchAdapter | None:
    """Load disabled-by-default SearXNG configuration without provisioning it."""
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ResearchExecutorError("SEARXNG_SEARCH_CONFIG_INVALID") from exc
    required = {"version", "enabled", "adapter_id", "base_url", "endpoint_policy", "timeout_seconds", "maximum_bytes", "maximum_results", "language", "categories", "time_range", "page", "integration_test_status", "provenance_behavior"}
    if not isinstance(value, dict) or set(value) != required or value.get("version") != 2:
        raise ResearchExecutorError("SEARXNG_SEARCH_CONFIG_INVALID")
    if value["enabled"] is False:
        return None
    if not isinstance(value["base_url"], str) or not isinstance(value["adapter_id"], str) or value.get("endpoint_policy") not in {"HTTPS_ONLY", "LOCAL_PRIVATE_ONLY"} or not all(isinstance(value[key], int) and value[key] > 0 for key in ("timeout_seconds", "maximum_bytes", "maximum_results", "page")):
        raise ResearchExecutorError("SEARXNG_SEARCH_CONFIG_INVALID")
    return SearxngSearchAdapter(
        adapter_id=value["adapter_id"], base_url=value["base_url"], timeout_seconds=value["timeout_seconds"],
        maximum_bytes=value["maximum_bytes"], maximum_results=value["maximum_results"], language=value["language"],
        categories=value["categories"], time_range=value["time_range"], page=value["page"],
        endpoint_policy=value["endpoint_policy"], source_classes_by_origin=source_classes_by_origin,
    )


def discovery_adapter_from_config(root) -> ResearchAdapter | None:
    """Build the optional bounded discovery chain; no backend is evidence."""
    publisher_states = publisher_discovery_states_from_config(root / "config" / "publisher-discovery.yaml")
    rss = rss_search_adapter_from_config(root / "config" / "open-discovery.yaml", source_coverage_path=root / "config" / "source-coverage.yaml")
    classes = getattr(rss, "source_classes_by_origin", {}) if rss else {}
    searxng = searxng_search_adapter_from_config(root / "config" / "general-search.yaml", source_classes_by_origin=classes)
    gdelt = gdelt_doc_adapter_from_config(root / "config" / "gdelt-discovery.yaml")
    adapters = [item for item in (rss, searxng, gdelt) if item is not None]
    if not adapters:
        return None
    result = DiscoveryAdapterChain(adapters) if len(adapters) > 1 else adapters[0]
    # Reporting only: these inactive capability states cannot issue a request
    # and cannot alter source or evidence classification.
    result.publisher_discovery_states = publisher_states
    return result


def _classification(raw: dict, action: dict, seen_urls: set[str]) -> tuple[str, str | None, dict | None]:
    requested = str(raw.get("result_type") or "").upper()
    url = str(raw.get("canonical_url") or raw.get("url") or raw.get("discovered_url") or "").strip()
    canonical = normalize_url(url) if url else None
    followup_target = normalize_url(str(action.get("target") or "")) if action.get("action_type") in FETCH_ACTIONS and action.get("target") else None
    if canonical and canonical in seen_urls and canonical != followup_target:
        return "DUPLICATE", canonical, None
    origin = (urlsplit(canonical).hostname or "").casefold() if canonical else ""
    if origin and (
        origin in set(action.get("excluded_origins", []))
        or _registrable_domain(origin) in set(action.get("excluded_origin_families", []))
    ):
        return "DUPLICATE", canonical, None
    if raw.get("event_id") and raw["event_id"] in set(action["known_event_ids"]):
        return "DUPLICATE", canonical, None
    if action.get("provenance_requirements", {}).get("must_be_distinct_event"):
        title_words = set(_query_words([raw.get("title") or raw.get("claim") or ""]))
        for known in action.get("known_event_fingerprints", []):
            known_words = set(_query_words([known.get("fingerprint", "")])) if isinstance(known, dict) else set()
            # A concise result title matching most of a known event label is a
            # cheap triage rejection, not an assertion about its evidence.
            if len(title_words) >= 3 and len(known_words) >= 3 and len(title_words & known_words) / min(len(title_words), len(known_words)) >= 0.7:
                return "DUPLICATE", canonical, None
    # Compatibility for historical deterministic fixtures.  Production paths
    # reach this state only through ``validate_exact_page`` below.
    if raw.get("verification_provenance") == "FIXTURE_VERIFIED_EXACT_PAGE":
        source_class = str(raw.get("source_class") or raw.get("source_type") or "unknown").casefold()
        return "POTENTIAL_EVIDENCE", canonical, {
            "state": "VALIDATED_EVIDENCE",
            "progression": ["DISCOVERED", "FETCHED", "EXTRACTED", "SOURCE_IDENTIFIED", "ORIGIN_CLASSIFIED", "ROLE_CLASSIFIED", "RELEVANCE_CONFIRMED", "POTENTIAL_EVIDENCE", "VALIDATED_EVIDENCE"],
            "reason": "FIXTURE_EXACT_PAGE_VALIDATION",
            "canonical_url": canonical,
            "origin": urlsplit(canonical).hostname if canonical else None,
            "source_class": source_class,
            "relation": "SUPPORTS",
            "directness": "DIRECT_STATEMENT",
        }
    validation = validate_exact_page(raw, action) if action.get("action_type") in FETCH_ACTIONS else None
    if validation:
        state = validation["state"]
        if state == "VALIDATED_EVIDENCE":
            return ("CONTRADICTION" if validation.get("relation") == "CONTRADICTS" else "POTENTIAL_EVIDENCE"), canonical, validation
        if state == "CONTEXT_ONLY":
            return "CONTEXT", canonical, validation
        if state == "SOURCE_UNKNOWN":
            return "LEAD", canonical, validation
        if state == "WRONG_EVENT" or state == "WRONG_ROLE":
            return "IRRELEVANT", canonical, validation
        if state == "EXTRACTION_FAILED" and str(raw.get("source_class") or raw.get("source_type") or "").casefold() in {"official", "primary", "independent", "paper"}:
            # Preserve an exact, known-source retrieval as an unverified
            # potential rather than pretending incomplete extraction is a
            # successful validation or a network dead end.
            return "POTENTIAL_EVIDENCE", canonical, validation
        if state in {"FETCH_FAILED", "EXTRACTION_FAILED", "SEARCH_RESULT_ONLY"}:
            return "DEAD_END", canonical, validation
    if requested in {"DUPLICATE", "IRRELEVANT", "DEAD_END", "CONTRADICTION", "CONTEXT", "LEAD", "POTENTIAL_EVIDENCE"}:
        return requested, canonical, validation
    if raw.get("relevant") is False:
        return "IRRELEVANT", canonical, validation
    if raw.get("contradiction_candidates") or raw.get("contradicts"):
        return "CONTRADICTION", canonical, validation
    source_class = str(raw.get("source_class") or raw.get("source_type") or "UNKNOWN").upper()
    if source_class in {"OFFICIAL", "PRIMARY", "INDEPENDENT", "PAPER"}:
        return "POTENTIAL_EVIDENCE", canonical, validation
    return "LEAD", canonical, validation


def _lead_attrition_state(action: dict, raw: dict, result_class: str, validation: dict | None) -> str | None:
    """Preserve why a lead stopped without overstating it as generic failure."""
    if action.get("action_type") in SEARCH_ACTIONS and result_class == "LEAD":
        return "DISCOVERED_NOT_SELECTED"
    if action.get("action_type") not in FETCH_ACTIONS:
        return None
    reason = str(raw.get("reason") or "")
    if reason == "SOURCE_DYNAMIC_ROUTE_REQUIRED":
        return "BROWSER_RENDER_REQUIRED"
    state = str((validation or {}).get("state") or "")
    if state == "FETCH_FAILED":
        return "FETCH_FAILED"
    if state == "EXTRACTION_FAILED":
        return "EXTRACTION_FAILED"
    if state == "SOURCE_UNKNOWN":
        return "SOURCE_UNRESOLVED"
    if state == "WRONG_EVENT":
        return "WRONG_EVENT"
    if state == "WRONG_ROLE":
        return "WRONG_ROLE"
    if state == "CONTEXT_ONLY":
        return "CONTEXT_ONLY"
    if state == "VALIDATED_EVIDENCE":
        return "VALIDATED_EVIDENCE"
    return None


def _remember_unusable_route(state: dict, action: dict, observation: dict) -> None:
    """Remember a technical route failure for this run/event only.

    This is a search-routing fact, not a source verdict.  It records just
    enough information to prevent a bounded recovery ladder from spending its
    next action on the identical route or publisher family.
    """
    if action.get("action_type") not in FETCH_ACTIONS or observation.get("observation_class") != "DEAD_END":
        return
    url = str(observation.get("url") or action.get("target") or "")
    origin = (urlsplit(url).hostname or "").casefold()
    if not origin:
        return
    entry = {
        "event_fingerprint": action.get("event_fingerprint"), "recovery_need_id": action.get("recovery_need_id"),
        "url": normalize_url(url), "origin": origin, "origin_family": _registrable_domain(origin),
        "failure_code": observation.get("reason") or observation.get("validation_reason") or "FETCH_FAILED",
        "publisher_family": _registrable_domain(origin), "query_fingerprint": action.get("query_fingerprint"),
        "backend": action.get("discovery_channel"), "state": "CURRENTLY_UNUSABLE",
    }
    memory = state.setdefault("route_memory", [])
    identity = (entry["event_fingerprint"], entry["url"], entry["failure_code"])
    if not any((item.get("event_fingerprint"), item.get("url"), item.get("failure_code")) == identity for item in memory if isinstance(item, dict)):
        memory.append(entry)


def _observation(action: dict, raw: dict, seen_urls: set[str]) -> dict:
    result_class, canonical, validation = _classification(raw, action, seen_urls)
    title = str(raw.get("title") or raw.get("claim") or raw.get("reason") or "Untitled research result")
    source_class = str(raw.get("source_class") or raw.get("source_type") or "unknown").lower()
    source_id = _stable_id("SRC", canonical or action["action_id"], title)
    fixture_verified = raw.get("verification_provenance") == "FIXTURE_VERIFIED_EXACT_PAGE"
    verification_status = (
        "VALIDATED_EVIDENCE"
        if validation and validation.get("state") == "VALIDATED_EVIDENCE"
        else "EXTRACTED_NOT_VERIFIED"
    )
    origin = urlsplit(canonical).hostname if canonical else None
    source_profile = _lead_source_profile(canonical, title, str((raw.get("search_result") or {}).get("snippet") or ""))
    if action.get("action_type") in FETCH_ACTIONS and canonical and raw.get("publisher"):
        source_profile["identity_state"] = "SOURCE_IDENTIFIED"
    observation_id = _stable_id("OBS", action["action_id"], canonical or title, result_class)
    kind = {
        "LEAD": "LEAD", "POTENTIAL_EVIDENCE": "POTENTIAL_EVIDENCE",
        "CONTEXT": "CONTEXT", "CONTRADICTION": "CONTRADICTION",
        "DUPLICATE": "DUPLICATE", "IRRELEVANT": "IRRELEVANT", "DEAD_END": "DEAD_END",
    }[result_class]
    return {
        "observation_id": observation_id,
        "kind": kind,
        "observation_class": result_class,
        "question_id": action["question_id"],
        "branch_id": action["branch_id"],
        "source_id": source_id if canonical else None,
        "url": canonical,
        "origin": origin,
        "title": title,
        "published_at": raw.get("published_at") or raw.get("publication_date"),
        "observed_at": raw.get("retrieved_at") or raw.get("discovered_at"),
        # A search result has a URL but has not retrieved that URL.  This is
        # intentionally distinct from a hash-bound exact-page fetch.
        "extraction_status": raw.get("fetch_status") or "NOT_RETRIEVED",
        "content_hash": raw.get("content_hash"),
        "extracted_text": raw.get("text") or raw.get("extracted_text") or raw.get("content"),
        "source_class": str((validation or {}).get("source_class") or source_class).lower(),
        "discovery_method": action["action_type"],
        "discovery_channel": str(raw.get("discovery_channel") or action.get("discovery_channel") or action["action_type"]),
        "related_entities": list(raw.get("related_entities") or action["known_entities"]),
        "related_event": raw.get("event_id"),
        "claim": str(raw.get("claim") or title),
        "claim_candidates": list(raw.get("claim_candidates") or []),
        "contradiction_candidates": list(raw.get("contradiction_candidates") or []),
        "relevance_status": "REJECTED" if result_class in {"IRRELEVANT", "DUPLICATE", "DEAD_END"} else "RETAINED",
        "verification_status": verification_status,
        "validation_state": (validation or {}).get("state", "DISCOVERED"),
        "validation_progression": (validation or {}).get("progression", ["DISCOVERED"]),
        "validation_reason": (validation or {}).get("reason"),
        "evidence_relation": (validation or {}).get("relation"),
        "directness": (validation or {}).get("directness"),
        "provenance": {
            "action_id": action["action_id"],
            "expected_result_type": action["expected_result_type"],
            "fixture_verification": fixture_verified,
            "canonical_url": canonical,
            "final_url": raw.get("final_url") or raw.get("canonical_url") or raw.get("url"),
            "page_title": raw.get("title"),
            "content_hash": raw.get("content_hash"),
            "language": raw.get("language"),
            "discovery_is_not_publication_evidence": True,
        },
        "publication_evidence": False,
        "supporting_evidence_ids": list(raw.get("supporting_evidence_ids") or []),
        "contradicting_evidence_ids": list(raw.get("contradicting_evidence_ids") or []),
        "follow_up_question": raw.get("follow_up_question"),
        "reason": raw.get("reason"),
        "search_result": deepcopy(raw.get("search_result")) if isinstance(raw.get("search_result"), dict) else None,
        "lead_attrition_state": _lead_attrition_state(action, raw, result_class, validation),
        "source_identity": source_profile,
        "publisher_profile": deepcopy(raw.get("publisher_profile")) if isinstance(raw.get("publisher_profile"), dict) else None,
        "article_attribution": deepcopy(raw.get("article_attribution")) if isinstance(raw.get("article_attribution"), dict) else None,
    }


def build_research_yield_report(
    execution: dict,
    *,
    recovery_before: dict | None = None,
    recovery_after: dict | None = None,
    intelligence_before: dict | None = None,
    intelligence_after: dict | None = None,
) -> dict:
    """Return deterministic, explainable research-yield diagnostics.

    An observation is not counted as useful merely because it exists.  It must
    be a retained lead, potential evidence, context, or contradiction.  New
    evidence is stricter still: it requires a deterministically validated
    exact-page observation, and normal downstream recovery remains
    authoritative for closing a need.
    """
    jobs = execution.get("jobs", []) if isinstance(execution, dict) else []
    actions = [
        action for job in jobs if isinstance(job, dict)
        for action in job.get("actions", []) if isinstance(action, dict)
    ]
    observations = [
        observation for job in jobs if isinstance(job, dict)
        for observation in job.get("observations", []) if isinstance(observation, dict)
    ]
    by_action: dict[str, list[dict]] = {}
    for observation in observations:
        action_id = observation.get("provenance", {}).get("action_id")
        if isinstance(action_id, str):
            by_action.setdefault(action_id, []).append(observation)
    useful_classes = {"LEAD", "POTENTIAL_EVIDENCE", "CONTEXT", "CONTRADICTION"}
    useful = [
        item for item in observations
        if item.get("observation_class") in useful_classes
        and item.get("relevance_status") == "RETAINED"
    ]
    attrition_counts: dict[str, int] = {}
    for item in observations:
        state = item.get("lead_attrition_state")
        if state:
            attrition_counts[str(state)] = attrition_counts.get(str(state), 0) + 1
    urls = {item["url"] for item in observations if isinstance(item.get("url"), str) and item["url"]}
    origins = {item["origin"] for item in observations if isinstance(item.get("origin"), str) and item["origin"]}
    before_ids = {
        item.get("need_id") for item in (recovery_before or {}).get("needs", [])
        if isinstance(item, dict) and isinstance(item.get("need_id"), str)
    }
    after_ids = {
        item.get("need_id") for item in (recovery_after or {}).get("needs", [])
        if isinstance(item, dict) and isinstance(item.get("need_id"), str)
    }
    closed = sorted(before_ids - after_ids) if recovery_before is not None and recovery_after is not None else []
    action_outcomes = []
    for action in actions:
        action_observations = by_action.get(action["action_id"], [])
        action_useful = [item for item in action_observations if item in useful]
        action_outcomes.append({
            "action_id": action["action_id"],
            "action_type": action["action_type"],
            "question_id": action["question_id"],
            "question": action.get("query"),
            "query_intent": action.get("query_intent"),
            "query_variant": action.get("query_variant"),
            "planned_channel": action.get("discovery_channel"),
            "desk": action["desk"],
            "recovery_need_id": action.get("recovery_need_id"),
            "source_discovery_channels": sorted({
                str(item.get("discovery_channel") or item.get("discovery_method") or "UNKNOWN")
                for item in action_observations
            }),
            "urls": sorted({item["url"] for item in action_observations if item.get("url")}),
            "source_ids": sorted({item["source_id"] for item in action_observations if item.get("source_id")}),
            "observation_types": sorted({item["observation_class"] for item in action_observations}),
            "result_count": len(action_observations),
            "useful_leads": sum(item.get("observation_class") == "LEAD" and item.get("relevance_status") == "RETAINED" for item in action_observations),
            "fetched_pages": sum(item.get("extraction_status") in {"RETRIEVED", "FETCHED"} for item in action_observations),
            "accepted_observations": sum(item.get("relevance_status") == "RETAINED" for item in action_observations),
            "retrieval_succeeded": any(item.get("extraction_status") in {"RETRIEVED", "FETCHED"} for item in action_observations),
            "duplicate": any(item.get("observation_class") == "DUPLICATE" for item in action_observations),
            "irrelevant": any(item.get("observation_class") == "IRRELEVANT" for item in action_observations),
            "contributed_useful_material": bool(action_useful),
            "contributed_new_evidence": any(
                item.get("observation_class") == "POTENTIAL_EVIDENCE"
                and item.get("verification_status") == "VALIDATED_EVIDENCE"
                for item in action_observations
            ),
            "introduced_new_origin": bool({item.get("origin") for item in action_observations if item.get("origin")}),
            "introduced_new_distinct_event": any(
                item.get("related_event") and item.get("related_event") not in set(action.get("known_event_ids", []))
                for item in action_observations
            ),
            "recovery_need_closed": action.get("recovery_need_id") in closed,
            "readiness_changed": action.get("recovery_need_id") in closed,
            "zero_yield": not action_useful,
        })
    useful_questions = {
        action["question_id"] for action in actions
        if any(item in useful for item in by_action.get(action["action_id"], []))
    }
    useful_branches = {
        action["branch_id"] for action in actions
        if any(item in useful for item in by_action.get(action["action_id"], []))
    }
    strategy_channel_yield = []
    for key in sorted({(
        item.get("query_intent"), item.get("query_variant"), item.get("planned_channel")
    ) for item in action_outcomes}):
        matching = [
            item for item in action_outcomes
            if (item.get("query_intent"), item.get("query_variant"), item.get("planned_channel")) == key
        ]
        strategy_channel_yield.append({
            "query_intent": key[0], "query_variant": key[1], "channel": key[2],
            "actions": len(matching),
            "result_count": sum(item["result_count"] for item in matching),
            "useful_leads": sum(item["useful_leads"] for item in matching),
            "fetched_pages": sum(item["fetched_pages"] for item in matching),
            "accepted_observations": sum(item["accepted_observations"] for item in matching),
            "recovery_need_closed": any(item["recovery_need_closed"] for item in matching),
            "new_distinct_event": any(item["introduced_new_distinct_event"] for item in matching),
            "zero_yield": all(item["zero_yield"] for item in matching),
        })
    backend_yield = []
    backend_names = sorted({
        str(item.get("discovery_channel") or "UNKNOWN") for item in observations
    } | {
        str(item.get("discovery_channel") or "UNKNOWN") for item in actions
    })
    for backend in backend_names:
        backend_actions = [
            item for item in action_outcomes
            if item.get("planned_channel") == backend or backend in item.get("source_discovery_channels", [])
        ]
        backend_observations = [
            item for item in observations
            if str(item.get("discovery_channel") or "UNKNOWN") == backend
        ]
        backend_yield.append({
            "backend": backend,
            "queries": sum(item["action_type"] in SEARCH_ACTIONS for item in backend_actions),
            "results_returned": len(backend_observations),
            "unique_urls": len({item.get("url") for item in backend_observations if item.get("url")}),
            "exact_pages_fetched": sum(item.get("extraction_status") in {"RETRIEVED", "FETCHED"} for item in backend_observations),
            "successful_extractions": sum(bool(item.get("extracted_text")) for item in backend_observations),
            "unknown_sources": sum(item.get("source_class") == "unknown" for item in backend_observations),
            "official_sources": sum(item.get("source_class") in {"official", "primary", "paper"} for item in backend_observations),
            "independent_sources": sum(item.get("source_class") == "independent" for item in backend_observations),
            "validated_evidence": sum(item.get("verification_status") == "VALIDATED_EVIDENCE" for item in backend_observations),
            "recovery_needs_closed": sum(item.get("recovery_need_closed") for item in backend_actions),
            "new_distinct_events": sum(item.get("introduced_new_distinct_event") for item in backend_actions),
            "dead_ends": sum(item.get("observation_class") == "DEAD_END" for item in backend_observations),
        })
    return {
        "schema_version": 1,
        "actions_executed": len(actions),
        "searches": sum(item["action_type"] in SEARCH_ACTIONS for item in actions),
        "fetches": sum(item["action_type"] in FETCH_ACTIONS for item in actions),
        "successful_retrievals": sum(item.get("extraction_status") in {"RETRIEVED", "FETCHED"} for item in observations),
        "failed_retrievals": sum(
            item.get("observation_class") == "DEAD_END" and item.get("provenance", {}).get("expected_result_type") == "EXTRACTED_SOURCE"
            for item in observations
        ),
        "unique_urls": len(urls),
        "unique_origins": len(origins),
        "duplicate_urls": sum(item.get("observation_class") == "DUPLICATE" for item in observations),
        "duplicate_events": sum(
            item.get("observation_class") == "DUPLICATE" and bool(item.get("related_event"))
            for item in observations
        ),
        "irrelevant_results": sum(item.get("observation_class") == "IRRELEVANT" for item in observations),
        "dead_ends": sum(item.get("observation_class") == "DEAD_END" for item in observations),
        "new_leads": sum(item.get("observation_class") == "LEAD" and item.get("relevance_status") == "RETAINED" for item in observations),
        "unknown_source_leads": sum(item.get("observation_class") == "LEAD" and item.get("source_class") == "unknown" for item in observations),
        "official_source_observations": sum(item.get("source_class") in {"official", "primary", "paper"} for item in observations),
        "independent_source_observations": sum(item.get("source_class") == "independent" for item in observations),
        "potential_primary_evidence": sum(item.get("observation_class") == "POTENTIAL_EVIDENCE" and item.get("source_class") in {"primary", "official", "paper"} for item in observations),
        "potential_independent_evidence": sum(item.get("observation_class") == "POTENTIAL_EVIDENCE" and item.get("source_class") == "independent" for item in observations),
        "validated_evidence_items": sum(item.get("verification_status") == "VALIDATED_EVIDENCE" for item in observations),
        "contradictions_found": sum(item.get("observation_class") == "CONTRADICTION" for item in observations),
        "recovery_needs_closed": len(closed),
        "recovery_needs_unresolved": len(after_ids) if recovery_after is not None else len(before_ids),
        "new_distinct_events": (
            max(0, int(recovery_after.get("distinct_event_count", 0)) - int(recovery_before.get("distinct_event_count", 0)))
            if recovery_before is not None and recovery_after is not None
            else len({
                item.get("related_event") for item in observations
                if item.get("related_event") and item.get("related_event") not in {
                    event for action in actions for event in action.get("known_event_ids", [])
                }
            })
        ),
        "breadth_gaps_closed": sum(item.startswith("BREADTH:") for item in closed),
        "leads_selected_for_followup": attrition_counts.get("SELECTED_FOR_FETCH", 0),
        "leads_skipped": attrition_counts.get("DISCOVERED_NOT_SELECTED", 0),
        "trafilatura_successes": sum(item.get("extraction_status") == "FETCHED" and item.get("provenance", {}).get("action_id") in by_action for item in observations),
        "extraction_failures": attrition_counts.get("EXTRACTION_FAILED", 0),
        "browser_fallback_candidates": attrition_counts.get("BROWSER_RENDER_REQUIRED", 0),
        "browser_fallback_executions": sum(item.get("extraction_method") == "crawl4ai" for item in observations),
        "source_identities_resolved": sum(item.get("source_identity", {}).get("identity_state") == "SOURCE_IDENTIFIED" for item in observations),
        "unknown_sources_remaining": sum(
            item.get("source_class") == "unknown"
            and item.get("observation_class") in {"LEAD", "POTENTIAL_EVIDENCE"}
            for item in observations
        ),
        "lead_attrition": dict(sorted(attrition_counts.items())),
        "questions_with_zero_useful_results": len({item["question_id"] for item in actions} - useful_questions),
        "branches_with_zero_useful_results": len({item["branch_id"] for item in actions} - useful_branches),
        "action_outcomes": action_outcomes,
        "strategy_channel_yield": strategy_channel_yield,
        "backend_yield": backend_yield,
    }


def _source_patch(observation: dict, action: dict) -> dict | None:
    if observation["observation_class"] != "POTENTIAL_EVIDENCE" or not observation.get("url"):
        return None
    source_type = observation["source_class"]
    if source_type not in {"primary", "official", "independent", "paper"}:
        return None
    if observation["verification_status"] != "VALIDATED_EVIDENCE":
        return None
    return {
        "id": observation["source_id"], "url": observation["url"],
        "publisher": observation["origin"], "title": observation["title"],
        "publication_date": observation["published_at"], "accessed_at": observation["observed_at"],
        "source_type": source_type, "claim_supported": observation["claim"],
        "content_hash": observation["content_hash"],
        "extracted_text": observation.get("extracted_text"),
        "language": observation.get("provenance", {}).get("language"),
        "evidence_relation": observation.get("evidence_relation"),
        "directness": observation.get("directness"),
        "executor_observation_id": observation["observation_id"],
        "verification_status": observation["verification_status"],
        "provenance": observation["provenance"],
        "recovery_need_id": action.get("recovery_need_id"),
    }


def execute_research_round(
    job: dict,
    adapter: ResearchAdapter,
    config: dict,
    *,
    actions: list[dict] | None = None,
    known_event_ids: list[str] | None = None,
) -> dict:
    """Execute one bounded round and feed observations to the state machine."""
    planned = actions if actions is not None else plan_research_actions(job, config, known_event_ids=known_event_ids)
    limits = config["executor"]["budget_action_limits"][job["budget_class"]]
    state = deepcopy(job.get("executor_state", {"search_actions": 0, "fetches": 0, "lead_followups": 0, "seen_urls": [], "seen_origins": [], "route_memory": []}))
    state.setdefault("lead_followups", 0)
    state.setdefault("route_memory", [])
    seen_urls = set(state["seen_urls"])
    branch_results: dict[str, list[dict]] = {item["branch_id"]: [] for item in job.get("branches", [])}
    observations, source_records, updates, candidate_discoveries = [], [], [], []
    lead_followup_selection: list[dict] = []
    lead_followup_candidates: list[dict] = []
    attempted_strategies: dict[str, set[int]] = {}
    strategy_counts: dict[str, int] = {}
    executed = []
    def run_action(action: dict) -> None:
        """Execute one bounded action and retain its structured observations."""
        nonlocal observations, source_records, updates, candidate_discoveries
        if action["job_id"] != job["job_id"] or action["action_type"] not in ACTION_TYPES:
            raise ResearchExecutorError("RESEARCH_ACTION_INVALID")
        is_search = action["action_type"] in SEARCH_ACTIONS
        is_lead_followup = bool(action.get("lead_followup"))
        counter = "search_actions" if is_search else ("lead_followups" if is_lead_followup else "fetches")
        ceiling = int(config["executor"]["lead_followup_limits"][job["budget_class"]]["total"]) if is_lead_followup else limits[counter]
        if state[counter] >= ceiling:
            return
        state[counter] += 1
        executed.append(action)
        if action.get("recovery_need_id"):
            need_id = str(action["recovery_need_id"])
            attempted_strategies.setdefault(need_id, set()).add(int(action.get("strategy_index", 0)))
            strategy_counts[need_id] = max(strategy_counts.get(need_id, 0), int(action.get("strategy_count", 1)))
        try:
            raw_results = adapter.execute(action)
        except ResearchExecutorError as exc:
            raw_results = [{"result_type": "DEAD_END", "reason": str(exc)}]
        if not isinstance(raw_results, list):
            raise ResearchExecutorError("RESEARCH_ADAPTER_RESULT_INVALID")
        for raw in raw_results:
            if not isinstance(raw, dict):
                raise ResearchExecutorError("RESEARCH_ADAPTER_RESULT_INVALID")
            # Failed follow-up responses must retain the exact target so lead
            # attrition can distinguish fetch/extraction/browser states.
            if action.get("action_type") in FETCH_ACTIONS and action.get("target") and not (raw.get("canonical_url") or raw.get("url")):
                raw = {**raw, "url": action["target"]}
            observation = _observation(action, raw, seen_urls)
            observations.append(observation)
            branch_results.setdefault(action["branch_id"], []).append(observation)
            _remember_unusable_route(state, action, observation)
            if observation.get("url"):
                seen_urls.add(observation["url"])
                if observation.get("origin"):
                    state["seen_origins"].append(observation["origin"])
            patch = _source_patch(observation, action)
            if patch:
                source_records.append(patch)
                role = "PRIMARY" if patch["source_type"] in {"primary", "official", "paper"} else "INDEPENDENT"
                if action.get("recovery_candidate_id") and patch["verification_status"] == "VALIDATED_EVIDENCE":
                    updates.append({
                        "candidate_id": action["recovery_candidate_id"], "source_id": patch["id"],
                        "role": role, "recovery_need_id": action.get("recovery_need_id"),
                    })
                if action.get("provenance_requirements", {}).get("must_be_distinct_event"):
                    candidate_discoveries.append({
                        "section_id": action["desk"],
                        "event_id": observation.get("related_event") or _stable_id("EVENT", observation["title"], observation["url"]),
                        "title": observation["title"], "claim": observation["claim"],
                        "source_id": patch["id"], "role": role,
                    })
        # A configured route is a preferred read-only channel, not a single
        # point of failure.  On a zero-yield route failure, make exactly one
        # provider-neutral discovery fallback and retain its provenance.
        fallback = action.get("channel_fallback")
        yielded = any(str(item.get("result_type") or "").upper() not in {"DEAD_END", "IRRELEVANT", "DUPLICATE"} for item in raw_results)
        if fallback and not yielded:
            fallback_type = str(fallback.get("action_type") or "SEARCH_DISCOVERY")
            if fallback_type in SEARCH_ACTIONS and state["search_actions"] < limits["search_actions"]:
                fallback_action = {
                    **action,
                    "action_id": _stable_id("ACT", action["action_id"], "CHANNEL_FALLBACK", fallback_type),
                    "action_type": fallback_type,
                    "target": None,
                    "expected_result_type": "DISCOVERY_RESULT",
                    "discovery_channel": str(fallback.get("channel") or "GOOGLE_NEWS_RSS"),
                    "discovery_backends": list(fallback.get("backends") or []),
                    "query_variant": f"{action.get('query_variant', 'CONFIGURED_ROUTE')}_FALLBACK",
                    "strategy_index": float(action.get("strategy_index", 0)) + 0.5,
                    "channel_fallback": None,
                }
                run_action(fallback_action)

    for action in planned[: config["executor"]["maximum_actions_per_round"]]:
        run_action(action)

    # Follow a bounded, rank- and diversity-selected set of discovery leads.
    # This reserve is separate from configured-source fetches so pre-existing
    # routes cannot starve exact-page inspection of newly discovered material.
    if getattr(adapter, "follow_discovery_leads", False):
        parents = {item["action_id"]: item for item in executed}
        followup_limits = config["executor"]["lead_followup_limits"][job["budget_class"]]
        selected_leads = select_leads_for_followup(observations, parents, followup_limits)
        lead_followup_candidates = [
            {"url": item.get("url"), "priority": item.get("lead_priority"), "attrition_state": item.get("lead_attrition_state"), "need_id": item.get("_followup_need"), "source_identity": item.get("source_identity")}
            for item in observations if item.get("observation_class") == "LEAD" and item.get("url")
        ]
        lead_followup_selection = [
            {"url": item.get("url"), "priority": item.get("lead_priority"), "need_id": item.get("_followup_need"), "source_identity": item.get("source_identity")}
            for item in selected_leads
        ]
        for observation in selected_leads:
            parent = parents[observation["provenance"]["action_id"]]
            fetch_action = {
                **parent,
                "action_id": _stable_id("ACT", parent["action_id"], "FETCH_URL", observation["url"]),
                "action_type": "FETCH_URL",
                "target": observation["url"],
                "expected_result_type": "EXTRACTED_SOURCE",
                "timeout_seconds": config["executor"]["action_timeout_seconds"],
                "lead_followup": True,
                # The discovery ladder already selected this exact page. A
                # failed retrieval is attrition evidence, not permission to
                # recursively spend search budget on its parent query.
                "channel_fallback": None,
            }
            run_action(fetch_action)
            if state["lead_followups"] >= followup_limits["total"]:
                break
    results = [{"branch_id": branch_id, "observations": values} for branch_id, values in branch_results.items() if values]
    advanced = advance_research_job(job, results, config)
    state["seen_urls"] = sorted(seen_urls)
    state["seen_origins"] = sorted(set(state["seen_origins"]))
    state["actions_executed"] = int(state.get("actions_executed", 0)) + len(executed)
    advanced["executor_state"] = state
    strategy_progress = [
        {
            "need_id": need_id,
            "executed_variants": sorted(indices),
            "strategy_count": strategy_counts[need_id],
            "attempt_exhausted": len(indices) >= strategy_counts[need_id],
        }
        for need_id, indices in sorted(attempted_strategies.items())
    ]
    return {
        "schema_version": 1,
        "status": "EXECUTED",
        "job": advanced,
        "actions": executed,
        "observations": observations,
        "source_packet_patch": {
            "sources": source_records,
            "candidate_evidence_updates": updates,
            "candidate_discoveries": candidate_discoveries,
        },
        # A recovery attempt is a whole bounded ladder, not a single RSS hit.
        "recovery_attempts": [item["need_id"] for item in strategy_progress if item["attempt_exhausted"]],
        "recovery_strategy_progress": strategy_progress,
        "budget_consumed": {"search_actions": state["search_actions"], "fetches": state["fetches"], "lead_followups": state["lead_followups"]},
        "lead_followup_selection": lead_followup_selection,
        "lead_followup_candidates": lead_followup_candidates,
        "remaining_gaps": list(advanced["context"]["SOURCE_GAPS"]),
        "stop_reason": advanced.get("stop_condition"),
    }


def apply_executor_results_to_packet(packet: dict, execution: dict) -> dict:
    """Create a new packet for normal source intelligence/recovery evaluation.

    This is deliberately a packet patch, not a recovery-success switch. Only an
    explicit fixture-verified exact page may update a candidate evidence role;
    subsequent source intelligence and recovery planning remain authoritative.
    """
    value = deepcopy(packet)
    existing_ids = {item["id"] for item in value.get("sources", [])}
    existing_urls = {normalize_url(item["url"]) for item in value.get("sources", [])}
    for source in execution["source_packet_patch"]["sources"]:
        if source["id"] not in existing_ids and normalize_url(source["url"]) not in existing_urls:
            value.setdefault("sources", []).append(source)
            existing_ids.add(source["id"])
            existing_urls.add(normalize_url(source["url"]))
    for update in execution["source_packet_patch"]["candidate_evidence_updates"]:
        for section in value.get("sections", []):
            for candidate in [*section.get("candidates", []), *section.get("recovery_candidates", [])]:
                if candidate.get("id") != update["candidate_id"]:
                    continue
                candidate.setdefault("discovery_source_ids", []).append(update["source_id"])
                candidate.setdefault("verification_source_ids", []).append(update["source_id"])
                field = "primary_evidence_source_ids" if update["role"] == "PRIMARY" else "independent_evidence_source_ids"
                candidate.setdefault(field, []).append(update["source_id"])
                candidate["recovery_revalidated"] = True
    for discovery in execution["source_packet_patch"].get("candidate_discoveries", []):
        section = next((item for item in value.get("sections", []) if item.get("section_id") == discovery["section_id"]), None)
        if section is None:
            continue
        candidate_id = _stable_id("CAND", discovery["section_id"], discovery["event_id"])
        candidate = next((item for item in section.get("candidates", []) if item.get("id") == candidate_id), None)
        if candidate is None:
            candidate = {
                "id": candidate_id, "rank": 1, "title": discovery["title"],
                "facts": [discovery["claim"]], "claims": [], "unknowns": [], "disputed_points": [],
                "discovery_source_ids": [], "verification_source_ids": [],
                "primary_evidence_source_ids": [], "independent_evidence_source_ids": [],
                "discovered_by": "VALIDATED_DISTINCT_EVENT_RECOVERY",
                # This marker is set only because the discovery entered this
                # patch from a validated exact page.  It is still not enough
                # to select the candidate: ordinary role, origin, date and
                # claim-policy checks below remain decisive.
                "recovery_revalidated": True,
                "event_id": discovery["event_id"],
            }
            section.setdefault("candidates", []).append(candidate)
        for field in ("discovery_source_ids", "verification_source_ids"):
            if discovery["source_id"] not in candidate[field]:
                candidate[field].append(discovery["source_id"])
        role_field = "primary_evidence_source_ids" if discovery["role"] == "PRIMARY" else "independent_evidence_source_ids"
        if discovery["source_id"] not in candidate[role_field]:
            candidate[role_field].append(discovery["source_id"])
    sources = {item["id"]: item for item in value.get("sources", [])}
    for section in value.get("sections", []):
        for candidate in [*section.get("candidates", []), *section.get("recovery_candidates", [])]:
            primary = [
                item for item in candidate.get("primary_evidence_source_ids", [])
                if sources.get(item, {}).get("source_type") in {"primary", "official", "paper"}
            ]
            independent = [
                item for item in candidate.get("independent_evidence_source_ids", [])
                if sources.get(item, {}).get("source_type") == "independent"
            ]
            primary_origins = {urlsplit(sources[item]["url"]).hostname for item in primary}
            independent_origins = {urlsplit(sources[item]["url"]).hostname for item in independent}
            policy = candidate_evidence_policy(candidate, sources, section_id=section.get("section_id"))
            candidate["evidence_policy"] = policy
            issues = []
            if "PRIMARY" in policy["required_roles"] and not primary:
                issues.append("PRIMARY_EVIDENCE_MISSING")
            if "INDEPENDENT" in policy["required_roles"] and not independent:
                issues.append("INDEPENDENT_EVIDENCE_MISSING")
            if primary_origins & independent_origins:
                issues.append("EVIDENCE_ROLE_ORIGIN_OVERLAP")
            candidate["evidence_eligibility"] = {
                "status": "ELIGIBLE" if not issues else "INELIGIBLE",
                "issues": issues,
            }
            if (
                candidate["evidence_eligibility"]["status"] == "ELIGIBLE"
                and candidate in section.get("candidates", [])
                and section.get("selected_candidate_id") is None
            ):
                section["selected_candidate_id"] = candidate["id"]
                section["status"] = "ACTIVE"
                section["selection_reason"] = "VALIDATED_DISTINCT_EVENT_RECOVERY"
        # A recovery-only candidate may re-open a NO_NEWS desk only after the
        # normal role/origin validation above has made it eligible.  This is
        # not a promotion switch: it preserves the candidate and its exact
        # retrieved source links, then lets source intelligence, event
        # clustering, and recovery re-evaluate the newly selected event.
        if section.get("status") == "NO_NEWS":
            recovered = [
                candidate for candidate in section.get("recovery_candidates", [])
                if candidate.get("evidence_eligibility", {}).get("status") == "ELIGIBLE"
            ]
            if recovered:
                recovered.sort(key=lambda candidate: (candidate.get("rank", 10**9), str(candidate.get("id") or "")))
                selected = recovered[0]
                section.update({
                    "status": "ACTIVE",
                    "candidates": list(section.get("recovery_candidates", [])),
                    "recovery_candidates": [],
                    "selected_candidate_id": selected["id"],
                    "selection_reason": "تمت إعادة فتح القسم بعد تحقق أدلة أولية ومستقلة من مسار الاسترداد المحدود.",
                    "no_news_reason": None,
                    "fallback_action": None,
                })
        elif section.get("status") == "ACTIVE":
            selected = next((item for item in section.get("candidates", []) if item.get("id") == section.get("selected_candidate_id")), None)
            replacements = [
                item for item in section.get("candidates", [])
                if item.get("id") != section.get("selected_candidate_id")
                and item.get("recovery_revalidated") is True
                and item.get("evidence_eligibility", {}).get("status") == "ELIGIBLE"
            ]
            if selected and selected.get("evidence_eligibility", {}).get("status") != "ELIGIBLE" and replacements:
                winner = sorted(replacements, key=lambda item: str(item.get("id")))[0]
                section["selected_candidate_id"] = winner["id"]
                section["selection_reason"] = "RECOVERY_EXACT_EVIDENCE_REPLACEMENT"
    return value


def replay_recovery_after_execution(packet: dict, execution: dict, coverage: dict, readiness: dict) -> dict:
    """Run normal normalization, clustering, and recovery against executor output."""
    patched = apply_executor_results_to_packet(packet, execution)
    intelligence = build_source_intelligence(patched)
    attempts = {need_id: 1 for need_id in execution.get("recovery_attempts", [])}
    recovery = build_recovery_plan(patched, intelligence, coverage, readiness, attempts_by_need=attempts)
    return {
        "schema_version": 1,
        "status": "READY" if recovery["status"] == "PASS" else "RESEARCH_GAPS_REMAIN",
        "packet": patched,
        "source_intelligence": intelligence,
        "recovery": recovery,
        "article_generation_allowed": recovery["article_generation_allowed"],
    }


def science_adapter_boundary(config: dict) -> dict:
    """Expose future science routes without enabling a science runtime."""
    return deepcopy(config["science"]["adapters"])
