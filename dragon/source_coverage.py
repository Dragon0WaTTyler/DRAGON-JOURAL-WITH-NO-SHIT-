"""Configuration-backed editorial-desk source coverage.

This is deliberately a coverage *map*, not a truth source.  It tells the
research and recovery planners which configured routes may be useful for a
desk.  Every discovered item still needs exact-page provenance and separate
primary/independent verification before it can support publication.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

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
    if desk_ids != expected_sections:
        raise SourceCoverageError(
            "SOURCE_COVERAGE_SECTION_INVENTORY_INVALID: "
            f"missing={sorted(expected_sections - desk_ids)} unknown={sorted(desk_ids - expected_sections)}"
        )
    return value


def desk_recovery_context(coverage: dict, section_id: str) -> dict:
    """Return only bounded configured routing hints for one recovery need."""
    desk = next(item for item in coverage["desks"] if item["section_id"] == section_id)
    sources = {item["source_id"]: item for item in coverage["sources"]}
    routes = [sources[source_id] for source_id in desk["source_ids"]]
    return {
        "coverage_status": desk["coverage_status"],
        "recovery_focus": desk["recovery_focus"],
        "configured_primary_source_ids": [item["source_id"] for item in routes if item["primary_capable"]],
        "configured_independent_source_ids": [item["source_id"] for item in routes if item["independent_reporting_capable"]],
        "configured_discovery_source_ids": [item["source_id"] for item in routes if item["discovery_only"]],
        # Routing hints only: exact pages still need normal extraction,
        # source intelligence, and provenance validation before any evidence
        # role can change.
        "configured_source_routes": [
            {
                "source_id": item["source_id"], "name": item["name"],
                "url": item["url"], "origin": item["origin"],
                "role": item["role"], "enabled": item["enabled"],
                "authority_class": item["authority_class"],
                "source_class": "OFFICIAL_INSTITUTION" if item["role"] == "PRIMARY" else "INDEPENDENT_NEWSROOM",
                "discovery_only": item["discovery_only"],
            }
            for item in routes if item["enabled"] and not item["discovery_only"]
        ],
        "allow_open_discovery": coverage["research_semantics"]["allow_open_discovery"],
    }
