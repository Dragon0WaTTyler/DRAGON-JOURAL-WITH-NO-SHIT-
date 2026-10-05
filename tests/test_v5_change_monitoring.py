import json
from pathlib import Path

import pytest

from dragon.change_monitoring import (
    ChangeMonitoringError,
    find_previous_monitor_report,
    load_change_watchlist,
    monitor_watchlist,
)
from dragon.discovery import FetchResponse


ROOT = Path(__file__).resolve().parents[1]


def target(**overrides) -> dict:
    value = {
        "target_id": "official-json",
        "label": "Official data",
        "url": "https://example.org/data.json",
        "enabled": True,
        "required": False,
        "material_type": "JSON",
        "strategy": "json-canonical",
        "expected_content_types": ["application/json"],
        "timeout_seconds": 7,
        "maximum_bytes": 50000,
        "integration_test_status": "PASS",
        "provenance_behavior": "Discovery only.",
        "license_terms_notes": "Retain the exact URL.",
    }
    value.update(overrides)
    return value


def test_repository_watchlist_is_strict_and_disabled_until_proven() -> None:
    value = load_change_watchlist(ROOT / "config" / "change-watchlist.yaml")
    assert value["targets"]
    assert all(item["enabled"] is False for item in value["targets"])
    assert all(item["integration_test_status"] == "NOT_RUN" for item in value["targets"])


def test_canonical_json_ignores_key_order_then_detects_material_change() -> None:
    payloads = iter((b'{"b":2,"a":1}', b'{"a":1,"b":2}', b'{"a":1,"b":3}'))

    def transport(url: str, timeout: int, maximum: int) -> FetchResponse:
        assert (timeout, maximum) == (7, 50000)
        return FetchResponse(url, 200, "application/json", next(payloads))

    watchlist = {"version": 1, "targets": [target()]}
    first = monitor_watchlist(watchlist, transport=transport, observed_at="2099-01-01T00:00:00Z")
    second = monitor_watchlist(watchlist, first, transport=transport, observed_at="2099-01-02T00:00:00Z")
    third = monitor_watchlist(watchlist, second, transport=transport, observed_at="2099-01-03T00:00:00Z")
    assert first["targets"][0]["status"] == "INITIAL_BASELINE"
    assert second["targets"][0]["status"] == "UNCHANGED"
    assert third["targets"][0]["status"] == "CHANGED"
    assert third["discovery_candidates"][0]["verification_status"] == "DISCOVERY_ONLY"


def test_optional_failure_degrades_but_required_failure_blocks() -> None:
    def failed(url: str, timeout: int, maximum: int) -> FetchResponse:
        return FetchResponse(url, 503, "application/json", b"{}")

    optional = monitor_watchlist({"version": 1, "targets": [target()]}, transport=failed)
    required = monitor_watchlist(
        {"version": 1, "targets": [target(required=True)]}, transport=failed
    )
    assert optional["status"] == "DEGRADED"
    assert optional["summary"]["optional_failures"] == ["official-json"]
    assert required["status"] == "FAIL"
    assert required["summary"]["required_failures"] == ["official-json"]


def test_previous_report_selection_excludes_same_and_future_dates(tmp_path: Path) -> None:
    for date in ("2099-01-01", "2099-01-02", "2099-01-03"):
        path = tmp_path / "daily-runs" / date / "source-monitoring" / "report.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({"date": date}), encoding="utf-8")
    found = find_previous_monitor_report(tmp_path, "2099-01-03")
    assert found == tmp_path / "daily-runs" / "2099-01-02" / "source-monitoring" / "report.json"


def test_duplicate_target_ids_are_rejected(tmp_path: Path) -> None:
    config = tmp_path / "change-watchlist.yaml"
    config.write_text("version: 1\ntargets: []\n", encoding="utf-8")
    schema = ROOT / "config" / "change-watchlist-schema.json"
    assert load_change_watchlist(config, schema)["targets"] == []
    value = {"version": 1, "targets": [target(), target()]}
    config.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ChangeMonitoringError) as caught:
        load_change_watchlist(config, schema)
    assert caught.value.code == "CHANGE_WATCHLIST_INVALID"


def test_enabled_target_requires_proven_integration(tmp_path: Path) -> None:
    config = tmp_path / "change-watchlist.yaml"
    value = {"version": 1, "targets": [target(integration_test_status="NOT_RUN")]}
    config.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ChangeMonitoringError) as caught:
        load_change_watchlist(config, ROOT / "config" / "change-watchlist-schema.json")
    assert "integration_test_status" in caught.value.detail
