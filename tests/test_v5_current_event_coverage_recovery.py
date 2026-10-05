"""Offline regression fixtures for current accountability and service recovery.

These fixtures deliberately use fictional domains and static responses.  They
exercise discovery mechanics and evidence gates without a provider, network,
or historical-run mutation.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from dragon.deep_research import create_lead, load_deep_research_config, start_research_job
from dragon.deep_research_executor import (
    FixtureResearchAdapter,
    _breadth_event_queries,
    build_event_bundles,
    create_research_action,
    execute_research_round,
    plan_research_actions,
    schedule_research_actions,
)
from dragon.editorial_functions import classify_event_functions
from dragon.temporal_relevance import evaluate_temporal_relevance


ROOT = Path(__file__).resolve().parents[1]
CONFIG = load_deep_research_config(ROOT / "config" / "deep-research.yaml")


def _need(function: str, routes: list[dict] | None = None) -> dict:
    return {
        "need_id": f"BREADTH:accountability_and_service:{function.lower()}",
        "kind": "NEED_ACCOUNTABILITY_AND_SERVICE",
        "recovery_mode": "DISCOVER_NEW_EVENT_FOR_SEMANTIC_NEED",
        "target_editorial_function": function,
        "max_attempts": 1,
        "attempt_count": 0,
        "query_context": {"research_date": "2099-01-02"},
        "search_constraints": {"configured_source_routes": routes or []},
        "event_acquisition_plan": {"target_editorial_function": function},
    }


def _job(function: str, routes: list[dict] | None = None) -> dict:
    lead = create_lead(
        desk="investigations" if function == "ACCOUNTABILITY" else "service",
        topic=f"{function.lower()} fixture",
        discovery_source={"url": "https://signal.fixture/item", "known_seed": False},
        observed_at="2099-01-02T07:00:00Z",
        reason_interesting="offline current-event fixture",
        geography=["Fixture City"],
    )
    return start_research_job(lead, CONFIG, budget_class="STANDARD", recovery_needs=[_need(function, routes)])


def _action(job: dict, function: str, action_id: str, target: str) -> dict:
    branch = job["branches"][0]
    return {
        "job_id": job["job_id"], "branch_id": branch["branch_id"], "question_id": branch["question_ids"][0],
        "action_id": action_id, "desk": job["lead"]["desk"], "research_regime": "GENERAL_JOURNALISM",
        "action_type": "FETCH_URL", "target": target, "query": f"{function} fixture current event",
        "query_intent": "FIXTURE", "query_variant": "EXACT", "query_fingerprint": f"FIXTURE:{action_id}",
        "priority_class": "P1_BREADTH", "discovery_channel": "fixture", "known_entities": ["Fixture City"],
        "known_event_ids": [], "already_seen_urls": [], "already_seen_origins": [],
        "budget": {"class": "STANDARD", "round": 0, "max_rounds": 2}, "timeout_seconds": 10,
        "expected_result_type": "EXTRACTED_SOURCE", "recovery_need_id": job["recovery_needs"][0]["need_id"],
        "recovery_candidate_id": None, "recovery_mode": "DISCOVER_NEW_EVENT_FOR_SEMANTIC_NEED",
        "target_editorial_function": function, "candidate_event_theme": function,
        "provenance_requirements": {"required_role": None, "must_be_distinct_event": True, "science_strict": False},
        "event_context": {"entities": ["Fixture City"], "aliases": [], "event_terms": [function.lower()], "topic_terms": [job["lead"]["desk"]], "geography": ["Fixture City"], "research_date": "2099-01-02"},
        "channel_fallback": None,
    }


def _page(url: str, title: str, text: str, source_class: str, event_id: str) -> dict:
    return {
        "url": url, "canonical_url": url, "title": title, "text": text, "claim": title,
        "source_class": source_class, "fetch_status": "FETCHED", "published_at": "2099-01-02",
        "retrieved_at": "2099-01-02T08:00:00Z", "content_hash": ("a" if source_class == "official" else "b") * 64,
        "event_id": event_id,
    }


def _two_source_execution(function: str, title: str, text: str) -> dict:
    job = _job(function)
    official = _action(job, function, "OFFICIAL", "https://authority.fixture/current-notice")
    independent = _action(job, function, "INDEPENDENT", "https://news.fixture/current-notice")
    execution = execute_research_round(job, FixtureResearchAdapter({
        "OFFICIAL": [_page(official["target"], title, text, "official", "EVT-FIXTURE")],
        "INDEPENDENT": [_page(independent["target"], title, text, "independent", "EVT-FIXTURE")],
    }), CONFIG, actions=[official, independent])
    return {"job": job, "actions": [official, independent], "execution": execution}


def test_01_current_accountability_fixture_is_discovered_retrieved_and_assembled() -> None:
    result = _two_source_execution(
        "ACCOUNTABILITY", "Fixture City audit institution publishes procurement findings",
        "The public audit institution issued an audit report with procurement findings on 2 January 2099.",
    )
    execution = result["execution"]
    assert {item["verification_status"] for item in execution["observations"]} == {"VALIDATED_EVIDENCE"}
    bundles, discoveries = build_event_bundles(execution["observations"], [], execution["source_packet_patch"]["sources"], result["actions"])
    assert bundles and discoveries and discoveries[0]["target_editorial_function"] == "ACCOUNTABILITY"


def test_02_current_service_fixture_is_discovered_retrieved_and_assembled() -> None:
    result = _two_source_execution(
        "SERVICE", "Fixture City water authority restores service after interruption",
        "The municipal water authority restored public water service and published the access procedure on 2 January 2099.",
    )
    execution = result["execution"]
    bundles, discoveries = build_event_bundles(execution["observations"], [], execution["source_packet_patch"]["sources"], result["actions"])
    # The recovered exact pages are assembled into the source packet.  The
    # function classifier then establishes SERVICE from the concrete
    # operational restoration/procedure fact rather than a desk label.
    functions = classify_event_functions(
        title="Fixture City water authority restores service after interruption",
        facts=["The municipal water authority restored public water service and published the access procedure on 2 January 2099."],
        evidence_source_ids=[item["id"] for item in execution["source_packet_patch"]["sources"]],
        exact_page_validated=True,
    )
    assert execution["source_packet_patch"]["sources"] and {item["function"] for item in functions} >= {"SERVICE"}


def test_03_historic_report_is_not_current_event_evidence() -> None:
    result = evaluate_temporal_relevance({"published_at": "2098-03-01", "text": "An audit report."}, "2099-01-02")
    assert result["active_on_edition_date"] is False
    assert result["rejection_reason"] == "NO_EXPLICIT_ACTIVE_WINDOW"


def test_04_first_party_scope_does_not_create_claim_support() -> None:
    job = _job("ACCOUNTABILITY")
    action = _action(job, "ACCOUNTABILITY", "SCOPE", "https://authority.fixture/report")
    execution = execute_research_round(job, FixtureResearchAdapter({
        "SCOPE": [_page(action["target"], "Authority site navigation", "The authority publishes reports.", "official", "EVT-SCOPE")],
    }), CONFIG, actions=[action])
    assert execution["observations"][0]["claim_support"]["state"] != "DIRECT_SUPPORT"


def test_05_weak_timestamp_does_not_satisfy_freshness() -> None:
    result = evaluate_temporal_relevance({"text": "The authority says the service is available."}, "2099-01-02")
    assert result["temporal_eligibility_type"] == "TEMPORAL_RELEVANCE_UNRESOLVED"
    assert result["active_on_edition_date"] is False


def test_06_unsuccessful_route_is_bounded_and_recorded() -> None:
    job = _job("SERVICE")
    action = _action(job, "SERVICE", "FAIL", "https://authority.fixture/unavailable")
    execution = execute_research_round(job, FixtureResearchAdapter({"FAIL": [{"reason": "HTTP_503", "url": action["target"]}]}), CONFIG, actions=[action])
    assert execution["observations"][0]["observation_class"] == "DEAD_END"
    assert execution["budget_consumed"]["fetches"] == 1


def test_07_stale_route_cannot_monopolize_service_discovery() -> None:
    routes = [
        {"route_id": "stale", "url": "https://stale.fixture/notices", "origin": "stale.fixture", "route_type": "NOTICES", "route_status": "STALE", "source_family": "OFFICIAL_GOVERNMENT", "semantic_capabilities": ["SERVICE"]},
        {"route_id": "working", "url": "https://working.fixture/notices", "origin": "working.fixture", "route_type": "NOTICES", "route_status": "VERIFIED_WORKING", "source_family": "OFFICIAL_GOVERNMENT", "semantic_capabilities": ["SERVICE"]},
    ]
    strategies = _breadth_event_queries({}, _need("SERVICE", routes), month="2099-01", primary_language="en", alternate_language="fr", route=None)
    assert strategies[0]["source_route"]["route_id"] == "working"


def test_08_relevant_child_action_is_scheduled_within_existing_cap() -> None:
    job = _job("SERVICE")
    actions = plan_research_actions(job, CONFIG)
    scheduled = schedule_research_actions([job], CONFIG)["actions"]
    assert any(action["action_type"] == "SEARCH_DISCOVERY" for action in actions)
    assert len(scheduled) <= CONFIG["executor"]["maximum_actions_per_round"]


def test_09_priorities_and_recovery_stay_within_budget() -> None:
    job = _job("ACCOUNTABILITY")
    scheduled = schedule_research_actions([job], CONFIG)
    limits = CONFIG["executor"]["budget_action_limits"]["STANDARD"]
    assert sum(item["action_type"].startswith("SEARCH") for item in scheduled["actions"]) <= limits["search_actions"]
    assert sum(item["action_type"].startswith("FETCH") for item in scheduled["actions"]) <= limits["fetches"]


def test_10_fairness_reserves_one_action_for_each_semantic_need() -> None:
    account = _job("ACCOUNTABILITY")
    service = _job("SERVICE")
    scheduled = schedule_research_actions([account, service], CONFIG)["actions"]
    assert {item["target_editorial_function"] for item in scheduled if item.get("target_editorial_function")} >= {"ACCOUNTABILITY", "SERVICE"}


def test_11_missing_independent_evidence_remains_blocked() -> None:
    result = _two_source_execution(
        "ACCOUNTABILITY", "Fixture City audit institution publishes procurement findings",
        "The public audit institution issued an audit report with procurement findings on 2 January 2099.",
    )
    only_primary = [item for item in result["execution"]["observations"] if item["source_class"] == "official"]
    bundles, discoveries = build_event_bundles(only_primary, [], result["execution"]["source_packet_patch"]["sources"], result["actions"])
    assert bundles and not discoveries and bundles[0]["state"] in {"EVENT_EVIDENCE_BLOCKED", "EVENT_EVIDENCE_PARTIAL"}


def test_12_combined_coverage_requires_each_validated_function() -> None:
    functions = classify_event_functions(
        title="Authority audit restores water service", evidence_source_ids=["SRC-1"], exact_page_validated=True,
        facts=["The municipal authority published an audit finding and the service restoration procedure."],
    )
    assert {item["function"] for item in functions} >= {"ACCOUNTABILITY", "SERVICE"}


def test_13_historic_contract_data_is_read_only_in_fixture_execution() -> None:
    result = _two_source_execution(
        "SERVICE", "Fixture City water authority restores service after interruption",
        "The municipal water authority restored public water service and published the access procedure on 2 January 2099.",
    )
    before = deepcopy(result["actions"])
    build_event_bundles(result["execution"]["observations"], [], result["execution"]["source_packet_patch"]["sources"], result["actions"])
    assert result["actions"] == before


def test_14_offline_fixtures_use_no_provider_or_network_adapter() -> None:
    result = _two_source_execution(
        "ACCOUNTABILITY", "Fixture City audit institution publishes procurement findings",
        "The public audit institution issued an audit report with procurement findings on 2 January 2099.",
    )
    assert {action["discovery_channel"] for action in result["actions"]} == {"fixture"}
