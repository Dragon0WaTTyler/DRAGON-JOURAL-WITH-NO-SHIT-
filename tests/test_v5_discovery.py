from pathlib import Path

import pytest

from dragon.discovery import (
    _validate_source_url,
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
    assert value["publisher"] == "example.org"
    assert value["author"] is None
    assert "AUTHOR_MISSING" in value["metadata_warnings"]
    assert "PUBLISHED_AT_MISSING" in value["metadata_warnings"]
    assert 0 < value["quality_score"] <= 1


def test_bad_source_date_is_quarantined_instead_of_entering_chronology(monkeypatch: pytest.MonkeyPatch) -> None:
    html = (
        "<html><head><meta name='date' content='not-a-date'><title>Report</title></head>"
        "<body><article>" + "<p>Substantive independently checkable report text.</p>" * 12
        + "</article></body></html>"
    ).encode()

    class Extracted:
        def as_dict(self) -> dict:
            return {
                "url": "https://example.org/report", "title": "Report", "author": None,
                "date": "not-a-date", "text": "checkable report evidence " * 20,
            }

    monkeypatch.setattr("trafilatura.bare_extraction", lambda *args, **kwargs: Extracted())
    value = fetch_and_extract_html(
        "https://example.org/report",
        transport=lambda *_: FetchResponse("https://example.org/report", 200, "text/html", html),
    )
    assert value["published_at"] is None
    assert set(value["metadata_warnings"]) >= {"AUTHOR_MISSING", "PUBLISHED_AT_INVALID"}


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (FetchResponse("https://example.org/blocked", 403, "text/html", b"denied"), "SOURCE_BLOCKED"),
        (FetchResponse("https://example.org/empty", 200, "text/html", b""), "SOURCE_CONTENT_EMPTY"),
    ],
)
def test_blocked_and_empty_sources_have_explicit_failure_codes(response: FetchResponse, expected: str) -> None:
    with pytest.raises(DiscoveryError) as caught:
        fetch_and_extract_html(response.url, transport=lambda *_: response)
    assert caught.value.code == expected


def test_source_timeout_has_an_explicit_retryable_failure_code() -> None:
    def timeout(*_: object) -> FetchResponse:
        raise TimeoutError("fixture timeout")

    with pytest.raises(DiscoveryError) as caught:
        fetch_and_extract_source("https://example.org/slow", transport=timeout)
    assert caught.value.code == "SOURCE_TIMEOUT"


@pytest.mark.parametrize(
    "url",
    [
        "https://127.0.0.1/private",
        "https://[::1]/private",
        "https://localhost/private",
        "https://service.internal/private",
        "https://user:password@example.org/source",
        "https://example.org:not-a-port/source",
    ],
)
def test_source_fetch_rejects_local_addresses_and_embedded_credentials(url: str) -> None:
    called = False

    def transport(*_: object) -> FetchResponse:
        nonlocal called
        called = True
        raise AssertionError("unsafe target reached the transport")

    with pytest.raises(DiscoveryError) as caught:
        fetch_and_extract_source(url, transport=transport)

    assert caught.value.code == "SOURCE_URL_UNSAFE"
    assert called is False


def test_source_redirect_to_private_address_is_rejected() -> None:
    with pytest.raises(DiscoveryError) as caught:
        fetch_and_extract_source(
            "https://example.org/source",
            transport=lambda *_: FetchResponse(
                "https://169.254.169.254/latest/meta-data", 200, "text/html", b"private"
            ),
        )
    assert caught.value.code == "SOURCE_REDIRECT_UNSAFE"


def test_dns_resolution_cannot_route_public_name_to_private_address(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "dragon.discovery.socket.getaddrinfo",
        lambda *args, **kwargs: [(2, 1, 6, "", ("10.0.0.8", 443))],
    )
    with pytest.raises(DiscoveryError) as caught:
        _validate_source_url("https://news.example/source", resolve_dns=True)
    assert caught.value.code == "SOURCE_URL_UNSAFE"


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


def test_broken_but_substantive_html_is_recovered_without_inventing_metadata() -> None:
    html = (
        "<html><head><title>Broken report</title><body><article><h1>Broken report</h1>"
        + "".join(
            f"<p>Substantive recoverable evidence {index} from a malformed source document.</p>"
            for index in range(12)
        )
    ).encode()
    value = fetch_and_extract_html(
        "https://example.org/broken",
        transport=lambda *_: FetchResponse("https://example.org/broken", 200, "text/html", html),
    )
    assert value["extraction_quality"] in {"MEDIUM", "HIGH"}
    assert len(value["text"]) >= 200
    assert value["author"] is None


def test_material_router_extracts_json_without_calling_html_parser() -> None:
    def transport(url: str, timeout: int, maximum: int) -> FetchResponse:
        return FetchResponse(url, 200, "application/json", b'[{"year":2026,"value":7},{"year":2025,"value":5}]')

    value = fetch_and_extract_source(
        "https://example.org/data.json", transport=transport, retrieved_at="2099-01-02T07:00:00Z"
    )
    assert value["material_type"] == "JSON"
    assert value["tables"][0][0] == ["value", "year"]
    assert value["verification_status"] == "EXTRACTED_NOT_VERIFIED"
