"""Configuration-backed editorial-desk source coverage.

This is deliberately a coverage *map*, not a truth source.  It tells the
research and recovery planners which configured routes may be useful for a
desk.  Every discovered item still needs exact-page provenance and separate
primary/independent verification before it can support publication.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse
from datetime import datetime, timezone
from copy import deepcopy
from urllib.request import Request, urlopen

import yaml


class SourceCoverageError(RuntimeError):
    pass


REQUIRED_SOURCE_FIELDS = {
    "source_id", "name", "url", "role", "origin", "authority_class",
    "primary_capable", "independent_reporting_capable", "discovery_only",
    "enabled", "required", "retrieval_method", "extraction_method",
    "freshness",
}
REQUIRED_DESK_FIELDS = {"section_id", "source_ids", "coverage_status", "recovery_focus"}
VALID_ROLES = {"PRIMARY", "INDEPENDENT", "DISCOVERY"}
ROUTE_FIELDS = {
    "route_id", "source_id", "route_url", "route_type", "supported_languages",
    "semantic_capabilities", "page_type_expected", "navigation_depth", "status",
    "verification_provenance", "last_verified",
}
VALID_ROUTE_TYPES = {
    "NEWS_LISTING", "PRESS_RELEASES", "PUBLICATIONS", "REPORTS", "DECISIONS",
    "NOTICES", "SERVICE_PORTAL", "CONSULTATIONS", "PROCUREMENT_RESULTS",
    "AUDIT_PUBLICATIONS", "COURT_DECISIONS", "REGULATORY_ACTIONS", "OTHER_PUBLIC_INDEX",
}
VALID_ROUTE_STATUS = {"VERIFIED_WORKING", "VERIFIED_DISCOVERY_ONLY", "TRANSIENT_FAILURE", "STALE", "CURRENTLY_UNUSABLE", "UNKNOWN"}
VALID_SOURCE_FAMILIES = {
    "OFFICIAL_GOVERNMENT", "PARLIAMENTARY", "JUDICIAL_PROSECUTORIAL", "REGULATORY",
    "PUBLIC_STATISTICS", "PUBLIC_FINANCE", "PUBLIC_PROCUREMENT", "LOCAL_GOVERNMENT",
    "PUBLIC_OPERATOR", "MOROCCAN_CIVIL_SOCIETY", "MOROCCAN_UNION",
    "MOROCCAN_PROFESSIONAL_BODY", "MOROCCAN_THINK_TANK", "INTERNATIONAL_ORGANIZATION",
    "ACADEMIC_RESEARCH", "INDEPENDENT_MEDIA", "WIRE_NEWS_AGENCY", "ARCHIVE_PUBLIC_RECORD",
    "SOCIAL_OFFICIAL", "SOCIAL_NONOFFICIAL", "DISCOVERY_ONLY",
}

# Need-scoped routing is execution metadata only.  It determines which
# configured families get an opportunity inside the unchanged action budget;
# it never confers an evidence role on a fetched artifact.
NEED_SOURCE_FAMILY_ORDER = {
    "ACCOUNTABILITY": (
        "JUDICIAL_PROSECUTORIAL", "REGULATORY", "PUBLIC_FINANCE",
        "PUBLIC_PROCUREMENT", "PARLIAMENTARY", "MOROCCAN_CIVIL_SOCIETY",
        "INDEPENDENT_MEDIA", "OFFICIAL_GOVERNMENT",
    ),
    "SERVICE": (
        "OFFICIAL_GOVERNMENT", "PUBLIC_OPERATOR", "PUBLIC_STATISTICS",
        "LOCAL_GOVERNMENT", "PUBLIC_FINANCE", "MOROCCAN_UNION",
        "MOROCCAN_CIVIL_SOCIETY", "INDEPENDENT_MEDIA",
    ),
}


def need_source_family_policy(function: str | None) -> list[str]:
    """Return deterministic family priority for a semantic recovery need."""
    return list(NEED_SOURCE_FAMILY_ORDER.get(str(function or "").upper(), ()))


def route_source_family(route: dict | None) -> str:
    """Read a route's normalized family without treating it as trust."""
    if not isinstance(route, dict):
        return "UNKNOWN"
    family = str(route.get("source_family") or "").upper().strip()
    return family if family in VALID_SOURCE_FAMILIES else "UNKNOWN"


def _default_source_family(source: dict) -> str:
    """Derive a conservative family for legacy entries without changing roles."""
    if source.get("discovery_only"):
        return "DISCOVERY_ONLY"
    if source.get("role") == "INDEPENDENT":
        return "INDEPENDENT_MEDIA"
    authority = str(source.get("authority_class") or "").upper()
    if "STAT" in authority or source.get("source_id") == "hcp":
        return "PUBLIC_STATISTICS"
    if "PROCURE" in authority or source.get("source_id") == "public-procurement":
        return "PUBLIC_PROCUREMENT"
    if source.get("source_id") in {"un-news", "un-ocha-opt", "who-news", "unesco-culture", "world-bank-morocco"}:
        return "INTERNATIONAL_ORGANIZATION"
    if source.get("source_id") in {"nature-research", "imist-journals"}:
        return "ACADEMIC_RESEARCH"
    if source.get("source_id") in {"archives-maroc", "bnrm"}:
        return "ARCHIVE_PUBLIC_RECORD"
    return "OFFICIAL_GOVERNMENT"


def validate_source_registry(coverage: dict) -> dict:
    """Validate/normalize source-intelligence metadata without granting evidence."""
    if not isinstance(coverage, dict):
        raise SourceCoverageError("SOURCE_REGISTRY_ROOT_INVALID")
    sources = coverage.get("sources")
    if not isinstance(sources, list):
        raise SourceCoverageError("SOURCE_REGISTRY_SOURCES_INVALID")
    normalized = deepcopy(coverage)
    profiles = normalized.get("source_profiles") or []
    if not isinstance(profiles, list):
        raise SourceCoverageError("SOURCE_REGISTRY_PROFILES_INVALID")
    source_ids = {item.get("source_id") for item in sources if isinstance(item, dict)}
    seen: set[str] = set()
    for profile in profiles:
        if not isinstance(profile, dict):
            raise SourceCoverageError("SOURCE_REGISTRY_PROFILE_INVALID")
        identifier = profile.get("source_id")
        if not isinstance(identifier, str) or not identifier or identifier in seen:
            raise SourceCoverageError("SOURCE_REGISTRY_PROFILE_ID_INVALID")
        if identifier not in source_ids:
            raise SourceCoverageError("SOURCE_REGISTRY_PROFILE_SOURCE_UNKNOWN")
        family = profile.get("source_family")
        if family not in VALID_SOURCE_FAMILIES:
            raise SourceCoverageError("SOURCE_REGISTRY_FAMILY_INVALID")
        if not isinstance(profile.get("authority_scope"), str) or not profile["authority_scope"].strip():
            raise SourceCoverageError("SOURCE_REGISTRY_AUTHORITY_SCOPE_INVALID")
        if not isinstance(profile.get("languages"), list) or not profile["languages"]:
            raise SourceCoverageError("SOURCE_REGISTRY_LANGUAGES_INVALID")
        routes = profile.get("routes") or {}
        if not isinstance(routes, dict):
            raise SourceCoverageError("SOURCE_REGISTRY_ROUTES_INVALID")
        for route_name, route_url in routes.items():
            if not isinstance(route_name, str) or not route_name or not _https(route_url):
                raise SourceCoverageError("SOURCE_REGISTRY_ROUTE_INVALID")
        seen.add(identifier)
    # Legacy entries are intentionally normalized in-memory only.  This gives
    # callers a complete inventory while preserving the committed schema.
    profile_by_id = {item["source_id"]: item for item in profiles}
    for source in normalized["sources"]:
        profile = profile_by_id.get(source.get("source_id"), {})
        source.setdefault("source_family", profile.get("source_family", _default_source_family(source)))
        source.setdefault("authority_scope", profile.get("authority_scope", "unspecified"))
        source.setdefault("publisher", profile.get("publisher", source.get("name")))
        source.setdefault("languages", profile.get("languages", ["ar", "fr", "en"]))
        source.setdefault("routes", profile.get("routes", {"homepage": source.get("url")}))
    normalized["source_profiles"] = profiles
    return normalized


def build_source_coverage_report(
    coverage: dict,
    *,
    edition_date: str | None = None,
    run_id: str | None = None,
    route_health: list[dict] | None = None,
) -> dict:
    """Build a deterministic coverage inventory; route metadata is not evidence."""
    normalized = validate_source_registry(coverage)
    sources = normalized["sources"]
    routes = normalized.get("institution_routes", [])
    enabled = [item for item in sources if item.get("enabled") is True]
    active_route_ids = {item.get("route_id") for item in routes if item.get("status") in {"VERIFIED_WORKING", "VERIFIED_DISCOVERY_ONLY"}}
    health = [deepcopy(item) for item in (route_health or []) if isinstance(item, dict)]
    working_ids = {item.get("source_id") for item in health if item.get("status") == "VERIFIED_WORKING"}
    family_counts: dict[str, int] = {}
    for source in sources:
        family = source.get("source_family", _default_source_family(source))
        family_counts[family] = family_counts.get(family, 0) + 1
    profiles_by_id = {item.get("source_id"): item for item in normalized.get("source_profiles", []) if isinstance(item, dict)}
    health_by_route = {item.get("route_id"): item for item in health}
    usability = []
    for source in sources:
        source_routes = [item for item in routes if item.get("source_id") == source.get("source_id")]
        route_health_states = [health_by_route.get(item.get("route_id"), {}).get("status") for item in source_routes]
        if any(state == "VERIFIED_WORKING" for state in route_health_states):
            route_types = {item.get("route_type") for item in source_routes}
            state = "DOCUMENT_USABLE" if route_types & {"PUBLICATIONS", "REPORTS", "DECISIONS", "AUDIT_PUBLICATIONS", "COURT_DECISIONS", "REGULATORY_ACTIONS"} else "DETAIL_USABLE"
        elif any(state in {"TRANSIENT_FAILURE", "STALE", "CURRENTLY_UNUSABLE"} for state in route_health_states):
            state = "DEGRADED"
        elif source.get("discovery_only"):
            state = "DISCOVERY_ONLY"
        else:
            state = "DISCOVERY_ONLY" if not source_routes else "DEGRADED"
        usability.append({"source_id": source.get("source_id"), "name": source.get("name"), "state": state, "active": source.get("enabled") is True})
    route_counts = {
        "with_feed": sum(bool(profiles_by_id.get(item.get("source_id"), {}).get("routes", {}).get("rss")) for item in sources),
        "with_detail_route": sum(item.get("route_type") not in {"NEWS_LISTING", "OTHER_PUBLIC_INDEX"} for item in routes),
        "with_document_route": sum(item.get("route_type") in {"PUBLICATIONS", "REPORTS", "DECISIONS", "AUDIT_PUBLICATIONS", "COURT_DECISIONS", "REGULATORY_ACTIONS"} for item in routes),
        "with_dataset_route": sum("DATASET" in (item.get("semantic_capabilities") or []) for item in routes),
    }
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "edition_date": edition_date,
        "run_id": run_id,
        "configured_source_count": len(sources),
        "active_source_count": len(enabled),
        "reachable_source_count": len(working_ids) if health else None,
        "active_route_count": len(active_route_ids),
        "route_counts": route_counts,
        "source_families": dict(sorted(family_counts.items())),
        "sources": [
            {
                "source_id": item.get("source_id"), "name": item.get("name"),
                "publisher": item.get("publisher", item.get("name")),
                "source_family": item.get("source_family", _default_source_family(item)),
                "authority_scope": item.get("authority_scope", "unspecified"),
                "role": item.get("role"), "enabled": item.get("enabled"),
                "routes": [deepcopy(route) for route in routes if route.get("source_id") == item.get("source_id")],
            }
            for item in sources
        ],
        "route_health": health,
        "source_usability": usability,
        "unreachable_sources": sorted({item.get("route_id") for item in health if item.get("status") in {"TRANSIENT_FAILURE", "CURRENTLY_UNUSABLE", "UNREACHABLE"}}),
        "discovery_only_sources": sorted(item.get("source_id") for item in sources if item.get("discovery_only")),
        "research_semantics": deepcopy(normalized.get("research_semantics", {})),
    }


def probe_source_routes(
    coverage: dict,
    *,
    transport=None,
    timeout_seconds: int = 8,
    max_routes: int = 32,
) -> list[dict]:
    """Perform a bounded, read-only health probe of configured public routes.

    The result is execution telemetry only.  A working route is never treated
    as an evidence role or a source-credibility score.
    """
    normalized = validate_source_registry(coverage)
    routes = [
        item for item in normalized.get("institution_routes", [])
        if item.get("status") in {"VERIFIED_WORKING", "VERIFIED_DISCOVERY_ONLY"}
    ][:max(0, int(max_routes))]
    if transport is None:
        def transport(url: str, timeout: int):
            request = Request(url, headers={"User-Agent": "DRAGON-source-health/1.0"}, method="HEAD")
            with urlopen(request, timeout=timeout) as response:  # nosec B310 - URLs are validated HTTPS routes
                return int(getattr(response, "status", 200)), str(response.geturl())
    results = []
    for route in routes:
        url = route["route_url"]
        started = datetime.now(timezone.utc)
        try:
            outcome = transport(url, timeout_seconds)
            if isinstance(outcome, tuple):
                status_code, final_url = outcome[0], outcome[1] if len(outcome) > 1 else url
            else:
                status_code, final_url = getattr(outcome, "status", 200), getattr(outcome, "url", url)
            ok = 200 <= int(status_code) < 400
            status = "VERIFIED_WORKING" if ok else "TRANSIENT_FAILURE"
            reason = None if ok else f"HTTP_{status_code}"
        except Exception as exc:  # telemetry must classify failures, not abort the run
            status, reason, status_code, final_url = "TRANSIENT_FAILURE", type(exc).__name__, None, url
        results.append({
            "route_id": route["route_id"], "source_id": route["source_id"],
            "url": url, "status": status, "http_status": status_code,
            "final_url": str(final_url), "reason": reason,
            "checked_at": started.isoformat(),
        })
    return results


def _https(value: object) -> bool:
    parsed = urlparse(str(value or ""))
    return parsed.scheme == "https" and bool(parsed.netloc)


def load_source_coverage(path: Path, expected_sections: set[str]) -> dict:
    """Load and strictly validate the committed desk/source coverage map."""
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise SourceCoverageError(str(exc)) from exc
    if not isinstance(value, dict) or value.get("version") != 1:
        raise SourceCoverageError("SOURCE_COVERAGE_ROOT_INVALID")
    semantics = value.get("research_semantics")
    if semantics != {
        "allow_open_discovery": True,
        "configured_sources_are": "preferred_seeds_not_whitelist",
        "open_discovery_mode": "read_only_research",
        "unknown_sources_begin_as": "LEAD",
        "untrusted_content_may_change_policy": False,
        "discovery_is_publication_evidence": False,
    }:
        raise SourceCoverageError("SOURCE_COVERAGE_RESEARCH_SEMANTICS_INVALID")
    sources = value.get("sources")
    desks = value.get("desks")
    if not isinstance(sources, list) or not isinstance(desks, list):
        raise SourceCoverageError("SOURCE_COVERAGE_COLLECTIONS_INVALID")
    source_ids: set[str] = set()
    for source in sources:
        if not isinstance(source, dict) or set(source) != REQUIRED_SOURCE_FIELDS:
            raise SourceCoverageError("SOURCE_COVERAGE_SOURCE_FIELDS_INVALID")
        identifier = source["source_id"]
        if not isinstance(identifier, str) or not identifier or identifier in source_ids:
            raise SourceCoverageError("SOURCE_COVERAGE_SOURCE_ID_INVALID")
        if source["role"] not in VALID_ROLES or not _https(source["url"]):
            raise SourceCoverageError("SOURCE_COVERAGE_SOURCE_ROUTE_INVALID")
        if not isinstance(source["origin"], str) or not source["origin"].strip():
            raise SourceCoverageError("SOURCE_COVERAGE_SOURCE_ORIGIN_INVALID")
        flags = ("primary_capable", "independent_reporting_capable", "discovery_only", "enabled", "required")
        if any(not isinstance(source[key], bool) for key in flags):
            raise SourceCoverageError("SOURCE_COVERAGE_SOURCE_FLAGS_INVALID")
        if source["discovery_only"] and (source["primary_capable"] or source["independent_reporting_capable"]):
            raise SourceCoverageError("SOURCE_COVERAGE_DISCOVERY_ROLE_INVALID")
        if any(not isinstance(source[key], str) or not source[key].strip() for key in ("name", "authority_class", "retrieval_method", "extraction_method", "freshness")):
            raise SourceCoverageError("SOURCE_COVERAGE_SOURCE_METADATA_INVALID")
        source_ids.add(identifier)
    sources_by_id = {item["source_id"]: item for item in sources}
    desk_ids: set[str] = set()
    for desk in desks:
        if not isinstance(desk, dict) or set(desk) != REQUIRED_DESK_FIELDS:
            raise SourceCoverageError("SOURCE_COVERAGE_DESK_FIELDS_INVALID")
        identifier = desk["section_id"]
        route_ids = desk["source_ids"]
        if (
            not isinstance(identifier, str)
            or identifier in desk_ids
            or not isinstance(route_ids, list)
            or not route_ids
            or len(route_ids) != len(set(route_ids))
            or not set(route_ids).issubset(source_ids)
            or desk["coverage_status"] not in {"COVERED", "PARTIAL", "GAP"}
            or not isinstance(desk["recovery_focus"], list)
            or not all(isinstance(item, str) and item for item in desk["recovery_focus"])
        ):
            raise SourceCoverageError("SOURCE_COVERAGE_DESK_INVALID")
        routes = [sources_by_id[source_id] for source_id in route_ids]
        if desk["coverage_status"] == "COVERED" and not (
            any(item["primary_capable"] for item in routes)
            and any(item["independent_reporting_capable"] for item in routes)
        ):
            raise SourceCoverageError("SOURCE_COVERAGE_COVERED_DESK_UNSUPPORTED")
        desk_ids.add(identifier)
    routes = value.get("institution_routes", [])
    if not isinstance(routes, list):
        raise SourceCoverageError("SOURCE_COVERAGE_ROUTE_REGISTRY_INVALID")
    route_ids: set[str] = set()
    for route in routes:
        if not isinstance(route, dict) or set(route) != ROUTE_FIELDS:
            raise SourceCoverageError("SOURCE_COVERAGE_ROUTE_FIELDS_INVALID")
        route_id = route.get("route_id")
        if not isinstance(route_id, str) or not route_id or route_id in route_ids:
            raise SourceCoverageError("SOURCE_COVERAGE_ROUTE_ID_INVALID")
        if route.get("source_id") not in source_ids or not _https(route.get("route_url")):
            raise SourceCoverageError("SOURCE_COVERAGE_ROUTE_TARGET_INVALID")
        if route.get("route_type") not in VALID_ROUTE_TYPES or route.get("status") not in VALID_ROUTE_STATUS:
            raise SourceCoverageError("SOURCE_COVERAGE_ROUTE_CLASS_INVALID")
        if not isinstance(route.get("supported_languages"), list) or not route["supported_languages"] or not all(isinstance(item, str) and item for item in route["supported_languages"]):
            raise SourceCoverageError("SOURCE_COVERAGE_ROUTE_LANGUAGE_INVALID")
        if not isinstance(route.get("semantic_capabilities"), list) or not route["semantic_capabilities"] or not all(isinstance(item, str) and item for item in route["semantic_capabilities"]):
            raise SourceCoverageError("SOURCE_COVERAGE_ROUTE_CAPABILITY_INVALID")
        if not isinstance(route.get("page_type_expected"), str) or not route["page_type_expected"].strip():
            raise SourceCoverageError("SOURCE_COVERAGE_ROUTE_PAGE_TYPE_INVALID")
        if not isinstance(route.get("navigation_depth"), int) or not 0 <= route["navigation_depth"] <= 2:
            raise SourceCoverageError("SOURCE_COVERAGE_ROUTE_DEPTH_INVALID")
        if not isinstance(route.get("verification_provenance"), str) or not route["verification_provenance"].strip() or not isinstance(route.get("last_verified"), str) or not route["last_verified"].strip():
            raise SourceCoverageError("SOURCE_COVERAGE_ROUTE_PROVENANCE_INVALID")
        route_ids.add(route_id)
    if desk_ids != expected_sections:
        raise SourceCoverageError(
            "SOURCE_COVERAGE_SECTION_INVENTORY_INVALID: "
            f"missing={sorted(expected_sections - desk_ids)} unknown={sorted(desk_ids - expected_sections)}"
        )
    return value


def desk_recovery_context(coverage: dict, section_id: str, *, capability: str | None = None) -> dict:
    """Return only bounded configured routing hints for one recovery need."""
    desk = next(item for item in coverage["desks"] if item["section_id"] == section_id)
    normalized = validate_source_registry(coverage)
    sources = {item["source_id"]: item for item in normalized["sources"]}
    routes = [sources[source_id] for source_id in desk["source_ids"]]
    route_source_ids = {route["source_id"] for route in routes}
    registry = [
        item for item in normalized.get("institution_routes", [])
        if item.get("status") in {"VERIFIED_WORKING", "VERIFIED_DISCOVERY_ONLY"}
        and (item.get("source_id") in route_source_ids or (capability and capability in (item.get("semantic_capabilities") or [])))
    ]
    if capability:
        for source_id in sorted({item.get("source_id") for item in registry if item.get("source_id")} - route_source_ids):
            if source_id in sources:
                routes.append(sources[source_id])
    registry_by_source: dict[str, list[dict]] = {}
    for route in registry:
        registry_by_source.setdefault(route["source_id"], []).append(route)
    configured_routes = []
    for item in routes:
        route_variants = registry_by_source.get(item["source_id"]) or [None]
        for variant in route_variants:
            configured_routes.append({
                "source_id": item["source_id"], "name": item["name"],
                "url": variant.get("route_url") if variant else item["url"],
                "origin": item["origin"], "role": item["role"], "enabled": item["enabled"],
                "authority_class": item["authority_class"],
                "source_family": item.get("source_family", _default_source_family(item)),
                "authority_scope": item.get("authority_scope", "unspecified"),
                "publisher": item.get("publisher", item.get("name")),
                "route_languages": list(item.get("languages", ["ar", "fr", "en"])),
                "source_class": "OFFICIAL_INSTITUTION" if item["role"] == "PRIMARY" else "INDEPENDENT_NEWSROOM",
                "discovery_only": item["discovery_only"],
                "route_id": variant.get("route_id") if variant else f"{item['source_id']}-canonical",
                "route_type": variant.get("route_type") if variant else "OTHER_PUBLIC_INDEX",
                "supported_languages": list(variant.get("supported_languages", ["ar", "fr", "en"])) if variant else ["ar", "fr", "en"],
                "semantic_capabilities": list(variant.get("semantic_capabilities", [])) if variant else [],
                "page_type_expected": variant.get("page_type_expected", "UNKNOWN_PAGE_TYPE") if variant else "UNKNOWN_PAGE_TYPE",
                "navigation_depth": variant.get("navigation_depth", 1) if variant else 1,
                "route_status": variant.get("status", "UNKNOWN") if variant else "UNKNOWN",
                "verification_provenance": variant.get("verification_provenance") if variant else "SOURCE_MAP_CANONICAL_DOMAIN_ONLY",
                "last_verified": variant.get("last_verified") if variant else None,
            })
    return {
        "coverage_status": desk["coverage_status"],
        "recovery_focus": desk["recovery_focus"],
        "configured_primary_source_ids": [item["source_id"] for item in routes if item["primary_capable"]],
        "configured_independent_source_ids": [item["source_id"] for item in routes if item["independent_reporting_capable"]],
        "configured_discovery_source_ids": [item["source_id"] for item in routes if item["discovery_only"]],
        # Routing hints only: exact pages still need normal extraction,
        # source intelligence, and provenance validation before any evidence
        # role can change.
        "configured_source_routes": [item for item in configured_routes if item["enabled"] and not item["discovery_only"]],
        # Discovery-only routes remain eligible navigation/search seeds. They
        # never grant an evidence role; exact artifacts still pass the normal
        # source and claim validation pipeline.
        "configured_discovery_routes": [item for item in configured_routes if item["enabled"]],
        "allow_open_discovery": coverage["research_semantics"]["allow_open_discovery"],
    }
