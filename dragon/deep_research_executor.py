"""Bounded, provider-neutral execution beneath the Deep Research Engine.

The executor can use injected adapters to discover or retrieve public material.
It never treats discovery as publication evidence and never calls an editorial
provider.  Fixture adapters make the state transitions deterministic in tests;
the optional HTTP adapter only executes direct fetch actions through DRAGON's
existing safe fetch/extract path.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timezone
import hashlib
import json
import re
from typing import Protocol
from urllib.parse import quote_plus, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from xml.etree import ElementTree

import yaml

from dragon.deep_research import advance_research_job
from dragon.discovery import DiscoveryError, default_transport, discover_rss, fetch_and_extract_source
from dragon.discovery import assess_source_url
from dragon.evidence_validation import validate_exact_page
from dragon.research_recovery import build_recovery_plan
from dragon.source_intelligence import build_source_intelligence, normalize_url
from dragon.source_coverage import need_source_family_policy, route_source_family
from dragon.authority_routing import authority_artifact_preferences, authority_route_metadata, authority_capability_from_text, configured_artifact_family_for_route
from dragon.publisher_profiles import PublisherProfileCache, publisher_profile_from_pages
from dragon.evidence_policy import candidate_evidence_policy
from dragon.editorial_functions import classify_event_functions, validated_function_names
from dragon.temporal_relevance import evaluate_temporal_relevance
from dragon.institutional_navigation import (
    classify_page_type, extract_listing_child_links, resolve_institution_identity,
    NAVIGATION_PAGE_TYPES, classify_navigation_type, select_listing_child_link, extract_outbound_link_candidates, extract_actor_attributions, detect_official_portal_republication,
)
from dragon.original_source_resolution import build_original_source_resolution, preferred_resolution_query, resolution_failure_for_observation
from dragon.post_fetch_qualification import qualify_fetched_artifact


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


def _route_search_origin(route: dict | None) -> str:
    """Return the canonical host used for bounded domain-scoped discovery.

    Source configuration may retain a ``www`` presentation host while the
    verified route itself is served from the apex domain (or vice versa).
    Discovery should constrain to the same public domain family without
    treating this normalization as an ownership or evidence decision.
    """
    if not isinstance(route, dict):
        return ""
    raw = str(route.get("origin") or "").strip().casefold().strip(".")
    if not raw:
        raw = (urlsplit(str(route.get("url") or "")).hostname or "").casefold().strip(".")
    return raw[4:] if raw.startswith("www.") else raw


def _lead_source_profile(url: str | None, title: str, snippet: str = "", *, semantic_target: str | None = None) -> dict:
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
    target = str(semantic_target or "").upper()
    institutional_markers = (
        ("cour des comptes", "audit", "oversight", "regulator", "procurement", "anti-corruption", "election integrity", "ministry", "authority", "رقابة", "افتحاص", "هيئة", "وزارة")
        if target == "ACCOUNTABILITY" else
        ("registration", "deadline", "schedule", "eligibility", "public service", "transport", "education", "health", "election", "ministry", "authority", "تسجيل", "أجل", "خدمة", "نقل", "تعليم")
        if target == "SERVICE" else ()
    )
    source_class_hint = "INSTITUTIONAL_CANDIDATE" if institutional_markers and any(marker in haystack for marker in institutional_markers) else "UNCLASSIFIED"
    return {
        "origin": origin or None,
        "origin_family": family,
        "routing_class": kind,
        "source_class_hint": source_class_hint,
        "identity_state": "SOURCE_UNRESOLVED" if kind == "SOURCE_UNRESOLVED" else "SOURCE_IDENTITY_PENDING",
    }


def _actor_first_query(observation: dict, action: dict, skeleton: dict) -> str:
    """Build a bounded actor/action lookup from observed text plus intent.

    The extracted event action can be an awkward normalized verb (for example
    ``close`` for a headline saying an authority *called to safeguard* an
    election).  Keep that observed value, but add a small function vocabulary
    and current-process hint so the canonical-source lookup can still find the
    issuer's directive.  These terms are search context only and never alter
    the event skeleton or evidence role.
    """
    target = str(action.get("target_editorial_function") or "").upper()
    context = action.get("event_context") if isinstance(action.get("event_context"), dict) else {}
    text = " ".join(str(observation.get(key) or "") for key in ("title", "claim", "extracted_text", "text")).casefold()
    vocabularies = {
        "ACCOUNTABILITY": ("monitoring", "integrity", "complaints", "directive", "enforcement", "oversight", "probity", "مراقبة", "نزاهة", "شكايات", "دورية", "زجر"),
        "SERVICE": ("deadline", "procedure", "access", "service", "registration", "polling", "notice", "آخر أجل", "إجراء", "ولوج", "تسجيل", "منصة", "إشعار"),
    }
    vocabulary = vocabularies.get(target, ())
    # Keep a small deterministic set of action terms in every actor-first
    # lookup.  The observed headline may normalize to an unhelpful verb
    # (for example ``close`` from a "calls to safeguard" title), so the
    # query must retain concrete function signals without changing event
    # facts or expanding the retrieval budget.
    default_hints = list(vocabulary[:2])
    observed_hints = [term for term in vocabulary if term.casefold() in text and term not in default_hints]
    observed_action = str(skeleton.get("action") or "").strip()
    generic_actions = {"close", "open", "make", "take", "call", "calls", "safeguard", "ensure", "support"}
    if observed_action.casefold() in generic_actions or observed_action.casefold() not in text:
        observed_action = ""
    process_hint = " ".join(str(context.get("current_process_context") or "").strip().split()[:2])
    research_date = str(context.get("research_date") or skeleton.get("published_at") or "").strip()
    date_hint = research_date[:7] if len(research_date) >= 7 else research_date
    parts = [
        str((observation.get("event_actor_candidates") or [{}])[0].get("name") or skeleton.get("actor") or "").strip(),
        observed_action,
        str(skeleton.get("object") or "").strip(),
        *dict.fromkeys([*default_hints, *observed_hints[:1]]),
        process_hint,
        " ".join(skeleton.get("geography") or []),
        date_hint,
    ]
    return " ".join(dict.fromkeys(item for item in parts if item)).strip()


def _recovery_actor(observation: dict) -> dict | None:
    """Return a page-observed actor eligible for bounded source recovery."""
    candidates = observation.get("event_actor_candidates") or []
    if isinstance(candidates, list):
        for candidate in candidates:
            if isinstance(candidate, dict) and str(candidate.get("name") or "").strip():
                return candidate
    resolution = observation.get("original_source_resolution")
    observed = resolution.get("observed") if isinstance(resolution, dict) else {}
    actor = str(observed.get("actor") or "").strip() if isinstance(observed, dict) else ""
    provenance = str(observed.get("actor_provenance") or "") if isinstance(observed, dict) else ""
    # This fallback is reserved for an explicit issuer/document attribution.
    # Inferred page actors remain useful discovery metadata, but are not
    # enough to open an additional recovery branch from a generic listing.
    return {"name": actor} if actor and provenance == "PAGE_TEXT_EXPLICIT" else None


def _select_actor_first_candidate(items: list[dict], actor: str, action: dict) -> dict | None:
    """Choose one bounded actor/action result for exact-page retrieval.

    Search results are discovery metadata only.  This helper may prioritize a
    concrete result whose title/snippet names the observed actor and action,
    even when the adapter has not yet resolved its source class.  The fetched
    page still passes the normal ownership, claim, and evidence-role gates.
    """
    target = str(action.get("target_editorial_function") or "").upper()
    terms = {
        "ACCOUNTABILITY": ("directive", "monitoring", "complaints", "enforcement", "oversight", "integrity", "probity", "مراقبة", "شكايات", "نزاهة"),
        "SERVICE": ("service", "procedure", "deadline", "registration", "access", "polling", "notice", "منصة", "إجراء", "تسجيل", "إشعار"),
    }.get(target, ())
    actor_text = str(actor or "").casefold().strip()
    route = action.get("source_route") if isinstance(action.get("source_route"), dict) else {}
    route_origin = _route_search_origin(route)
    scored: list[tuple[int, str, dict]] = []
    for item in items:
        if not isinstance(item, dict) or item.get("observation_class") in {"DUPLICATE", "IRRELEVANT", "DEAD_END"}:
            continue
        url = str(item.get("url") or item.get("canonical_url") or "").strip()
        host = (urlsplit(url).hostname or "").casefold().strip(".")
        haystack = " ".join(str(item.get(key) or "") for key in ("title", "snippet", "claim")).casefold()
        actor_hit = bool(actor_text and actor_text in haystack)
        action_hits = sum(1 for term in terms if term.casefold() in haystack)
        supplied = str(item.get("source_class") or item.get("source_type") or "").casefold()
        official_hint = supplied in {"official", "primary", "paper"} or host.endswith(".gov") or host.endswith(".gov.ma")
        route_hint = bool(route_origin and (host == route_origin or host.endswith(f".{route_origin}")))
        # A result on the explicitly configured issuer route is a bounded
        # acquisition candidate even when the search adapter has not assigned
        # it a source class and its listing title omits the canonical actor.
        # Route identity only permits a fetch; normal role and evidence gates
        # still decide whether the fetched page is usable.
        if not (official_hint or route_hint or (actor_hit and action_hits >= 1)):
            continue
        score = (100 if official_hint else 0) + (25 if route_hint else 0) + (20 if actor_hit else 0) + min(action_hits, 4) * 8
        scored.append((score, url, item))
    return max(scored, key=lambda value: (value[0], value[1]))[2] if scored else None


def _skip_mode_b_feedback(action: dict) -> bool:
    """Whether same-lead feedback would defeat semantic source diversity."""
    return (
        action.get("recovery_mode") == "DISCOVER_NEW_EVENT_FOR_SEMANTIC_NEED"
        and str(action.get("target_editorial_function") or "").upper() in {"ACCOUNTABILITY", "SERVICE"}
    )


def _lead_priority(observation: dict, action: dict) -> tuple[str, list[str], tuple]:
    """Categorical fetch priority, not a journalism-confidence score."""
    result = observation.get("search_result", {}) if isinstance(observation.get("search_result"), dict) else {}
    title = str(observation.get("title") or "")
    snippet = str(result.get("snippet") or observation.get("claim") or "")
    target = str(action.get("target_editorial_function") or action.get("candidate_event_theme") or "")
    profile = _lead_source_profile(observation.get("url"), title, snippet, semantic_target=target)
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
    if action.get("route_scoped"):
        # Route-scoped ranking is retrieval triage only.  It uses observed
        # title/snippet/URL signals and never assigns a source role or
        # semantic function.  Active-window language is deliberately weighted
        # above publication recency for SERVICE.
        url_path = str(observation.get("url") or "").casefold()
        artifact_markers = {
            "ACCOUNTABILITY": ("decision", "directive", "report", "audit", "oversight", "monitor", "complaint", "enforcement", "prosecution", "mobilisation", "electoral", "communique", "arrêt", "rapport", "رقابة", "شكايات", "مراقبة", "النيابة", "تعبئة", "مخالفات", "انتخابات", "انتخاب", "نزاهة", "تتبع", "متابعة", "دورية", "بلاغ"),
            "SERVICE": ("notice", "registration", "deadline", "procedure", "polling", "proxy", "voting", "election", "eligibility", "service", "avis", "inscription", "échéance", "bureau", "تسجيل", "أجل", "إشعار", "إشعارات", "منصة", "إجراء", "التصويت", "الاقتراع", "الانتخابات", "الوكالة", "مكاتب", "الناخب", "الناخبات", "تسليم", "الموعد", "إلكترونية"),
        }.get(target, ())
        action_hits = sum(marker in haystack for marker in artifact_markers)
        url_hits = sum(marker in url_path for marker in ("notice", "decision", "directive", "report", "publication", "communique", "avis", "inscription", "procedure", "service", "/news/", "الأخبار", "بلاغ", "مذكرة"))
        # Percent-encoded Arabic detail URLs are still exact-artifact
        # signals.  This is retrieval triage only; it never changes the
        # observed title/text or evidence role.
        path = urlsplit(str(observation.get("url") or "")).path
        path_depth = len([part for part in path.split("/") if part])
        if path_depth >= 3 and ("%" in path or "/news/" in path or "/actualites/" in path):
            url_hits += 2
        active_markers = ("active", "ongoing", "deadline", "until", "through", "en cours", "date limite", "jusqu", "مستمر", "نشط", "آخر أجل", "شتنبر", "غشت", "2026", "مفتوح", "مستمرة")
        active_hits = sum(marker in haystack for marker in active_markers)
        route_name = str((action.get("source_route") or {}).get("name") or "").casefold() if isinstance(action.get("source_route"), dict) else ""
        route_name_hits = sum(marker in haystack for marker in re.findall(r"[\w\u0600-\u06ff]+", route_name) if len(marker) > 3)
        duplicate_hint = any(
            str(item.get("fingerprint") or "").casefold() in haystack
            for item in action.get("known_event_fingerprints", [])
            if isinstance(item, dict) and item.get("fingerprint")
        )
        generic_penalty = 3 if any(marker in url_path for marker in ("/", "/tag=", "homepage", "/about")) and not url_hits else 0
        route_score = action_hits * 2 + url_hits * 2 + active_hits * 3 + route_name_hits + (1 if action.get("source_route") else 0) - generic_penalty - (5 if duplicate_hint else 0)
        if action_hits:
            reasons.append("SEMANTIC_ACTION_SIGNAL")
        if active_hits:
            reasons.append("ACTIVE_WINDOW_SIGNAL")
        if url_hits:
            reasons.append("EXACT_ARTIFACT_PATH_SIGNAL")
        if route_name_hits:
            reasons.append("ROUTE_ACTOR_SIGNAL")
        if duplicate_hint:
            reasons.append("KNOWN_EVENT_DUPLICATE_HINT")
        if route_score >= 6 and not duplicate_hint:
            return "HIGH", reasons, (0, -route_score, int(result.get("rank") or 10**6), str(observation.get("url") or ""))
        if route_score >= 2 and not duplicate_hint:
            # A meaningful route-scoped action signal should receive the
            # first fetch opportunity even when an open-web lead is labelled
            # HIGH by generic token overlap.  This is retrieval priority only.
            return "MEDIUM", reasons, (0, -route_score, int(result.get("rank") or 10**6), str(observation.get("url") or ""))
        reasons.append("LOW_ROUTE_ARTIFACT_SIGNAL")
        return "LOW", reasons, (2, -route_score, int(result.get("rank") or 10**6), str(observation.get("url") or ""))
    if overlap:
        reasons.append("ENTITY_OR_EVENT_OVERLAP")
    if result.get("published_at") or observation.get("published_at"):
        reasons.append("DATE_AVAILABLE")
    if profile["routing_class"] in {"SOCIAL", "AGGREGATOR", "SOURCE_UNRESOLVED"}:
        reasons.append(profile["routing_class"])
        return "LOW", reasons, (2, 0, int(result.get("rank") or 10**6), str(observation.get("url") or ""))
    if profile.get("source_class_hint") == "INSTITUTIONAL_CANDIDATE" and overlap >= 1:
        reasons.append("SEMANTIC_SOURCE_CLASS_MATCH")
        return "HIGH", reasons, (0, 0, int(result.get("rank") or 10**6), str(observation.get("url") or ""))
    if overlap >= 2:
        reasons.append("PUBLISHER_CANDIDATE")
        return "HIGH", reasons, (0, 0, int(result.get("rank") or 10**6), str(observation.get("url") or ""))
    reasons.append("LIMITED_CONTEXT_MATCH")
    return "MEDIUM", reasons, (1, 0, int(result.get("rank") or 10**6), str(observation.get("url") or ""))


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
            semantic_target=str(action.get("target_editorial_function") or action.get("candidate_event_theme") or ""),
        )
        observation["lead_priority"] = priority
        observation["lead_priority_reasons"] = reasons
        observation["source_identity"] = profile
        if observation.get("lead_attrition_state") != "SELECTED_FOR_FETCH":
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
    need_order = sorted(groups, key=lambda value: (
        PRIORITY_ORDER.get(str(actions_by_id[groups[value][0]["provenance"]["action_id"]].get("priority_class") or "P3_CONTEXT"), 99), value
    ))
    seen_by_need: dict[str, tuple[set[str], set[str]]] = {need: (set(), set()) for need in need_order}
    selected_by_need: dict[str, int] = {need: 0 for need in need_order}

    def take_one(need: str, *, target_count: int) -> bool:
        items = groups[need]
        parent = actions_by_id[items[0]["provenance"]["action_id"]]
        allowance = int(limits.get(str(parent.get("priority_class") or "P3_CONTEXT"), 0))
        seen_families, seen_titles = seen_by_need[need]
        for item in sorted(items, key=lambda value: value["_lead_sort_key"]):
            if selected_by_need[need] >= min(target_count, allowance):
                return False
            if item.get("_followup_need"):
                continue
            item_parent = actions_by_id[item["provenance"]["action_id"]]
            # Discovery eligibility is a network-safety check, not an
            # evidence-role check.  Reject unsafe targets before they enter
            # the bounded fetch queue, while retaining an auditable reason.
            lead_safety = assess_source_url(str(item.get("url") or ""))
            if lead_safety.get("state") == "URL_UNSAFE":
                item["lead_attrition_state"] = "DISCOVERED_NOT_SELECTED"
                item["lead_attrition_reason"] = "RESULT_FILTERED_SECURITY"
                item["discovery_filter_reason"] = lead_safety.get("reason") or "URL_UNSAFE"
                continue
            require_event_diversity = (
                str(item_parent.get("priority_class") or "") == "P1_DISTINCT_EVENT"
                and not item_parent.get("event_lead_feedback")
            )
            profile = item["source_identity"]
            route_origin = str((item_parent.get("source_route") or {}).get("origin") or "").casefold() if isinstance(item_parent.get("source_route"), dict) else ""
            candidate_origin = str(profile.get("origin") or "").casefold()
            route_relation = bool(item_parent.get("route_scoped") and route_origin and candidate_origin and (
                candidate_origin == route_origin
                or _registrable_domain(candidate_origin) == _registrable_domain(route_origin)
            ))
            hint_url = str(item.get("publisher_hint_url") or "").strip()
            hint_origin = (urlsplit(hint_url).hostname or "").casefold() if hint_url else ""
            hint_safe = bool(hint_url and hint_origin and assess_source_url(hint_url).get("state") != "URL_UNSAFE")
            hint_route_relation = bool(
                item_parent.get("route_scoped") and route_origin and hint_origin and
                (hint_origin == route_origin or _registrable_domain(hint_origin) == _registrable_domain(route_origin)) and hint_safe
            )
            # A safe publisher hint is a discovery navigation seed even when
            # its ownership is not yet resolved.  It never becomes evidence;
            # the exact fetched page must still pass source-role validation.
            hint_fetchable = hint_safe and hint_origin not in set(parent.get("excluded_origins", [])) and _registrable_domain(hint_origin) not in set(parent.get("excluded_origin_families", []))
            title_key = " ".join(re.findall(r"[\w\u0600-\u06ff]+", str(item.get("title") or "").casefold())[:8])
            if (
                profile["routing_class"] == "SOCIAL"
                or (profile["routing_class"] == "AGGREGATOR" and not hint_fetchable)
                or (profile["routing_class"] == "SOURCE_UNRESOLVED" and not route_relation)
                or profile.get("origin") in set(parent.get("excluded_origins", []))
                or profile.get("origin_family") in set(parent.get("excluded_origin_families", []))
                or profile.get("origin_family") in seen_families
                or (require_event_diversity and title_key in seen_titles)
            ):
                if profile["routing_class"] == "AGGREGATOR":
                    item["lead_attrition_reason"] = (
                        "AGGREGATOR_WRAPPER_WITH_PUBLISHER_HINT"
                        if item.get("publisher_hint_url") else
                        "AGGREGATOR_WRAPPER_DISCOVERY_ONLY"
                    )
                elif profile["routing_class"] == "SOCIAL":
                    item["lead_attrition_reason"] = "SOCIAL_DISCOVERY_ONLY"
                else:
                    item["lead_attrition_reason"] = "LOW_SOURCE_ROUTING_PRIORITY"
                continue
            if profile["routing_class"] == "AGGREGATOR" and hint_fetchable:
                # A wrapper may be followed only to a publisher hint that is
                # already within the verified route's domain family.  The
                # hint is a bounded navigation seed, never an evidence role.
                item["followup_target_url"] = hint_url
                item["followup_resolution_mode"] = "VERIFIED_ROUTE_PUBLISHER_HINT_NAVIGATION" if hint_route_relation else "SAFE_PUBLISHER_HINT_NAVIGATION"
            item["lead_attrition_state"] = "SELECTED_FOR_FETCH"
            item["lead_attrition_reason"] = "RESERVED_SEMANTIC_BRANCH_CAPACITY"
            item["_followup_need"] = need
            selected.append(item)
            selected_by_need[need] += 1
            seen_families.add(profile.get("origin_family"))
            seen_titles.add(title_key)
            return True
        return False

    total_limit = int(limits.get("total", 0))
    # Reserve the first exact-artifact opportunity for every viable need
    # before filling a second slot for an earlier need.
    for need in need_order:
        if len(selected) >= total_limit:
            return selected
        take_one(need, target_count=1)
    for need in need_order:
        if len(selected) >= total_limit:
            return selected
        while len(selected) < total_limit and take_one(need, target_count=selected_by_need[need] + 1):
            pass
    for need in need_order:
        allowance = int(limits.get(str(actions_by_id[groups[need][0]["provenance"]["action_id"]].get("priority_class") or "P3_CONTEXT"), 0))
        if selected_by_need[need] >= allowance:
            for item in groups[need]:
                if not item.get("_followup_need"):
                    item["lead_attrition_reason"] = "FOLLOWUP_BUDGET_EXHAUSTED"
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

# Categorical, auditable reasons a new event can contribute editorial breadth.
# This is a conservative screen, not an importance score or a replacement for
# editor review.  Text with none of these concrete public-interest signals may
# remain a lead/evidence observation, but cannot create a breadth candidate.
_EDITORIAL_VALUE_MARKERS = (
    ("INSTITUTIONAL_ACTION", ("ministry", "government", "official", "court", "parliament", "election", "policy", "institution", "وزارة", "حكومة", "برلمان", "انتخابات", "قرار")),
    ("SERVICE_USEFULNESS", ("service", "timetable", "schedule", "warning", "transport", "health", "school", "خدمة", "موعد", "نقل", "صحة", "تعليم")),
    ("ACCOUNTABILITY_VALUE", ("audit", "procurement", "oversight", "public record", "تدقيق", "افتحاص", "صفقة", "رقابة")),
    ("PUBLIC_CONSEQUENCE", ("economy", "infrastructure", "development", "displacement", "sanctions", "اقتصاد", "بنية", "تنمية", "عقوبات")),
    ("CULTURAL_OR_SCIENTIFIC_DEVELOPMENT", ("culture", "museum", "heritage", "research", "cultural", "ثقافة", "تراث", "بحث")),
)

_EVENT_ACTION_MARKERS = (
    "sign", "signs", "signed", "ban", "bans", "banned", "announce", "announces", "announced", "launch", "launches", "launched", "approve", "approves", "approved", "adopt", "adopts", "adopted", "report", "reports", "reported", "sanction", "sanctions", "agree", "agrees", "agreed", "open", "opens", "opened", "close", "closes", "closed", "arrest", "arrests", "arrested", "appoint", "appoints", "appointed", "elect", "elects", "elected", "register", "registers", "registered", "registration", "inspect", "inspects", "inspected", "monitor", "monitors", "monitored", "enforce", "enforces", "enforced", "deadline", "expires", "expire", "change", "changes", "changed", "suspend", "suspends", "suspended",
    "inscription", "inscrit", "ouvre", "ouvert", "ferme", "fermeture", "contrôle", "contrôler", "surveille", "surveillance", "publie", "publié", "publiée", "publier", "orders", "order", "directive", "circular", "monitoring", "تنفيذ", "يفتش", "يفتح", "يغلق", "يسجل", "مراقبة", "يراقب", "مهلة", "ينتهي", "تغيير", "يوقف",
    "يفتح", "يوقع", "توقع", "يعلن", "أعلن", "يعتمد", "يحظر", "يفرض", "ينشر", "تقرير", "انتخاب", "اتفاق",
    "دعا", "دعت", "يدعو", "تدعو", "توجيهات", "التصدي", "تتبع", "مواكبة", "بلاغ",
)
_EVENT_GEOGRAPHIES = (
    "morocco", "meknes", "sudan", "gaza", "palestine", "israel", "west bank", "ceuta", "spain", "hong kong", "africa",
    "المغرب", "مكناس", "السودان", "غزة", "فلسطين",
)
_EVENT_IDENTITY_STOP_WORDS = {
    "the", "and", "for", "with", "from", "this", "that", "of", "in", "to", "on", "at", "a", "an",
    "news", "live", "briefing", "story", "report", "group", "bank", "daily", "update",
}


def _desk_terms(values: list[object]) -> str:
    """Translate internal desk IDs to finite, reader-facing search vocabulary."""
    terms = [_DESK_SEARCH_TERMS.get(str(value), str(value).replace("_", " ")) for value in values]
    return " ".join(item for item in terms if item)[:180]


def _first_present(*values: object) -> str | None:
    return next((str(value).strip() for value in values if str(value or "").strip()), None)


def _editorial_value_reason(observation: dict, action: dict) -> tuple[str | None, str | None]:
    """Return a categorical public-interest rationale for a new event.

    A result which passes source verification but has no discernible public
    consequence is retained as an observation, never promoted merely to fill
    a desk.
    """
    title = str(observation.get("title") or "").strip()
    if not title or title.casefold() == "untitled research result":
        return None, "NO_DISCERNIBLE_EVENT"
    edition_date = str(action.get("event_context", {}).get("research_date") or "")
    # Production actions carry the edition date.  A few legacy fixture
    # actions do not; retain their historical editorial-value behavior rather
    # than treating an absent comparison date as proof of staleness.
    if edition_date:
        temporal = evaluate_temporal_relevance(observation, edition_date)
        if not temporal.get("active_on_edition_date"):
            return None, temporal.get("rejection_reason") or "TEMPORAL_RELEVANCE_UNRESOLVED"
    text = " ".join(str(observation.get(key) or "") for key in ("title", "claim", "extracted_text")).casefold()
    for reason, markers in _EDITORIAL_VALUE_MARKERS:
        if any(marker in text for marker in markers):
            return reason, None
    return None, "RESULTS_LOW_EDITORIAL_VALUE"


def extract_event_skeleton(raw: dict, action: dict) -> dict:
    """Build a modest, deterministic event description from an exact page.

    It intentionally answers only whether a concrete event appears present.
    It does not classify a publisher as independent or make evidence usable.
    """
    metadata = raw.get("article_metadata") if isinstance(raw.get("article_metadata"), dict) else {}
    title = str(raw.get("title") or metadata.get("title") or "").strip()
    title_state = str(raw.get("title_state") or metadata.get("title_state") or ("TITLE_RESOLVED" if title else "TITLE_UNRESOLVED"))
    date_info = raw.get("publication_date") if isinstance(raw.get("publication_date"), dict) else metadata.get("publication_date", {})
    published_at = str(raw.get("published_at") or date_info.get("normalized") or "").strip()
    text = str(raw.get("text") or raw.get("extracted_text") or raw.get("content") or "").strip()
    page_type = classify_page_type(raw, action=action)
    structured = raw.get("structured_fields") if isinstance(raw.get("structured_fields"), dict) else {}
    if title_state == "TITLE_UNRESOLVED" or not title:
        return {"state": "EVENT_UNRESOLVED", "reason": "TITLE_UNRESOLVED"}
    minimum_text = 80 if page_type in {"OFFICIAL_NOTICE", "OFFICIAL_DECISION", "PRESS_RELEASE", "PROCUREMENT_NOTICE", "SERVICE_NOTICE", "REPORT_DETAIL"} or structured else 200
    if len(text) < minimum_text:
        return {"state": "EVENT_UNRESOLVED", "reason": "ARTICLE_TEXT_UNUSABLE"}
    research_month = str(action.get("event_context", {}).get("research_date") or "")[:7]
    edition_date = str(action.get("event_context", {}).get("research_date") or "")
    temporal = evaluate_temporal_relevance(raw, edition_date, exact_text=text) if edition_date else None
    # Event time is a separate observed field.  It must not be silently
    # replaced with page-publication time when a source supplies both.
    event_date = (temporal or {}).get("event_time") or raw.get("event_date") or raw.get("event_time")
    if not published_at and temporal and not temporal.get("active_on_edition_date"):
        return {"state": "EVENT_UNRESOLVED", "reason": "NO_PUBLICATION_DATE", "temporal_relevance": temporal}
    if not published_at and not temporal:
        return {"state": "EVENT_UNRESOLVED", "reason": "NO_PUBLICATION_DATE"}
    if temporal is not None and not temporal.get("active_on_edition_date"):
        return {"state": "EVENT_OUTSIDE_WINDOW", "reason": temporal.get("rejection_reason") or "TEMPORAL_RELEVANCE_UNRESOLVED", "title": title, "published_at": published_at, "temporal_relevance": temporal}
    subject = " ".join((title, text[:1600]))
    lowered = subject.casefold()
    subject_words = set(_query_words([subject]))
    # Never use substring matching here: ``ban`` inside ``bank`` created a
    # false action, which then made unrelated pages look like one event.
    action_marker = next((marker for marker in _EVENT_ACTION_MARKERS if marker.casefold() in subject_words), None)
    if not action_marker and structured:
        # Structured notice fields can carry the action even when the prose is
        # terse.  Preserve the field provenance in the resulting skeleton.
        action_marker = next((str(structured.get(key)).strip() for key in ("action", "status", "procedure", "decision") if str(structured.get(key) or "").strip()), None)
    if not action_marker:
        return {"state": "EVENT_UNRESOLVED", "reason": "NO_CONCRETE_ACTION", "title": title, "published_at": published_at}
    words = _query_words([title])
    marker_words = _query_words([action_marker])
    action_index = next((index for index, word in enumerate(words) if word in marker_words), min(len(words), 6))
    actor = " ".join(words[:action_index]).strip() or None
    # Prefer a named institutional actor explicitly present in the page title
    # (page-derived attribution only; never query or recovery context).
    observed_actors = extract_actor_attributions(raw).get("actors", [])
    title_prefix = title.casefold()[:220]
    for candidate in observed_actors:
        if any(str(alias).casefold() in title_prefix for alias in (candidate.get("aliases") or [])):
            actor = candidate.get("name") or actor
            break
    object_terms = " ".join(words[action_index + 1: action_index + 8]).strip() or None
    # Geography is an observed page fact.  Target geography in the query or
    # recovery need is never copied into the event skeleton.
    geography = [place for place in _EVENT_GEOGRAPHIES if place in lowered]
    geography = sorted(set(geography))
    identifiers = re.findall(r"\b(?:[A-Z]{2,}[\-\d]{2,}|\d{3,})\b", subject)
    fingerprint_parts = [actor or "", action_marker, object_terms or "", (event_date or published_at or temporal.get("deadline") or temporal.get("effective_start") or "")[:10], " ".join(geography), " ".join(sorted(set(identifiers))[:3])]
    fingerprint = _stable_id("EVENT", *fingerprint_parts)
    return {
        "state": "CONCRETE_EVENT", "title": title, "published_at": published_at or None,
        "event_date": str(event_date).strip() if event_date else None,
        "page_type": page_type, "structured_fields": deepcopy(structured),
        "temporal_relevance": temporal,
        "actor": actor, "action": action_marker, "object": object_terms,
        "geography": geography, "institution": (metadata.get("publisher") or {}).get("name") if isinstance(metadata.get("publisher"), dict) else raw.get("publisher"),
        "identifiers": sorted(set(identifiers))[:5], "topic": title,
        "field_provenance": {
            "actor": "PAGE_TEXT_INFERRED" if actor else "OTHER_DERIVED",
            "action": "PAGE_TEXT_INFERRED" if action_marker else "OTHER_DERIVED",
            "object": "PAGE_TEXT_INFERRED" if object_terms else "OTHER_DERIVED",
            "geography": "PAGE_TEXT_INFERRED" if geography else "GEOGRAPHY_UNRESOLVED",
            "event_date": "PAGE_STRUCTURED_METADATA" if event_date else "OTHER_DERIVED",
            "institution": "PAGE_STRUCTURED_METADATA" if (metadata.get("publisher") or raw.get("publisher")) else "OTHER_DERIVED",
        },
        "event_fingerprint": fingerprint,
        "lead_paragraphs": "\n".join(part for part in re.split(r"\n\s*\n", text)[:2] if part)[:1200],
    }


def _event_date(value: object) -> str:
    """Return the calendar portion of an article/event timestamp."""
    match = re.match(r"(\d{4}-\d{2}-\d{2})", str(value or ""))
    return match.group(1) if match else ""


def _event_dates_within_window(left: str, right: str, *, days: int = 3) -> bool:
    try:
        return abs((date.fromisoformat(left) - date.fromisoformat(right)).days) <= days
    except ValueError:
        return False


def _event_terms_from_skeleton(skeleton: dict) -> set[str]:
    """Terms suitable for identity comparison, never for claim validation."""
    return {
        item.casefold() for item in _query_words([
            skeleton.get("actor"), skeleton.get("object"), skeleton.get("topic"), *skeleton.get("geography", []),
        ]) if item.casefold() not in _EVENT_IDENTITY_STOP_WORDS and not item.isdigit()
    }


def _meaningful_event_identifiers(values: object) -> set[str]:
    result = set()
    for value in values if isinstance(values, list) else []:
        item = str(value).casefold()
        if re.fullmatch(r"(?:19|20)\d{2}", item) or item in {"000", "100"}:
            continue
        if re.search(r"[a-z]|[\u0600-\u06ff]", item):
            result.add(item)
    return result


def _canonical_event_action(value: object) -> str:
    """Keep cross-language action comparison finite and deterministic."""
    action = str(value or "").casefold().strip()
    groups = {
        "sign": {"sign", "signed", "signs", "يوقع", "توقع", "اتفاق"},
        "ban": {"ban", "bans", "banned", "sanction", "sanctions", "يحظر", "يفرض"},
        "announce": {"announce", "announced", "launch", "launched", "يعلن", "أعلن", "اعلنت"},
        "approve": {"approve", "approved", "adopt", "adopted", "يعتمد"},
        "report": {"report", "reported", "publish", "published", "publie", "publié", "publiée", "تقرير", "ينشر"},
    }
    return next((name for name, aliases in groups.items() if action in aliases), action)


def match_event_skeletons(anchor: dict, candidate: dict) -> dict:
    """Classify whether two pages describe the same event, not the same claims."""
    if anchor.get("state") != "CONCRETE_EVENT" or candidate.get("state") != "CONCRETE_EVENT":
        return {"state": "EVENT_MATCH_UNRESOLVED", "reasons": ["EVENT_SKELETON_UNAVAILABLE"]}
    anchor_date, candidate_date = _event_date(anchor.get("published_at")), _event_date(candidate.get("published_at"))
    anchor_action = _canonical_event_action(anchor.get("action"))
    candidate_action = _canonical_event_action(candidate.get("action"))
    anchor_geography = {str(item).casefold() for item in anchor.get("geography", [])}
    candidate_geography = {str(item).casefold() for item in candidate.get("geography", [])}
    anchor_identifiers = _meaningful_event_identifiers(anchor.get("identifiers", []))
    candidate_identifiers = _meaningful_event_identifiers(candidate.get("identifiers", []))
    shared_terms = _event_terms_from_skeleton(anchor) & _event_terms_from_skeleton(candidate)
    shared_geography = anchor_geography & candidate_geography
    shared_identifiers = anchor_identifiers & candidate_identifiers
    reasons = []
    dates_within_window = bool(anchor_date and candidate_date and _event_dates_within_window(anchor_date, candidate_date))
    if dates_within_window:
        reasons.append("DATE_MATCH" if anchor_date == candidate_date else "DATE_WINDOW_MATCH")
    if anchor_action and anchor_action == candidate_action:
        reasons.append("ACTION_MATCH")
    if shared_geography:
        reasons.append("GEOGRAPHY_MATCH")
    if shared_identifiers:
        reasons.append("IDENTIFIER_MATCH")
    if len(shared_terms) >= 2:
        reasons.append("ENTITY_TOPIC_MATCH")
    if anchor_date and candidate_date and not dates_within_window and not shared_identifiers:
        return {"state": "DIFFERENT_EVENT", "reasons": ["DATE_MISMATCH"], "shared_terms": sorted(shared_terms)}
    if anchor_action and candidate_action and anchor_action != candidate_action and not shared_identifiers:
        return {"state": "DIFFERENT_EVENT", "reasons": ["ACTION_MISMATCH"], "shared_terms": sorted(shared_terms)}
    if (dates_within_window and anchor_action == candidate_action and (shared_geography or len(shared_terms) >= 2)) or (
        shared_identifiers and dates_within_window
    ):
        return {"state": "SAME_EVENT_HIGH_CONFIDENCE", "reasons": reasons, "shared_terms": sorted(shared_terms)}
    if anchor_action == candidate_action and (shared_geography or len(shared_terms) >= 2):
        return {"state": "SAME_EVENT_PLAUSIBLE", "reasons": reasons, "shared_terms": sorted(shared_terms)}
    return {"state": "EVENT_MATCH_UNRESOLVED", "reasons": reasons or ["INSUFFICIENT_SHARED_EVENT_CUES"], "shared_terms": sorted(shared_terms)}


def _event_lead_id(job: dict, action: dict, skeleton: dict) -> str:
    """Create a run-scoped identity for one provisional discovery event."""
    return _stable_id("EVL", job.get("job_id"), action.get("recovery_need_id"), skeleton.get("event_fingerprint"), action.get("action_id"))


def _recovery_event_id(need_id: object, target_function: object, skeleton: dict) -> str:
    """Stable identity for a new semantic event, independent of retrieval IDs."""
    fingerprint = skeleton.get("event_fingerprint")
    if not fingerprint:
        fingerprint = "|".join(str(skeleton.get(key) or "") for key in (
            "actor", "action", "object", "topic", "published_at", "event_time",
        ))
    return _stable_id("EVTREC", need_id, target_function, fingerprint)


def _mark_semantic_event_blocked(bundle: dict, reason: str, policy: dict | None = None) -> None:
    """Retain a concrete Mode-B event while recording its terminal evidence blocker.

    This is deliberately bookkeeping only.  A blocked event is never promoted,
    never creates P0 work, and never lends evidence to a later alternative.
    The memory is run-scoped and lets the same semantic need spend a later
    bounded slot on a different event instead of retrying the same dead end.
    """
    if not bundle.get("new_recovery_event") or not bundle.get("observations"):
        return
    bundle.update(state="EVENT_EVIDENCE_BLOCKED", failure_reason=reason)
    bundle["evidence_policy"] = deepcopy(policy or bundle.get("evidence_policy") or {})
    bundle["blocked_event_memory"] = {
        "event_lead_id": bundle.get("event_lead_id"),
        "event_fingerprint": bundle.get("event_fingerprint"),
        "recovery_need_id": bundle.get("recovery_need_id"),
        "target_editorial_function": bundle.get("target_editorial_function"),
        "blocker": reason,
        "missing_evidence_role": (
            "PRIMARY" if policy and "PRIMARY" in policy.get("required_roles", []) and not any(item.get("role") == "PRIMARY" for item in bundle.get("source_roles", []))
            else "INDEPENDENT" if policy and "INDEPENDENT" in policy.get("required_roles", []) and not any(item.get("role") == "INDEPENDENT" for item in bundle.get("source_roles", []))
            else None
        ),
        "evidence_ids": list(bundle.get("evidence_ids") or []),
        "source_ids": list(bundle.get("sources") or []),
        "attempted_source_routes": list(bundle.get("attempted_source_routes") or []),
        "attempted_observation_ids": list(bundle.get("observations") or []),
        "pivot_eligible": True,
        "normal_recovery_attempted": True,
    }


_ROLE_STOP_WORDS = _EVENT_IDENTITY_STOP_WORDS | {
    "official", "institutional", "portal", "institution", "international", "national", "commission",
}


def _organization_aliases(*values: object) -> set[str]:
    """Extract exact, auditable organization aliases rather than fuzzy names."""
    aliases = set()
    for value in values:
        text = str(value or "")
        host = urlsplit(text).hostname or ""
        for label in host.casefold().split("."):
            if len(label) >= 4 and label not in _ROLE_STOP_WORDS:
                aliases.add(label)
        for token in re.findall(r"\b[A-Z][A-Z0-9-]{2,}\b", text):
            aliases.add(token.casefold())
        normalized = " ".join(_query_words([text])).casefold()
        if len(normalized) >= 6 and normalized not in _ROLE_STOP_WORDS:
            aliases.add(normalized)
        words = normalized.split()
        # Exact adjacent aliases cover localized official names embedded in a
        # longer actor phrase without relying on fuzzy similarity.
        generic = {"tax", "audit", "date", "due", "extension", "will", "be", "extended", "report", "notice", "article", "fy", "ay", "what", "the", "latest", "update", "october"}
        aliases.update(
            " ".join(words[index:index + 2]) for index in range(max(0, len(words) - 1))
            if len(" ".join(words[index:index + 2])) >= 6
            and not set(words[index:index + 2]) <= generic
        )
    return aliases


def classify_document_type(raw: dict) -> str:
    """Classify a fetched artifact without assigning it an evidence role."""
    metadata = raw.get("article_metadata") if isinstance(raw.get("article_metadata"), dict) else {}
    types = {str(item).casefold() for item in metadata.get("jsonld_article_types", [])}
    attribution = raw.get("article_attribution") if isinstance(raw.get("article_attribution"), dict) else {}
    signals = metadata.get("signals") if isinstance(metadata.get("signals"), dict) else {}
    text = " ".join([
        *(str(raw.get(key) or "") for key in ("title", "text", "extracted_text", "publisher")),
        *(str(value or "") for value in signals.values()),
    ]).casefold()
    if "court" in text and any(marker in text for marker in ("judgment", "decision", "ruling", "حكم", "قرار قضائي")):
        return "COURT_DECISION"
    title_text = " ".join(str(raw.get(key) or "") for key in ("title", "h1")).casefold()
    # A generic tax-audit explainer is a news/information article, not an
    # institutional audit artifact.  Require an observed report/inspection
    # phrase (or an explicit structured type) before using AUDIT_REPORT.
    if ("audit report" in text or "inspection report" in text or "rapport d'audit" in text or "تقرير تدقيق" in text or "تقرير الافتحاص" in text) and not (
        any(marker in title_text for marker in ("due date", "deadline", "date limite", "آخر أجل"))
    ):
        return "AUDIT_REPORT"
    if any(marker in title_text for marker in ("due date", "deadline", "date limite", "آخر أجل")) and not types:
        return "NEWS_ARTICLE"
    if any(marker in text for marker in ("directive", "circular", "enforcement instruction", "توجيه", "دورية", "تعليمة")):
        return "OFFICIAL_STATEMENT"
    if any(marker in text for marker in ("statistical release", "dataset", "statistics", "إحصائيات", "بيانات إحصائية")):
        return "STATISTICAL_RELEASE"
    if any(marker in text for marker in ("regulation", "decree", "gazette", "مرسوم", "قانون تنظيمي")):
        return "REGULATION"
    if any(marker in text for marker in ("report", "rapport", "تقرير")) and not types:
        return "REPORT"
    if types & {"newsarticle", "article", "reportagenewsarticle", "analysisnewsarticle", "liveblogposting"}:
        return "NEWS_ARTICLE"
    if any(marker in text for marker in ("memorandum", "memorandum of understanding", "signed document", "مذكرة تفاهم")) or (
        any(marker in text for marker in ("signed", "signs", "وقع", "توقيع"))
        and any(marker in text for marker in ("agreement", "accord", "contract", "اتفاق"))
    ):
        return "SIGNED_DOCUMENT"
    if any(marker in text for marker in ("press release", "press-release", "بلاغ صحفي")):
        return "PRESS_RELEASE"
    if any(marker in text for marker in ("official statement", "institutional portal", "portail institutionnel", "بيان")):
        return "OFFICIAL_STATEMENT"
    if attribution.get("article_origin_state") in {"WIRE_REPUBLICATION", "PARTNER_REPUBLICATION"}:
        return "NEWS_ARTICLE"
    return "OTHER"


def _route_first_party_document_publication(raw: dict, action: dict, document_type: str) -> dict | None:
    """Recognize the issuer's own, explicitly published document page.

    A configured route is only an ownership constraint here; it does not
    supply claim content, a publication date, or temporal relevance.  The
    exact page must independently expose a resolved publisher, a matching
    route host, an institutional document type, and language showing that the
    publisher made that document public.  This creates a source-role finding
    for that narrow document-publication claim only.
    """
    route = action.get("source_route") if isinstance(action.get("source_route"), dict) else {}
    metadata = raw.get("article_metadata") if isinstance(raw.get("article_metadata"), dict) else {}
    publisher = metadata.get("publisher") if isinstance(metadata.get("publisher"), dict) else {}
    url = str(raw.get("canonical_url") or raw.get("url") or "")
    page_host = (urlsplit(url).hostname or "").casefold().strip(".")
    route_host = str(route.get("origin") or "").casefold().strip(".")
    if not route_host:
        route_host = (urlsplit(str(route.get("url") or "")).hostname or "").casefold().strip(".")
    route_is_primary = (
        str(route.get("role") or "").upper() == "PRIMARY"
        and str(route.get("authority_class") or "").upper() == "PRIMARY_ORIGINAL"
        and route.get("discovery_only") is False
    )
    if not route_is_primary or not page_host or page_host != route_host:
        return None
    if document_type not in {"REPORT", "AUDIT_REPORT", "STATISTICAL_RELEASE", "COURT_DECISION", "REGULATION"}:
        return None
    publisher_name = publisher.get("name") or raw.get("publisher")
    publisher_aliases = _organization_aliases(publisher_name)
    route_aliases = _organization_aliases(
        route.get("publisher"), route.get("name"), route.get("institution"), route.get("authority_id"),
    )
    shared_aliases = sorted(alias for alias in publisher_aliases & route_aliases if len(alias) >= 4)
    if not publisher_name or not shared_aliases:
        return None
    text = " ".join(str(raw.get(key) or "") for key in ("title", "text", "extracted_text", "claim")).casefold()
    publication_markers = (
        "rend public", "rendre public", "publie", "publié", "publication", "made public",
        "published", "publish", "ينشر", "نشر", "ينشر التقرير", "نشر التقرير",
    )
    if not any(marker in text for marker in publication_markers):
        return None
    return {
        "source_class": "primary",
        "evidence_role": "PRIMARY",
        "document_type": document_type,
        "publisher_event_relation": "PUBLISHER_IS_DOCUMENT_ISSUER",
        "article_origin_state": "FIRST_PARTY_ARTIFACT",
        "independence_state": "NOT_APPLICABLE_PRIMARY",
        "shared_organization_aliases": shared_aliases,
        "claim_scope": "NARROW_DOCUMENT_PUBLICATION",
        "reason": "PRIMARY_CONFIGURED_ROUTE_PAGE_PUBLISHER_AND_DOCUMENT_PUBLICATION_MATCH",
    }


def resolve_exact_source_role(raw: dict, action: dict, skeleton: dict | None) -> dict:
    """Resolve a narrow source role from exact-page and event relationship facts.

    This deliberately answers only what this page can establish.  It does not
    endorse an institution's interpretation or silently turn newsroom branding
    into independent evidence.
    """
    metadata = raw.get("article_metadata") if isinstance(raw.get("article_metadata"), dict) else {}
    publisher = metadata.get("publisher") if isinstance(metadata.get("publisher"), dict) else {}
    attribution = raw.get("article_attribution") if isinstance(raw.get("article_attribution"), dict) else {}
    profile = raw.get("publisher_profile") if isinstance(raw.get("publisher_profile"), dict) else {}
    # Route/profile context establishes portal identity only; it is never
    # copied into the page's observed claim fields.
    origin_detail = detect_official_portal_republication({
        **raw,
        "source_route": action.get("source_route") if isinstance(action.get("source_route"), dict) else None,
    })
    url = str(raw.get("canonical_url") or raw.get("url") or "")
    title = str(raw.get("title") or metadata.get("title") or "")
    text = str(raw.get("text") or raw.get("extracted_text") or "")
    document_type = classify_document_type(raw)
    publisher_aliases = _organization_aliases(
        publisher.get("name"), profile.get("canonical_publisher_name"), profile.get("canonical_domain"),
        url, raw.get("publisher"),
        *(profile.get("known_aliases") or []),
    )
    # Query entities/targets are retrieval context only.  They must never
    # manufacture a publisher/event relationship on the fetched page.
    event_aliases = _organization_aliases((skeleton or {}).get("actor"))
    shared_aliases = sorted(alias for alias in publisher_aliases & event_aliases if len(alias) >= 4)
    if (skeleton or {}).get("state") != "CONCRETE_EVENT":
        document_publication = _route_first_party_document_publication(raw, action, document_type)
        if document_publication and origin_detail.get("article_origin_state") != "OFFICIAL_PORTAL_REPUBLICATION":
            return document_publication
        return {
            "source_class": "unknown", "evidence_role": "UNRESOLVED", "document_type": document_type,
            "publisher_event_relation": "RELATION_UNRESOLVED", "article_origin_state": "SYNDICATION_UNRESOLVED",
            "independence_state": "INDEPENDENCE_UNRESOLVED", "shared_organization_aliases": shared_aliases,
            "reason": "EVENT_MATCH_UNRESOLVED",
        }
    # A hostname-shaped title supplies no page-derived assertion that the
    # publisher performed the extracted action.  In particular, it must not
    # turn a host-label actor inferred from the same title into a circular
    # primary-source identity match.
    host_label = re.sub(r"[^a-z0-9\u0600-\u06ff]+", "", (urlsplit(url).hostname or "").casefold())
    title_label = re.sub(r"[^a-z0-9\u0600-\u06ff]+", "", title.casefold())
    if shared_aliases and host_label and title_label == host_label:
        return {
            "source_class": "unknown", "evidence_role": "UNRESOLVED", "document_type": document_type,
            "publisher_event_relation": "RELATION_UNRESOLVED", "article_origin_state": "SYNDICATION_UNRESOLVED",
            "independence_state": "INDEPENDENCE_UNRESOLVED", "shared_organization_aliases": shared_aliases,
            "reason": "PUBLISHER_EVENT_RELATION_TITLE_IS_HOST_LABEL",
        }
    if origin_detail.get("article_origin_state") == "OFFICIAL_PORTAL_REPUBLICATION":
        # A portal page can report an issuer's action, but republication is
        # not the original artifact and must not silently become PRIMARY.
        return {
            "source_class": "unknown", "evidence_role": "UNRESOLVED", "document_type": document_type,
            "publisher_event_relation": "PUBLISHER_REPORTS_STATED_ISSUER",
            "article_origin_state": "OFFICIAL_PORTAL_REPUBLICATION",
            "independence_state": "NOT_INDEPENDENT_REPUBLICATION",
            "shared_organization_aliases": shared_aliases,
            "stated_issuing_authority": origin_detail.get("issuing_institution"),
            "content_origin": origin_detail.get("content_origin"),
            "original_artifact_state": origin_detail.get("original_artifact_state"),
            "reason": "OFFICIAL_PORTAL_REPUBLICATION_ORIGINAL_ARTIFACT_UNRESOLVED",
        }
    action_value = _canonical_event_action((skeleton or {}).get("action"))
    action_terms = set(_query_words([title, text[:2000]]))
    action_forms = {
        "sign": {"sign", "signed", "signs", "signing"},
        "ban": {"ban", "bans", "banned", "banning", "sanction", "sanctions"},
        "announce": {"announce", "announces", "announced", "announcing", "launch", "launched"},
        "approve": {"approve", "approves", "approved", "adopt", "adopts", "adopted"},
        "report": {"report", "reports", "reported", "publish", "published"},
    }
    direct_action = bool(action_value and action_terms & action_forms.get(action_value, {action_value}))
    if shared_aliases and document_type in {"PRESS_RELEASE", "OFFICIAL_STATEMENT", "SIGNED_DOCUMENT", "REPORT", "AUDIT_REPORT", "STATISTICAL_RELEASE", "COURT_DECISION", "REGULATION"}:
        relation = "PUBLISHER_IS_EVENT_ACTOR" if direct_action else "PUBLISHER_IS_PARTY_TO_EVENT"
        if document_type == "STATISTICAL_RELEASE":
            relation = "PUBLISHER_IS_STATISTICAL_AUTHORITY"
        elif document_type == "REGULATION":
            relation = "PUBLISHER_IS_REGULATOR"
        elif document_type in {"REPORT", "AUDIT_REPORT", "COURT_DECISION"}:
            relation = "PUBLISHER_IS_DOCUMENT_ISSUER"
        if direct_action or document_type in {"AUDIT_REPORT", "STATISTICAL_RELEASE", "COURT_DECISION", "REGULATION"}:
            return {
                "source_class": "primary", "evidence_role": "PRIMARY", "document_type": document_type,
                "publisher_event_relation": relation, "article_origin_state": "FIRST_PARTY_ARTIFACT",
                "independence_state": "NOT_APPLICABLE_PRIMARY", "shared_organization_aliases": shared_aliases,
                "reason": "PRIMARY_PUBLISHER_EVENT_RELATION_AND_DIRECT_ARTIFACT",
            }
        return {
            "source_class": "unknown", "evidence_role": "UNRESOLVED", "document_type": document_type,
            "publisher_event_relation": relation, "article_origin_state": "FIRST_PARTY_ARTIFACT",
            "independence_state": "NOT_APPLICABLE_PRIMARY", "shared_organization_aliases": shared_aliases,
            "reason": "FIRST_PARTY_ARTIFACT_DOES_NOT_DIRECTLY_ESTABLISH_LIMITED_CLAIM",
        }
    detected_origin = str(origin_detail.get("article_origin_state") or "")
    origin_state = detected_origin if detected_origin in {"OFFICIAL_PORTAL_REPUBLICATION", "PRIMARY_ORIGINAL_ARTIFACT"} else str(attribution.get("article_origin_state") or "SYNDICATION_UNRESOLVED")
    if document_type == "NEWS_ARTICLE":
        if origin_state in {"WIRE_REPUBLICATION", "PARTNER_REPUBLICATION"}:
            return {
                "source_class": "unknown", "evidence_role": "UNRESOLVED", "document_type": document_type,
                "publisher_event_relation": "PUBLISHER_REPORTS_OTHER_ACTOR", "article_origin_state": origin_state,
                "independence_state": origin_state, "shared_organization_aliases": shared_aliases,
                "reason": "ARTICLE_LINEAGE_IS_NOT_AN_INDEPENDENT_ORIGIN",
            }
        publisher_known = bool(publisher.get("name") or profile.get("canonical_domain"))
        byline = attribution.get("author_byline")
        if publisher_known and byline and origin_state == "ORIGINAL_UNKNOWN":
            return {
                "source_class": "independent", "evidence_role": "INDEPENDENT", "document_type": document_type,
                "publisher_event_relation": "PUBLISHER_REPORTS_OTHER_ACTOR", "article_origin_state": "INDEPENDENT_ORIGINAL_REPORTING",
                "independence_state": "INDEPENDENT_ORIGINAL_REPORTING", "shared_organization_aliases": shared_aliases,
                "reason": "BYLINED_NEWS_ARTICLE_WITHOUT_WIRE_OR_PARTNER_CREDIT",
            }
        return {
            "source_class": "unknown", "evidence_role": "UNRESOLVED", "document_type": document_type,
            "publisher_event_relation": "PUBLISHER_REPORTS_OTHER_ACTOR", "article_origin_state": origin_state,
            "independence_state": "INDEPENDENT_REPORTING_ORIGIN_UNCERTAIN", "shared_organization_aliases": shared_aliases,
            "reason": "NEWS_ARTICLE_LINEAGE_OR_PUBLISHER_IDENTITY_INSUFFICIENT",
        }
    return {
        "source_class": "unknown", "evidence_role": "UNRESOLVED", "document_type": document_type,
        "publisher_event_relation": "RELATION_UNRESOLVED", "article_origin_state": origin_state,
        "independence_state": "INDEPENDENCE_UNRESOLVED", "shared_organization_aliases": shared_aliases,
        "reason": "PUBLISHER_EVENT_RELATION_NOT_ESTABLISHED",
    }


def _breadth_target_section(need: dict) -> str:
    """Pick one eligible desk deterministically for an edition-wide event hunt.

    A breadth need is not a request to repeat every active desk in one query.
    Cycling the finite eligible list gives parallel needs different editorial
    targets, while retaining a stable route for audit and replay.
    """
    plan = need.get("event_acquisition_plan", {})
    target_function = str(plan.get("target_editorial_function") or need.get("target_editorial_function") or "")
    if target_function == "ACCOUNTABILITY":
        return "investigations"
    if target_function == "SERVICE":
        return "service"
    sections = list(need.get("search_constraints", {}).get("eligible_section_ids", []))
    if not sections:
        sections = list(need.get("topic_identifiers", []))
    if not sections:
        return "front"
    match = re.search(r":(\d+)$", str(need.get("need_id") or ""))
    index = int(match.group(1)) - 1 if match else 0
    return str(sections[index % len(sections)])


def _breadth_event_desk_preferences(bundle: dict, eligible_sections: list[str]) -> list[str]:
    """Route a verified breadth event to a semantically fitting eligible desk.

    The event still must pass evidence, distinctness, and normal candidate
    eligibility.  This only avoids wasting a genuinely new Morocco/World
    event in an already-covered desk when another eligible empty desk better
    describes its documented subject.
    """
    skeleton = bundle.get("event_skeleton") if isinstance(bundle.get("event_skeleton"), dict) else {}
    functions = {
        item.get("function") for item in bundle.get("editorial_functions", [])
        if isinstance(item, dict) and item.get("status") == "VALIDATED"
    }
    if "ACCOUNTABILITY" in functions and "investigations" in eligible_sections:
        return ["investigations", *[section for section in eligible_sections if section != "investigations"]]
    if "SERVICE" in functions and "service" in eligible_sections:
        return ["service", *[section for section in eligible_sections if section != "service"]]
    words = set(_query_words([skeleton.get("title"), skeleton.get("topic"), skeleton.get("object"), skeleton.get("lead_paragraphs")]))
    affinities = (
        ("3adl_7o9o9", {"corruption", "anti-corruption", "court", "justice", "rights", "probity", "integrity", "فساد", "نزاهة", "محكمة"}),
        ("iqtisad_flous", {"economy", "economic", "finance", "investment", "trade", "procurement", "اقتصاد", "مالية", "استثمار"}),
        ("mojtama3", {"youth", "society", "community", "social", "شباب", "مجتمع"}),
        ("ta3lim", {"school", "university", "education", "student", "تعليم", "جامعة"}),
        ("se77a", {"health", "hospital", "medical", "صحة", "مستشفى"}),
        ("bi2a_manakh", {"climate", "environment", "water", "مناخ", "بيئة", "مياه"}),
        ("bniya_transport", {"transport", "rail", "airport", "road", "infrastructure", "نقل", "مطار", "طريق"}),
    )
    preferred = [section for section, markers in affinities if section in eligible_sections and words & markers]
    return preferred + [section for section in eligible_sections if section not in preferred]


_PIVOT_SOURCE_CLASS_BRANCHES = {
    "ACCOUNTABILITY": [
        {
            "class": "REGULATOR",
            "terms": {"ar": "هيئة تنظيمية قرار رقابة امتثال إنفاذ", "fr": "régulateur décision contrôle conformité application", "en": "regulator decision oversight compliance enforcement"},
        },
        {
            "class": "AUDIT_BODY",
            "terms": {"ar": "مجلس حسابات تقرير افتحاص نتائج رقابة مالية", "fr": "cour des comptes rapport audit constat contrôle financier", "en": "audit body report audit finding financial oversight"},
        },
        {
            "class": "PROSECUTION_JUDICIARY",
            "terms": {"ar": "نيابة عامة دورية شكايات متابعة زجر", "fr": "parquet circulaire plaintes poursuite enforcement", "en": "prosecution directive complaints enforcement"},
        },
        {
            "class": "ELECTION_INTEGRITY",
            "terms": {"ar": "نزاهة الانتخابات مراقبة مراحل اقتراع مخالفات", "fr": "intégrité électorale suivi étapes scrutin infractions", "en": "election integrity monitoring electoral violations"},
        },
        {
            "class": "ANTI_CORRUPTION",
            "terms": {"ar": "هيئة محاربة الرشوة وقاية نزاهة تبليغ", "fr": "anti-corruption prévention intégrité signalement", "en": "anti-corruption integrity reporting prevention"},
        },
        {
            "class": "OTHER_FORMAL_OVERSIGHT",
            "terms": {"ar": "رقابة مؤسساتية قرار رسمي تتبع", "fr": "contrôle institutionnel décision officielle suivi", "en": "formal oversight official decision monitoring"},
        },
    ],
    "SERVICE": [
        {
            "class": "MINISTRY",
            "terms": {"ar": "وزارة بلاغ رسمي إجراء عمومي", "fr": "ministère communiqué procédure publique", "en": "ministry official notice public procedure"},
        },
        {
            "class": "ELECTION_ADMINISTRATION",
            "terms": {"ar": "إدارة الانتخابات مكتب التصويت إشعار ناخبين", "fr": "administration électorale bureau de vote avis électeurs", "en": "election administration polling station voter notice"},
        },
        {
            "class": "PUBLIC_SERVICE_OPERATOR",
            "terms": {"ar": "مؤسسة عمومية منصة خدمة ولوج تشغيلي", "fr": "opérateur public plateforme service accès opérationnel", "en": "public service operator platform operational access"},
        },
        {
            "class": "ADMINISTRATIVE_PORTAL",
            "terms": {"ar": "بوابة إدارية تسجيل مهلة طلب إلكتروني", "fr": "portail administratif inscription délai demande en ligne", "en": "administrative portal registration deadline online application"},
        },
        {
            "class": "TRANSPORT_AUTHORITY",
            "terms": {"ar": "نقل عمومي إشعار مواعيد خدمة", "fr": "autorité transport avis horaires service", "en": "transport authority notice schedule service"},
        },
        {
            "class": "OTHER_SERVICE_AUTHORITY",
            "terms": {"ar": "مرفق عمومي إجراء مستفيدين ولوج", "fr": "service public procédure usagers accès", "en": "public authority procedure user access"},
        },
    ],
}


def _pivot_source_class_branches(
    target_function: str,
    attempted: list[str] | None = None,
    current_process_context: str | None = None,
) -> list[dict]:
    """Return a bounded, function-first branch set for a semantic pivot.

    Branches are retrieval context only.  The exact page still determines
    actor, event, evidence role, and semantic function.  Memory is applied
    before selecting the four-strategy ladder so a failed class does not
    consume every alternative slot.
    """
    attempted_set = {str(item).upper() for item in (attempted or [])}
    branches = [deepcopy(item) for item in _PIVOT_SOURCE_CLASS_BRANCHES.get(str(target_function).upper(), [])]
    fresh = [item for item in branches if item["class"] not in attempted_set]
    selected = fresh or branches
    context = str(current_process_context or "").casefold()
    if context:
        target = str(target_function).upper()
        marker_orders = {
            "ACCOUNTABILITY": [
                (("election", "electoral", "scrutin", "vote", "انتخاب", "اقتراع"), "ELECTION_INTEGRITY"),
                (("procurement", "tender", "marché", "صفقة"), "AUDIT_BODY"),
                (("corruption", "رشوة", "فساد"), "ANTI_CORRUPTION"),
            ],
            "SERVICE": [
                (("election", "electoral", "poll", "vote", "انتخاب", "اقتراع"), "ELECTION_ADMINISTRATION"),
                (("transport", "نقل"), "TRANSPORT_AUTHORITY"),
                (("education", "school", "تعليم"), "OTHER_SERVICE_AUTHORITY"),
                (("health", "hospital", "صحة"), "OTHER_SERVICE_AUTHORITY"),
            ],
        }
        preferred = next((order for markers, order in marker_orders.get(target, []) if any(marker in context for marker in markers)), None)
        if preferred:
            selected = sorted(selected, key=lambda item: (0 if item["class"] == preferred else 1, item["class"]))
    return selected


def _breadth_event_queries(job: dict, need: dict, *, month: str, primary_language: str, alternate_language: str | None, route: dict | None) -> list[dict]:
    """Return an event-acquisition ladder without copying provider prose.

    The plan is structured by the recovery planner: editorial gap, proposed
    event themes, date and eligible desks.  Existing retrieval adapters remain
    unchanged; this only gives them inspectable, distinct search intents.
    """
    plan = need.get("event_acquisition_plan", {})
    target_section = _breadth_target_section(need)
    target_function = str(plan.get("target_editorial_function") or need.get("target_editorial_function") or "")
    if target_function:
        context = need.get("query_context", {}) if isinstance(need.get("query_context", {}), dict) else {}
        pivot_mode = str(need.get("pivot_mode") or "") == "FIND_ALTERNATIVE_EVENT_FOR_SEMANTIC_NEED"
        # Function-first acquisition never puts a desk label in the query.
        # The configured desk remains only a placement route after validation.
        terms = (
            ("مراقبة مخالفات شكايات متابعة نزاهة رقابة", "oversight violations complaints monitoring enforcement integrity prosecution audit finding", "surveillance infractions plaintes suivi intégrité contrôle poursuite constat audit")
            if target_function == "ACCOUNTABILITY" else
            # Service discovery must cover operational public-service changes,
            # not only election-administration notices.  These are retrieval
            # terms; the exact fetched page still has to establish function,
            # freshness, ownership, claim support, and evidence roles.
            ("خدمة عمومية نقل صحة تعليم ماء كهرباء منصة تشغيل استئناف انقطاع ولوج إجراء مهلة تسجيل", "public transport health education water electricity operational platform restoration interruption access procedure deadline registration", "transport santé éducation eau électricité plateforme opérationnelle reprise interruption accès procédure délai inscription")
        )
        geography = "Morocco" if target_function in {"ACCOUNTABILITY", "SERVICE"} else ""
        # Current-process context is retrieval guidance only.  It is copied
        # into the query plan/action metadata but never into observed event
        # facts or evidence-role fields.
        current_process = " ".join(str(
            context.get("current_process_context")
            or context.get("current_public_process")
            or need.get("current_process_context")
            or ""
        ).split())[:160]
        base_terms = terms[0] if primary_language == "ar" else terms[1] if primary_language == "en" else terms[2]
        alternate_terms = terms[2] if alternate_language == "fr" else terms[1]
        attempted_source_classes = list(need.get("pivot_source_classes_attempted") or need.get("source_class_attempts") or [])
        semantic_discovery_mode = bool(
            need.get("recovery_mode") == "DISCOVER_NEW_EVENT_FOR_SEMANTIC_NEED"
            or str(need.get("kind") or "").startswith("NEED_ACCOUNTABILITY_AND_SERVICE")
        )
        branch_mode = "PIVOT" if pivot_mode else "INITIAL_SEMANTIC" if semantic_discovery_mode else None
        pivot_branches = _pivot_source_class_branches(target_function, attempted_source_classes, current_process) if branch_mode else []
        if pivot_mode:
            pivot_terms = (
                ("قرار هيئة تنظيمية رقابة امتثال إنفاذ تتبع" if primary_language == "ar" else
                 "regulator decision oversight compliance enforcement monitoring" if primary_language == "en" else
                 "décision régulateur contrôle conformité exécution suivi")
                if target_function == "ACCOUNTABILITY" else
                ("خدمة عمومية منصة تشغيلية إجراء مهلة تسجيل ولوج" if primary_language == "ar" else
                 "official public service operational platform procedure deadline registration access" if primary_language == "en" else
                 "service public plateforme opérationnelle procédure délai inscription accès")
            )
            base_terms = f"{base_terms} {pivot_terms}"
            alternate_terms = f"{alternate_terms} {pivot_terms}"
        base = " ".join(item for item in (geography, current_process, base_terms, month) if item)
        alternate = " ".join(item for item in (geography, current_process, alternate_terms, month) if item)
        query_context_values = [
            *(context.get("entities") or []), *(context.get("aliases") or []),
            *(context.get("event_terms") or []),
        ]
        actor_hint = " ".join(str(item) for item in query_context_values if item)
        explicit_authority = authority_capability_from_text(actor_hint)
        authority_preferences = authority_artifact_preferences(
            target_function, actor=actor_hint, event_terms=" ".join(str(item) for item in (plan.get("candidate_event_themes") or [])),
        )
        authority_order = [str(item.get("authority_capability")) for item in authority_preferences]
        authority_rank = {value: index for index, value in enumerate(authority_order)}
        requested_artifact_families = {
            str(value).upper()
            for value in (
                plan.get("expected_artifact_family"),
                need.get("expected_artifact_family"),
                need.get("search_constraints", {}).get("expected_artifact_family"),
            )
            if isinstance(value, str) and value.strip()
        }
        route_candidates = [
            item for item in [
                *need.get("search_constraints", {}).get("configured_source_routes", []),
                *need.get("search_constraints", {}).get("configured_discovery_routes", []),
                *plan.get("canonical_source_routes", []),
            ] if item.get("url")
        ]
        # De-duplicate route aliases before applying family diversification.
        deduped_routes = []
        seen_route_keys = set()
        for item in route_candidates:
            key = str(item.get("route_id") or item.get("url"))
            if key in seen_route_keys:
                continue
            seen_route_keys.add(key)
            deduped_routes.append(item)
        route_candidates = deduped_routes
        if target_function == "ACCOUNTABILITY":
            markers = ("AUDIT", "REGULATOR", "COURT", "OVERSIGHT", "PROCUREMENT", "PRIMARY")
        else:
            markers = ("PUBLIC", "SERVICE", "HEALTH", "EDUCATION", "TRANSPORT", "PRIMARY")
        desired_route_types = (
            {"AUDIT_PUBLICATIONS", "REPORTS", "PRESS_RELEASES", "DECISIONS", "COURT_DECISIONS", "REGULATORY_ACTIONS", "PROCUREMENT_RESULTS", "NEWS_LISTING"}
            if target_function == "ACCOUNTABILITY" else
            {"SERVICE_PORTAL", "NOTICES", "CONSULTATIONS", "PROCUREMENT_RESULTS", "NEWS_LISTING", "PUBLICATIONS"}
        )
        status_order = {"VERIFIED_WORKING": 0, "VERIFIED_DISCOVERY_ONLY": 1, "UNKNOWN": 2, "STALE": 3, "TRANSIENT_FAILURE": 4, "CURRENTLY_UNUSABLE": 5}

        def artifact_variant_priority(item: dict) -> int:
            """Prefer a verified document surface only when it matches the need.

            This affects discovery order only: it neither grants evidence nor
            removes generic route variants from later bounded strategies.
            """
            metadata = authority_route_metadata(item, target_function, actor=actor_hint)
            configured_family = configured_artifact_family_for_route(
                item, metadata.get("authority_capability"),
            )
            expected = requested_artifact_families or {
                str(artifact).upper()
                for preference in authority_preferences
                if str(preference.get("authority_capability")) == metadata.get("authority_capability")
                for artifact in preference.get("artifact_families", [])
            }
            verified = str(item.get("route_status") or item.get("status") or "").upper().startswith("VERIFIED_")
            return 0 if verified and configured_family and configured_family in expected else 1

        legacy_route_sort = lambda item: (
            # A verified cross-function national/public portal is a useful
            # process hub for both missing families.  This is capability
            # routing, not a source-quality or evidence decision.
            0 if len(set(item.get("semantic_capabilities") or []) & {target_function, "ACCOUNTABILITY", "SERVICE"}) >= 2 and str(item.get("route_type") or "") in {"NEWS_LISTING", "OTHER_PUBLIC_INDEX"} else 1,
            0 if str(item.get("route_type") or "") in desired_route_types else 1,
            status_order.get(str(item.get("route_status") or item.get("status") or "UNKNOWN"), 9),
            0 if any(marker in str(item.get("name") or "").upper() for marker in markers) else 1,
            0 if any(marker in str(item.get("authority_class") or "").upper() for marker in markers) else 1,
            str(item.get("origin") or ""), str(item.get("url") or ""),
        )
        has_normalized_families = any(route_source_family(item) != "UNKNOWN" for item in route_candidates)
        if has_normalized_families:
            route_candidates.sort(key=lambda item: (
                authority_rank.get(authority_route_metadata(item, target_function, actor=actor_hint).get("authority_capability"), 99),
                artifact_variant_priority(item),
                legacy_route_sort(item),
            ))
        else:
            route_candidates.sort(key=legacy_route_sort)
        if explicit_authority:
            # An explicitly attributed actor narrows authority routing.  A
            # national portal or independent newsroom may remain as a
            # documented fallback, but unrelated official institutions do
            # not get selected merely because their family is nearby.
            fallback_capabilities = {"OFFICIAL_NATIONAL_PORTAL", "INDEPENDENT_NEWSROOM"}
            relevant = [
                item for item in route_candidates
                if authority_route_metadata(item, target_function, actor=actor_hint).get("authority_capability") in {explicit_authority, *fallback_capabilities}
            ]
            route_candidates = relevant
        elif has_normalized_families:
            # Statistics and central-bank routes answer narrow indicators,
            # rates, and financial-stability questions. They are not generic
            # accountability or public-service authorities; keep them out of
            # those lanes unless the need explicitly names that subject.
            subject_text = " ".join(str(item) for item in query_context_values).casefold()
            financial_or_stats = any(marker in subject_text for marker in (
                "rate", "monetary", "banking", "inflation", "statistics", "indicator", "finance",
                "سعر", "نقد", "بنك", "إحصاء", "مؤشر", "مالية",
            ))
            if not financial_or_stats:
                route_candidates = [
                    item for item in route_candidates
                    if authority_route_metadata(item, target_function, actor=actor_hint).get("authority_capability") not in {"CENTRAL_BANK", "FINANCE_AUTHORITY", "STATISTICS_AUTHORITY"}
                ]
            if target_function == "SERVICE":
                service_capabilities = {"PUBLIC_SERVICE_OPERATOR", "EXECUTIVE_MINISTRY", "LOCAL_AUTHORITY", "PUBLIC_AGENCY", "OFFICIAL_NATIONAL_PORTAL"}
                route_candidates = [
                    item for item in route_candidates
                    if authority_route_metadata(item, target_function, actor=actor_hint).get("authority_capability") in service_capabilities
                ]
        recognized_families = {
            route_source_family(item) for item in route_candidates
            if route_source_family(item) != "UNKNOWN"
        }
        family_order = [family for family in need_source_family_policy(target_function) if family in recognized_families]
        family_routes = []
        same_family_fallback_routes = []
        if family_order:
            for family in family_order:
                candidates = [item for item in route_candidates if route_source_family(item) == family]
                if candidates:
                    family_routes.append(candidates[0])
                    # Retain generic/other variants without creating new
                    # actions when a specific artifact route displaced them.
                    if artifact_variant_priority(candidates[0]) == 0:
                        same_family_fallback_routes.extend(candidates[1:])
        # Legacy fixtures without normalized family metadata retain their
        # historical route choice; production routes carry source_family and
        # therefore use need-scoped family diversification.
        selected_routes = family_routes or route_candidates[:1]
        canonical_route = selected_routes[0] if selected_routes else None
        route_origin = _route_search_origin(canonical_route)
        route_languages = set(canonical_route.get("supported_languages") or []) if canonical_route else set()
        route_language = next((lang for lang in (primary_language, alternate_language, "en") if lang and lang in route_languages), primary_language)
        language_terms = {
            "ar": terms[0], "en": terms[1], "fr": terms[2],
        }
        route_base_terms = language_terms.get(route_language, base_terms)
        if pivot_mode:
            route_base_terms = f"{route_base_terms} {pivot_terms}"
        # A discovery run must not carry a historic hard-coded current window.
        # ``month`` is the run's bounded temporal context (YYYY-MM), not an
        # observed publication date or an evidence fact.
        try:
            window_year, window_number = (int(part) for part in month.split("-", 1))
        except (TypeError, ValueError):
            window_year, window_number = 0, 0
        month_names = {
            "ar": ("يناير", "فبراير", "مارس", "أبريل", "ماي", "يونيو", "يوليوز", "غشت", "شتنبر", "أكتوبر", "نونبر", "دجنبر"),
            "fr": ("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"),
            "en": ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"),
        }
        month_name = month_names.get(route_language, month_names["en"])[window_number - 1] if 1 <= window_number <= 12 else month
        route_temporal = {
            "ar": f"نشط مستمر {month_name} {window_year}".strip(),
            "fr": f"actif en cours {month_name} {window_year}".strip(),
            "en": f"active ongoing {month_name} {window_year}".strip(),
        }.get(route_language, f"active ongoing {month}".strip())
        route_terms = " ".join(item for item in (current_process, route_base_terms, route_temporal) if item)
        route_query = " ".join(item for item in (f"site:{route_origin}" if route_origin else "", route_terms) if item)
        strategies = [
            {
                "intent": f"{('ALTERNATIVE_' if pivot_mode else '')}FUNCTION_{target_function}_VERIFIED_ROUTE_ARTIFACT", "variant": "ALTERNATIVE_ROUTE_SCOPED_ARTIFACT" if pivot_mode else "ROUTE_SCOPED_ARTIFACT",
                "query": route_query or base, "channel": "SEARXNG_GENERAL_SEARCH", "backends": ["searxng-general-search"],
                "language": primary_language, "target_desk": target_section,
                "candidate_event_theme": target_function, "source_route": canonical_route,
                "route_scoped": bool(canonical_route),
                "route_search_objective": "ACTIVE_WINDOW_ARTIFACT" if target_function == "SERVICE" else "CURRENT_FUNCTION_ARTIFACT",
                "current_process_context": current_process or None,
            },
            {
                "intent": f"{('ALTERNATIVE_' if pivot_mode else '')}FUNCTION_{target_function}_PRIMARY_WINDOW", "variant": "ALTERNATIVE_FUNCTION_DATE" if pivot_mode else "FUNCTION_DATE",
                "query": base, "channel": "SEARXNG_GENERAL_SEARCH", "backends": ["searxng-general-search"],
                "language": primary_language, "target_desk": target_section,
                "candidate_event_theme": target_function,
                "current_process_context": current_process or None,
                "fallback": {"action_type": "SEARCH_DISCOVERY", "channel": "GOOGLE_NEWS_RSS", "backends": ["public-rss-search"]},
            },
            {
                "intent": f"{('ALTERNATIVE_' if pivot_mode else '')}FUNCTION_{target_function}_CANONICAL_INSTITUTION", "variant": "ALTERNATIVE_CANONICAL_NAVIGATION" if pivot_mode else "CANONICAL_NAVIGATION",
                "query": " ".join(item for item in (current_process, route_base_terms if canonical_route else base_terms, "current notices decisions") if item),
                "action_type": "FETCH_CONFIGURED_SOURCE" if canonical_route else "SEARCH_DISCOVERY",
                "target": canonical_route.get("url") if canonical_route else None,
                "channel": "CONFIGURED_INSTITUTION_NAVIGATION", "backends": [] if canonical_route else ["searxng-general-search"],
                "language": primary_language, "target_desk": target_section,
                "candidate_event_theme": target_function,
                "discovery_only": True,
                "source_route": canonical_route,
                "current_process_context": current_process or None,
            },
            {
                "intent": f"{('ALTERNATIVE_' if pivot_mode else '')}FUNCTION_{target_function}_ALTERNATE_LANGUAGE", "variant": "ALTERNATIVE_FUNCTION" if pivot_mode else "FUNCTION_ALTERNATE",
                "query": alternate, "channel": "GOOGLE_NEWS_RSS", "backends": ["public-rss-search"],
                "language": alternate_language or primary_language, "target_desk": target_section,
                "candidate_event_theme": target_function,
                "current_process_context": current_process or None,
            },
        ]
        # Give each bounded semantic strategy a distinct relevant family when
        # the registry exposes one. This is retrieval fairness only; role and
        # claim validation still happen on the exact fetched artifact.
        strategy_routes = [*family_routes, *same_family_fallback_routes]
        if strategy_routes:
            for strategy_index, strategy in enumerate(strategies):
                selected_route = strategy_routes[strategy_index % len(strategy_routes)]
                strategy["source_route"] = selected_route
                strategy["source_family"] = route_source_family(selected_route)
                authority_meta = authority_route_metadata(selected_route, target_function, actor=actor_hint)
                strategy.update({
                    "authority_capability": authority_meta["authority_capability"],
                    "selected_authority_id": authority_meta["authority_id"],
                    "artifact_family": authority_meta["artifact_family"],
                    "authority_selection_reason": authority_meta["authority_selection_reason"],
                    "artifact_selection_reason": authority_meta["artifact_selection_reason"],
                })
                strategy["source_family_selection_reason"] = "NEED_SOURCE_FAMILY_POLICY" if strategy_index < len(family_order) else "UNTRIED_RELEVANT_FAMILY"
                strategy["expected_information_gain"] = "NEW_SOURCE_FAMILY" if strategy_index else "EXACT_AUTHORITY_ROUTE"
                # With one configured route, scoping the first two search
                # strategies produces the same physical request.  Keep the
                # first exact-route lookup, then preserve a genuinely broad
                # discovery pass.  Where multiple family routes exist, the
                # second route remains independently scoped.
                strategy["route_scoped"] = bool(selected_route and (strategy_index == 0 or len(strategy_routes) > 1))
                if strategy.get("route_scoped"):
                    selected_origin = _route_search_origin(selected_route)
                    selected_languages = set(selected_route.get("supported_languages") or [])
                    selected_language = next((lang for lang in (primary_language, alternate_language, "en") if lang and lang in selected_languages), primary_language)
                    selected_terms = language_terms.get(selected_language, base_terms)
                    strategy["query"] = " ".join(item for item in (f"site:{selected_origin}" if selected_origin else "", current_process, selected_terms, route_temporal) if item)
                elif strategy_index == 2:
                    strategy["target"] = selected_route.get("url") if selected_route else None
                    strategy["action_type"] = "FETCH_CONFIGURED_SOURCE" if selected_route else "SEARCH_DISCOVERY"
        else:
            for strategy in strategies:
                strategy.setdefault("source_family", route_source_family(strategy.get("source_route")))
                authority_meta = authority_route_metadata(strategy.get("source_route"), target_function, actor=actor_hint)
                strategy.update({
                    "authority_capability": authority_meta["authority_capability"],
                    "selected_authority_id": authority_meta["authority_id"],
                    "artifact_family": authority_meta["artifact_family"],
                    "authority_selection_reason": authority_meta["authority_selection_reason"],
                    "artifact_selection_reason": authority_meta["artifact_selection_reason"],
                })
        source_class_priorities = (
            ["AUDIT_INSTITUTION", "REGULATOR", "COURT_OR_PROSECUTION", "ELECTION_INTEGRITY", "PROCUREMENT_OVERSIGHT", "INDEPENDENT_ACCOUNTABILITY_REPORTING"]
            if target_function == "ACCOUNTABILITY" else
            ["MINISTRY", "PUBLIC_AGENCY", "TRANSPORT_OPERATOR", "MUNICIPALITY", "ELECTION_ADMINISTRATION", "EDUCATION_AUTHORITY", "HEALTH_AUTHORITY", "UTILITY", "PUBLIC_SERVICE_PORTAL"]
        )
        for strategy_index, strategy in enumerate(strategies):
            if branch_mode and pivot_branches:
                branch = pivot_branches[strategy_index % len(pivot_branches)]
                branch_language = str(strategy.get("language") or primary_language)
                branch_terms = branch["terms"].get(branch_language) or branch["terms"].get(primary_language) or branch["terms"]["en"]
                # Preserve the legacy semantic ladder when no current
                # process is available.  The class metadata still records a
                # diversified branch, while the original Arabic/French
                # function vocabulary remains available to callers/tests and
                # to ordinary initial discovery.  Contextual/pivot runs use
                # the compact branch query below.
                branch_contextual = bool(current_process or pivot_mode)
                # Keep class-branch queries compact enough for bounded public
                # indexes.  Concatenating the full semantic ladder and the
                # process headline can suppress otherwise useful results.
                # This is discovery context only; observed facts remain
                # derived exclusively from fetched pages.
                if branch_contextual:
                    branch_temporal = (f"active deadline {month}" if target_function == "SERVICE" else f"active {month}")
                    # Three branch tokens retain the class signal while keeping
                    # Google News/RSS and similar bounded indexes usable.
                    compact_branch_terms = " ".join(branch_terms.split()[:3])
                    branch_query = " ".join(item for item in (geography, current_process, compact_branch_terms, branch_temporal) if item)
                    if strategy_index == 0 and route_origin:
                        strategy["query"] = f"site:{route_origin} {branch_query}".strip()
                    elif strategy_index == 2:
                        strategy["query"] = " ".join(item for item in (current_process, compact_branch_terms, "current notices decisions") if item)
                    else:
                        strategy["query"] = branch_query
                    # If the primary search backend is unavailable, the existing
                    # RSS fallback should receive a short French/English query,
                    # not the Arabic branch text that often produces blank feeds.
                    rss_terms = branch["terms"].get("en") or branch["terms"].get("fr") or branch_terms
                    rss_compact_terms = " ".join(rss_terms.split()[:2])
                    rss_process = (
                        current_process
                        if len(current_process.split()) <= 4
                        else current_process.split()[0]
                    ) if current_process else ""
                    rss_temporal = "deadline September 2026" if target_function == "SERVICE" else "September 2026"
                    rss_query = " ".join(item for item in (geography, rss_process, rss_compact_terms, rss_temporal) if item)
                    strategy["fallback_query"] = rss_query
                    if strategy.get("channel") == "GOOGLE_NEWS_RSS":
                        strategy["query"] = rss_query
                strategy["target_source_class"] = branch["class"]
                strategy["source_class_branch"] = branch["class"]
                strategy["first_party_discovery_objective"] = "FIRST_PARTY_SELF_ACTION"
                strategy["institution_discovery_mode"] = "OPEN_DISCOVERY_THEN_OWNERSHIP_VALIDATION"
                strategy["source_class_branch_mode"] = branch_mode
                strategy["source_class_selection_reason"] = "CURRENT_PROCESS_CONTEXT" if current_process else "FUNCTION_DEFAULT_ORDER"
                strategy["source_class_memory_before"] = sorted(set(attempted_source_classes) | {
                    str(previous.get("target_source_class"))
                    for previous in strategies[:strategy_index]
                    if previous.get("target_source_class")
                })
                strategy["source_class_priorities"] = [branch["class"], *[item for item in source_class_priorities if item != branch["class"]]]
            else:
                strategy["source_class_priorities"] = source_class_priorities
        return strategies
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
    recovery_mode = (
        (recovery_need or {}).get("recovery_mode")
        or ("DISCOVER_NEW_EVENT_FOR_SEMANTIC_NEED" if recovery_need and not recovery_need.get("event_id") and recovery_need.get("target_editorial_function") else "CORROBORATE_EXISTING_EVENT")
    )
    recovery_intent = (
        "FIND_ALTERNATIVE_EVENT_FOR_SEMANTIC_NEED"
        if (recovery_need or {}).get("pivot_mode") == "FIND_ALTERNATIVE_EVENT_FOR_SEMANTIC_NEED"
        else "COMPLETE_CURRENT_EVENT_EVIDENCE"
        if recovery_mode == "CORROBORATE_EXISTING_EVENT"
        else "DISCOVER_NEW_EVENT_FOR_SEMANTIC_NEED"
    )
    return {
        "schema_version": 1,
        "action_id": _stable_id(
            "ACT", job["job_id"], job.get("round", 0), branch["branch_id"],
            action_type, recovery_need.get("need_id") if recovery_need else "",
            target or query,
        ),
        "job_id": job["job_id"],
        "branch_id": branch["branch_id"],
        "research_lane": job.get("research_lane") or ("HARD_BREADTH" if recovery_need and str(recovery_need.get("need_id") or "").startswith("BREADTH:") else "GENERAL_DISCOVERY"),
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
        "target_editorial_function": (recovery_need or {}).get("target_editorial_function") or (recovery_need or {}).get("event_acquisition_plan", {}).get("target_editorial_function"),
        "source_class_priorities": list(strategy.get("source_class_priorities") or []),
        "target_source_class": strategy.get("target_source_class"),
        "source_class_branch": strategy.get("source_class_branch"),
        "first_party_discovery_objective": strategy.get("first_party_discovery_objective"),
        "institution_discovery_mode": strategy.get("institution_discovery_mode"),
        "source_class_branch_mode": strategy.get("source_class_branch_mode"),
        "source_class_selection_reason": strategy.get("source_class_selection_reason"),
        "source_class_memory_before": list(strategy.get("source_class_memory_before") or []),
        "current_process_context": strategy.get("current_process_context"),
        "acceptable_story_roles": list((recovery_need or {}).get("event_acquisition_plan", {}).get("acceptable_story_roles", [])),
        "target": target,
        "discovery_only": bool(strategy.get("discovery_only")),
        "source_route": deepcopy(strategy.get("source_route")) if isinstance(strategy.get("source_route"), dict) else None,
        "source_family": strategy.get("source_family") or route_source_family(strategy.get("source_route")),
        "candidate_source_families": list((recovery_need or {}).get("candidate_source_families") or (recovery_need or {}).get("search_constraints", {}).get("candidate_source_families", [])),
        "candidate_authority_capabilities": list((recovery_need or {}).get("candidate_authority_capabilities") or (recovery_need or {}).get("search_constraints", {}).get("candidate_authority_capabilities", [])),
        "candidate_artifact_families": list((recovery_need or {}).get("candidate_artifact_families") or (recovery_need or {}).get("search_constraints", {}).get("candidate_artifact_families", [])),
        "selected_source_family": strategy.get("source_family") or route_source_family(strategy.get("source_route")),
        "authority_capability": strategy.get("authority_capability") or authority_route_metadata(strategy.get("source_route"), (recovery_need or {}).get("target_editorial_function")).get("authority_capability"),
        "selected_authority_id": strategy.get("selected_authority_id") or authority_route_metadata(strategy.get("source_route"), (recovery_need or {}).get("target_editorial_function")).get("authority_id"),
        "artifact_family": strategy.get("artifact_family") or authority_route_metadata(strategy.get("source_route"), (recovery_need or {}).get("target_editorial_function")).get("artifact_family"),
        "authority_selection_reason": strategy.get("authority_selection_reason"),
        "artifact_selection_reason": strategy.get("artifact_selection_reason"),
        "candidate_routes": [
            {"route_id": item.get("route_id"), "source_id": item.get("source_id"), "source_family": route_source_family(item), "url": item.get("url")}
            for item in ((recovery_need or {}).get("search_constraints", {}).get("configured_source_routes", []) or [])
            if isinstance(item, dict) and item.get("url")
        ],
        "selection_reason": strategy.get("source_family_selection_reason") or ("NEED_SOURCE_FAMILY_POLICY" if strategy.get("source_family") else "LEGACY_ROUTE_ORDER"),
        "families_already_attempted": list((recovery_need or {}).get("families_already_attempted") or []),
        "expected_information_gain": strategy.get("expected_information_gain") or ("NEW_SOURCE_FAMILY" if strategy.get("source_family") else "ROUTE_ARTIFACT"),
        "actual_information_gain": None,
        "route_scoped": bool(strategy.get("route_scoped")),
        "route_search_objective": strategy.get("route_search_objective"),
        "navigation_depth": int(strategy.get("navigation_depth", 0) or 0),
        "navigation_parent_url": strategy.get("navigation_parent_url"),
        "known_entities": list(job["lead"].get("event_entities", [])),
        "event_context": {
            "entities": list((recovery_need or {}).get("query_context", {}).get("entities", [])),
            "aliases": list((recovery_need or {}).get("query_context", {}).get("aliases", [])),
            "event_terms": list((recovery_need or {}).get("query_context", {}).get("event_terms", [])),
            "topic_terms": list((recovery_need or {}).get("topic_identifiers", [])),
            "geography": list((recovery_need or {}).get("query_context", {}).get("geography", [])),
            "research_date": (recovery_need or {}).get("query_context", {}).get("research_date"),
            "geography_policy": (recovery_need or {}).get("geography_policy") or (recovery_need or {}).get("event_acquisition_plan", {}).get("geography_scope"),
            "allowed_geographies": list((recovery_need or {}).get("allowed_geographies", [])),
            "scope_origin": (recovery_need or {}).get("scope_origin"),
            "scope_reason": (recovery_need or {}).get("scope_reason"),
            "current_process_context": strategy.get("current_process_context"),
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
        "pivot_mode": (recovery_need or {}).get("pivot_mode"),
        "blocked_event_memory": deepcopy((recovery_need or {}).get("blocked_event_memory") or []),
        "recovery_intent": recovery_intent,
        # Recovery mode is explicit: breadth/function needs without an
        # existing event discover a new root; candidate evidence needs
        # corroborate an existing event lead.
        "recovery_mode": recovery_mode,
        "originating_recovery_need_id": recovery_need.get("need_id") if recovery_need else None,
        "recovery_candidate_id": recovery_need.get("candidate_id") if recovery_need else None,
        "channel_fallback": deepcopy(strategy.get("fallback")) if strategy.get("fallback") else None,
        "channel_fallback_query": strategy.get("fallback_query"),
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
            or (
                item.get("pivot_mode") == "FIND_ALTERNATIVE_EVENT_FOR_SEMANTIC_NEED"
                and int(item.get("pivot_attempt_count", 0)) < 1
            )
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
    # ``query_fingerprint`` deliberately retains the strategy intent for
    # telemetry.  It is therefore not a physical-request identity: two
    # labels can otherwise dispatch the same query to the same backend.
    seen_requests: set[tuple[str, str, str, str]] = set()
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
            request_value = action.get("target") if action.get("target") else action.get("query")
            physical_request = (
                str(action["action_type"]),
                str(action.get("discovery_channel") or ""),
                str(action.get("search_language") or ""),
                " ".join(str(request_value or "").casefold().split()),
            )
            if physical_request in seen_requests:
                continue
            seen_requests.add(physical_request)
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
    first_wave_all = [item for item in all_actions if int(item.get("strategy_index", 0)) == 0]
    hard_lane_present = any(
        str(item.get("research_lane") or "").startswith("HARD")
        or str(item.get("recovery_need_id") or "").startswith("BREADTH:")
        for item in all_actions
    )
    # Preserve one existing round slot for ordinary desk discovery whenever
    # hard-breadth lanes are active.  This is a reservation inside the fixed
    # round cap, not an additional request budget; it prevents mandatory
    # semantic work from starving the newspaper's general discovery lanes.
    if hard_lane_present:
        general = sorted(
            (
                item for item in first_wave_all
                if item.get("research_lane") == "GENERAL_DISCOVERY"
                and not item.get("recovery_need_id")
            ),
            key=lambda item: (str(item.get("job_id") or ""), item.get("action_id", "")),
        )
        if general and len(selected) < cap:
            selected.append(general[0])
    for priority in ("P0_BLOCKING_EVIDENCE", "P1_BREADTH", "P1_DISTINCT_EVENT", "P2_CONTRADICTION"):
        candidate = next((item for item in sorted(first_wave, key=lambda value: (str(value.get("recovery_need_id") or value["job_id"]), value["action_id"])) if item["priority_class"] == priority), None)
        if candidate is not None and len(selected) < cap:
            selected.append(candidate)
    # Mandatory semantic breadth needs receive one additional family branch
    # when available.  This uses the existing round cap; it only prevents a
    # generic first-wave action from consuming every opportunity for a
    # second, relevant source family.
    semantic_first_wave = [
        item for item in first_wave
        if item.get("priority_class") == "P1_BREADTH"
        and str(item.get("target_editorial_function") or "").upper() in {"ACCOUNTABILITY", "SERVICE"}
    ]
    for branch in sorted(semantic_first_wave, key=lambda item: str(item.get("recovery_need_id") or item["action_id"])):
        if len(selected) >= cap:
            break
        if branch["action_id"] not in {item["action_id"] for item in selected}:
            selected.append(branch)
    semantic_need_ids = {
        item.get("recovery_need_id") for item in selected
        if item.get("priority_class") == "P1_BREADTH"
        and str(item.get("target_editorial_function") or "").upper() in {"ACCOUNTABILITY", "SERVICE"}
    }
    for need_id in sorted(item for item in semantic_need_ids if item):
        if len(selected) >= cap:
            break
        branch = next((item for item in eligible_actions if item.get("recovery_need_id") == need_id and int(item.get("strategy_index", 0)) == 1), None)
        if branch is not None:
            selected.append(branch)
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
        "budget_allocation": {
            "round_cap": cap,
            "hard_breadth_reserved_slots": int(bool(hard_lane_present and any(item.get("research_lane") == "GENERAL_DISCOVERY" and not item.get("recovery_need_id") for item in first_wave_all))),
            "budget_increased": False,
        },
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
                return [{"result_type": "DEAD_END", "reason": f"RSS_HTTP_{response.status}", "diagnostic": "BACKEND_UNAVAILABLE", "discovery_channel": self.adapter_id, "backend_counts": {"raw_results": 0, "parsed_results": 0, "filtered_results": 0}}]
            try:
                feed_root = ElementTree.fromstring(response.body)
                feed_nodes = list(feed_root.findall(".//item")) + list(feed_root.findall(".//{http://www.w3.org/2005/Atom}entry"))
                raw_result_count = len(feed_nodes)
            except ElementTree.ParseError:
                raw_result_count = 0
            candidates = discover_rss(
                response.body, provider_id=self.adapter_id, endpoint=response.url
            )[: self.maximum_results]
        except (DiscoveryError, OSError, TimeoutError) as exc:
            return [{"result_type": "DEAD_END", "reason": getattr(exc, "code", type(exc).__name__), "diagnostic": "BACKEND_UNAVAILABLE", "discovery_channel": self.adapter_id, "backend_counts": {"raw_results": 0, "parsed_results": 0, "filtered_results": 0}}]
        timestamp = datetime.now(timezone.utc).isoformat()
        if not candidates:
            return [{"result_type": "DEAD_END", "reason": "RSS_NO_MATCHES", "diagnostic": "BACKEND_EMPTY" if raw_result_count == 0 else "RSS_ENTRY_PRESENT_PARSER_DROPPED", "discovery_channel": self.adapter_id, "backend_counts": {"raw_results": raw_result_count, "parsed_results": 0, "filtered_results": raw_result_count}}]
        return [
            {
                "result_type": "LEAD",
                "canonical_url": normalize_url(item["discovered_url"]),
                "title": item["title"],
                "source_class": "unknown",
                "discovered_at": timestamp,
                "discovery_channel": self.adapter_id,
                "backend_counts": {"raw_results": raw_result_count, "parsed_results": len(candidates), "filtered_results": max(0, raw_result_count - len(candidates))},
                "discovery_endpoint": response.url,
                "verification_provenance": "DISCOVERY_ONLY_RSS",
                "search_result": {
                    "query": str(action.get("query") or ""), "backend": self.adapter_id,
                    "result_url": normalize_url(item["discovered_url"]), "title": item["title"],
                    "snippet": item.get("discovery_description"), "published_at": None, "engine": "rss",
                    "rank": index, "discovered_at": timestamp,
                },
                # Feed publisher hints are explicitly discovery-only.  The
                # wrapper URL remains the observed lead and must still pass
                # the normal exact-page/evidence pipeline.
                **({"publisher_hint_url": item["publisher_hint_url"]} if item.get("publisher_hint_url") else {}),
                **({"publisher_hint_name": item["publisher_hint_name"]} if item.get("publisher_hint_name") else {}),
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
                "result_type": "DEAD_END", "reason": "SEARCH_BACKEND_UNAVAILABLE", "diagnostic": "BACKEND_UNAVAILABLE",
                "detail": getattr(exc, "code", type(exc).__name__), "discovery_channel": self.adapter_id,
                "backend_counts": {"raw_results": 0, "parsed_results": 0, "filtered_results": 0},
            }]
        results = payload.get("results") if isinstance(payload, dict) else None
        if not isinstance(results, list):
            return [{"result_type": "DEAD_END", "reason": "SEARXNG_RESPONSE_INVALID", "diagnostic": "BACKEND_SCHEMA_UNEXPECTED", "discovery_channel": self.adapter_id, "backend_counts": {"raw_results": 0, "parsed_results": 0, "filtered_results": 0}}]
        normalized = []
        missing_url_results = 0
        invalid_url_results = 0
        timestamp = datetime.now(timezone.utc).isoformat()
        for rank, item in enumerate(results[: self.maximum_results], start=1):
            if not isinstance(item, dict) or not isinstance(item.get("url"), str) or not item.get("url", "").strip():
                missing_url_results += 1
                continue
            url = item["url"].strip()
            if not url.startswith(("https://", "http://")):
                invalid_url_results += 1
                continue
            normalized.append({
                "result_type": "LEAD", "canonical_url": normalize_url(url),
                "title": str(item.get("title") or "Untitled search result"),
                "claim": str(item.get("content") or item.get("title") or ""),
                "published_at": item.get("publishedDate") or item.get("published_at"),
                "discovered_at": timestamp, "source_class": "unknown",
                "discovery_channel": self.adapter_id,
                "verification_provenance": "DISCOVERY_ONLY_SEARXNG",
                "search_result": {
                    "query": str(action.get("query") or ""), "backend": self.adapter_id,
                    "result_url": normalize_url(url), "title": str(item.get("title") or ""),
                    "snippet": str(item.get("content") or ""), "engine": item.get("engine"),
                    "rank": rank, "discovered_at": timestamp,
                    "language": item.get("language") or action.get("search_language"),
                },
                "language": item.get("language") or action.get("search_language"),
            })
        backend_counts = {"raw_results": len(results), "parsed_results": len(normalized), "filtered_results": missing_url_results + invalid_url_results}
        for item in normalized:
            item["backend_counts"] = backend_counts
        if normalized:
            return normalized
        return [{
            "result_type": "DEAD_END",
            "reason": "SEARXNG_NO_MATCHES",
            "diagnostic": (
                "BACKEND_EMPTY" if not results else
                "RESULT_URL_MISSING" if missing_url_results and not invalid_url_results else
                "RESULT_URL_INVALID" if invalid_url_results and not missing_url_results else
                "RESULT_PARSE_EMPTY"
            ),
            "discovery_channel": self.adapter_id,
            "backend_counts": {"raw_results": len(results), "parsed_results": len(normalized), "filtered_results": missing_url_results + invalid_url_results},
        }]


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
        fixture_state = "DISCOVERY_ONLY_INDEX" if action.get("discovery_only") else "VALIDATED_EVIDENCE"
        return "LEAD" if action.get("discovery_only") else "POTENTIAL_EVIDENCE", canonical, {
            "state": fixture_state,
            "progression": ["DISCOVERED", "FETCHED", "EXTRACTED", "SOURCE_IDENTIFIED", "ORIGIN_CLASSIFIED", "ROLE_CLASSIFIED", "RELEVANCE_CONFIRMED", "POTENTIAL_EVIDENCE", "VALIDATED_EVIDENCE"],
            "reason": "CANONICAL_LISTING_DISCOVERY_ONLY_EXACT_PAGE_REQUIRED" if action.get("discovery_only") else "FIXTURE_EXACT_PAGE_VALIDATION",
            "canonical_url": canonical,
            "origin": urlsplit(canonical).hostname if canonical else None,
            "source_class": source_class,
            "relation": "SUPPORTS",
            "directness": "DIRECT_STATEMENT",
        }
    # Role cannot be truthfully assigned from a configured-origin label alone.
    # For an exact page, first extract the bounded event description, then ask
    # whether its resolved publisher is an actor or issuer for the *limited*
    # claim.  The role resolver is deliberately before validation, since the
    # latter correctly refuses unknown sources.
    role_resolution = None
    event_skeleton = None
    if action.get("action_type") in FETCH_ACTIONS:
        event_skeleton = extract_event_skeleton(raw, action)
        role_resolution = resolve_exact_source_role(raw, action, event_skeleton)
        role_resolution["original_source_resolution"] = build_original_source_resolution(
            raw, action, skeleton=event_skeleton,
        )
        role_resolution["field_provenance"] = {
            "publisher": "PAGE_STRUCTURED_METADATA" if (isinstance(raw.get("article_metadata"), dict) and ((raw.get("article_metadata") or {}).get("publisher") or {}).get("name")) else ("PAGE_TEXT_INFERRED" if raw.get("publisher") else "OTHER_DERIVED"),
            "event_actor": ((event_skeleton.get("field_provenance") or {}).get("actor") if isinstance(event_skeleton, dict) else None) or "OTHER_DERIVED",
            "document_type": "PAGE_TEXT_INFERRED",
            "publisher_event_relation": "OBSERVED_PAGE_FACTS_ONLY",
            "evidence_role": "OBSERVED_PAGE_FACTS_ONLY",
        }
        resolved_class = str(role_resolution.get("source_class") or "unknown").casefold()
        supplied_class = str(raw.get("source_class") or raw.get("source_type") or "unknown").casefold()
        actor_first_context = bool(
            action.get("actor_first_search") or action.get("actor_first_fetch")
            or "ACTOR_FIRST" in str(action.get("query_intent") or "")
        )
        if resolved_class in {"primary", "independent"}:
            raw["source_class"] = resolved_class
        elif supplied_class in {"primary", "paper"} or (actor_first_context and supplied_class in {"official", "independent"}):
            # A configured/search-labelled source class cannot override an
            # unresolved observed publisher/event relationship.
            raw["source_class"] = "unknown"
        raw["source_role_resolution"] = role_resolution
    validation = validate_exact_page(raw, action) if action.get("action_type") in FETCH_ACTIONS else None
    if validation:
        if role_resolution:
            validation["source_role_resolution"] = deepcopy(role_resolution)
        # A concrete skeleton is needed to connect a recovered exact page back
        # to an originating lead as well as for distinct-event work.  It is
        # identity metadata, not an evidence upgrade.
        if (event_skeleton or {}).get("state") == "CONCRETE_EVENT":
            validation["event_skeleton"] = event_skeleton
        state = validation["state"]
        if state == "VALIDATED_EVIDENCE":
            if action.get("discovery_only"):
                validation["state"] = "DISCOVERY_ONLY_INDEX"
                validation["reason"] = "CANONICAL_LISTING_DISCOVERY_ONLY_EXACT_PAGE_REQUIRED"
                return "LEAD", canonical, validation
            return ("CONTRADICTION" if validation.get("relation") == "CONTRADICTS" else "POTENTIAL_EVIDENCE"), canonical, validation
        if state == "CONTEXT_ONLY":
            return "CONTEXT", canonical, validation
        if state == "SOURCE_UNKNOWN":
            skeleton = validation.get("event_skeleton", {})
            if skeleton.get("state") == "CONCRETE_EVENT":
                validation["event_state"] = "EVENT_LEAD_DISCOVERY_ONLY"
                validation["reason"] = "NEW_EVENT_LEAD_SOURCE_ROLE_UNVERIFIED"
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
        metadata = raw.get("article_metadata") if isinstance(raw.get("article_metadata"), dict) else {}
        publisher = (metadata.get("publisher") or {}) if isinstance(metadata.get("publisher"), dict) else {}
        if str(raw.get("title_state") or metadata.get("title_state") or "") == "TITLE_UNRESOLVED":
            return "TITLE_UNRESOLVED"
        date_info = raw.get("publication_date") if isinstance(raw.get("publication_date"), dict) else metadata.get("publication_date") or {}
        if not date_info.get("raw"):
            return "NO_PUBLICATION_DATE"
        if publisher.get("state") == "PUBLISHER_RESOLVED_ARTICLE_ROLE_PENDING":
            return "PUBLISHER_RESOLVED_ARTICLE_ROLE_PENDING"
        if metadata.get("metadata_extraction_status") == "ARTICLE_METADATA_INSUFFICIENT":
            return "ARTICLE_METADATA_INSUFFICIENT"
        return "PUBLISHER_UNRESOLVED"
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
    title = _first_present(raw.get("title"), raw.get("claim"), raw.get("reason"))
    title_state = str(raw.get("title_state") or (raw.get("article_metadata") or {}).get("title_state") or ("TITLE_RESOLVED" if title else "TITLE_UNRESOLVED"))
    source_class = str(raw.get("source_class") or raw.get("source_type") or "unknown").lower()
    page_type = classify_page_type(raw, action=action)
    known_profile = action.get("source_route") if isinstance(action.get("source_route"), dict) else None
    institution_identity = resolve_institution_identity(raw, known_profile=known_profile)
    url_safety = assess_source_url(canonical or "") if canonical else {"state": "URL_UNSAFE", "reason": "MISSING_URL"}
    source_trust_state = (
        "URL_UNSAFE" if url_safety.get("state") == "URL_UNSAFE" else
        "URL_SAFE_CANONICAL_INSTITUTION" if institution_identity.get("state") == "INSTITUTION_IDENTITY_RESOLVED" else
        "URL_SAFE_INSTITUTION_CANDIDATE"
    )
    route = action.get("source_route") if isinstance(action.get("source_route"), dict) else None
    extraction_status = str(raw.get("fetch_status") or "NOT_RETRIEVED").upper()
    route_health = None
    if route:
        is_route_search = action.get("action_type") in SEARCH_ACTIONS and action.get("route_scoped")
        route_health = {
            "route_id": route.get("route_id"),
            "route_url": route.get("url"),
            "route_type_expected": route.get("route_type"),
            "page_type_observed": page_type,
            "request_outcome": "ROUTE_SCOPED_SEARCHED" if is_route_search else "FETCHED" if extraction_status in {"FETCHED", "RETRIEVED"} else str(raw.get("reason") or extraction_status),
            "status": str(route.get("route_status") or "UNKNOWN") if is_route_search else "VERIFIED_WORKING" if extraction_status in {"FETCHED", "RETRIEVED"} else "TRANSIENT_FAILURE" if raw.get("reason") else str(route.get("route_status") or "UNKNOWN"),
            "semantic_capabilities": list(route.get("semantic_capabilities") or []),
            "navigation_depth": route.get("navigation_depth"),
        }
    navigation_type = classify_navigation_type(raw, action=action)
    expected_artifact_family = action.get("artifact_family") or action.get("expected_artifact_family")
    event_context = action.get("event_context") if isinstance(action.get("event_context"), dict) else {}
    anchors = [
        *(event_context.get("entities") or []), *(event_context.get("aliases") or []),
        *(event_context.get("event_terms") or []), action.get("actor"), action.get("document_type"),
    ]
    listing_links = extract_listing_child_links(
        raw,
        semantic_target=action.get("target_editorial_function") or action.get("candidate_event_theme"),
        edition_date=event_context.get("research_date"),
        expected_artifact_family=expected_artifact_family,
        anchors=anchors,
    ) if navigation_type in {"LISTING_PAGE", "NEWS_INDEX", "PRESS_RELEASE_INDEX", "DOCUMENT_INDEX", "REPORT_INDEX", "PUBLICATION_INDEX", "PROCUREMENT_LISTING", "SEARCH_RESULTS_PAGE", "CATEGORY_PAGE", "ARCHIVE_INDEX", "DATASET_INDEX", "OTHER_NAVIGATION", "PORTAL_HOME"} else []
    service_candidates = [
        {key: item.get(key) for key in ("label", "url", "candidate_type", "possible_document_type", "target_domain", "same_domain", "score", "reasons")}
        for item in listing_links
        if (action.get("target_editorial_function") or "").upper() == "SERVICE"
    ]
    source_id = _stable_id("SRC", canonical or action["action_id"], title or "TITLE_UNRESOLVED")
    temporal_relevance = evaluate_temporal_relevance(raw, str(action.get("event_context", {}).get("research_date") or ""), exact_text=str(raw.get("text") or raw.get("extracted_text") or "")) if raw.get("text") or raw.get("extracted_text") else None
    if temporal_relevance is not None and isinstance(action.get("listing_temporal_context"), dict):
        # Preserve the listing -> detail temporal chain for audit.  The
        # listing's dates never independently grant currentness to the child.
        temporal_relevance["listing_temporal_context"] = deepcopy(action["listing_temporal_context"])
        temporal_relevance["temporal_provenance_chain"] = [
            {"stage": "LISTING_PAGE", "temporal": deepcopy(action["listing_temporal_context"])},
            {"stage": "EXACT_DETAIL_OR_ARTIFACT", "temporal": {key: temporal_relevance.get(key) for key in ("publication_time", "event_time", "effective_start", "effective_end", "deadline", "active_on_edition_date")}},
        ]
    fixture_verified = raw.get("verification_provenance") == "FIXTURE_VERIFIED_EXACT_PAGE"
    verification_status = (
        "VALIDATED_EVIDENCE"
        if validation and validation.get("state") == "VALIDATED_EVIDENCE"
        else "EXTRACTED_NOT_VERIFIED"
    )
    origin = urlsplit(canonical).hostname if canonical else None
    source_profile = _lead_source_profile(canonical, str(title or ""), str((raw.get("search_result") or {}).get("snippet") or ""))
    # Identity routing is additive and intentionally does not grant an
    # evidence role.  The exact page still must pass the role/evidence gate.
    source_profile.update({
        "institution_identity_state": institution_identity.get("state"),
        "institution_profile_type": institution_identity.get("profile_type"),
        "canonical_institution_domain": institution_identity.get("canonical_institution_domain"),
        "institution_relationship": institution_identity.get("relationship"),
    })
    provenance_links = extract_outbound_link_candidates(
        raw,
        semantic_target=action.get("target_editorial_function") or action.get("candidate_event_theme"),
        institution_domain=institution_identity.get("canonical_institution_domain"),
    )
    attribution = extract_actor_attributions(raw)
    origin_detail = detect_official_portal_republication({
        **raw,
        "source_route": action.get("source_route") if isinstance(action.get("source_route"), dict) else None,
    })
    # Acquisition-only provenance resolver. It derives a bounded original
    # source plan from exact page facts; it never upgrades the observation's
    # role and never treats action/query context as an observed claim.
    event_skeleton = (validation or {}).get("event_skeleton") if isinstance(validation, dict) else None
    original_source_resolution = build_original_source_resolution(
        {**raw, **origin_detail}, action,
        skeleton=event_skeleton if isinstance(event_skeleton, dict) else None,
    )
    if action.get("action_type") in FETCH_ACTIONS and not action.get("discovery_only") and not action.get("provenance_followup"):
        if not provenance_links:
            provenance_diagnostic = "OFFICIAL_LINK_NOT_EXTRACTED"
        elif not any(item.get("type") in {"CITED_PRIMARY_SOURCE", "OFFICIAL_SERVICE_DESTINATION", "OFFICIAL_DOCUMENT", "INSTITUTIONAL_DETAIL"} and item.get("reason") != "OFFICIAL_HOMEPAGE_NAVIGATION_ONLY" for item in provenance_links):
            provenance_diagnostic = "OFFICIAL_LINK_REJECTED"
        elif not attribution.get("actors"):
            provenance_diagnostic = "ACTOR_UNRESOLVED"
        else:
            provenance_diagnostic = None
    else:
        provenance_diagnostic = None
    metadata_publisher = ((raw.get("article_metadata") or {}).get("publisher") or {}) if isinstance(raw.get("article_metadata"), dict) else {}
    if metadata_publisher.get("state") == "PUBLISHER_RESOLVED_ARTICLE_ROLE_PENDING":
        source_profile.update({
            "identity_state": "PUBLISHER_RESOLVED_ARTICLE_ROLE_PENDING",
            "publisher_name": metadata_publisher.get("name"),
            "publisher_signal": metadata_publisher.get("source"),
        })
    if action.get("action_type") in FETCH_ACTIONS and canonical and raw.get("publisher"):
        source_profile["identity_state"] = "SOURCE_IDENTIFIED"
    metadata_publisher_name = (
        ((raw.get("article_metadata") or {}).get("publisher") or {}).get("name")
        if isinstance(raw.get("article_metadata"), dict) else None
    )
    page_publisher = origin_detail.get("portal_publisher") or metadata_publisher_name or raw.get("publisher")
    post_fetch_qualification = qualify_fetched_artifact(
        raw,
        page_type=page_type,
        validation=validation,
        role_resolution=(validation or {}).get("source_role_resolution") if isinstance(validation, dict) else None,
        temporal=temporal_relevance,
        origin_detail=origin_detail,
        event_skeleton=(validation or {}).get("event_skeleton") if isinstance(validation, dict) else None,
    )
    support = post_fetch_qualification.get("claim_support") if isinstance(post_fetch_qualification.get("claim_support"), dict) else {}
    role_detail = (validation or {}).get("source_role_resolution") if isinstance(validation, dict) and isinstance((validation or {}).get("source_role_resolution"), dict) else {}
    support_observation = None
    if support.get("locator") and support.get("support_type") in {"DIRECT_SUPPORT", "PARTIAL_SUPPORT", "CONTEXT_ONLY", "CONTRADICTS"}:
        observed_role = role_detail.get("evidence_role")
        if observed_role in {None, "UNRESOLVED"}:
            observed_role = "REPUBLICATION" if role_detail.get("article_origin_state") == "OFFICIAL_PORTAL_REPUBLICATION" else "SECONDARY"
        support_observation = {
            "state": "OBSERVATION_CREATED",
            "claim_support": deepcopy(support),
            "role": observed_role,
            "publisher": post_fetch_qualification.get("publisher"),
            "issuer": post_fetch_qualification.get("issuer"),
            "origin": post_fetch_qualification.get("origin"),
            "original_artifact_state": origin_detail.get("original_artifact_state"),
            "lineage_edges": deepcopy(origin_detail.get("provenance_edges") or []),
            "primary_requirement_satisfied": observed_role == "PRIMARY",
            "requirement_state": "MET" if observed_role == "PRIMARY" else "NOT_MET",
            "observation_id": None,
        }
    observation_id = _stable_id("OBS", action["action_id"], canonical or title or "TITLE_UNRESOLVED", result_class)
    if support_observation:
        support_observation["observation_id"] = observation_id
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
        "title_state": title_state,
        "title_source": raw.get("title_source") or (raw.get("article_metadata") or {}).get("title_source"),
        "published_at": raw.get("published_at") or raw.get("publication_date"),
        "observed_at": raw.get("retrieved_at") or raw.get("discovered_at"),
        # A search result has a URL but has not retrieved that URL.  This is
        # intentionally distinct from a hash-bound exact-page fetch.
        "extraction_status": raw.get("fetch_status") or "NOT_RETRIEVED",
        "discovery_reason": raw.get("reason"),
        "discovery_diagnostic": raw.get("diagnostic"),
        "discovery_detail": raw.get("detail"),
        "content_hash": raw.get("content_hash"),
        "extracted_text": raw.get("text") or raw.get("extracted_text") or raw.get("content"),
        "source_class": str((validation or {}).get("source_class") or source_class).lower(),
        "page_type": page_type,
        "institution_identity": institution_identity,
        "url_safety": url_safety,
        "source_trust_state": source_trust_state,
        "route_health": route_health,
        "route_scoped": bool(action.get("route_scoped")),
        "route_search_objective": action.get("route_search_objective"),
        "redirect_provenance": deepcopy(raw.get("transport")) if isinstance(raw.get("transport"), dict) else None,
        "links": deepcopy(raw.get("links") or []),
        "outbound_link_candidates": provenance_links,
        "official_link_candidates": [item for item in provenance_links if item.get("type") in {"CITED_PRIMARY_SOURCE", "OFFICIAL_SERVICE_DESTINATION", "OFFICIAL_DOCUMENT", "INSTITUTIONAL_DETAIL"}],
        "citation_attributions": attribution.get("attribution_phrases", []),
        "event_actor_candidates": attribution.get("actors", []),
        "document_identifiers": attribution.get("document_identifiers", []),
        "origin_detail": origin_detail,
        "original_source_resolution": original_source_resolution,
        "page_publisher": page_publisher,
        "content_origin": origin_detail.get("content_origin"),
        "stated_issuing_authority": origin_detail.get("issuing_institution"),
        "document_references": deepcopy(origin_detail.get("document_references") or []),
        "original_artifact_state": origin_detail.get("original_artifact_state"),
        "provenance_edges": [
            *deepcopy(origin_detail.get("provenance_edges") or []),
            *deepcopy(original_source_resolution.get("provenance_edges") or []),
        ],
        "provenance_recovery_reason": provenance_diagnostic,
        "resolution_failure_category": resolution_failure_for_observation({
            "original_source_resolution": original_source_resolution,
            "validation_state": (validation or {}).get("state", "DISCOVERED"),
            "validation_reason": (validation or {}).get("reason"),
            "content_origin": origin_detail.get("content_origin"),
            "original_artifact_state": origin_detail.get("original_artifact_state"),
        }),
        "listing_links": listing_links,
        "navigation_url": canonical,
        "navigation_type": navigation_type,
        "expected_artifact_family": expected_artifact_family,
        "links_discovered": len(raw.get("links") or []),
        "links_relevant": len(listing_links),
        "artifact_candidates": [
            {key: item.get(key) for key in ("url", "candidate_class", "possible_document_type", "possible_date", "current_window_signal", "score", "reasons")}
            for item in listing_links if item.get("candidate_class") in {"EXACT_ARTIFACT_MATCH", "STRONG_ARTIFACT_CANDIDATE"}
        ],
        "selected_target": None,
        "selection_reason": None,
        "followup_scheduled": False,
        "followup_result": None,
        "exact_artifact_reached": page_type not in NAVIGATION_PAGE_TYPES,
        "service_candidates_found": len(service_candidates),
        "service_target_candidates": service_candidates,
        "service_relevant_candidates": sum(item.get("candidate_type") not in {"GENERIC_CATEGORY", "LANGUAGE_VARIANT", "PAGINATION"} for item in service_candidates),
        "service_selected_target": None,
        "service_followup_result": None,
        "exact_service_target_reached": bool((action.get("target_editorial_function") or "").upper() == "SERVICE" and int(action.get("navigation_depth", 0) or 0) >= 1 and page_type not in NAVIGATION_PAGE_TYPES),
        "listing_resolution_state": (
            "CHILD_LINKS_AVAILABLE" if listing_links else "LISTING_NO_DETAIL_SELECTED"
        ) if navigation_type in NAVIGATION_PAGE_TYPES or page_type == "LISTING_PAGE" else None,
        "source_resolution_state": ((raw.get("article_metadata") or {}).get("publisher") or {}).get("state") if isinstance((raw.get("article_metadata") or {}).get("publisher"), dict) else None,
        "structured_fields": deepcopy(raw.get("structured_fields")) if isinstance(raw.get("structured_fields"), dict) else None,
        "discovery_method": action["action_type"],
        "discovery_channel": str(raw.get("discovery_channel") or action.get("discovery_channel") or action["action_type"]),
        "backend_counts": deepcopy(raw.get("backend_counts")) if isinstance(raw.get("backend_counts"), dict) else None,
        # RSS publisher hints describe the feed's stated outlet, not the
        # wrapper page that was observed.  Keep them namespaced as discovery
        # metadata so they cannot satisfy source identity or evidence gates.
        "publisher_hint_url": raw.get("publisher_hint_url"),
        "publisher_hint_name": raw.get("publisher_hint_name"),
        "navigation_depth": int(action.get("navigation_depth", 0) or 0),
        "navigation_parent_url": action.get("navigation_parent_url"),
        "navigation_failure_reason": "DETAIL_FETCH_FAILED" if int(action.get("navigation_depth", 0) or 0) == 2 and result_class == "DEAD_END" else None,
        # Related entities are observed-page facts only.  Search targets and
        # recovery entities remain in provenance/search context and must never
        # leak into the canonical observation.
        "related_entities": list(raw.get("related_entities") or []),
        "related_event": raw.get("event_id"),
        "claim": str(raw.get("claim") or title or ""),
        "claim_candidates": list(raw.get("claim_candidates") or []),
        "contradiction_candidates": list(raw.get("contradiction_candidates") or []),
        "relevance_status": "REJECTED" if result_class in {"IRRELEVANT", "DUPLICATE", "DEAD_END"} else "RETAINED",
        "verification_status": verification_status,
        "validation_state": (validation or {}).get("state", "DISCOVERED"),
        "validation_progression": (validation or {}).get("progression", ["DISCOVERED"]),
        "validation_reason": (validation or {}).get("reason"),
        "event_skeleton": deepcopy((validation or {}).get("event_skeleton")) if isinstance((validation or {}).get("event_skeleton"), dict) else None,
        "temporal_relevance": deepcopy(temporal_relevance),
        "event_state": (validation or {}).get("event_state") or ((validation or {}).get("event_skeleton") or {}).get("state"),
        "event_unresolved_reason": (
            "NO_CONCRETE_OPERATIONAL_CHANGE" if int(action.get("navigation_depth", 0) or 0) == 2 and not isinstance((validation or {}).get("event_skeleton"), dict)
            else None
        ),
        "article_metadata": deepcopy(raw.get("article_metadata")) if isinstance(raw.get("article_metadata"), dict) else None,
        "source_role_resolution": deepcopy((validation or {}).get("source_role_resolution") or raw.get("source_role_resolution")) if isinstance((validation or {}).get("source_role_resolution") or raw.get("source_role_resolution"), dict) else None,
        "evidence_relation": (validation or {}).get("relation"),
        "directness": (validation or {}).get("directness"),
        "provenance": {
            "action_id": action["action_id"],
            "originating_event_lead_id": action.get("originating_event_lead_id"),
            "originating_breadth_need_id": action.get("originating_breadth_need_id"),
            "originating_recovery_need_id": action.get("originating_recovery_need_id") or action.get("recovery_need_id"),
            "recovery_mode": action.get("recovery_mode"),
            "query_fingerprint": action.get("query_fingerprint"),
            "excluded_origins": list(action.get("excluded_origins") or []),
            "target_evidence_role": action.get("provenance_requirements", {}).get("required_role"),
            "expected_result_type": action["expected_result_type"],
            "fixture_verification": fixture_verified,
            "canonical_url": canonical,
            "final_url": raw.get("final_url") or raw.get("canonical_url") or raw.get("url"),
            "page_title": raw.get("title"),
            "content_hash": raw.get("content_hash"),
            "language": raw.get("language"),
            "discovery_is_not_publication_evidence": True,
            "originating_observation_id": action.get("originating_observation_id"),
            "outbound_link_type": action.get("outbound_link_type"),
            "actor_first": bool(action.get("actor_first_search") or action.get("actor_first_fetch")),
            "route_id": route.get("route_id") if route else None,
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
        "post_fetch_qualification": post_fetch_qualification,
        "claim_support": deepcopy(post_fetch_qualification.get("claim_support")),
        "support_observation": support_observation,
    }


def _publisher_family(observation: dict) -> str | None:
    profile = observation.get("publisher_profile") if isinstance(observation.get("publisher_profile"), dict) else {}
    return _registrable_domain(str(profile.get("canonical_domain") or observation.get("origin") or ""))


def build_event_bundles(
    observations: list[dict], event_leads: list[dict], source_records: list[dict], actions: list[dict],
) -> tuple[list[dict], list[dict]]:
    """Attach exact observations to run-scoped provisional events.

    This is evidence bookkeeping, not a source-evidence shortcut: discovery
    observations can start an event but only validated exact pages add roles.
    """
    bundles: list[dict] = []
    aliases: dict[str, str] = {}
    sources = {item.get("id"): item for item in source_records if isinstance(item, dict) and item.get("id")}
    actions_by_need = {str(item.get("recovery_need_id") or ""): item for item in actions if isinstance(item, dict)}
    actions_by_id = {str(item.get("action_id")): item for item in actions if isinstance(item, dict) and item.get("action_id")}

    def by_id(value: object) -> dict | None:
        canonical = aliases.get(str(value or ""), str(value or ""))
        return next((item for item in bundles if item["event_lead_id"] == canonical), None)

    def add_lead(lead: dict) -> dict:
        skeleton = lead.get("event_skeleton") if isinstance(lead.get("event_skeleton"), dict) else {}
        lead_id = str(lead["event_lead_id"])
        semantic_mode = str(lead.get("recovery_mode") or "") == "DISCOVER_NEW_EVENT_FOR_SEMANTIC_NEED" or bool(lead.get("target_editorial_function")) and str(lead.get("recovery_need_id") or "").startswith("BREADTH:")
        for bundle in bundles:
            match = match_event_skeletons(bundle["event_skeleton"], skeleton)
            if match["state"] == "SAME_EVENT_HIGH_CONFIDENCE":
                aliases[lead_id] = bundle["event_lead_id"]
                bundle["merged_event_lead_ids"].append(lead_id)
                return bundle
        bundle = {
            "schema_version": 1, "event_lead_id": lead_id, "merged_event_lead_ids": [lead_id],
            "state": "EVENT_LEAD_DISCOVERY_ONLY", "event_lead_state": "NEW_RECOVERY_EVENT_LEAD" if semantic_mode else "EVENT_LEAD_DISCOVERY_ONLY",
            "event_fingerprint": skeleton.get("event_fingerprint"),
            "event_skeleton": deepcopy(skeleton), "recovery_need_id": lead.get("recovery_need_id"),
            "desk": lead.get("desk"), "observations": [], "support_observations": [], "sources": [], "source_roles": [],
            "publisher_families": [], "evidence_ids": [], "claims": [], "contradictions": [],
            "unresolved_origin_issues": [], "matches": [], "candidate_discovery": None,
        "provenance_edges": [], "attempted_source_routes": [], "blocked_event_memory": None,
            "recovery_mode": lead.get("recovery_mode"), "target_editorial_function": lead.get("target_editorial_function"),
            "new_recovery_event": semantic_mode,
        }
        bundles.append(bundle)
        return bundle

    for lead in event_leads:
        if isinstance(lead, dict) and lead.get("event_lead_id") and isinstance(lead.get("event_skeleton"), dict):
            add_lead(lead)

    for observation in observations:
        skeleton = observation.get("event_skeleton") if isinstance(observation.get("event_skeleton"), dict) else {}
        if skeleton.get("state") != "CONCRETE_EVENT":
            continue
        provenance = observation.get("provenance") if isinstance(observation.get("provenance"), dict) else {}
        action = actions_by_id.get(str(provenance.get("action_id") or ""), {})
        bundle = by_id(provenance.get("originating_event_lead_id") or observation.get("event_lead_id"))
        match = None
        if bundle is None:
            high = next(((item, match_event_skeletons(item["event_skeleton"], skeleton)) for item in bundles
                         if match_event_skeletons(item["event_skeleton"], skeleton)["state"] == "SAME_EVENT_HIGH_CONFIDENCE"), None)
            if high:
                bundle, match = high
        else:
            match = match_event_skeletons(bundle["event_skeleton"], skeleton)
        if bundle is None:
            # Mode B has no pre-existing event lead by design.  Once an exact
            # artifact yields a concrete event, create a need-scoped root
            # unless the event is plausibly the same as an existing cluster.
            mode = str(provenance.get("recovery_mode") or action.get("recovery_mode") or "")
            if mode != "DISCOVER_NEW_EVENT_FOR_SEMANTIC_NEED":
                continue
            plausible = next((item for item in bundles if match_event_skeletons(item["event_skeleton"], skeleton)["state"] in {"SAME_EVENT_PLAUSIBLE", "EVENT_MATCH_UNRESOLVED"}), None)
            if plausible:
                plausible_match = match_event_skeletons(plausible["event_skeleton"], skeleton)
                plausible["matches"].append({"observation_id": observation.get("observation_id"), **plausible_match})
                continue
            need_id = provenance.get("originating_recovery_need_id") or provenance.get("originating_breadth_need_id") or action.get("recovery_need_id")
            target_function = action.get("target_editorial_function") or action.get("event_acquisition_plan", {}).get("target_editorial_function")
            new_id = _recovery_event_id(need_id, target_function, skeleton)
            bundle = {
                "schema_version": 1, "event_lead_id": new_id,
                "merged_event_lead_ids": [new_id], "state": "EVENT_LEAD_DISCOVERY_ONLY",
                "event_lead_state": "NEW_RECOVERY_EVENT_LEAD",
                "event_fingerprint": skeleton.get("event_fingerprint"),
                "event_skeleton": deepcopy(skeleton),
                "recovery_need_id": need_id, "originating_recovery_need_id": need_id,
                "recovery_mode": mode, "target_editorial_function": target_function,
                "desk": action.get("desk"), "observations": [], "support_observations": [], "sources": [],
                "source_roles": [], "publisher_families": [], "evidence_ids": [],
                "claims": [], "contradictions": [], "unresolved_origin_issues": [],
                "matches": [], "candidate_discovery": None, "provenance_edges": [], "attempted_source_routes": [],
                "new_recovery_event": True, "blocked_event_memory": None,
            }
            bundles.append(bundle)
            match = {"state": "DIFFERENT_EVENT", "reasons": ["NEW_NEED_SCOPED_EVENT"]}
        if match and match["state"] not in {"SAME_EVENT_HIGH_CONFIDENCE", "SAME_EVENT_PLAUSIBLE"} and not (
            bundle.get("new_recovery_event") and match.get("state") == "DIFFERENT_EVENT"
        ):
            bundle["matches"].append({"observation_id": observation.get("observation_id"), **match})
            continue
        bundle["observations"].append(observation.get("observation_id"))
        if isinstance(observation.get("support_observation"), dict):
            support_record = deepcopy(observation["support_observation"])
            support_record.setdefault("publisher", observation.get("page_publisher") or observation.get("origin"))
            support_record.setdefault("issuer", observation.get("stated_issuing_authority"))
            support_record.setdefault("origin", observation.get("content_origin"))
            support_record.setdefault("original_artifact_state", observation.get("original_artifact_state"))
            support_record.setdefault("lineage_edges", deepcopy(observation.get("provenance_edges") or []))
            bundle["support_observations"].append(support_record)
        parent_id = provenance.get("originating_observation_id")
        if parent_id:
            bundle["provenance_edges"].append({"from_observation_id": parent_id, "relation": "CITES_OR_POINTS_TO", "to_source_id": observation.get("source_id"), "to_observation_id": observation.get("observation_id")})
        # Preserve the full source-chain assertions from the observation
        # (discovery -> attribution -> target). They remain provenance
        # metadata; they never upgrade a republication to PRIMARY.
        bundle["provenance_edges"].extend(
            deepcopy(item) for item in (observation.get("provenance_edges") or [])
            if isinstance(item, dict)
        )
        bundle["matches"].append({"observation_id": observation.get("observation_id"), **(match or {"state": "SAME_EVENT_HIGH_CONFIDENCE", "reasons": ["EVENT_LEAD_ANCHOR"]})})
        route_id = provenance.get("route_id")
        if route_id:
            bundle["attempted_source_routes"].append(route_id)
        if observation.get("source_id"):
            bundle["sources"].append(observation["source_id"])
        family = _publisher_family(observation)
        if family:
            bundle["publisher_families"].append(family)
        if observation.get("verification_status") == "VALIDATED_EVIDENCE":
            role = "PRIMARY" if observation.get("source_class") in {"primary", "official", "paper"} else "INDEPENDENT" if observation.get("source_class") == "independent" else "UNKNOWN"
            role_detail = observation.get("source_role_resolution") if isinstance(observation.get("source_role_resolution"), dict) else {}
            publisher = ((observation.get("article_metadata") or {}).get("publisher") or {}).get("name") if isinstance((observation.get("article_metadata") or {}).get("publisher"), dict) else None
            bundle["evidence_ids"].append(observation.get("source_id"))
            bundle["source_roles"].append({
                "source_id": observation.get("source_id"), "role": role,
                "publisher": publisher or observation.get("origin"), "publisher_family": family,
                "document_type": role_detail.get("document_type"),
                "publisher_event_relation": role_detail.get("publisher_event_relation"),
                "article_origin_state": role_detail.get("article_origin_state"),
                "independence_state": role_detail.get("independence_state"),
                "claim_relation": observation.get("evidence_relation"),
                "directness": observation.get("directness"),
                "event_match": (bundle["matches"][-1] if bundle["matches"] else {}).get("state"),
                "role_reason": role_detail.get("reason"),
            })
            bundle["claims"].append({"source_id": observation.get("source_id"), "relation": observation.get("evidence_relation"), "directness": observation.get("directness")})
            if observation.get("evidence_relation") == "CONTRADICTS":
                bundle["contradictions"].append(observation.get("source_id"))
        elif observation.get("event_state") == "EVENT_LEAD_DISCOVERY_ONLY":
            bundle["unresolved_origin_issues"].append(observation.get("source_resolution_state") or "SOURCE_ORIGIN_UNRESOLVED")

    discoveries = []
    for bundle in bundles:
        for key in ("observations", "sources", "publisher_families", "evidence_ids", "contradictions", "unresolved_origin_issues"):
            bundle[key] = list(dict.fromkeys(item for item in bundle[key] if item))
        support_items = {str(item.get("observation_id")): item for item in bundle.get("support_observations", []) if isinstance(item, dict) and item.get("observation_id")}
        bundle["support_observations"] = [support_items[key] for key in sorted(support_items)]
        bundle["provenance_edges"] = [item for item in bundle.get("provenance_edges", []) if isinstance(item, dict)]
        bundle["attempted_source_routes"] = list(dict.fromkeys(item for item in bundle.get("attempted_source_routes", []) if item))
        role_items = {json.dumps(item, ensure_ascii=False, sort_keys=True): item for item in bundle["source_roles"]}
        bundle["source_roles"] = [role_items[key] for key in sorted(role_items)]
        if bundle["contradictions"]:
            bundle.update(state="EVENT_CONTRADICTED", failure_reason="CONTRADICTION_RETAINED")
            continue
        primary = [item["source_id"] for item in bundle["source_roles"] if item["role"] == "PRIMARY"]
        independent = [item["source_id"] for item in bundle["source_roles"] if item["role"] == "INDEPENDENT"]
        candidate = {"title": bundle["event_skeleton"].get("title"), "facts": [bundle["event_skeleton"].get("title")], "primary_evidence_source_ids": primary, "independent_evidence_source_ids": independent}
        policy = candidate_evidence_policy(candidate, sources, section_id=bundle.get("desk"))
        actual = {item["role"] for item in bundle["source_roles"]}
        if not bundle["evidence_ids"]:
            missing_reason = "MISSING_PRIMARY" if "PRIMARY" in policy["required_roles"] else "MISSING_INDEPENDENT"
            _mark_semantic_event_blocked(bundle, missing_reason, policy)
            if bundle.get("state") != "EVENT_EVIDENCE_BLOCKED":
                bundle.update(state="EVENT_LEAD_DISCOVERY_ONLY", failure_reason=missing_reason, evidence_policy=policy)
            continue
        if not set(policy["required_roles"]) <= actual:
            missing = "MISSING_PRIMARY" if "PRIMARY" in policy["required_roles"] and "PRIMARY" not in actual else "MISSING_INDEPENDENT"
            _mark_semantic_event_blocked(bundle, missing, policy)
            if bundle.get("state") != "EVENT_EVIDENCE_BLOCKED":
                bundle.update(state="EVENT_EVIDENCE_PARTIAL", failure_reason=missing, evidence_policy=policy)
            continue
        primary_families = {item["publisher_family"] for item in bundle["source_roles"] if item["role"] == "PRIMARY"}
        independent_families = {item["publisher_family"] for item in bundle["source_roles"] if item["role"] == "INDEPENDENT"}
        if primary_families & independent_families:
            _mark_semantic_event_blocked(bundle, "SOURCE_ORIGIN_UNRESOLVED", policy)
            if bundle.get("state") != "EVENT_EVIDENCE_BLOCKED":
                bundle.update(state="EVENT_EVIDENCE_PARTIAL", failure_reason="SOURCE_ORIGIN_UNRESOLVED", evidence_policy=policy)
            continue
        action = actions_by_need.get(str(bundle.get("recovery_need_id") or ""), {})
        synthetic = {"title": candidate["title"], "claim": candidate["title"], "extracted_text": bundle["event_skeleton"].get("lead_paragraphs"), "published_at": bundle["event_skeleton"].get("published_at")}
        value_reason, rejection = _editorial_value_reason(synthetic, action)
        if not value_reason:
            bundle.update(state="EVENT_REJECTED", failure_reason=rejection or "LOW_EDITORIAL_VALUE", evidence_policy=policy)
            continue
        editorial_functions = classify_event_functions(
                title=candidate["title"],
                facts=[
                    candidate["title"],
                    bundle["event_skeleton"].get("actor"),
                    bundle["event_skeleton"].get("action"),
                    bundle["event_skeleton"].get("object"),
                    bundle["event_skeleton"].get("lead_paragraphs"),
                ],
            evidence_source_ids=bundle["evidence_ids"],
            exact_page_validated=True,
        )
        target_function = str(action.get("event_acquisition_plan", {}).get("target_editorial_function") or action.get("target_editorial_function") or "")
        function_names = {item["function"] for item in editorial_functions}
        if target_function and target_function not in function_names:
            bundle.update(
                state="EVENT_REJECTED", failure_reason="FUNCTION_NOT_ESTABLISHED",
                evidence_policy=policy, editorial_functions=editorial_functions,
            )
            continue
        bundle.update(state="EVENT_VALIDATED", evidence_policy=policy, editorial_functions=editorial_functions)
        eligible_sections = [
            str(section) for section in action.get("event_context", {}).get("topic_terms", [])
            if str(section) in {"siyasa_dawla", "iqtisad_flous", "mojtama3", "ta3lim", "se77a", "3adl_7o9o9", "bi2a_manakh", "bniya_transport", "filastin_middle_east", "africa_sahel", "world", "investigations", "opinion", "service", "sport", "culture", "science"}
        ]
        discovery = {
            "section_id": bundle.get("desk") or action.get("desk"), "event_id": bundle["event_lead_id"], "event_lead_id": bundle["event_lead_id"],
            "title": candidate["title"], "claim": candidate["title"], "source_ids": list(bundle["evidence_ids"]),
            "source_roles": deepcopy(bundle["source_roles"]), "editorial_value_reason": value_reason,
            "editorial_functions": deepcopy(editorial_functions),
            "target_editorial_function": target_function or None,
            "temporal_relevance": deepcopy(bundle["event_skeleton"].get("temporal_relevance")),
            "acceptable_story_roles": list(action.get("acceptable_story_roles") or []),
            "recovery_need_id": bundle.get("recovery_need_id"),
            "eligible_section_ids": eligible_sections,
            "preferred_section_ids": _breadth_event_desk_preferences(bundle, eligible_sections),
        }
        bundle["candidate_discovery"] = discovery
        discoveries.append(deepcopy(discovery))
    return bundles, discoveries


def build_observation_snapshot(actions: list[dict], observations: list[dict], bundles: list[dict]) -> dict:
    """Content-address a replay-only observation snapshot, never live evidence."""
    items = [{
        "observation_id": item.get("observation_id"), "url": item.get("url"), "source_id": item.get("source_id"),
        "title": item.get("title"), "published_at": item.get("published_at"), "source_class": item.get("source_class"),
        "verification_status": item.get("verification_status"), "evidence_relation": item.get("evidence_relation"),
        "directness": item.get("directness"), "content_hash": item.get("content_hash"), "event_skeleton": item.get("event_skeleton"),
        "event_state": item.get("event_state"), "provenance": item.get("provenance"),
        "extraction_status": item.get("extraction_status"), "article_metadata": item.get("article_metadata"),
        "article_attribution": item.get("article_attribution"), "publisher_profile": item.get("publisher_profile"),
        "source_role_resolution": item.get("source_role_resolution"), "validation_state": item.get("validation_state"),
        "original_source_resolution": item.get("original_source_resolution"),
        "resolution_failure_category": item.get("resolution_failure_category"),
        "post_fetch_qualification": item.get("post_fetch_qualification"),
        "claim_support": item.get("claim_support"),
        "support_observation": item.get("support_observation"),
    } for item in observations]
    payload = {"mode": "TEST_REPLAY_EVIDENCE", "actions": actions, "observations": items, "event_bundles": bundles}
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {**payload, "snapshot_hash": hashlib.sha256(canonical.encode("utf-8")).hexdigest()}


def replay_event_bundles_from_snapshot(snapshot: dict) -> dict:
    """Read a deterministic test/audit snapshot without reusing it in live work."""
    if snapshot.get("mode") != "TEST_REPLAY_EVIDENCE":
        raise ResearchExecutorError("OBSERVATION_SNAPSHOT_NOT_REPLAY_EVIDENCE")
    payload = {key: snapshot.get(key) for key in ("mode", "actions", "observations", "event_bundles")}
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if snapshot.get("snapshot_hash") != hashlib.sha256(canonical.encode("utf-8")).hexdigest():
        raise ResearchExecutorError("OBSERVATION_SNAPSHOT_HASH_MISMATCH")
    return {"mode": "TEST_REPLAY_EVIDENCE", "event_bundles": deepcopy(snapshot.get("event_bundles", [])), "production_evidence_reuse": False}


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
    event_bundles = [
        bundle for job in jobs if isinstance(job, dict)
        for bundle in job.get("source_packet_patch", {}).get("event_bundles", []) if isinstance(bundle, dict)
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
    qualification_items = [
        item.get("post_fetch_qualification") for item in observations
        if item.get("extraction_status") in {"FETCHED", "RETRIEVED"}
        and isinstance(item.get("post_fetch_qualification"), dict)
    ]
    qualification_blockers: dict[str, int] = {}
    qualification_states: dict[str, int] = {}
    support_types: dict[str, int] = {}
    support_diagnoses: dict[str, int] = {}
    support_observation_roles: dict[str, int] = {}
    support_observation_records = [
        item.get("support_observation") for item in observations
        if item.get("extraction_status") in {"FETCHED", "RETRIEVED"}
        and isinstance(item.get("support_observation"), dict)
    ]
    for item in qualification_items:
        state = str(item.get("state") or "UNKNOWN")
        blocker = str(item.get("first_blocking_reason") or "UNKNOWN")
        qualification_states[state] = qualification_states.get(state, 0) + 1
        qualification_blockers[blocker] = qualification_blockers.get(blocker, 0) + 1
        support_type = str((item.get("claim_support") or {}).get("support_type") or "NO_SUPPORT")
        support_types[support_type] = support_types.get(support_type, 0) + 1
        diagnosis = str((item.get("claim_support") or {}).get("diagnosis") or "UNRESOLVED")
        support_diagnoses[diagnosis] = support_diagnoses.get(diagnosis, 0) + 1
    for support_record in support_observation_records:
        support_role = str(support_record.get("role") or "UNRESOLVED")
        support_observation_roles[support_role] = support_observation_roles.get(support_role, 0) + 1
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
            "research_lane": action.get("research_lane"),
            "target_editorial_function": action.get("target_editorial_function"),
            "target_source_class": action.get("target_source_class"),
            "first_party_discovery_objective": action.get("first_party_discovery_objective"),
            "institution_discovery_mode": action.get("institution_discovery_mode"),
            "source_class_selection_reason": action.get("source_class_selection_reason"),
            "current_process_context": action.get("current_process_context"),
            "source_class_memory_before": list(action.get("source_class_memory_before") or []),
            "route_scoped": bool(action.get("route_scoped")),
            "route_search_objective": action.get("route_search_objective"),
            "source_route_id": (action.get("source_route") or {}).get("route_id") if isinstance(action.get("source_route"), dict) else None,
            "recovery_need_id": action.get("recovery_need_id"),
            "source_discovery_channels": sorted({
                str(item.get("discovery_channel") or item.get("discovery_method") or "UNKNOWN")
                for item in action_observations
            }),
            "urls": sorted({item["url"] for item in action_observations if item.get("url")}),
            "source_ids": sorted({item["source_id"] for item in action_observations if item.get("source_id")}),
            "observation_types": sorted({item["observation_class"] for item in action_observations}),
            "discovery_diagnostics": sorted({str(item.get("discovery_diagnostic")) for item in action_observations if item.get("discovery_diagnostic")}),
            "discovery_reasons": sorted({str(item.get("discovery_reason")) for item in action_observations if item.get("discovery_reason")}),
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
            "post_fetch_qualification": {
                "fetched": sum(item.get("extraction_status") in {"FETCHED", "RETRIEVED"} for item in action_observations),
                "states": sorted({str((item.get("post_fetch_qualification") or {}).get("state")) for item in action_observations if isinstance(item.get("post_fetch_qualification"), dict)}),
                "first_blockers": sorted({str((item.get("post_fetch_qualification") or {}).get("first_blocking_reason")) for item in action_observations if isinstance(item.get("post_fetch_qualification"), dict)}),
                "support_types": sorted({str(((item.get("post_fetch_qualification") or {}).get("claim_support") or {}).get("support_type") or "NO_SUPPORT") for item in action_observations if isinstance(item.get("post_fetch_qualification"), dict)}),
            },
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
            "discovery_diagnostics": sorted({str(item.get("discovery_diagnostic")) for item in backend_observations if item.get("discovery_diagnostic")}),
        })
    discovery_diagnostics: dict[str, int] = {}
    for item in observations:
        diagnostic = str(item.get("discovery_diagnostic") or "")
        if diagnostic:
            discovery_diagnostics[diagnostic] = discovery_diagnostics.get(diagnostic, 0) + 1
    direct_route_entries = [
        entry for job in jobs if isinstance(job, dict)
        for entry in (job.get("direct_route_selection") or [])
        if isinstance(entry, dict)
    ]
    function_metrics = {}
    for function in ("ACCOUNTABILITY", "SERVICE"):
        function_actions = [
            action for action in actions
            if str(action.get("target_editorial_function") or "").upper() == function
        ]
        function_action_ids = {action.get("action_id") for action in function_actions}
        function_observations = [
            item for item in observations
            if item.get("provenance", {}).get("action_id") in function_action_ids
        ]
        function_metrics[function] = {
            "candidate_source_families": sorted({str(family) for action in function_actions for family in action.get("candidate_source_families", []) if family}),
            "selected_source_families": sorted({str(action.get("selected_source_family")) for action in function_actions if action.get("selected_source_family") and action.get("selected_source_family") != "UNKNOWN"}),
            "selected_source_routes": sorted({str((action.get("source_route") or {}).get("route_id")) for action in function_actions if isinstance(action.get("source_route"), dict) and (action.get("source_route") or {}).get("route_id")}),
            "candidate_authority_capabilities": sorted({str(capability) for action in function_actions for capability in action.get("candidate_authority_capabilities", []) if capability}),
            "selected_authorities": sorted({str(action.get("selected_authority_id")) for action in function_actions if action.get("selected_authority_id")}),
            "selected_authority_capabilities": sorted({str(action.get("authority_capability")) for action in function_actions if action.get("authority_capability") and action.get("authority_capability") != "AUTHORITY_UNRESOLVED"}),
            "target_artifact_families": sorted({str(action.get("artifact_family")) for action in function_actions if action.get("artifact_family")}),
            "authority_selection_reasons": sorted({str(action.get("authority_selection_reason")) for action in function_actions if action.get("authority_selection_reason")}),
            "artifact_selection_reasons": sorted({str(action.get("artifact_selection_reason")) for action in function_actions if action.get("artifact_selection_reason")}),
            "family_selection_reasons": sorted({str(action.get("selection_reason")) for action in function_actions if action.get("selection_reason")}),
            "source_classes_queried": sorted({item for action in function_actions for item in action.get("source_class_priorities", [])}),
            "source_class_branches_attempted": sorted({str(action.get("target_source_class")) for action in function_actions if action.get("target_source_class")}),
            "source_class_memory": sorted({str(item) for action in function_actions for item in action.get("source_class_memory_before", [])}),
            "source_class_selection_reasons": sorted({str(action.get("source_class_selection_reason")) for action in function_actions if action.get("source_class_selection_reason")}),
            "first_party_discovery_actions": sum(action.get("first_party_discovery_objective") == "FIRST_PARTY_SELF_ACTION" for action in function_actions),
            "institution_discovery_actions": sum(action.get("institution_discovery_mode") == "OPEN_DISCOVERY_THEN_OWNERSHIP_VALIDATION" for action in function_actions),
            "searches": sum(action.get("action_type") in SEARCH_ACTIONS for action in function_actions),
            "leads": sum(item.get("observation_class") == "LEAD" for item in function_observations),
            "fetch_selections": sum(item.get("lead_attrition_state") == "SELECTED_FOR_FETCH" for item in function_observations),
            "pages_fetched": sum(item.get("extraction_status") in {"RETRIEVED", "FETCHED"} for item in function_observations),
            "active_window_leads": sum(
                (item.get("temporal_relevance") or {}).get("active_on_edition_date") is True
                for item in function_observations
            ),
            "concrete_events": sum((item.get("event_skeleton") or {}).get("state") == "CONCRETE_EVENT" for item in function_observations),
            "first_party_domains_resolved": len({
                str(item.get("institution_identity", {}).get("canonical_institution_domain"))
                for item in function_observations
                if isinstance(item.get("institution_identity"), dict)
                and item.get("institution_identity", {}).get("canonical_institution_domain")
            }),
            "primary_observations": sum(str(item.get("source_class") or "").casefold() in {"primary", "official", "paper"} for item in function_observations),
            "event_b_candidates": sum(
                str((bundle.get("candidate_discovery") or {}).get("target_editorial_function") or "").upper() == function
                for bundle in event_bundles
            ),
            "validated_events": sum(
                item.get("state") == "EVENT_VALIDATED"
                and any(str((bundle.get("candidate_discovery") or {}).get("target_editorial_function") or "").upper() == function for bundle in event_bundles)
                for item in event_bundles
            ),
            "closures": sum(
                item.get("recovery_need_closed") and str(item.get("target_editorial_function") or "").upper() == function
                for item in action_outcomes
            ),
        }
    institutional_observations = [
        item for item in observations
        if isinstance(item.get("institution_identity"), dict)
        and item.get("institution_identity", {}).get("profile_type") not in {None, "OTHER_INSTITUTION"}
    ]
    listing_observations = [item for item in observations if item.get("navigation_type") or item.get("page_type") == "LISTING_PAGE"]
    child_actions = [item for item in actions if int(item.get("navigation_depth", 0) or 0) == 2]
    institutional_identity = {
        "institutional_leads": sum(item.get("observation_class") == "LEAD" for item in institutional_observations),
        "identities_resolved": sum(item.get("institution_identity", {}).get("state") == "INSTITUTION_IDENTITY_RESOLVED" for item in institutional_observations),
        "canonical_domains_resolved": sum(bool(item.get("institution_identity", {}).get("canonical_institution_domain")) for item in institutional_observations),
        "unresolved_identities": sum(item.get("institution_identity", {}).get("state") != "INSTITUTION_IDENTITY_RESOLVED" for item in institutional_observations),
    }
    listing_resolution = {
        "listing_pages": len(listing_observations),
        "child_links_extracted": sum(len(item.get("listing_links") or []) for item in listing_observations),
        "navigation_pages": len(listing_observations),
        "navigation_types": sorted({str(item.get("navigation_type")) for item in listing_observations if item.get("navigation_type")} ),
        "links_discovered": sum(int(item.get("links_discovered", 0) or 0) for item in listing_observations),
        "links_relevant": sum(int(item.get("links_relevant", 0) or 0) for item in listing_observations),
        "artifact_candidates": sum(len(item.get("artifact_candidates") or []) for item in listing_observations),
        "followups_scheduled": sum(bool(item.get("followup_scheduled")) for item in listing_observations),
        "child_links_selected": sum(item.get("listing_resolution_state") == "CHILD_DETAIL_SELECTED" for item in listing_observations),
        "detail_fetches": len(child_actions),
        "exact_artifacts_reached": sum(bool(item.get("exact_artifact_reached")) and item.get("extraction_status") in {"FETCHED", "RETRIEVED"} for item in observations if item.get("provenance", {}).get("action_id") in {action.get("action_id") for action in child_actions}),
        "maximum_navigation_depth": 2,
    }
    provenance_recovery = {
        "secondary_pages_inspected": sum(1 for item in observations if item.get("extraction_status") == "FETCHED" and item.get("source_class") == "unknown"),
        "attribution_phrases": sum(len(item.get("citation_attributions") or []) for item in observations),
        "official_links_extracted": sum(len(item.get("official_link_candidates") or []) for item in observations),
        "official_links_selected": sum(1 for action in actions if action.get("outbound_link_type")),
        "outbound_link_followups": sum(bool(action.get("provenance_followup") and action.get("outbound_link_type")) for action in actions),
        "actor_first_searches": sum(bool(action.get("actor_first_search")) for action in actions),
        "actor_first_fetches": sum(bool(action.get("actor_first_fetch")) for action in actions),
        "event_actors_resolved": sum(bool(item.get("event_actor_candidates")) for item in observations),
        "diagnostics": sorted(set(str(item.get("provenance_recovery_reason") or item.get("reason") or "") for item in observations if item.get("provenance_recovery_reason") or item.get("reason"))),
    }
    route_health = [deepcopy(item["route_health"]) for item in observations if isinstance(item.get("route_health"), dict)]
    route_scoped_all_actions = [item for item in actions if item.get("route_scoped")]
    route_scoped_actions = [item for item in route_scoped_all_actions if item.get("action_type") in SEARCH_ACTIONS]
    route_scoped_search_ids = {item.get("action_id") for item in route_scoped_actions}
    route_scoped_observations = [
        item for item in observations
        if item.get("provenance", {}).get("action_id") in route_scoped_search_ids
    ]
    route_scoped_all_ids = {item.get("action_id") for item in route_scoped_all_actions}
    route_scoped_fetch_observations = [
        item for item in observations
        if item.get("provenance", {}).get("action_id") in route_scoped_all_ids
        and item.get("extraction_status") in {"FETCHED", "RETRIEVED"}
    ]
    route_scoped_retrieval = {
        "routes_attempted": sorted({
            (item.get("source_route") or {}).get("route_id")
            for item in route_scoped_actions if isinstance(item.get("source_route"), dict) and (item.get("source_route") or {}).get("route_id")
        }),
        "queries": len(route_scoped_actions),
        "results": len(route_scoped_observations),
        "exact_detail_candidates": sum(bool(item.get("url")) and item.get("page_type") not in {"LISTING_PAGE", "PORTAL_HOME", "AGGREGATOR"} for item in route_scoped_observations),
        "selected_fetches": len(route_scoped_fetch_observations),
        "fetched_artifacts": len(route_scoped_fetch_observations),
        "active_window_results": sum((item.get("temporal_relevance") or {}).get("active_on_edition_date") is True for item in route_scoped_fetch_observations),
    }
    semantic_closure = {"attempted": 0, "validated_functions": {"ACCOUNTABILITY": 0, "SERVICE": 0}, "promoted_candidates": 0, "closures": 0, "failure_stages": {}}
    for bundle in event_bundles:
        if not isinstance(bundle, dict):
            continue
        semantic_closure["attempted"] += 1
        for fn in (bundle.get("editorial_functions") or []):
            if isinstance(fn, dict) and fn.get("status") == "VALIDATED" and fn.get("function") in semantic_closure["validated_functions"]:
                semantic_closure["validated_functions"][fn["function"]] += 1
        if bundle.get("candidate_discovery"):
            semantic_closure["promoted_candidates"] += 1
        if bundle.get("state") == "EVENT_VALIDATED" and bundle.get("candidate_discovery"):
            semantic_closure["closures"] += 1
        else:
            stage = str(bundle.get("failure_reason") or "EVENT_MATCH")
            semantic_closure["failure_stages"][stage] = semantic_closure["failure_stages"].get(stage, 0) + 1
    for item in observations:
        if item.get("verification_status") == "VALIDATED_EVIDENCE" and not any(item.get("observation_id") in bundle.get("observations", []) for bundle in event_bundles):
            semantic_closure["failure_stages"]["EVENT_MATCH"] = semantic_closure["failure_stages"].get("EVENT_MATCH", 0) + 1
    hard_lane_actions = [
        item for item in actions
        if str(item.get("research_lane") or "").startswith(("ACCOUNTABILITY", "SERVICE", "BREADTH:"))
        or str(item.get("recovery_need_id") or "").startswith("BREADTH:")
    ]
    hard_lane_names = sorted({
        str(item.get("research_lane")) for item in hard_lane_actions
        if item.get("research_lane")
    })
    hard_breadth_planning = {
        "lanes_attempted": hard_lane_names,
        "planned_actions": sum(
            str(item.get("research_lane") or "").startswith(("ACCOUNTABILITY", "SERVICE", "BREADTH:"))
            or str(item.get("recovery_need_id") or "").startswith("BREADTH:")
            for job in jobs for item in job.get("actions", []) if isinstance(item, dict)
        ),
        "executed_actions": len(hard_lane_actions),
        "general_discovery_actions": sum(item.get("research_lane") == "GENERAL_DISCOVERY" for item in actions),
        "budget_increased": False,
    }
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
        "pages_with_title_resolved": sum(item.get("extraction_status") == "FETCHED" and item.get("title_state") == "TITLE_RESOLVED" for item in observations),
        "pages_with_date_resolved": sum(item.get("extraction_status") == "FETCHED" and bool((item.get("article_metadata") or {}).get("publication_date", {}).get("normalized")) for item in observations),
        "pages_with_publisher_resolved": sum(item.get("extraction_status") == "FETCHED" and item.get("source_resolution_state") == "PUBLISHER_RESOLVED_ARTICLE_ROLE_PENDING" for item in observations),
        "pages_with_byline_or_credit": sum(item.get("extraction_status") == "FETCHED" and bool((item.get("article_attribution") or {}).get("author_byline") or (item.get("article_attribution") or {}).get("wire_credit") or (item.get("article_attribution") or {}).get("partner_credit")) for item in observations),
        "article_text_extracted": sum(item.get("extraction_status") == "FETCHED" and bool(item.get("extracted_text")) for item in observations),
        "concrete_events_extracted": sum((item.get("event_skeleton") or {}).get("state") == "CONCRETE_EVENT" for item in observations),
        "new_unverified_event_leads": sum(item.get("event_state") == "EVENT_LEAD_DISCOVERY_ONLY" for item in observations),
        "alternative_coverage_searches_triggered": sum(item.get("query_intent") == "EVENT_LEAD_ALTERNATIVE_COVERAGE" for item in actions),
        "semantic_pivot_actions": sum(str(item.get("pivot_mode") or "") == "FIND_ALTERNATIVE_EVENT_FOR_SEMANTIC_NEED" for item in actions),
        "starting_event_leads": sum(len(job.get("source_packet_patch", {}).get("event_leads", [])) for job in jobs if isinstance(job, dict)),
        "observations_attached_to_event_leads": sum(len(item.get("observations", [])) for item in event_bundles),
        "unattached_event_observations": sum(
            bool((item.get("event_skeleton") or {}).get("state") == "CONCRETE_EVENT")
            and not any(item.get("observation_id") in bundle.get("observations", []) for bundle in event_bundles)
            for item in observations
        ),
        "same_event_matches": sum(
            match.get("state") in {"SAME_EVENT_HIGH_CONFIDENCE", "SAME_EVENT_PLAUSIBLE"}
            for bundle in event_bundles for match in bundle.get("matches", []) if isinstance(match, dict)
        ),
        "unresolved_event_matches": sum(
            match.get("state") == "EVENT_MATCH_UNRESOLVED"
            for bundle in event_bundles for match in bundle.get("matches", []) if isinstance(match, dict)
        ),
        "evidence_bundles_created": len(event_bundles),
        "new_recovery_event_roots": sum(bool(item.get("new_recovery_event")) for item in event_bundles),
        "partial_event_bundles": sum(item.get("state") == "EVENT_EVIDENCE_PARTIAL" for item in event_bundles),
        "blocked_event_bundles": sum(item.get("state") == "EVENT_EVIDENCE_BLOCKED" for item in event_bundles),
        "pivot_eligible_blocked_events": sum(bool((item.get("blocked_event_memory") or {}).get("pivot_eligible")) for item in event_bundles),
        "complete_event_bundles": sum(item.get("state") == "EVENT_VALIDATED" for item in event_bundles),
        "validated_events": sum(item.get("state") == "EVENT_VALIDATED" for item in event_bundles),
        "contradicted_events": sum(item.get("state") == "EVENT_CONTRADICTED" for item in event_bundles),
        "promoted_event_candidates": sum(bool(item.get("candidate_discovery")) for item in event_bundles),
        "source_identities_resolved": sum(item.get("source_identity", {}).get("identity_state") in {"SOURCE_IDENTIFIED", "PUBLISHER_RESOLVED_ARTICLE_ROLE_PENDING"} for item in observations),
        "unknown_sources_remaining": sum(
            item.get("source_class") == "unknown"
            and item.get("observation_class") in {"LEAD", "POTENTIAL_EVIDENCE"}
            for item in observations
        ),
        "lead_attrition": dict(sorted(attrition_counts.items())),
        "post_fetch_qualification": {
            "fetched_pages": len(qualification_items),
            "states": dict(sorted(qualification_states.items())),
            "first_blockers": dict(sorted(qualification_blockers.items())),
            "support_types": dict(sorted(support_types.items())),
            "diagnoses": dict(sorted(support_diagnoses.items())),
            "observations_created": sum(support_observation_roles.values()),
            "observation_roles": dict(sorted(support_observation_roles.items())),
            "eligible_observations": sum(item.get("first_blocking_reason") == "ELIGIBLE_OBSERVATION" for item in qualification_items),
        },
        "claim_support_resolution": {
            "fetched_pages": len(qualification_items),
            "support_types": dict(sorted(support_types.items())),
            "diagnoses": dict(sorted(support_diagnoses.items())),
            "exact_locators": sum(bool((item.get("claim_support") or {}).get("locator")) for item in qualification_items),
            "direct_support": support_types.get("DIRECT_SUPPORT", 0),
            "partial_support": support_types.get("PARTIAL_SUPPORT", 0),
            "context_only": support_types.get("CONTEXT_ONLY", 0),
            "contradicts": support_types.get("CONTRADICTS", 0),
            "ambiguous": support_types.get("AMBIGUOUS", 0),
            "no_support": support_types.get("NO_SUPPORT", 0),
        },
        "questions_with_zero_useful_results": len({item["question_id"] for item in actions} - useful_questions),
        "branches_with_zero_useful_results": len({item["branch_id"] for item in actions} - useful_branches),
        "action_outcomes": action_outcomes,
        "strategy_channel_yield": strategy_channel_yield,
        "backend_yield": backend_yield,
        "discovery_diagnostics": discovery_diagnostics,
        "fetch_bridge": {
            "direct_route_attempts": len(direct_route_entries),
            "direct_route_selected": sum(item.get("status") == "DIRECT_SOURCE_ROUTE_SELECTED" for item in direct_route_entries),
            "direct_route_skipped": sum(item.get("status") == "DIRECT_SOURCE_ROUTE_SKIPPED" for item in direct_route_entries),
            "direct_route_reasons": sorted({str(item.get("reason")) for item in direct_route_entries if item.get("reason")}),
        },
        "function_metrics": function_metrics,
        "institutional_identity": institutional_identity,
        "listing_resolution": listing_resolution,
        "provenance_recovery": provenance_recovery,
        "route_health": {
            "routes_observed": len(route_health),
            "working": sum(item.get("status") == "VERIFIED_WORKING" for item in route_health),
            "transient_failures": sum(item.get("status") == "TRANSIENT_FAILURE" for item in route_health),
            "observed": route_health,
        },
        "route_scoped_retrieval": route_scoped_retrieval,
        "semantic_closure": semantic_closure,
        "hard_breadth_planning": hard_breadth_planning,
        "hidden_budget_expansion": "NONE",
        "budget_allocation": execution.get("budget_allocation") or {
            "jobs": [item.get("budget_allocation", {}) for item in jobs if item.get("budget_allocation")],
            "budget_increased": False,
        },
    }


def _source_patch(observation: dict, action: dict) -> dict | None:
    if observation["observation_class"] != "POTENTIAL_EVIDENCE" or not observation.get("url"):
        return None
    source_type = observation["source_class"]
    if source_type not in {"primary", "official", "independent", "paper"}:
        return None
    if observation["verification_status"] != "VALIDATED_EVIDENCE":
        return None
    role_detail = observation.get("source_role_resolution") if isinstance(observation.get("source_role_resolution"), dict) else {}
    metadata_publisher = ((observation.get("article_metadata") or {}).get("publisher") or {}) if isinstance(observation.get("article_metadata"), dict) else {}
    return {
        "id": observation["source_id"], "url": observation["url"],
        "publisher": metadata_publisher.get("name") or observation["origin"], "title": observation["title"],
        "publication_date": observation["published_at"], "accessed_at": observation["observed_at"],
        "source_type": source_type, "claim_supported": observation["claim"],
        "content_hash": observation["content_hash"],
        "extracted_text": observation.get("extracted_text"),
        "language": observation.get("provenance", {}).get("language"),
        "evidence_relation": observation.get("evidence_relation"),
        "directness": observation.get("directness"),
        "executor_observation_id": observation["observation_id"],
        "verification_status": observation["verification_status"],
        "document_type": role_detail.get("document_type"),
        "publisher_event_relation": role_detail.get("publisher_event_relation"),
        "article_origin_state": role_detail.get("article_origin_state"),
        "content_origin": observation.get("content_origin"),
        "stated_issuing_authority": observation.get("stated_issuing_authority"),
        "original_artifact_state": observation.get("original_artifact_state"),
        "document_references": deepcopy(observation.get("document_references") or []),
        "provenance_edges": deepcopy(observation.get("provenance_edges") or []),
        "original_source_resolution": deepcopy(observation.get("original_source_resolution") or {}),
        "resolution_failure_category": observation.get("resolution_failure_category"),
        "independence_state": role_detail.get("independence_state"),
        "role_reason": role_detail.get("reason"),
        "page_type": observation.get("page_type"),
        "institution_identity": deepcopy(observation.get("institution_identity")),
        "structured_fields": deepcopy(observation.get("structured_fields")),
        "temporal_relevance": deepcopy(observation.get("temporal_relevance")),
        "claim_support": deepcopy(observation.get("claim_support") or (observation.get("post_fetch_qualification") or {}).get("claim_support")),
        "provenance": observation["provenance"],
        "recovery_need_id": action.get("recovery_need_id"),
    }


def replay_exact_source_roles(observations: list[dict], actions: list[dict]) -> tuple[list[dict], list[dict]]:
    """Re-evaluate captured exact pages using current deterministic role rules.

    This intentionally produces TEST_REPLAY_EVIDENCE diagnostics only.  It
    does not fetch, mutate a captured run, or make an old page current-edition
    production evidence.  The returned source patches are useful solely for
    exercising the same packet/bundle transitions in a replay harness.
    """
    replayed = deepcopy(observations)
    action_by_id = {item.get("action_id"): item for item in actions if isinstance(item, dict)}
    sources = []
    for observation in replayed:
        provenance = observation.get("provenance") if isinstance(observation.get("provenance"), dict) else {}
        action = action_by_id.get(provenance.get("action_id"))
        if not action or action.get("action_type") not in FETCH_ACTIONS:
            continue
        if str(observation.get("extraction_status") or "").upper() not in {"FETCHED", "RETRIEVED"}:
            continue
        text = str(observation.get("extracted_text") or "")
        if not observation.get("url") or len(text) < 40 or not observation.get("content_hash"):
            continue
        raw = {
            "url": observation.get("url"), "canonical_url": observation.get("url"),
            "title": observation.get("title"), "title_state": observation.get("title_state"),
            "published_at": observation.get("published_at"), "text": text,
            "content_hash": observation.get("content_hash"), "fetch_status": observation.get("extraction_status"),
            "source_class": observation.get("source_class") or "unknown", "claim": observation.get("claim"),
            "article_metadata": deepcopy(observation.get("article_metadata")) if isinstance(observation.get("article_metadata"), dict) else {},
            "article_attribution": deepcopy(observation.get("article_attribution")) if isinstance(observation.get("article_attribution"), dict) else {},
            "publisher_profile": deepcopy(observation.get("publisher_profile")) if isinstance(observation.get("publisher_profile"), dict) else {},
            "publisher": ((observation.get("article_metadata") or {}).get("publisher") or {}).get("name") if isinstance(observation.get("article_metadata"), dict) else None,
        }
        skeleton = extract_event_skeleton(raw, action)
        resolution = resolve_exact_source_role(raw, action, skeleton)
        resolution["original_source_resolution"] = build_original_source_resolution(
            raw, action, skeleton=skeleton,
        )
        origin_detail = detect_official_portal_republication({
            **raw,
            "source_route": action.get("source_route") if isinstance(action.get("source_route"), dict) else None,
        })
        original_source_resolution = build_original_source_resolution(
            {**raw, **origin_detail}, action, skeleton=skeleton if isinstance(skeleton, dict) else None,
        )
        resolution["field_provenance"] = {
            "publisher": "PAGE_STRUCTURED_METADATA" if (isinstance(raw.get("article_metadata"), dict) and ((raw.get("article_metadata") or {}).get("publisher") or {}).get("name")) else ("PAGE_TEXT_INFERRED" if raw.get("publisher") else "OTHER_DERIVED"),
            "event_actor": ((skeleton.get("field_provenance") or {}).get("actor") if isinstance(skeleton, dict) else None) or "OTHER_DERIVED",
            "document_type": "PAGE_TEXT_INFERRED",
            "publisher_event_relation": "OBSERVED_PAGE_FACTS_ONLY",
            "evidence_role": "OBSERVED_PAGE_FACTS_ONLY",
        }
        resolved_class = str(resolution.get("source_class") or "unknown").casefold()
        supplied_class = str(raw.get("source_class") or raw.get("source_type") or "unknown").casefold()
        actor_first_context = bool(
            action.get("actor_first_search") or action.get("actor_first_fetch")
            or "ACTOR_FIRST" in str(action.get("query_intent") or "")
        )
        if resolved_class in {"primary", "independent"}:
            raw["source_class"] = resolved_class
        elif supplied_class in {"primary", "paper"} or (actor_first_context and supplied_class in {"official", "independent"}):
            # Replays must apply the same fail-closed rule as live execution:
            # a captured/configured label cannot override observed-page role
            # resolution.
            raw["source_class"] = "unknown"
        validation = validate_exact_page(raw, action)
        observation["event_skeleton"] = skeleton if skeleton.get("state") == "CONCRETE_EVENT" else observation.get("event_skeleton")
        observation["source_role_resolution"] = resolution
        observation["origin_detail"] = origin_detail
        observation["original_source_resolution"] = original_source_resolution
        observation["page_publisher"] = origin_detail.get("portal_publisher") or raw.get("publisher")
        observation["content_origin"] = origin_detail.get("content_origin")
        observation["stated_issuing_authority"] = origin_detail.get("issuing_institution")
        observation["document_references"] = deepcopy(origin_detail.get("document_references") or [])
        observation["original_artifact_state"] = origin_detail.get("original_artifact_state")
        observation["provenance_edges"] = [
            *deepcopy(origin_detail.get("provenance_edges") or []),
            *deepcopy(original_source_resolution.get("provenance_edges") or []),
        ]
        observation["resolution_failure_category"] = resolution_failure_for_observation({
            "original_source_resolution": original_source_resolution,
            "validation_state": validation.get("state"),
            "validation_reason": validation.get("reason"),
            "content_origin": origin_detail.get("content_origin"),
            "original_artifact_state": origin_detail.get("original_artifact_state"),
        })
        observation["source_class"] = str(validation.get("source_class") or raw["source_class"] or "unknown").casefold()
        observation["validation_state"] = validation.get("state", observation.get("validation_state"))
        observation["validation_progression"] = validation.get("progression", observation.get("validation_progression"))
        observation["validation_reason"] = validation.get("reason", observation.get("validation_reason"))
        observation["evidence_relation"] = validation.get("relation", observation.get("evidence_relation"))
        observation["directness"] = validation.get("directness", observation.get("directness"))
        observation["verification_status"] = "VALIDATED_EVIDENCE" if validation.get("state") == "VALIDATED_EVIDENCE" else "EXTRACTED_NOT_VERIFIED"
        observation["post_fetch_qualification"] = qualify_fetched_artifact(
            raw,
            page_type=classify_page_type(raw, action=action),
            validation=validation,
            role_resolution=resolution,
            temporal=observation.get("temporal_relevance") if isinstance(observation.get("temporal_relevance"), dict) else None,
            origin_detail=origin_detail,
            event_skeleton=skeleton,
        )
        observation["claim_support"] = deepcopy(observation["post_fetch_qualification"].get("claim_support"))
        support = observation["claim_support"] if isinstance(observation.get("claim_support"), dict) else {}
        observed_role = resolution.get("evidence_role")
        if observed_role in {None, "UNRESOLVED"}:
            observed_role = "REPUBLICATION" if resolution.get("article_origin_state") == "OFFICIAL_PORTAL_REPUBLICATION" else "SECONDARY"
        observation["support_observation"] = {
            "state": "OBSERVATION_CREATED",
            "claim_support": deepcopy(support),
            "role": observed_role,
            "publisher": observation.get("page_publisher") or observation.get("origin"),
            "issuer": observation.get("stated_issuing_authority"),
            "origin": observation.get("content_origin"),
            "original_artifact_state": observation.get("original_artifact_state"),
            "lineage_edges": deepcopy(observation.get("provenance_edges") or []),
            "primary_requirement_satisfied": observed_role == "PRIMARY",
            "requirement_state": "MET" if observed_role == "PRIMARY" else "NOT_MET",
            "observation_id": observation.get("observation_id"),
        } if support.get("locator") and support.get("support_type") in {"DIRECT_SUPPORT", "PARTIAL_SUPPORT", "CONTEXT_ONLY", "CONTRADICTS"} else None
        if observation["verification_status"] == "VALIDATED_EVIDENCE":
            observation["observation_class"] = "POTENTIAL_EVIDENCE"
            observation["kind"] = "POTENTIAL_EVIDENCE"
            patch = _source_patch(observation, action)
            if patch:
                sources.append(patch)
    return replayed, sources


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
    observations, source_records, updates, candidate_discoveries, event_leads = [], [], [], [], []
    lead_followup_selection: list[dict] = []
    lead_followup_candidates: list[dict] = []
    provenance_followup_selection: list[dict] = []
    direct_route_selection: list[dict] = []
    actor_first_telemetry: list[dict] = []
    attempted_strategies: dict[str, set[int]] = {}
    strategy_counts: dict[str, int] = {}
    executed = []

    def generic_search_budget_available(action: dict) -> bool:
        """Reserve one existing search slot for actor-first recovery.

        Semantic recovery may discover the concrete actor only after an exact
        page is fetched. Dynamic fallback and event-fingerprint searches must
        not consume the final search slot before that observed actor can be
        resolved. Actor-first actions themselves consume the reserved slot;
        the configured ceiling is unchanged.
        """
        reserve = int(
            bool(
                action.get("recovery_need_id")
                and action.get("recovery_mode") == "DISCOVER_NEW_EVENT_FOR_SEMANTIC_NEED"
                and not action.get("actor_first_search")
                and str(action.get("target_editorial_function") or "").upper() in {"ACCOUNTABILITY", "SERVICE"}
            )
        )
        return state["search_actions"] < max(0, limits["search_actions"] - reserve)

    def run_action(action: dict) -> None:
        """Execute one bounded action and retain its structured observations."""
        nonlocal observations, source_records, updates, candidate_discoveries, event_leads, lead_followup_selection, provenance_followup_selection, direct_route_selection, actor_first_telemetry
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
        # Keep retrieval telemetry separate from evidence semantics.  This
        # records whether the action produced any bounded material; it never
        # treats a result as trusted or publication-eligible.
        action["actual_information_gain"] = (
            "NEW_RETRIEVAL_MATERIAL"
            if any(str(item.get("result_type") or "").upper() not in {"DEAD_END", "IRRELEVANT", "DUPLICATE"} for item in raw_results if isinstance(item, dict))
            else "NO_NEW_INFORMATION"
        )
        feedback_leads: list[dict] = []
        listing_children: list[tuple[dict, dict]] = []
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
            # Bounded provenance recovery applies to fetched secondary or
            # unresolved leads only.  It consumes the existing follow-up cap
            # and never upgrades the originating observation's evidence role.
            if (
                action.get("action_type") in FETCH_ACTIONS
                and not action.get("discovery_only")
                and not action.get("provenance_followup")
                and not action.get("actor_first_search")
                and action.get("recovery_need_id")
                and observation.get("extraction_status") == "FETCHED"
                and state["lead_followups"] < int(config["executor"]["lead_followup_limits"][job["budget_class"]]["total"])
            ):
                candidates = [item for item in observation.get("official_link_candidates", []) if item.get("type") in {"CITED_PRIMARY_SOURCE", "OFFICIAL_SERVICE_DESTINATION", "OFFICIAL_DOCUMENT", "INSTITUTIONAL_DETAIL"} and item.get("reason") != "OFFICIAL_HOMEPAGE_NAVIGATION_ONLY" and (item.get("type") != "INSTITUTIONAL_DETAIL" or item.get("service_signal") or item.get("document_signal") or item.get("citation_signal") or str(item.get("url") or "").casefold().split("?")[0].rstrip("/").endswith(("/detail", "/notice", "/report", "/decision", "/document")))]
                for item in candidates:
                    item["url_safety"] = assess_source_url(str(item.get("url") or ""))
                unsafe_candidates = [item for item in candidates if item.get("url_safety", {}).get("state") == "URL_UNSAFE"]
                candidates = sorted(
                    [item for item in candidates if item.get("url_safety", {}).get("state") != "URL_UNSAFE"],
                    key=lambda item: ({"CITED_PRIMARY_SOURCE": 0, "OFFICIAL_SERVICE_DESTINATION": 1, "OFFICIAL_DOCUMENT": 2, "INSTITUTIONAL_DETAIL": 3}.get(item.get("type"), 9), item.get("url", "")),
                )
                target_function = str(action.get("target_editorial_function") or "").upper()
                if candidates:
                    selected = candidates[0]
                    observation["provenance_recovery_state"] = "OFFICIAL_LINK_SELECTED"
                    observation["provenance_recovery_reason"] = selected.get("type")
                    provenance_followup_selection.append({"parent_observation_id": observation.get("observation_id"), "url": selected.get("url"), "link_type": selected.get("type"), "need_id": action.get("recovery_need_id")})
                    child_action = {
                        **action,
                        "action_id": _stable_id("ACT", action["action_id"], "OFFICIAL_LINK", selected["url"]),
                        "action_type": "FETCH_URL", "target": selected["url"], "expected_result_type": "EXTRACTED_SOURCE",
                        "lead_followup": True, "provenance_followup": True, "outbound_link_type": selected.get("type"),
                        "expected_artifact_family": action.get("artifact_family") or action.get("expected_artifact_family"),
                        "originating_observation_id": observation.get("observation_id"), "navigation_parent_url": observation.get("url"),
                        "discovery_channel": f"{action.get('discovery_channel') or 'FETCH'}-official-link",
                        "query_intent": "EXPLICIT_OFFICIAL_LINK_RECOVERY", "channel_fallback": None,
                    }
                    # A cited link can legitimately be navigation-only or a
                    # portal republication.  Preserve that fetch, but do not
                    # let it suppress the bounded actor-first route when the
                    # page has an observed actor and the child did not yield
                    # validated evidence.  This is discovery/ownership
                    # recovery only; it never upgrades the parent role.
                    child_start = len(observations)
                    run_action(child_action)
                    child_items = observations[child_start:]
                    child_validated = any(
                        item.get("verification_status") == "VALIDATED_EVIDENCE"
                        and str(item.get("source_class") or "").casefold() in {"primary", "official", "independent", "paper"}
                        for item in child_items
                    )
                    recovery_actor = _recovery_actor(observation)
                    if (
                        not child_validated
                        and recovery_actor
                        and state["search_actions"] < limits["search_actions"]
                        and state["lead_followups"] < int(config["executor"]["lead_followup_limits"][job["budget_class"]]["total"])
                    ):
                        actor = recovery_actor
                        skeleton = observation.get("event_skeleton") or {}
                        query = preferred_resolution_query(observation.get("original_source_resolution")) or _actor_first_query(observation, action, skeleton)
                        if query:
                            search_action = {
                                **action,
                                "action_id": _stable_id("ACT", action["action_id"], "ACTOR_FIRST_SEARCH", actor.get("name"), selected.get("url")),
                                "action_type": "SEARCH_OFFICIAL_SOURCE", "target": None, "query": query,
                                "query_intent": "ACTOR_FIRST_CANONICAL_ARTIFACT", "query_variant": "ACTOR_ACTION_OBJECT_DATE",
                                "query_fingerprint": query_fingerprint(query, intent="ACTOR_FIRST_CANONICAL_ARTIFACT"),
                                # Actor/object terms may be English even when
                                # the originating portal route is Arabic. Let
                                # the configured multilingual backend infer
                                # the language rather than inheriting a
                                # potentially incompatible route language.
                                "search_language": "auto",
                                "actor_first_search": True, "route_scoped": False, "route_search_objective": None,
                                "lead_followup": False,
                                "originating_observation_id": observation.get("observation_id"),
                                "discovery_channel": "SEARXNG_GENERAL_SEARCH", "discovery_backends": ["searxng-general-search"],
                                "expected_result_type": "DISCOVERY_RESULT", "channel_fallback": None,
                            }
                            actor_first_telemetry.append({"parent_observation_id": observation.get("observation_id"), "actor": actor.get("name"), "query": query, "status": "SEARCH_DISPATCHED", "after_official_link": selected.get("url")})
                            before = len(observations)
                            run_action(search_action)
                            new_items = [item for item in observations[before:] if item.get("url") and item.get("observation_id") != observation.get("observation_id")]
                            exact = _select_actor_first_candidate(new_items, str(actor.get("name") or ""), search_action)
                            if exact and state["lead_followups"] < int(config["executor"]["lead_followup_limits"][job["budget_class"]]["total"]):
                                actor_first_telemetry.append({"parent_observation_id": observation.get("observation_id"), "artifact_url": exact.get("url"), "status": "ARTIFACT_FETCH_DISPATCHED", "after_official_link": selected.get("url")})
                                run_action({**search_action, "action_id": _stable_id("ACT", search_action["action_id"], "FETCH", exact["url"]), "action_type": "FETCH_URL", "target": exact["url"], "lead_followup": True, "provenance_followup": True, "actor_first_fetch": True, "route_scoped": False, "route_search_objective": None, "originating_observation_id": observation.get("observation_id"), "expected_result_type": "EXTRACTED_SOURCE", "discovery_channel": "SEARXNG_GENERAL_SEARCH-actor-first", "query_intent": "ACTOR_FIRST_EXACT_ARTIFACT", "channel_fallback": None})
                elif unsafe_candidates:
                    observation["provenance_recovery_reason"] = "OFFICIAL_LINK_REJECTED"
                    observation["provenance_recovery_detail"] = [{"url": item.get("url"), "reason": item.get("url_safety", {}).get("reason")} for item in unsafe_candidates]
                elif (actor := _recovery_actor(observation)) and state["search_actions"] < limits["search_actions"] and target_function:
                    skeleton = observation.get("event_skeleton") or {}
                    query = preferred_resolution_query(observation.get("original_source_resolution")) or _actor_first_query(observation, action, skeleton)
                    if query:
                        search_action = {
                            **action,
                            "action_id": _stable_id("ACT", action["action_id"], "ACTOR_FIRST_SEARCH", actor.get("name")),
                            "action_type": "SEARCH_OFFICIAL_SOURCE", "target": None, "query": query,
                            "query_intent": "ACTOR_FIRST_CANONICAL_ARTIFACT", "query_variant": "ACTOR_ACTION_OBJECT_DATE",
                            "query_fingerprint": query_fingerprint(query, intent="ACTOR_FIRST_CANONICAL_ARTIFACT"),
                            "search_language": "auto",
                            "actor_first_search": True, "route_scoped": False, "route_search_objective": None, "originating_observation_id": observation.get("observation_id"),
                            "lead_followup": False,
                            "discovery_channel": "SEARXNG_GENERAL_SEARCH", "discovery_backends": ["searxng-general-search"],
                            "expected_result_type": "DISCOVERY_RESULT", "channel_fallback": None,
                        }
                        actor_first_telemetry.append({"parent_observation_id": observation.get("observation_id"), "actor": actor.get("name"), "query": query, "status": "SEARCH_DISPATCHED"})
                        before = len(observations)
                        run_action(search_action)
                        new_items = [item for item in observations[before:] if item.get("url") and item.get("observation_id") != observation.get("observation_id")]
                        exact = _select_actor_first_candidate(new_items, str(actor.get("name") or ""), search_action)
                        if exact and state["lead_followups"] < int(config["executor"]["lead_followup_limits"][job["budget_class"]]["total"]):
                            actor_first_telemetry.append({"parent_observation_id": observation.get("observation_id"), "artifact_url": exact.get("url"), "status": "ARTIFACT_FETCH_DISPATCHED"})
                            run_action({**search_action, "action_id": _stable_id("ACT", search_action["action_id"], "FETCH", exact["url"]), "action_type": "FETCH_URL", "target": exact["url"], "lead_followup": True, "provenance_followup": True, "actor_first_fetch": True, "route_scoped": False, "route_search_objective": None, "originating_observation_id": observation.get("observation_id"), "expected_result_type": "EXTRACTED_SOURCE", "discovery_channel": "SEARXNG_GENERAL_SEARCH-actor-first", "query_intent": "ACTOR_FIRST_EXACT_ARTIFACT", "channel_fallback": None})
            if observation.get("navigation_type") in NAVIGATION_PAGE_TYPES or observation.get("page_type") == "LISTING_PAGE":
                child = select_listing_child_link(
                    raw,
                    semantic_target=action.get("target_editorial_function") or action.get("candidate_event_theme"),
                    edition_date=action.get("event_context", {}).get("research_date") if isinstance(action.get("event_context"), dict) else None,
                    expected_artifact_family=action.get("artifact_family") or action.get("expected_artifact_family"),
                    anchors=(action.get("event_context") or {}).get("entities", []) + (action.get("event_context") or {}).get("event_terms", []) if isinstance(action.get("event_context"), dict) else None,
                )
                service_endpoint_followup = bool(
                    child and (action.get("target_editorial_function") or "").upper() == "SERVICE"
                    and observation.get("page_type") == "CATEGORY_PAGE"
                    and child.get("candidate_type") in {"SERVICE_ENDPOINT", "APPLICATION_PORTAL", "SERVICE_DETAIL"}
                )
                # A route-scoped semantic search may already expose a strong
                # exact artifact lead in the same result set.  Preserve the
                # existing follow-up cap for that lead instead of spending it
                # on a generic listing child first.  This is retrieval order
                # only; the child remains navigation material and may still be
                # used when no exact route lead is available.
                route_exact_lead = False
                if (
                    child
                    and getattr(adapter, "follow_discovery_leads", False)
                    and action.get("route_scoped")
                    and str(action.get("target_editorial_function") or action.get("candidate_event_theme") or "").upper() in {"ACCOUNTABILITY", "SERVICE"}
                ):
                    for candidate in observations:
                        if candidate.get("observation_class") != "LEAD" or candidate.get("provenance", {}).get("action_id") != action.get("action_id"):
                            continue
                        # The just-fetched route index can score highly from
                        # its own route URL and title.  It is navigation
                        # material, however, not the competing exact lead
                        # that may justify deferring its selected child.
                        if (
                            candidate.get("url") == action.get("target")
                            and (
                                candidate.get("page_type") in NAVIGATION_PAGE_TYPES
                                or candidate.get("navigation_type") in NAVIGATION_PAGE_TYPES
                            )
                        ):
                            continue
                        priority, reasons, _ = _lead_priority(candidate, action)
                        if priority in {"HIGH", "MEDIUM"} and any(reason in reasons for reason in {"SEMANTIC_ACTION_SIGNAL", "ACTIVE_WINDOW_SIGNAL", "EXACT_ARTIFACT_PATH_SIGNAL"}):
                            route_exact_lead = True
                            break
                if route_exact_lead:
                    observation["listing_resolution_state"] = "DEFERRED_FOR_ROUTE_EXACT_LEAD"
                    observation["listing_resolution_reason"] = "ROUTE_EXACT_ARTIFACT_PRIORITY"
                elif child and (int(action.get("navigation_depth", 0) or 0) < 2 or service_endpoint_followup):
                    observation["service_endpoint_followup"] = service_endpoint_followup
                    listing_children.append((observation, child))
                elif not child:
                    observation["listing_resolution_state"] = "LISTING_NO_DETAIL_SELECTED"
                else:
                    observation["listing_resolution_state"] = "MAXIMUM_NAVIGATION_DEPTH_REACHED"
            if observation.get("event_state") == "EVENT_LEAD_DISCOVERY_ONLY":
                skeleton = observation.get("event_skeleton") or {}
                event_lead = {
                    "schema_version": 1,
                    "event_lead_id": _event_lead_id(job, action, skeleton),
                    "state": "EVENT_LEAD_DISCOVERY_ONLY",
                    "observation_id": observation["observation_id"],
                    "recovery_need_id": action.get("recovery_need_id"),
                    "recovery_mode": action.get("recovery_mode"),
                    "target_editorial_function": action.get("target_editorial_function") or action.get("event_acquisition_plan", {}).get("target_editorial_function"),
                    "event_lead_state": "NEW_RECOVERY_EVENT_LEAD" if action.get("recovery_mode") == "DISCOVER_NEW_EVENT_FOR_SEMANTIC_NEED" else "EVENT_LEAD_DISCOVERY_ONLY",
                    "desk": action.get("desk"),
                    "url": observation.get("url"),
                    "publisher_resolution": observation.get("source_resolution_state") or "PUBLISHER_UNRESOLVED",
                    "event_skeleton": deepcopy(skeleton),
                    "publication_evidence": False,
                    "cannot_close_breadth": True,
                }
                event_leads.append(event_lead)
                if not action.get("event_lead_feedback"):
                    feedback_leads.append(event_lead)
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
                if action.get("provenance_requirements", {}).get("must_be_distinct_event") and not action.get("originating_event_lead_id"):
                    value_reason, proposal_rejection = _editorial_value_reason(observation, action)
                    observation["editorial_value_reason"] = value_reason
                    observation["event_proposal_rejection"] = proposal_rejection
                    if value_reason:
                        candidate_discoveries.append({
                            "section_id": action["desk"],
                            "event_id": observation.get("related_event") or _stable_id("EVENT", observation["title"], observation["url"]),
                            "title": observation["title"], "claim": observation["claim"],
                            "source_id": patch["id"], "role": role,
                            "editorial_value_reason": value_reason,
                            "acceptable_story_roles": list(action.get("acceptable_story_roles") or []),
                        })
        # A listing/index consumes at most one additional existing follow-up
        # slot for its strongest child.  Depth is fixed at listing -> detail;
        # no recursive crawler or unbounded site traversal is introduced.
        child_cap = config["executor"]["lead_followup_limits"][job["budget_class"]]["total"]
        for listing_observation, child in listing_children:
            if state["lead_followups"] >= child_cap:
                listing_observation["listing_resolution_state"] = "CHILD_FOLLOWUP_BUDGET_EXHAUSTED"
                listing_observation["listing_resolution_reason"] = "FOLLOWUP_BUDGET_EXHAUSTED"
                continue
            child_action = {
                **action,
                "action_id": _stable_id("ACT", action["action_id"], "LISTING_CHILD", child["url"]),
                "action_type": "FETCH_URL", "target": child["url"],
                "expected_result_type": "EXTRACTED_SOURCE", "lead_followup": True,
                "discovery_only": False, "navigation_depth": 2,
                "navigation_parent_url": listing_observation.get("url"),
                "listing_temporal_context": deepcopy(listing_observation.get("temporal_relevance")),
                "navigation_type": listing_observation.get("navigation_type"),
                "expected_artifact_family": action.get("artifact_family") or action.get("expected_artifact_family"),
                "selected_target_class": child.get("candidate_class"),
                "service_endpoint_followup": bool(listing_observation.get("service_endpoint_followup")),
                "listing_parent_observation_id": listing_observation.get("observation_id"),
                "query_variant": f"{action.get('query_variant', 'LISTING')}_CHILD_DETAIL",
                "query_intent": "LISTING_TO_DETAIL_EXACT_ARTIFACT",
                "discovery_channel": f"{action.get('discovery_channel') or 'CONFIGURED'}-listing-child",
                "channel_fallback": None,
            }
            listing_observation["listing_resolution_state"] = "CHILD_DETAIL_SELECTED"
            listing_observation["selected_child_link"] = deepcopy(child)
            listing_observation["selected_target"] = child.get("url")
            listing_observation["selection_reason"] = child.get("candidate_class") or "RELEVANT_DETAIL_LINK"
            listing_observation["followup_scheduled"] = True
            listing_observation["followup_result"] = "SCHEDULED"
            if (action.get("target_editorial_function") or "").upper() == "SERVICE":
                listing_observation["service_selected_target"] = child.get("url")
                listing_observation["service_followup_result"] = "SCHEDULED"
            lead_followup_selection.append({
                "url": child["url"], "priority": "LISTING_CHILD_DETAIL",
                "need_id": action.get("recovery_need_id"),
                "source_identity": listing_observation.get("institution_identity"),
            })
            run_action(child_action)
        # A concrete event from an unknown-role source is useful discovery
        # context, not evidence.  Spend at most one ordinary bounded search
        # action on better coverage of its fingerprint.
        for event_lead in feedback_leads:
            # Mode B already has an explicit source-class ladder for finding a
            # new semantic event.  Re-querying the just-created unknown-role
            # lead here only repeats the same class and consumes a bounded
            # search slot before untouched classes run.  Keep this feedback
            # path for Mode A/event-corroboration recovery.
            if _skip_mode_b_feedback(action):
                event_lead["feedback_skipped_reason"] = "MODE_B_SOURCE_CLASS_DIVERSITY"
                continue
            skeleton = event_lead["event_skeleton"]
            query = " ".join(item for item in (
                skeleton.get("actor"), skeleton.get("action"), skeleton.get("object"),
                " ".join(skeleton.get("geography") or []), skeleton.get("published_at", "")[:7],
            ) if item).strip()
            if not query:
                continue
            feedback_action = {
                **action,
                "action_id": _stable_id("ACT", action["action_id"], "EVENT_LEAD_ALTERNATIVE", skeleton.get("event_fingerprint")),
                "action_type": "FIND_DISTINCT_EVENT",
                "target": None,
                "query": query,
                "query_intent": "EVENT_LEAD_ALTERNATIVE_COVERAGE",
                "query_variant": "EVENT_FINGERPRINT",
                "query_fingerprint": query_fingerprint(query, intent="EVENT_LEAD_ALTERNATIVE_COVERAGE"),
                "discovery_channel": "SEARXNG_GENERAL_SEARCH",
                "discovery_backends": ["searxng-general-search"],
                "expected_result_type": "DISCOVERY_RESULT",
                "channel_fallback": None,
                "event_lead_feedback": True,
                "originating_event_lead_id": event_lead["event_lead_id"],
                "originating_breadth_need_id": event_lead.get("recovery_need_id"),
            }
            if generic_search_budget_available(feedback_action):
                run_action(feedback_action)
        # A configured route is a preferred read-only channel, not a single
        # point of failure.  On a zero-yield route failure, make exactly one
        # provider-neutral discovery fallback and retain its provenance.
        fallback = action.get("channel_fallback")
        yielded = any(str(item.get("result_type") or "").upper() not in {"DEAD_END", "IRRELEVANT", "DUPLICATE"} for item in raw_results)
        # A verified route is a concrete, read-only discovery surface even
        # when the configured search backend is empty or unavailable.  Fetch
        # that route once within the existing follow-up cap; the resulting
        # page remains discovery/navigation material until exact-page evidence
        # validation runs.  This is deliberately before generic fallback so a
        # known institution is not abandoned when search returns no target.
        route = action.get("source_route") if isinstance(action.get("source_route"), dict) else None
        route_url = str((route or {}).get("url") or (route or {}).get("route_url") or "").strip()
        if (
            is_search and not yielded and action.get("route_scoped") and route_url
            and not action.get("direct_source_route")
            and state["lead_followups"] < int(config["executor"]["lead_followup_limits"][job["budget_class"]]["total"])
        ):
            safety = assess_source_url(route_url)
            if safety.get("state") == "URL_UNSAFE":
                direct_route_selection.append({"need_id": action.get("recovery_need_id"), "route_id": (route or {}).get("route_id"), "url": route_url, "status": "DIRECT_SOURCE_ROUTE_SKIPPED", "reason": safety.get("reason") or "URL_UNSAFE"})
            elif normalize_url(route_url) in seen_urls:
                direct_route_selection.append({"need_id": action.get("recovery_need_id"), "route_id": (route or {}).get("route_id"), "url": route_url, "status": "DIRECT_SOURCE_ROUTE_SKIPPED", "reason": "RESULT_FILTERED_DUPLICATE"})
            else:
                direct_route_selection.append({"need_id": action.get("recovery_need_id"), "route_id": (route or {}).get("route_id"), "url": route_url, "status": "DIRECT_SOURCE_ROUTE_SELECTED", "reason": "BACKEND_EMPTY_OR_UNAVAILABLE"})
                run_action({
                    **action,
                    "action_id": _stable_id("ACT", action["action_id"], "DIRECT_SOURCE_ROUTE", route_url),
                    "action_type": "FETCH_URL", "target": route_url,
                    "lead_followup": True, "direct_source_route": True,
                    "discovery_only": True, "provenance_followup": False,
                    "expected_result_type": "EXTRACTED_SOURCE",
                    "query_intent": "DIRECT_SOURCE_ROUTE_DISCOVERY",
                    "navigation_parent_url": None, "channel_fallback": None,
                    "discovery_channel": f"{action.get('discovery_channel') or 'SEARCH'}-direct-route",
                })
        if fallback and not yielded:
            fallback_type = str(fallback.get("action_type") or "SEARCH_DISCOVERY")
            if fallback_type in SEARCH_ACTIONS and generic_search_budget_available(action):
                fallback_action = {
                    **action,
                    "action_id": _stable_id("ACT", action["action_id"], "CHANNEL_FALLBACK", fallback_type),
                    "action_type": fallback_type,
                    "target": None,
                    "expected_result_type": "DISCOVERY_RESULT",
                    "discovery_channel": str(fallback.get("channel") or "GOOGLE_NEWS_RSS"),
                    "discovery_backends": list(fallback.get("backends") or []),
                    "query_variant": f"{action.get('query_variant', 'CONFIGURED_ROUTE')}_FALLBACK",
                    "query": action.get("channel_fallback_query") or action.get("query"),
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
        lead_followup_selection.extend([
            {"url": item.get("url"), "target_url": item.get("followup_target_url") or item.get("url"), "priority": item.get("lead_priority"), "need_id": item.get("_followup_need"), "source_identity": item.get("source_identity"), "resolution": item.get("followup_resolution_mode")}
            for item in selected_leads
        ])
        for observation in selected_leads:
            parent = parents[observation["provenance"]["action_id"]]
            target_url = observation.get("followup_target_url") or observation["url"]
            fetch_action = {
                **parent,
                "action_id": _stable_id("ACT", parent["action_id"], "FETCH_URL", target_url),
                "action_type": "FETCH_URL",
                "target": target_url,
                "lead_wrapper_url": observation["url"] if target_url != observation["url"] else None,
                "lead_followup_resolution": observation.get("followup_resolution_mode"),
                "discovery_only": bool(observation.get("followup_target_url")),
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
        # An exact page can reveal a concrete but unknown-role event and
        # trigger one alternative-coverage search.  Reconsider only its new
        # discovery leads within the same reserved follow-up budget; never
        # refetch the first-pass URLs or expand the cap.
        followed_urls = {
            item.get("url") for item in lead_followup_selection
            if item.get("url")
        }
        if state["lead_followups"] < followup_limits["total"]:
            parents = {item["action_id"]: item for item in executed}
            additional = [
                item for item in select_leads_for_followup(observations, parents, followup_limits)
                if item.get("url") not in followed_urls
            ]
            for observation in additional:
                parent = parents[observation["provenance"]["action_id"]]
                target_url = observation.get("followup_target_url") or observation["url"]
                fetch_action = {
                    **parent,
                    "action_id": _stable_id("ACT", parent["action_id"], "FETCH_URL", target_url),
                    "action_type": "FETCH_URL", "target": target_url,
                    "lead_wrapper_url": observation["url"] if target_url != observation["url"] else None,
                    "lead_followup_resolution": observation.get("followup_resolution_mode"),
                    "discovery_only": bool(observation.get("followup_target_url")),
                    "expected_result_type": "EXTRACTED_SOURCE",
                    "timeout_seconds": config["executor"]["action_timeout_seconds"],
                    "lead_followup": True, "channel_fallback": None,
                }
                lead_followup_selection.append({
                    "url": observation.get("url"), "target_url": target_url, "priority": observation.get("lead_priority"),
                    "need_id": observation.get("_followup_need"), "source_identity": observation.get("source_identity"), "resolution": observation.get("followup_resolution_mode"),
                })
                run_action(fetch_action)
                if state["lead_followups"] >= followup_limits["total"]:
                    break
    # Event leads and their alternative exact pages are evaluated together.
    # This happens before downstream recovery so a complete, claim-policy-safe
    # bundle can become one normal candidate patch rather than disconnected
    # article-level discoveries.
    event_bundles, bundle_discoveries = build_event_bundles(observations, event_leads, source_records, executed)
    # Persist need-scoped event roots alongside ordinary discovery leads.  A
    # root is bookkeeping only and cannot create a blocking P0 by itself.
    for bundle in event_bundles:
        if bundle.get("new_recovery_event") and not any(item.get("event_lead_id") == bundle.get("event_lead_id") for item in event_leads):
            skeleton = bundle.get("event_skeleton") or {}
            event_leads.append({
                "schema_version": 1,
                "event_lead_id": bundle.get("event_lead_id"),
                "state": "NEW_RECOVERY_EVENT_LEAD",
                "observation_id": (bundle.get("observations") or [None])[0],
                "recovery_need_id": bundle.get("recovery_need_id"),
                "originating_recovery_need_id": bundle.get("originating_recovery_need_id"),
                "recovery_mode": bundle.get("recovery_mode"),
                "target_editorial_function": bundle.get("target_editorial_function"),
                "desk": bundle.get("desk"),
                "url": next((item.get("url") for item in observations if item.get("observation_id") in bundle.get("observations", [])), None),
                "event_skeleton": deepcopy(skeleton),
                "publication_evidence": False,
                "blocked_event_memory": deepcopy(bundle.get("blocked_event_memory")),
                "cannot_close_breadth": True,
            })
    candidate_discoveries.extend(bundle_discoveries)
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
    configured_limits = config["executor"]["budget_action_limits"][job["budget_class"]]
    followup_capacity = config["executor"]["lead_followup_limits"][job["budget_class"]]
    function_needs = {
        str(need.get("target_editorial_function")): need.get("need_id")
        for need in job.get("recovery_needs", [])
        if need.get("target_editorial_function")
    }
    pivot_attempts = sorted({
        str(action.get("recovery_need_id"))
        for action in executed
        if action.get("pivot_mode") == "FIND_ALTERNATIVE_EVENT_FOR_SEMANTIC_NEED" and action.get("recovery_need_id")
    })
    pivot_source_classes = [
        {"need_id": str(action.get("recovery_need_id")), "source_class": str(action.get("target_source_class"))}
        for action in executed
        if action.get("pivot_mode") == "FIND_ALTERNATIVE_EVENT_FOR_SEMANTIC_NEED"
        and action.get("recovery_need_id") and action.get("target_source_class")
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
            "event_leads": event_leads,
            "event_bundles": event_bundles,
            "semantic_pivot_attempts": [{"need_id": need_id, "count": 1} for need_id in pivot_attempts],
            "semantic_pivot_source_classes": pivot_source_classes,
        },
        "observation_snapshot": build_observation_snapshot(executed, observations, event_bundles),
        # A recovery attempt is a whole bounded ladder, not a single RSS hit.
        "recovery_attempts": [item["need_id"] for item in strategy_progress if item["attempt_exhausted"]],
        "recovery_strategy_progress": strategy_progress,
        "budget_consumed": {"search_actions": state["search_actions"], "fetches": state["fetches"], "lead_followups": state["lead_followups"]},
        "budget_allocation": {
            "budget_class": job["budget_class"],
            "global_budget_before": dict(configured_limits),
            "global_budget_after": dict(configured_limits),
            "function_specific_reservations": {
                function: {"need_id": need_id, "followup_cap": followup_capacity.get("P1_BREADTH", 0)}
                for function, need_id in sorted(function_needs.items())
            },
            "generic_discovery_allocation": {"search_actions": configured_limits.get("search_actions", 0), "fetches": configured_limits.get("fetches", 0)},
            "unused_or_deferred": {"search_actions": max(0, configured_limits.get("search_actions", 0) - state["search_actions"]), "fetches": max(0, configured_limits.get("fetches", 0) - state["fetches"])},
            "budget_increased": False,
        },
        "lead_followup_selection": lead_followup_selection,
        "lead_followup_candidates": lead_followup_candidates,
        "provenance_followup_selection": provenance_followup_selection,
        "direct_route_selection": direct_route_selection,
        "actor_first_telemetry": actor_first_telemetry,
        "provenance_recovery": {
            "official_links_selected": len(provenance_followup_selection),
            "outbound_link_followups": len(provenance_followup_selection),
            "actor_first_searches": sum(1 for item in actor_first_telemetry if item.get("status") == "SEARCH_DISPATCHED"),
            "actor_first_fetches": sum(1 for item in actor_first_telemetry if item.get("status") == "ARTIFACT_FETCH_DISPATCHED"),
        },
        "provenance_telemetry": {
            "secondary_pages_inspected": sum(1 for item in observations if item.get("extraction_status") == "FETCHED" and (item.get("source_class") or "unknown").lower() == "unknown"),
            "attribution_phrases": sum(len(item.get("citation_attributions") or []) for item in observations),
            "official_links_extracted": sum(len(item.get("official_link_candidates") or []) for item in observations),
            "official_links_selected": len(provenance_followup_selection),
            "actor_first_searches": sum(1 for item in actor_first_telemetry if item.get("status") == "SEARCH_DISPATCHED"),
            "actor_first_fetches": sum(1 for item in actor_first_telemetry if item.get("status") == "ARTIFACT_FETCH_DISPATCHED"),
            "outbound_link_followups": len(provenance_followup_selection),
        },
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
    for lead in execution["source_packet_patch"].get("event_leads", []):
        if lead.get("state") not in {"EVENT_LEAD_DISCOVERY_ONLY", "NEW_RECOVERY_EVENT_LEAD"} or not lead.get("url"):
            continue
        stored = value.setdefault("discovery_event_leads", [])
        if not any(item.get("url") == lead["url"] for item in stored if isinstance(item, dict)):
            stored.append(deepcopy(lead))
    # Persist explicit run-scoped bundle diagnostics separately from sources.
    # These entries are research provenance, never a production evidence cache.
    if execution["source_packet_patch"].get("event_bundles"):
        # Event bundles are run-scoped research memory.  Epoch-1/alternative
        # work must not erase a blocked Event A when it creates Event B.
        existing_bundles = {
            str(item.get("event_lead_id")): deepcopy(item)
            for item in value.get("event_evidence_bundles", [])
            if isinstance(item, dict) and item.get("event_lead_id")
        }
        for bundle in execution["source_packet_patch"]["event_bundles"]:
            if isinstance(bundle, dict) and bundle.get("event_lead_id"):
                existing_bundles[str(bundle["event_lead_id"])] = deepcopy(bundle)
        value["event_evidence_bundles"] = [existing_bundles[key] for key in sorted(existing_bundles)]
    if execution["source_packet_patch"].get("semantic_pivot_attempts"):
        counts = {
            str(item.get("need_id")): int(item.get("count", 0))
            for item in value.get("semantic_pivot_attempts", [])
            if isinstance(item, dict) and item.get("need_id")
        }
        for item in execution["source_packet_patch"]["semantic_pivot_attempts"]:
            if isinstance(item, dict) and item.get("need_id"):
                key = str(item["need_id"])
                counts[key] = min(1, counts.get(key, 0) + int(item.get("count", 0)))
        value["semantic_pivot_attempts"] = [
            {"need_id": key, "count": counts[key]} for key in sorted(counts)
        ]
    existing_classes = {
        (str(item.get("need_id")), str(item.get("source_class")).upper())
        for item in value.get("semantic_pivot_source_classes", [])
        if isinstance(item, dict) and item.get("need_id") and item.get("source_class")
    }
    for item in execution["source_packet_patch"].get("semantic_pivot_source_classes", []):
        if isinstance(item, dict) and item.get("need_id") and item.get("source_class"):
            existing_classes.add((str(item["need_id"]), str(item["source_class"]).upper()))
    value["semantic_pivot_source_classes"] = [
        {"need_id": need_id, "source_class": source_class}
        for need_id, source_class in sorted(existing_classes)
    ]
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
        # Do not trust a malformed/out-of-band patch to bypass the categorical
        # breadth-value screen enforced by the executor.
        if not discovery.get("editorial_value_reason"):
            continue
        target_function = str(discovery.get("target_editorial_function") or "")
        if target_function and target_function not in validated_function_names({"editorial_functions": discovery.get("editorial_functions", [])}):
            continue
        section_id = discovery.get("section_id")
        # For a breadth acquisition, the producing desk is a query route, not
        # a command to place the candidate there.  Prefer a declared,
        # semantically fitting eligible desk that is presently NO_NEWS.  This
        # lets a validated new event close the gap it was asked to address,
        # while ordinary (non-breadth) discoveries retain their exact desk.
        if str(discovery.get("recovery_need_id") or "").startswith("BREADTH:"):
            eligible = {str(item) for item in discovery.get("eligible_section_ids", [])}
            for preferred in discovery.get("preferred_section_ids", []):
                candidate_section = next((item for item in value.get("sections", []) if item.get("section_id") == preferred), None)
                if candidate_section and preferred in eligible and candidate_section.get("status") == "NO_NEWS":
                    section_id = preferred
                    break
        section = next((item for item in value.get("sections", []) if item.get("section_id") == section_id), None)
        if section is None:
            continue
        candidate_id = _stable_id("CAND", section_id, discovery["event_id"])
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
                "editorial_value_reason": discovery.get("editorial_value_reason"),
                "editorial_functions": deepcopy(discovery.get("editorial_functions", [])),
                "permitted_story_roles": list(discovery.get("acceptable_story_roles") or []),
            }
            section.setdefault("candidates", []).append(candidate)
        elif discovery.get("editorial_functions"):
            candidate["editorial_functions"] = deepcopy(discovery["editorial_functions"])
        role_entries = discovery.get("source_roles") if isinstance(discovery.get("source_roles"), list) else []
        if not role_entries and discovery.get("source_id"):
            role_entries = [{"source_id": discovery["source_id"], "role": discovery.get("role")}]
        for entry in role_entries:
            if not isinstance(entry, dict) or not entry.get("source_id"):
                continue
            source_id, role = entry["source_id"], str(entry.get("role") or "").upper()
            for field in ("discovery_source_ids", "verification_source_ids"):
                if source_id not in candidate[field]:
                    candidate[field].append(source_id)
            role_field = "primary_evidence_source_ids" if role == "PRIMARY" else "independent_evidence_source_ids" if role == "INDEPENDENT" else None
            if role_field and source_id not in candidate[role_field]:
                candidate[role_field].append(source_id)
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
