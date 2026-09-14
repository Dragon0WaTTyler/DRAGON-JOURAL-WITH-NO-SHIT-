from pathlib import Path

import pytest

from dragon.providers import SECTION_HEADINGS
from dragon.source_coverage import (
    SourceCoverageError,
    build_source_coverage_report,
    load_source_coverage,
    validate_source_registry,
)


ROOT = Path(__file__).resolve().parents[1]
SECTIONS = {section_id for section_id, _ in SECTION_HEADINGS}


def test_verified_registry_exposes_families_without_granting_evidence() -> None:
    coverage = load_source_coverage(ROOT / "config" / "source-coverage.yaml", SECTIONS)
    normalized = validate_source_registry(coverage)
    assert normalized["research_semantics"]["configured_sources_are"] == "preferred_seeds_not_whitelist"
    assert any(item.get("source_family") == "PARLIAMENTARY" for item in normalized["sources"])
    assert all(item.get("primary_evidence") is not True for item in normalized["sources"])


def test_coverage_report_is_deterministic_inventory_and_health_is_separate() -> None:
    coverage = load_source_coverage(ROOT / "config" / "source-coverage.yaml", SECTIONS)
    report = build_source_coverage_report(
        coverage,
        edition_date="2099-01-02",
        run_id="fresh",
        route_health=[{"route_id": "parliament-home", "status": "VERIFIED_WORKING"}],
    )
    assert report["configured_source_count"] >= 25
    assert report["active_source_count"] >= 20
    assert report["reachable_source_count"] == 1
    assert report["source_families"]["PARLIAMENTARY"] == 1
    assert report["research_semantics"]["allow_open_discovery"] is True
    assert any(item["source_id"] == "parliament-morocco" and item["state"] == "DETAIL_USABLE" for item in report["source_usability"])


def test_route_health_probe_is_bounded_and_does_not_change_route_role() -> None:
    coverage = load_source_coverage(ROOT / "config" / "source-coverage.yaml", SECTIONS)
    from dragon.source_coverage import probe_source_routes
    calls = []
    def transport(url, timeout):
        calls.append((url, timeout))
        return 200, url
    health = probe_source_routes(coverage, transport=transport, max_routes=2)
    assert len(calls) == len(health) == 2
    assert all(item["status"] == "VERIFIED_WORKING" for item in health)
    assert all(item["http_status"] == 200 for item in health)


def test_registry_rejects_unknown_family_and_unknown_source() -> None:
    coverage = load_source_coverage(ROOT / "config" / "source-coverage.yaml", SECTIONS)
    coverage["source_profiles"] = [{
        "source_id": "not-configured", "source_family": "OFFICIAL_GOVERNMENT",
        "authority_scope": "test", "languages": ["en"], "routes": {"homepage": "https://example.org"},
    }]
    with pytest.raises(SourceCoverageError, match="SOURCE_REGISTRY_PROFILE_SOURCE_UNKNOWN"):
        validate_source_registry(coverage)
