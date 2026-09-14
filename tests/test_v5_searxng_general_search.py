"""Deterministic SearXNG routing and safety tests; no service is contacted."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from dragon.deep_research import create_lead, load_deep_research_config, start_research_job
from dragon.deep_research_executor import (
    DiscoveryAdapterChain,
    FixtureResearchAdapter,
    ResearchExecutorError,
    RssSearchAdapter,
    SearxngSearchAdapter,
    build_research_yield_report,
    execute_research_round,
    plan_research_actions,
    searxng_search_adapter_from_config,
)
from dragon.discovery import FetchResponse


ROOT = Path(__file__).resolve().parents[1]
CONFIG = load_deep_research_config(ROOT / "config" / "deep-research.yaml")


def _job(*, desk: str = "meknes_local", need: dict | None = None) -> dict:
    lead = create_lead(
        desk=desk, topic="Meknes public procurement audit",
        discovery_source={"url": "https://signal.example/meknes", "known_seed": False},
        observed_at="2099-01-02", reason_interesting="fixture", geography=["Meknes"],
    )
    return start_research_job(lead, CONFIG, budget_class="STANDARD", recovery_needs=[need] if need else [])


def test_local_private_config_is_allowed_but_non_loopback_http_is_rejected(tmp_path: Path) -> None:
    config = {
        "version": 2, "enabled": True, "adapter_id": "searxng-general-search",
        "base_url": "http://127.0.0.1:8088", "endpoint_policy": "LOCAL_PRIVATE_ONLY",
        "timeout_seconds": 3, "maximum_bytes": 1000, "maximum_results": 2,
        "language": "auto", "categories": "general", "time_range": "month", "page": 1,
        "integration_test_status": "PASS", "provenance_behavior": "DISCOVERY_ONLY_EXACT_PAGE_REQUIRED",
    }
    path = tmp_path / "general-search.yaml"
    path.write_text(__import__("yaml").safe_dump(config), encoding="utf-8")
    assert searxng_search_adapter_from_config(path) is not None
    config["base_url"] = "http://search.example"
    path.write_text(__import__("yaml").safe_dump(config), encoding="utf-8")
    with pytest.raises(ResearchExecutorError, match="SEARXNG_SEARCH_CONFIG_INVALID"):
        searxng_search_adapter_from_config(path)


def test_searxng_propagates_bounded_language_date_category_and_page() -> None:
    requested: list[str] = []
    adapter = SearxngSearchAdapter(
        adapter_id="searxng-general-search", base_url="https://search.example",
        timeout_seconds=3, maximum_bytes=100_000, maximum_results=2,
        language="auto", categories="general", time_range="month", page=1,
        transport=lambda url, *_: (requested.append(url) or FetchResponse(url, 200, "application/json", b'{"results": []}')),
    )
    adapter.execute({"action_type": "SEARCH_DISCOVERY", "query": "Meknes audit", "search_language": "fr", "search_time_range": "day", "search_categories": "news", "search_page": 2})
    params = parse_qs(urlsplit(requested[0]).query)
    assert params == {"q": ["Meknes audit"], "format": ["json"], "pageno": ["2"], "language": ["fr"], "categories": ["news"], "time_range": ["day"]}


def test_searxng_preserves_raw_parsed_and_filtered_counts() -> None:
    adapter = SearxngSearchAdapter(
        adapter_id="searxng-fixture", base_url="https://search.example",
        timeout_seconds=3, maximum_bytes=100_000, maximum_results=5,
        transport=lambda *_: FetchResponse("https://search.example/search", 200, "application/json", b'{"results":[{"title":"target","url":"https://example.org/target"},{"title":"missing"},{"title":"bad","url":"ftp://example.org/bad"}]}'),
    )
    value = adapter.execute({"action_type": "SEARCH_DISCOVERY", "query": "target"})
    assert value[0]["result_type"] == "LEAD"
    assert value[0]["backend_counts"] == {"raw_results": 3, "parsed_results": 1, "filtered_results": 2}


def test_unavailable_searxng_uses_bounded_rss_fallback_without_promoting_search_metadata() -> None:
    need = {
        "need_id": "independent", "candidate_id": "weak", "kind": "FIND_INDEPENDENT_CORROBORATION", "max_attempts": 1,
        "missing_evidence_role": "INDEPENDENT", "topic_identifiers": ["Meknes audit"],
        "query_context": {"entities": ["Meknes"], "geography": ["Meknes"], "event_terms": ["public procurement audit"], "research_date": "2099-01-02"},
    }
    job = _job(need=need)
    searx_action = next(item for item in plan_research_actions(job, CONFIG) if item["discovery_channel"] == "SEARXNG_GENERAL_SEARCH")
    searx = SearxngSearchAdapter(
        adapter_id="searxng-general-search", base_url="https://search.example", timeout_seconds=3,
        maximum_bytes=100_000, maximum_results=2, transport=lambda *_: (_ for _ in ()).throw(TimeoutError()),
    )
    rss = RssSearchAdapter(
        adapter_id="public-rss-search", endpoint_template="https://rss.example/?q={query}",
        transport=lambda url, *_: FetchResponse(url, 200, "application/rss+xml", b"<rss><channel><item><title>Unknown outlet</title><link>https://outside.example/report</link></item></channel></rss>"),
    )
    execution = execute_research_round(job, DiscoveryAdapterChain([rss, searx]), CONFIG, actions=[searx_action])
    assert {item["discovery_channel"] for item in execution["observations"]} >= {"searxng-general-search", "public-rss-search"}
    lead = next(item for item in execution["observations"] if item["discovery_channel"] == "public-rss-search")
    assert lead["observation_class"] == "LEAD"
    assert lead["publication_evidence"] is False


def test_morocco_language_variants_are_distinct_and_bounded() -> None:
    need = {
        "need_id": "independent", "candidate_id": "weak", "kind": "FIND_INDEPENDENT_CORROBORATION", "max_attempts": 1,
        "query_context": {"entities": ["Meknes"], "geography": ["Morocco"], "event_terms": ["audit"], "research_date": "2099-01-02"},
    }
    actions = plan_research_actions(_job(need=need), CONFIG)
    searx = [item for item in actions if item["discovery_channel"] == "SEARXNG_GENERAL_SEARCH"]
    assert [item["search_language"] for item in searx[:2]] == ["ar", "fr"]
    assert len({item["query_fingerprint"] for item in searx}) == len(searx)
    assert len(searx) <= 3


def test_backend_yield_is_reported_per_actual_backend() -> None:
    job = _job()
    action = plan_research_actions(job, CONFIG)[0]
    execution = execute_research_round(
        job, FixtureResearchAdapter({action["action_type"]: [{"result_type": "DEAD_END", "reason": "fixture"}]}),
        CONFIG, actions=[action],
    )
    report = build_research_yield_report({"jobs": [execution]})
    row = next(item for item in report["backend_yield"] if item["backend"] == action["discovery_channel"])
    assert row["queries"] == 1
    assert row["dead_ends"] == 1


def test_searxng_lead_followup_keeps_searxng_backend_identity() -> None:
    class Backend:
        follow_discovery_leads = True

        def __init__(self, adapter_id: str) -> None:
            self.adapter_id = adapter_id

        def execute(self, action: dict) -> list[dict]:
            return [{"result_type": "DEAD_END", "reason": self.adapter_id, "discovery_channel": self.adapter_id}]

    result = DiscoveryAdapterChain([Backend("public-rss-search"), Backend("searxng-general-search")]).execute({
        "action_type": "FETCH_URL", "target": "https://example.org/page",
        "discovery_backends": ["searxng-general-search"], "discovery_channel": "SEARXNG_GENERAL_SEARCH",
    })
    assert result[0]["discovery_channel"] == "searxng-general-search"
