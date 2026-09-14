from pathlib import Path

from dragon.deep_research import create_lead, load_deep_research_config, start_research_job
from dragon.deep_research_executor import (
    FixtureResearchAdapter,
    RssSearchAdapter,
    SearxngSearchAdapter,
    execute_research_round,
    plan_research_actions,
)
from dragon.discovery import FetchResponse


ROOT = Path(__file__).resolve().parents[1]
CONFIG = load_deep_research_config(ROOT / "config" / "deep-research.yaml")


def _job() -> dict:
    lead = create_lead(
        desk="service", topic="Public service route", discovery_source={"url": "https://seed.example/lead"},
        observed_at="2026-09-13", reason_interesting="fixture", geography=["Morocco"],
    )
    need = {
        "need_id": "BREADTH:accountability_and_service:2", "kind": "NEED_SERVICE",
        "query_context": {"geography": ["Morocco"], "research_date": "2026-09-13"},
        "max_attempts": 1,
    }
    return start_research_job(lead, CONFIG, budget_class="STANDARD", recovery_needs=[need])


def test_valid_result_is_followed_by_a_bounded_fetch():
    job = _job()
    action = plan_research_actions(job, CONFIG)[0]
    adapter = FixtureResearchAdapter({
        action["action_type"]: [{
            "result_type": "LEAD", "canonical_url": "https://official.example/notice",
            "title": "Operational notice", "claim": "deadline", "fetch_status": "NOT_RETRIEVED",
        }],
        "FETCH_URL": [{
            "result_type": "LEAD", "canonical_url": "https://official.example/notice",
            "title": "Operational notice", "claim": "deadline", "text": "An operational deadline notice.",
            "fetch_status": "FETCHED", "content_hash": "a" * 64, "published_at": "2026-09-13",
        }],
    })
    adapter.follow_discovery_leads = True
    execution = execute_research_round(job, adapter, CONFIG, actions=[action])
    assert any(item["action_type"] == "FETCH_URL" for item in execution["actions"])
    assert any(item.get("extraction_status") == "FETCHED" for item in execution["observations"])


def test_route_search_empty_uses_verified_route_fetch_without_changing_evidence_role():
    job = _job()
    action = plan_research_actions(job, CONFIG)[0]
    action = {
        **action,
        "channel_fallback": None,
        "route_scoped": True,
        "source_route": {
            "route_id": "verified-route", "url": "https://official.example/news",
            "origin": "official.example", "route_type": "NEWS_LISTING",
        },
    }
    route_url = action["source_route"]["url"]
    adapter = FixtureResearchAdapter({
        action["action_type"]: [{"result_type": "DEAD_END", "reason": "SEARXNG_NO_MATCHES", "diagnostic": "BACKEND_EMPTY"}],
        "FETCH_URL": [{
            "result_type": "LEAD", "canonical_url": route_url, "title": "Institutional listing",
            "claim": "listing", "text": "Official listing navigation.", "fetch_status": "FETCHED",
            "content_hash": "b" * 64, "published_at": "2026-09-13", "publisher": "Official Portal",
        }],
    })
    execution = execute_research_round(job, adapter, CONFIG, actions=[action])
    assert execution["direct_route_selection"][0]["status"] == "DIRECT_SOURCE_ROUTE_SELECTED"
    assert any(item["action_type"] == "FETCH_URL" and item.get("direct_source_route") for item in execution["actions"])
    fetched = next(item for item in execution["observations"] if item.get("extraction_status") == "FETCHED")
    assert fetched["publication_evidence"] is False


def test_empty_and_parse_empty_are_distinct_backend_diagnostics():
    empty = SearxngSearchAdapter(
        adapter_id="searx-empty", base_url="https://search.example", timeout_seconds=3,
        maximum_bytes=10000, maximum_results=4,
        transport=lambda url, *_: FetchResponse(url, 200, "application/json", b'{"results": []}'),
    ).execute({"action_type": "SEARCH_DISCOVERY", "query": "empty"})[0]
    malformed_items = SearxngSearchAdapter(
        adapter_id="searx-parse", base_url="https://search.example", timeout_seconds=3,
        maximum_bytes=10000, maximum_results=4,
        transport=lambda url, *_: FetchResponse(url, 200, "application/json", b'{"results": [{"title": "missing url"}]}'),
    ).execute({"action_type": "SEARCH_DISCOVERY", "query": "parse"})[0]
    assert empty["diagnostic"] == "BACKEND_EMPTY"
    assert malformed_items["diagnostic"] == "RESULT_URL_MISSING"


def test_unsafe_discovery_target_is_filtered_before_fetch():
    job = _job()
    action = plan_research_actions(job, CONFIG)[0]
    adapter = FixtureResearchAdapter({
        action["action_type"]: [{
            "result_type": "LEAD", "canonical_url": "http://127.0.0.1/private",
            "title": "Unsafe result", "claim": "service",
        }],
        "FETCH_URL": [{"result_type": "LEAD", "canonical_url": "http://127.0.0.1/private", "fetch_status": "FETCHED", "text": "should not fetch", "content_hash": "c" * 64}],
    })
    adapter.follow_discovery_leads = True
    execution = execute_research_round(job, adapter, CONFIG, actions=[action])
    assert not any(item["action_type"] == "FETCH_URL" for item in execution["actions"])
    lead = execution["observations"][0]
    assert lead["lead_attrition_reason"] == "RESULT_FILTERED_SECURITY"


def test_rss_empty_is_backend_empty_not_a_generic_no_matches_state():
    result = RssSearchAdapter(
        adapter_id="rss-empty", endpoint_template="https://search.example/rss?q={query}",
        transport=lambda url, *_: FetchResponse(url, 200, "application/rss+xml", b"<rss><channel/></rss>"),
    ).execute({"action_type": "SEARCH_DISCOVERY", "query": "empty"})[0]
    assert result["reason"] == "RSS_NO_MATCHES"
    assert result["diagnostic"] == "BACKEND_EMPTY"
