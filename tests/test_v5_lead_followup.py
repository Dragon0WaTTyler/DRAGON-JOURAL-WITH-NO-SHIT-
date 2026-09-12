"""Deterministic lead-to-exact-page selection tests; no network/provider use."""

from __future__ import annotations

from pathlib import Path

from dragon.deep_research import create_lead, load_deep_research_config, start_research_job
from dragon.deep_research_executor import (
    FixtureResearchAdapter,
    build_research_yield_report,
    execute_research_round,
    plan_research_actions,
    select_leads_for_followup,
)


ROOT = Path(__file__).resolve().parents[1]
CONFIG = load_deep_research_config(ROOT / "config" / "deep-research.yaml")


def _need(kind: str = "FIND_INDEPENDENT_CORROBORATION") -> dict:
    return {
        "need_id": "need-1", "candidate_id": "weak", "kind": kind,
        "max_attempts": 1, "missing_evidence_role": "INDEPENDENT",
        "query_context": {"entities": ["Meknes"], "geography": ["Morocco"], "event_terms": ["audit"], "research_date": "2099-01-02"},
    }


def _job(*, needs: list[dict] | None = None) -> dict:
    return start_research_job(
        create_lead(desk="meknes_local", topic="Meknes audit", geography=["Meknes"],
                    discovery_source={"url": "https://signal.example/a"}, observed_at="2099-01-02", reason_interesting="fixture"),
        CONFIG, budget_class="STANDARD", recovery_needs=needs or [_need()],
    )


def _lead(url: str, title: str, *, rank: int = 1) -> dict:
    return {
        "result_type": "LEAD", "url": url, "title": title, "source_class": "unknown",
        "search_result": {"rank": rank, "snippet": "Meknes audit public procurement", "published_at": "2099-01-02"},
    }


def _search_action(job: dict) -> dict:
    return next(item for item in plan_research_actions(job, CONFIG) if item["action_type"] in {"SEARCH_DISCOVERY", "SEARCH_INDEPENDENT_COVERAGE", "SEARCH_OFFICIAL_SOURCE", "RECOVER_INDEPENDENT_SOURCE", "RECOVER_PRIMARY_SOURCE", "FIND_DISTINCT_EVENT"})


def _adapter(responses: dict) -> FixtureResearchAdapter:
    adapter = FixtureResearchAdapter(responses)
    adapter.follow_discovery_leads = True
    return adapter


def test_discovery_url_is_not_marked_retrieved_before_exact_fetch() -> None:
    job = _job()
    action = _search_action(job)
    execution = execute_research_round(job, _adapter({action["action_type"]: [_lead("https://news.example/a", "Meknes audit report")]}), CONFIG, actions=[action])
    observation = execution["observations"][0]
    assert observation["extraction_status"] == "NOT_RETRIEVED"
    assert observation["lead_attrition_state"] == "SELECTED_FOR_FETCH"


def test_selection_prefers_high_relevance_and_publisher_diversity() -> None:
    action = {"action_id": "A", "action_type": "SEARCH_DISCOVERY", "question_id": "Q", "priority_class": "P0_BLOCKING_EVIDENCE", "recovery_need_id": "N", "known_entities": ["Meknes"], "event_context": {"event_terms": ["audit"]}, "query": "Meknes audit"}
    observations = [
        {"url": "https://one.example/a", "title": "Meknes audit", "observation_class": "LEAD", "provenance": {"action_id": "A"}, "search_result": {"rank": 1, "snippet": "Meknes audit"}},
        {"url": "https://one.example/b", "title": "Meknes audit second", "observation_class": "LEAD", "provenance": {"action_id": "A"}, "search_result": {"rank": 2, "snippet": "Meknes audit"}},
        {"url": "https://two.example/a", "title": "Meknes audit independent", "observation_class": "LEAD", "provenance": {"action_id": "A"}, "search_result": {"rank": 3, "snippet": "Meknes audit"}},
    ]
    selected = select_leads_for_followup(observations, {"A": action}, {"total": 3, "P0_BLOCKING_EVIDENCE": 3, "P1_BREADTH": 0, "P1_DISTINCT_EVENT": 0, "P2_CONTRADICTION": 0, "P3_CONTEXT": 0})
    assert [item["url"] for item in selected] == ["https://one.example/a", "https://two.example/a"]


def test_social_and_aggregator_leads_are_skipped_before_expensive_fetch() -> None:
    job = _job()
    action = _search_action(job)
    execution = execute_research_round(job, _adapter({action["action_type"]: [
        _lead("https://www.facebook.com/post/1", "Meknes audit"),
        _lead("https://news.example/a", "Meknes audit"),
    ]}), CONFIG, actions=[action])
    social = next(item for item in execution["observations"] if "facebook" in item.get("url", ""))
    assert social["lead_attrition_state"] == "DISCOVERED_NOT_SELECTED"
    assert social["source_identity"]["routing_class"] == "SOCIAL"
    assert any(item["action_type"] == "FETCH_URL" for item in execution["actions"])


def test_reserved_followup_budget_is_not_consumed_by_configured_fetches() -> None:
    job = _job()
    planned = [_search_action(job)]
    execution = execute_research_round(job, _adapter({
        planned[0]["action_type"]: [_lead("https://news.example/a", "Meknes audit")],
        "FETCH_URL": [{"url": "https://news.example/a", "title": "Meknes audit", "fetch_status": "FETCHED", "text": "Meknes audit " * 20, "content_hash": "a" * 64, "source_class": "unknown", "publisher": "News"}],
    }), CONFIG, actions=planned)
    assert execution["budget_consumed"]["lead_followups"] == 1
    assert execution["budget_consumed"]["fetches"] == 0


def test_dynamic_page_is_reported_as_browser_candidate_not_validated_content() -> None:
    job = _job()
    action = _search_action(job)
    execution = execute_research_round(job, _adapter({
        action["action_type"]: [_lead("https://dynamic.example/a", "Meknes audit")],
        "FETCH_URL": [{"result_type": "DEAD_END", "reason": "SOURCE_DYNAMIC_ROUTE_REQUIRED"}],
    }), CONFIG, actions=[action])
    followup = next(item for item in execution["observations"] if item["lead_attrition_state"] == "BROWSER_RENDER_REQUIRED")
    assert followup["publication_evidence"] is False
    assert followup["validation_state"] == "FETCH_FAILED"


def test_unknown_exact_page_resolves_identity_without_independent_promotion() -> None:
    job = _job()
    action = _search_action(job)
    execution = execute_research_round(job, _adapter({
        action["action_type"]: [_lead("https://fesnews.example/a", "Meknes audit")],
        "FETCH_URL": [{"url": "https://fesnews.example/a", "title": "Meknes audit", "fetch_status": "FETCHED", "text": "Meknes audit " * 20, "content_hash": "b" * 64, "source_class": "unknown", "publisher": "FesNews", "author": "Desk"}],
    }), CONFIG, actions=[action])
    fetched = next(item for item in execution["observations"] if item["provenance"]["expected_result_type"] == "EXTRACTED_SOURCE")
    assert fetched["source_identity"]["identity_state"] == "SOURCE_IDENTIFIED"
    assert fetched["validation_state"] == "SOURCE_UNKNOWN"
    assert fetched["publication_evidence"] is False


def test_followup_telemetry_exposes_attrition_counts() -> None:
    job = _job()
    action = _search_action(job)
    execution = execute_research_round(job, _adapter({action["action_type"]: [_lead("https://news.example/a", "Meknes audit")], "FETCH_URL": [{"result_type": "DEAD_END", "reason": "SOURCE_FETCH_FAILED"}]}), CONFIG, actions=[action])
    report = build_research_yield_report({"jobs": [execution]})
    assert report["leads_selected_for_followup"] == 1
    assert report["lead_attrition"]["FETCH_FAILED"] == 1
    assert report["browser_fallback_executions"] == 0
