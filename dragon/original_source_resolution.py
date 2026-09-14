"""Bounded, evidence-neutral resolution of attributed original sources.

This module sits between an exact fetched lead and the evidence resolver.  It
only turns page-observed attribution into auditable acquisition targets.  It
never assigns a source role, promotes a page, or treats search context as a
fact.  The returned plan is intentionally small so callers can spend their
existing follow-up budget on one genuinely new route.
"""

from __future__ import annotations

from copy import deepcopy
import re
from urllib.parse import urlsplit


RESOLUTION_FAILURES = {
    "ORIGINAL_ACTOR_UNKNOWN",
    "ORIGINAL_ACTOR_KNOWN_TARGET_UNKNOWN",
    "INSTITUTION_KNOWN_NO_ARTIFACT_ROUTE",
    "ARTIFACT_ROUTE_DISCOVERED_FETCH_FAILED",
    "ARTIFACT_FETCHED_IDENTITY_UNVERIFIED",
    "ARTIFACT_FETCHED_TEMPORALLY_IRRELEVANT",
    "ARTIFACT_FETCHED_NO_SUPPORTING_CONTENT",
    "PORTAL_REPUBLICATION_ONLY",
    "SYNDICATED_REPORT_ONLY",
    "INDEPENDENT_ORIGIN_NOT_FOUND",
    "INSTITUTIONAL_PAGE_AMBIGUOUS",
    "SEARCH_RESULT_ONLY",
    "DOCUMENT_DISCOVERED_NOT_EXTRACTABLE",
    "SOURCE_RELATIONSHIP_UNRESOLVED",
}

_FAMILY_BY_DOCUMENT = {
    "CIRCULAR": ("OFFICIAL_CIRCULAR", "DIRECTIVES", "NOTICES"),
    "DIRECTIVE": ("DIRECTIVES", "OFFICIAL_NOTICES", "DECISIONS"),
    "COMMUNIQUE": ("PRESS_RELEASES", "OFFICIAL_COMMUNIQUES", "NOTICES"),
    "DECISION": ("DECISIONS", "REGULATORY_ACTIONS", "COURT_DECISIONS"),
    "SERVICE_NOTICE": ("SERVICE_NOTICES", "NOTICES", "SERVICE_PORTAL"),
}
_FAMILY_MARKERS = {
    "REPORT": ("report", "rapport", "تقرير"),
    "AUDIT": ("audit", "inspection", "افتـحاص", "افتحاص", "تدقيق"),
    "SERVICE": ("service", "procedure", "deadline", "registration", "منصة", "إشعار", "آخر أجل"),
    "PROSECUTION": ("prosecution", "prosecutor", "parquet", "النيابة", "دورية", "شكايات"),
}


def _page_text(raw: dict) -> str:
    return " ".join(
        str(raw.get(key) or "")
        for key in ("title", "text", "extracted_text", "content", "claim")
    ).strip()


def _observed_actor(raw: dict, skeleton: dict | None = None) -> tuple[str | None, str | None]:
    """Return an actor only when it is page-derived, never query-derived."""
    explicit = raw.get("stated_issuing_authority") or raw.get("issuing_institution")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip(), "PAGE_TEXT_EXPLICIT"
    refs = raw.get("document_references")
    if isinstance(refs, list):
        for ref in refs:
            if isinstance(ref, dict) and isinstance(ref.get("issuer"), str) and ref.get("issuer"):
                if str(ref.get("issuer_provenance") or "").startswith("PAGE_"):
                    return str(ref["issuer"]).strip(), str(ref.get("issuer_provenance"))
    if isinstance(skeleton, dict):
        provenance = skeleton.get("field_provenance") or {}
        actor = skeleton.get("actor")
        if actor and str(provenance.get("actor") or "").startswith("PAGE_"):
            return str(actor).strip(), str(provenance.get("actor"))
    # Keep the small known-actor extractor useful even when the caller has not
    # already built a skeleton.  Import lazily to avoid an import cycle.
    try:
        from dragon.institutional_navigation import extract_actor_attributions
        for item in extract_actor_attributions(raw).get("actors", []):
            if item.get("name") and str(item.get("provenance") or "").startswith("TEXT"):
                return str(item["name"]).strip(), "PAGE_TEXT_INFERRED"
    except Exception:  # pragma: no cover - defensive audit metadata only
        pass
    return None, None


def _observed_document_refs(raw: dict) -> list[dict]:
    refs = raw.get("document_references")
    if isinstance(refs, list):
        return [deepcopy(item) for item in refs if isinstance(item, dict)]
    try:
        from dragon.institutional_navigation import extract_document_references
        return extract_document_references(raw)
    except Exception:  # pragma: no cover - metadata must not break fetching
        return []


def _artifact_families(text: str, refs: list[dict]) -> list[str]:
    families: list[str] = []
    for ref in refs:
        families.extend(_FAMILY_BY_DOCUMENT.get(str(ref.get("document_type") or "").upper(), ()))
    lowered = text.casefold()
    for family, markers in _FAMILY_MARKERS.items():
        if any(marker.casefold() in lowered for marker in markers):
            families.append(family)
    return list(dict.fromkeys(families))[:8]


def _claim_type(text: str, refs: list[dict]) -> str:
    lowered = text.casefold()
    if any(token in lowered for token in ("prosecution", "prosecutor", "parquet", "النيابة", "دورية", "شكايات")):
        return "PROSECUTION_CRIMINAL_ACTION"
    if any(token in lowered for token in ("service", "procedure", "deadline", "registration", "منصة", "إشعار", "آخر أجل")):
        return "SERVICE_FACT"
    if any(token in lowered for token in ("audit", "inspection", "افتحاص", "تدقيق", "تقرير")):
        return "AUDIT_OR_OVERSIGHT"
    if any(str(item.get("document_type") or "").upper() in {"DECISION", "DIRECTIVE", "CIRCULAR"} for item in refs):
        return "INSTITUTIONAL_ACTION"
    return "UNCLASSIFIED_INSTITUTIONAL_CLAIM"


def _route_origin(route: dict) -> str | None:
    value = str(route.get("origin") or route.get("canonical_domain") or "").strip().casefold().strip(".")
    if value:
        return value
    return (urlsplit(str(route.get("url") or route.get("route_url") or "")).hostname or "").casefold() or None


def _route_matches_actor(route: dict, actor: str) -> bool:
    if not actor:
        return False
    haystack = " ".join(
        str(route.get(key) or "")
        for key in ("name", "institution", "source_name", "authority_class", "source_id")
    ).casefold()
    words = [word for word in re.findall(r"[\w\u0600-\u06ff-]+", actor.casefold()) if len(word) > 2]
    return bool(words and all(word in haystack for word in words)) or actor.casefold() in haystack


def _date_terms(raw: dict, skeleton: dict | None) -> list[str]:
    values = []
    for value in (raw.get("published_at"), (skeleton or {}).get("published_at")):
        match = re.search(r"(\d{4}-\d{2}(?:-\d{2})?)", str(value or ""))
        if match:
            values.append(match.group(1))
    text = _page_text(raw)
    # Keep explicit years/months as discovery terms; never invent an event
    # date from the recovery job or edition date.
    values.extend(re.findall(r"\b(?:19|20)\d{2}(?:[-/]\d{1,2}(?:[-/]\d{1,2})?)?\b", text))
    return list(dict.fromkeys(values))[:3]


def build_original_source_resolution(raw: dict, action: dict | None = None, *, routes: list[dict] | None = None, skeleton: dict | None = None) -> dict:
    """Build a bounded acquisition plan from exact-page observations.

    ``action`` contributes only routing metadata (route list and target label)
    and is explicitly namespaced in the result.  No query, target actor, or
    target function is copied into observed facts.
    """
    action = action if isinstance(action, dict) else {}
    text = _page_text(raw)
    refs = _observed_document_refs(raw)
    actor, actor_provenance = _observed_actor(raw, skeleton)
    observed_action = str((skeleton or {}).get("action") or "").strip() if isinstance(skeleton, dict) else ""
    observed_object = str((skeleton or {}).get("object") or "").strip() if isinstance(skeleton, dict) else ""
    dates = _date_terms(raw, skeleton)
    families = _artifact_families(text, refs)
    claim_type = _claim_type(text, refs)
    route_values = [item for item in (routes or []) if isinstance(item, dict)]
    if not route_values and isinstance(action.get("source_route"), dict):
        route_values = [action["source_route"]]
    matched_routes = [route for route in route_values if actor and _route_matches_actor(route, actor)]
    # A portal route is still useful as a search surface when the issuing
    # actor is not the portal publisher; retain it as a discovery target but
    # mark the ownership relationship explicitly unresolved.
    if not matched_routes and route_values and any(str(item.get("route_type") or "") for item in route_values):
        matched_routes = route_values[:1]
    targets = []
    for route in matched_routes[:2]:
        url = str(route.get("url") or route.get("route_url") or "").strip()
        origin = _route_origin(route)
        if not url and not origin:
            continue
        targets.append({
            "route_id": route.get("route_id"), "url": url or None, "origin": origin,
            "route_type": route.get("route_type"), "source_id": route.get("source_id"),
            "ownership": "ACTOR_ROUTE_MATCH" if _route_matches_actor(route, actor or "") else "PORTAL_SURFACE_ONLY",
            "discovery_only": True,
        })
    query_parts = [actor, observed_action, observed_object, *families[:2], *dates[:1]]
    base = " ".join(dict.fromkeys(item for item in query_parts if item)).strip()
    query_variants = []
    for target in targets[:2]:
        prefix = f"site:{target['origin']} " if target.get("origin") else ""
        query_variants.append({"query": f"{prefix}{base}".strip(), "route_id": target.get("route_id"), "language": action.get("search_language") or "auto", "purpose": "ORIGINAL_ARTIFACT_DISCOVERY"})
    if base and not query_variants:
        query_variants.append({"query": base, "route_id": None, "language": action.get("search_language") or "auto", "purpose": "ORIGINAL_ARTIFACT_DISCOVERY"})
    if not actor:
        failure = "ORIGINAL_ACTOR_UNKNOWN"
    elif not targets:
        failure = "INSTITUTION_KNOWN_NO_ARTIFACT_ROUTE"
    elif not query_variants:
        failure = "ORIGINAL_ACTOR_KNOWN_TARGET_UNKNOWN"
    else:
        failure = None
    edges = []
    if raw.get("canonical_url") or raw.get("url"):
        edges.append({"type": "DISCOVERY_SOURCE", "from": raw.get("canonical_url") or raw.get("url"), "to": "ATTRIBUTED_ORIGINAL_ACTOR" if actor else "UNRESOLVED_ACTOR"})
    if actor:
        edges.append({"type": "ATTRIBUTED_ORIGINAL_ACTOR", "from": actor, "to": "RESOLVED_PRIMARY_TARGET" if targets else "UNRESOLVED_PRIMARY_TARGET", "provenance": actor_provenance})
    for target in targets:
        edges.append({"type": "CANDIDATE_ARTIFACT_ROUTE", "from": actor, "to": target.get("url") or target.get("origin"), "route_id": target.get("route_id"), "ownership": target.get("ownership")})
    return {
        "schema_version": 1,
        "status": "TARGETS_READY" if targets else "UNRESOLVED",
        "failure_category": failure,
        "observed": {
            "actor": actor, "actor_provenance": actor_provenance,
            "action": observed_action or None, "object": observed_object or None,
            "dates": dates, "claim_type": claim_type,
            "document_references": refs, "artifact_families": families,
        },
        "search_context": {
            "target_function": action.get("target_editorial_function"),
            "target_need_id": action.get("recovery_need_id"),
            "query_variants": deepcopy(query_variants),
        },
        "candidate_targets": targets,
        "attempt_limit": min(2, len(query_variants)),
        "provenance_edges": edges,
        "original_artifact_state": "ORIGINAL_ARTIFACT_SEARCHABLE" if targets else "ORIGINAL_ARTIFACT_NOT_FOUND",
        "role_effect": "NONE_UNTIL_EXACT_TARGET_VALIDATED",
    }


def resolution_failure_for_observation(observation: dict) -> str:
    """Return a precise internal blocker while retaining public MISSING_PRIMARY."""
    if not isinstance(observation, dict):
        return "SOURCE_RELATIONSHIP_UNRESOLVED"
    resolution = observation.get("original_source_resolution") if isinstance(observation.get("original_source_resolution"), dict) else {}
    if resolution.get("failure_category"):
        return str(resolution["failure_category"])
    state = str(observation.get("validation_state") or "")
    reason = str(observation.get("validation_reason") or "")
    if state == "SOURCE_UNKNOWN":
        return "ARTIFACT_FETCHED_IDENTITY_UNVERIFIED"
    if "TEMPOR" in reason:
        return "ARTIFACT_FETCHED_TEMPORALLY_IRRELEVANT"
    if state in {"WRONG_EVENT", "WRONG_ROLE"}:
        return "ARTIFACT_FETCHED_NO_SUPPORTING_CONTENT"
    if observation.get("content_origin") and observation.get("original_artifact_state") == "ORIGINAL_ARTIFACT_NOT_FOUND":
        return "PORTAL_REPUBLICATION_ONLY"
    return "SOURCE_RELATIONSHIP_UNRESOLVED"


def preferred_resolution_query(plan: dict | None) -> str | None:
    """Return the first bounded original-artifact query, if one exists."""
    if not isinstance(plan, dict):
        return None
    variants = plan.get("search_context", {}).get("query_variants", [])
    for item in variants if isinstance(variants, list) else []:
        query = str(item.get("query") or "").strip() if isinstance(item, dict) else ""
        if query:
            return query
    return None


# Friendly aliases for callers/tests that use the architecture vocabulary.
resolve_original_source = build_original_source_resolution
build_source_resolution_plan = build_original_source_resolution
