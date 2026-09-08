from pathlib import Path

import pytest

from dragon.discovery import (
    DiscoveryError,
    FetchResponse,
    discover_rss,
    fetch_and_extract_html,
    fetch_and_extract_source,
    load_provider_registry,
    provider_prompt_context,
    registry_report,
)


ROOT = Path(__file__).resolve().parents[1]


def test_registry_is_strict_and_truthful_about_availability() -> None:
    registry = load_provider_registry(ROOT / "config" / "provider-registry.yaml")
    report = registry_report(registry)
    states = {item["provider_id"]: item["health_state"] for item in report["providers"]}
    assert report["status"] == "PASS"
    assert states["morocco-primary-seeds"] == "AVAILABLE"
    assert states["openalex"] == "CONFIGURED_NOT_PROVEN"
    assert states["rsshub-optional"] == "DISABLED"
    context = provider_prompt_context(registry)
    assert "rsshub-optional" not in {item["provider_id"] for item in context["providers"]}
    assert "not verification" in context["warning"]
    assert context["material_routing"]["pdf_office_table_json"] == "structured-document"


def test_rss_adapter_marks_every_candidate_discovery_only() -> None:
    xml = b"""<rss><channel><item><title>One</title><link>https://example.org/exact</link></item></channel></rss>"""
    assert discover_rss(xml, provider_id="feed", endpoint="https://example.org/feed") == [
        {
            "provider_id": "feed",
            "title": "One",
            "discovered_url": "https://example.org/exact",
            "verification_status": "DISCOVERY_ONLY",
        }
    ]


def test_trafilatura_adapter_extracts_bounded_html_with_provenance() -> None:
    html = (
        "<html><head><title>Exact report</title></head><body><article><h1>Exact report</h1>"
        + "".join(
            f"<p>Section {number} contains substantive source evidence with distinct detail for extraction quality checks and provenance.</p>"
            for number in range(12)
        )
        + "</article></body></html>"
    ).encode()

    def transport(url: str, timeout: int, maximum: int) -> FetchResponse:
        assert timeout == 7 and maximum == 50_000
        return FetchResponse(url, 200, "text/html", html)

    value = fetch_and_extract_html(
        "https://example.org/report",
        transport=transport,
        timeout_seconds=7,
        maximum_bytes=50_000,
        retrieved_at="2099-01-02T07:00:00Z",
    )
    assert value["extraction_method"] == "trafilatura-bare-extraction"
    assert value["verification_status"] == "EXTRACTED_NOT_VERIFIED"
    assert value["content_hash"]
    assert len(value["text"]) >= 200


def test_extractor_routes_non_html_material_instead_of_forcing_parser() -> None:
    def transport(url: str, timeout: int, maximum: int) -> FetchResponse:
        return FetchResponse(url, 200, "application/pdf", b"%PDF")

    with pytest.raises(DiscoveryError) as caught:
        fetch_and_extract_html("https://example.org/report.pdf", transport=transport)
    assert caught.value.code == "SOURCE_MATERIAL_ROUTE_REQUIRED"


def test_js_heavy_static_shell_requests_exceptional_browser_route() -> None:
    def transport(url: str, timeout: int, maximum: int) -> FetchResponse:
        return FetchResponse(url, 200, "text/html", b"<html><script src='app.js'></script><main></main></html>")

    with pytest.raises(DiscoveryError) as caught:
        fetch_and_extract_html("https://example.org/dynamic", transport=transport)
    assert caught.value.code == "SOURCE_DYNAMIC_ROUTE_REQUIRED"


def test_material_router_extracts_json_without_calling_html_parser() -> None:
    def transport(url: str, timeout: int, maximum: int) -> FetchResponse:
        return FetchResponse(url, 200, "application/json", b'[{"year":2026,"value":7},{"year":2025,"value":5}]')

    value = fetch_and_extract_source(
        "https://example.org/data.json", transport=transport, retrieved_at="2099-01-02T07:00:00Z"
    )
    assert value["material_type"] == "JSON"
    assert value["tables"][0][0] == ["value", "year"]
    assert value["verification_status"] == "EXTRACTED_NOT_VERIFIED"
