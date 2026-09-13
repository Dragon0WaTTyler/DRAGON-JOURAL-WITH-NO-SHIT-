"""Deterministic acceptance tests for Deep Research Executor v1."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dragon.config import load_local_config
from dragon.deep_research import (
    create_lead,
    derive_research_outcome,
    evaluate_claim_policy,
    load_deep_research_config,
    start_research_job,
)
from dragon.deep_research_executor import (
    ACTION_TYPES,
    FixtureResearchAdapter,
    HttpResearchAdapter,
    RssSearchAdapter,
    ResearchExecutorError,
    apply_executor_results_to_packet,
    build_observation_snapshot,
    build_research_yield_report,
    create_research_action,
    execute_research_round,
    match_event_skeletons,
    plan_research_actions,
    rank_discovery_leads,
    select_leads_for_followup,
    query_fingerprint,
    query_ladder,
    _breadth_event_queries,
    replay_recovery_after_execution,
    replay_event_bundles_from_snapshot,
    resolve_exact_source_role,
    schedule_research_actions,
    science_adapter_boundary,
)
from dragon.discovery import FetchResponse
from dragon.investigation_scope import evaluate_super_investigation_scope
from dragon.pipeline import build_stage_definitions
from dragon.providers import SyntheticEditorialProvider
from dragon.research_recovery import build_recovery_plan
from dragon.source_coverage import load_source_coverage
from dragon.source_intelligence import build_source_intelligence
from dragon.stages import StageContext


ROOT = Path(__file__).resolve().parents[1]
CONFIG = load_deep_research_config(ROOT / "config" / "deep-research.yaml")
SECTIONS = {
    "front", "siyasa_dawla", "iqtisad_flous", "mojtama3", "ta3lim", "se77a",
    "3adl_7o9o9", "bi2a_manakh", "bniya_transport", "meknes_local",
    "filastin_middle_east", "africa_sahel", "world", "business_companies",
    "technology", "science", "sport", "culture", "adab", "history",
    "investigations", "opinion", "service",
}


def _lead(*, desk: str = "world", geography: list[str] | None = None) -> dict:
    return create_lead(
        desk=desk, topic="مشروع عام واختبار الأدلة",
        discovery_source={"url": "https://unknown.example/signal", "known_seed": False},
        observed_at="2099-01-02T07:00:00Z", reason_interesting="fixture signal",
        geography=geography,
    )


def _job(*, desk: str = "world", budget: str = "STANDARD", needs: list[dict] | None = None, geography: list[str] | None = None) -> dict:
    return start_research_job(_lead(desk=desk, geography=geography), CONFIG, budget_class=budget, recovery_needs=needs)


def _result(url: str, source_class: str = "independent", **extra: object) -> dict:
    return {
        "url": url, "title": "Fixture result", "source_class": source_class,
        "claim": "Fixture claim from a precise public page.",
        "published_at": "2099-01-02", "retrieved_at": "2099-01-02T07:01:00Z",
        "content_hash": "a" * 64, **extra,
    }


def test_function_breadth_uses_bounded_verified_route_search_without_budget_growth() -> None:
    need = {
        "need_id": "BREADTH:accountability_and_service:1",
        "kind": "NEED_ACCOUNTABILITY_AND_SERVICE",
        "target_editorial_function": "SERVICE",
        "query_context": {"research_date": "2026-09-13"},
        "search_constraints": {
            "configured_source_routes": [],
            "configured_discovery_routes": [{
                "route_id": "portal-news", "url": "https://maroc.ma/en/news", "origin": "maroc.ma",
                "route_type": "NEWS_LISTING", "route_status": "VERIFIED_DISCOVERY_ONLY",
                "name": "National portal", "authority_class": "NATIONAL_PORTAL",
            }],
        },
        "event_acquisition_plan": {"target_editorial_function": "SERVICE"},
    }
    strategies = _breadth_event_queries(_job(desk="service"), need, month="2026-09", primary_language="en", alternate_language="fr", route=None)
    assert len(strategies) == 4
    route = strategies[0]
    assert route["route_scoped"] is True
    assert route["source_route"]["route_id"] == "portal-news"
    assert route["query"].startswith("site:maroc.ma ")
    assert route["backends"] == ["searxng-general-search"]
    assert "active" in route["query"] and "deadline" in route["query"]


def test_route_scoped_search_context_does_not_grant_evidence_role() -> None:
    action = {
        "action_id": "ROUTE-SEARCH", "question_id": "Q", "branch_id": "B",
        "action_type": "SEARCH_DISCOVERY", "target_editorial_function": "SERVICE",
        "candidate_event_theme": "SERVICE", "route_scoped": True,
        "route_search_objective": "ACTIVE_WINDOW_ARTIFACT",
        "source_route": {"route_id": "portal-news", "url": "https://maroc.ma/en/news", "origin": "maroc.ma", "route_status": "VERIFIED_WORKING", "route_type": "NEWS_LISTING"},
        "query": "site:maroc.ma registration deadline active September 2026",
        "expected_result_type": "DISCOVERY_RESULT",
        "event_context": {"research_date": "2026-09-13", "geography": ["Morocco"]},
        "provenance_requirements": {"required_role": "PRIMARY"},
    }
    obs = __import__("dragon.deep_research_executor", fromlist=["_observation"])._observation(
        action,
        {"url": "https://maroc.ma/en/news/item", "title": "Announcement", "text": "A public announcement.", "fetch_status": "NOT_RETRIEVED", "source_class": "unknown"},
        set(),
    )
    assert obs["route_scoped"] is True
    assert obs["source_trust_state"] == "URL_SAFE_CANONICAL_INSTITUTION"
    assert (obs.get("source_role_resolution") or {}).get("evidence_role") != "PRIMARY"
    assert obs["verification_status"] != "VALIDATED_EVIDENCE"


def test_semantic_capability_routing_includes_maroc_portal_for_both_functions() -> None:
    routes = [
        {"route_id": "cdc", "url": "https://audit.example/press", "origin": "audit.example", "route_type": "PRESS_RELEASES", "route_status": "VERIFIED_WORKING", "name": "Audit institution", "authority_class": "PRIMARY_ORIGINAL", "semantic_capabilities": ["ACCOUNTABILITY"]},
        {"route_id": "maroc", "url": "https://maroc.ma/en/news", "origin": "maroc.ma", "route_type": "NEWS_LISTING", "route_status": "VERIFIED_DISCOVERY_ONLY", "name": "National portal", "authority_class": "PRIMARY_ORIGINAL", "semantic_capabilities": ["ACCOUNTABILITY", "SERVICE"], "supported_languages": ["en", "fr", "ar"]},
    ]
    for function in ("ACCOUNTABILITY", "SERVICE"):
        need = {"need_id": f"BREADTH:accountability_and_service:{function}", "kind": "NEED_ACCOUNTABILITY_AND_SERVICE", "target_editorial_function": function, "query_context": {"research_date": "2026-09-13"}, "search_constraints": {"configured_source_routes": routes}, "event_acquisition_plan": {"target_editorial_function": function}}
        strategy = _breadth_event_queries(_job(desk="service"), need, month="2026-09", primary_language="ar", alternate_language="fr", route=None)[0]
        assert strategy["source_route"]["route_id"] == "maroc"
        assert strategy["route_scoped"] is True


def test_route_scoped_ranking_prefers_active_exact_service_artifact() -> None:
    action = {"action_id": "RANK", "action_type": "SEARCH_DISCOVERY", "route_scoped": True, "target_editorial_function": "SERVICE", "candidate_event_theme": "SERVICE", "query": "site:maroc.ma polling station deadline", "source_route": {"origin": "maroc.ma", "route_id": "maroc", "route_type": "NEWS_LISTING"}, "known_event_fingerprints": []}
    observations = [
        {"observation_id": "generic", "observation_class": "LEAD", "url": "https://maroc.ma/en/news/politics", "title": "Current political news", "claim": "Current political news", "search_result": {"rank": 1, "snippet": "A general political update."}, "provenance": {"action_id": "RANK"}},
        {"observation_id": "active", "observation_class": "LEAD", "url": "https://maroc.ma/en/news/polling-notice", "title": "Polling station notice: proxy procedure through 22 September", "claim": "Polling station notice", "search_result": {"rank": 4, "snippet": "The active deadline and procedure remain available through 22 September."}, "provenance": {"action_id": "RANK"}},
    ]
    ranked = sorted(rank_discovery_leads(observations, {"RANK": action}), key=lambda item: item["_lead_sort_key"])
    assert ranked[0]["observation_id"] == "active"
    assert "ACTIVE_WINDOW_SIGNAL" in ranked[0]["lead_priority_reasons"]


def test_followup_selection_reserves_one_slot_per_need() -> None:
    def lead(action_id, need, url, title):
        return {"observation_id": url, "observation_class": "LEAD", "url": url, "title": title, "claim": title, "search_result": {"rank": 1, "snippet": title}, "provenance": {"action_id": action_id}}
    actions = {
        "A": {"action_id": "A", "action_type": "SEARCH_DISCOVERY", "recovery_need_id": "A", "priority_class": "P1_BREADTH", "query": "audit", "target_editorial_function": "ACCOUNTABILITY", "route_scoped": True, "source_route": {"origin": "a.example"}},
        "S": {"action_id": "S", "action_type": "SEARCH_DISCOVERY", "recovery_need_id": "S", "priority_class": "P1_BREADTH", "query": "service", "target_editorial_function": "SERVICE", "route_scoped": True, "source_route": {"origin": "s.example"}},
    }
    selected = select_leads_for_followup([lead("A", "A", "https://a.example/notice", "Audit directive"), lead("S", "S", "https://s.example/notice", "Service deadline")], actions, {"total": 2, "P1_BREADTH": 2})
    assert {item["_followup_need"] for item in selected} == {"A", "S"}


def _coverage() -> dict:
    return load_source_coverage(ROOT / "config" / "source-coverage.yaml", SECTIONS)


def test_question_plans_bounded_search_action() -> None:
    job = _job()
    action = plan_research_actions(job, CONFIG)[0]
    assert action["action_type"] == "SEARCH_DISCOVERY"
    assert action["question_id"] == job["branches"][0]["question_ids"][0]
    assert action["timeout_seconds"] == 15
    assert action["provenance_requirements"]["discovery_is_not_publication_evidence"] is True


def test_every_declared_action_type_has_a_valid_action_contract() -> None:
    job = _job()
    branch = job["branches"][0]
    assert {create_research_action(job, branch, action_type=value)["action_type"] for value in ACTION_TYPES} == ACTION_TYPES


def test_discovery_result_becomes_structured_unknown_source_lead() -> None:
    job = _job()
    execution = execute_research_round(job, FixtureResearchAdapter({"SEARCH_DISCOVERY": [_result("https://obscure.example/item", "unknown")]}), CONFIG)
    observation = execution["observations"][0]
    assert observation["observation_class"] == "LEAD"
    assert observation["publication_evidence"] is False
    assert observation["provenance"]["discovery_is_not_publication_evidence"] is True


def test_public_rss_search_discovers_unknown_domains_as_leads_only() -> None:
    adapter = RssSearchAdapter(
        adapter_id="public-rss-test",
        endpoint_template="https://search.example/rss?q={query}",
        transport=lambda url, timeout, maximum: FetchResponse(
            url, 200, "application/rss+xml",
            b"<rss><channel><item><title>Unknown source</title><link>https://outside.example/report</link></item></channel></rss>",
        ),
    )
    execution = execute_research_round(_job(), adapter, CONFIG)
    observation = execution["observations"][0]
    assert observation["observation_class"] == "LEAD"
    assert observation["url"] == "https://outside.example/report"
    assert observation["discovery_channel"] == "public-rss-test"
    assert observation["publication_evidence"] is False


def test_followup_fetch_inspects_rss_leads_within_the_reserved_lead_budget() -> None:
    adapter = FixtureResearchAdapter({
        "SEARCH_DISCOVERY": [_result("https://unknown.example/lead", "unknown")],
        "FETCH_URL": [_result("https://known.example/exact-page", "official", fetch_status="FETCHED")],
    })
    adapter.follow_discovery_leads = True
    execution = execute_research_round(_job(), adapter, CONFIG)
    assert "FETCH_URL" in [item["action_type"] for item in execution["actions"]]
    fetched = next(item for item in execution["observations"] if item["provenance"]["action_id"] in {
        action["action_id"] for action in execution["actions"] if action["action_type"] == "FETCH_URL"
    })
    assert fetched["observation_class"] == "POTENTIAL_EVIDENCE"
    assert fetched["verification_status"] == "EXTRACTED_NOT_VERIFIED"
    assert fetched["publication_evidence"] is False
    assert execution["budget_consumed"]["lead_followups"] >= 1


def test_yield_report_marks_dead_ends_as_non_useful_and_exposes_zero_yield_branches() -> None:
    execution = {
        "jobs": [execute_research_round(
            _job(), FixtureResearchAdapter({"SEARCH_DISCOVERY": [{"result_type": "DEAD_END", "reason": "fixture"}]}), CONFIG
        )]
    }
    report = build_research_yield_report(execution)
    assert report["actions_executed"] > 0
    assert report["dead_ends"] > 0
    assert report["new_leads"] == 0
    assert report["questions_with_zero_useful_results"] == report["actions_executed"]
    assert all(item["contributed_useful_material"] is False for item in report["action_outcomes"])


def test_function_metrics_expose_first_party_discovery_and_context_selection() -> None:
    need = {
        "need_id": "BREADTH:accountability_and_service:1",
        "kind": "NEED_ACCOUNTABILITY_AND_SERVICE",
        "recovery_mode": "DISCOVER_NEW_EVENT_FOR_SEMANTIC_NEED",
        "target_editorial_function": "ACCOUNTABILITY",
        "query_context": {"research_date": "2026-09-13", "current_process_context": "active national election process"},
        "search_constraints": {"configured_source_routes": []},
        "event_acquisition_plan": {"target_editorial_function": "ACCOUNTABILITY"},
    }
    job = _job(desk="investigations", needs=[need])
    actions = plan_research_actions(job, CONFIG)
    execution = execute_research_round(job, FixtureResearchAdapter({actions[0]["action_type"]: [{"result_type": "DEAD_END", "reason": "fixture"}]}), CONFIG, actions=actions[:1])
    report = build_research_yield_report({"jobs": [execution]})
    metrics = report["function_metrics"]["ACCOUNTABILITY"]
    assert metrics["first_party_discovery_actions"] == 1
    assert metrics["institution_discovery_actions"] == 1
    assert metrics["source_class_selection_reasons"] == ["CURRENT_PROCESS_CONTEXT"]


@pytest.mark.parametrize(("source_class", "expected"), [("official", "PRIMARY"), ("independent", "INDEPENDENT")])
def test_known_source_classes_become_potential_not_automatic_evidence(source_class: str, expected: str) -> None:
    job = _job()
    execution = execute_research_round(job, FixtureResearchAdapter({"SEARCH_DISCOVERY": [_result(f"https://{source_class}.example/item", source_class)]}), CONFIG)
    observation = execution["observations"][0]
    assert observation["observation_class"] == "POTENTIAL_EVIDENCE"
    assert observation["verification_status"] == "EXTRACTED_NOT_VERIFIED"
    assert execution["source_packet_patch"]["candidate_evidence_updates"] == []
    assert expected in {"PRIMARY", "INDEPENDENT"}


def test_duplicate_url_and_known_event_are_rejected() -> None:
    job = _job()
    job["executor_state"] = {"search_actions": 0, "fetches": 0, "seen_urls": ["https://news.example/item"], "seen_origins": []}
    execution = execute_research_round(job, FixtureResearchAdapter({"SEARCH_DISCOVERY": [_result("https://news.example/item", "independent")]}), CONFIG)
    assert execution["observations"][0]["observation_class"] == "DUPLICATE"
    assert execution["job"]["stop_condition"] == "NO_BETTER_SOURCES"
    fresh = _job()
    execution = execute_research_round(fresh, FixtureResearchAdapter({"SEARCH_DISCOVERY": [_result("https://new.example/item", "independent", event_id="EVT-KNOWN")]}), CONFIG, known_event_ids=["EVT-KNOWN"])
    assert execution["observations"][0]["observation_class"] == "DUPLICATE"


def test_irrelevant_material_is_retained_as_rejected_observation() -> None:
    execution = execute_research_round(_job(), FixtureResearchAdapter({"SEARCH_DISCOVERY": [_result("https://noise.example/item", relevant=False)]}), CONFIG)
    assert execution["observations"][0]["observation_class"] == "IRRELEVANT"
    assert execution["observations"][0]["relevance_status"] == "REJECTED"


def test_contradiction_executes_and_opens_bounded_follow_up() -> None:
    job = _job()
    parent = job["branches"][0]["question_ids"][0]
    execution = execute_research_round(job, FixtureResearchAdapter({"SEARCH_DISCOVERY": [_result(
        "https://audit.example/item", contradiction_candidates=["audit"],
        supporting_evidence_ids=["official"], contradicting_evidence_ids=["audit"],
        follow_up_question="ما السجل الزمني الذي يفسر التعارض؟",
    )]}), CONFIG)
    advanced = execution["job"]
    assert advanced["contradictions"][0]["status"] == "UNRESOLVED"
    assert any(item["parent_question_id"] == parent for item in advanced["question_tree"])
    assert len(advanced["branches"]) <= advanced["budget"]["max_branches"]


def test_follow_up_action_produces_a_new_observation() -> None:
    first = execute_research_round(_job(), FixtureResearchAdapter({"SEARCH_DISCOVERY": [_result(
        "https://audit.example/item", contradiction_candidates=["audit"], follow_up_question="ابحث عن النسخة الأصلية",
    )]}), CONFIG)
    second = execute_research_round(first["job"], FixtureResearchAdapter({"FOLLOW_REFERENCE": [_result("https://official.example/original", "official")]}), CONFIG)
    assert second["actions"][0]["action_type"] == "FOLLOW_REFERENCE"
    assert second["observations"][0]["url"] == "https://official.example/original"


def test_repetition_and_action_budgets_stop_unbounded_expansion() -> None:
    job = _job(budget="QUICK")
    branch = job["branches"][0]
    actions = [
        create_research_action(job, branch, action_type="SEARCH_DISCOVERY"),
        create_research_action(job, branch, action_type="SEARCH_DISCOVERY", target="repeat"),
        create_research_action(job, branch, action_type="SEARCH_DISCOVERY", target="third"),
    ]
    execution = execute_research_round(job, FixtureResearchAdapter({"SEARCH_DISCOVERY": [_result("https://repeat.example/item")]}), CONFIG, actions=actions)
    assert len(execution["actions"]) <= CONFIG["executor"]["budget_action_limits"]["QUICK"]["search_actions"]
    assert execution["job"]["status"] == "STOPPED"


def test_repeated_executor_material_stops_the_next_branch_round() -> None:
    first = execute_research_round(_job(), FixtureResearchAdapter({"SEARCH_DISCOVERY": [_result("https://repeat.example/item")]}), CONFIG)
    second = execute_research_round(first["job"], FixtureResearchAdapter({"SEARCH_DISCOVERY": [_result("https://repeat.example/item")]}), CONFIG)
    assert all(item["observation_class"] == "DUPLICATE" for item in second["observations"])
    assert second["job"]["stop_condition"] == "NO_BETTER_SOURCES"


def test_context_compression_keeps_open_questions_visible() -> None:
    job = _job()
    responses = [_result(f"https://source{index}.example/item", "unknown") for index in range(8)]
    execution = execute_research_round(job, FixtureResearchAdapter({"SEARCH_DISCOVERY": responses}), CONFIG)
    assert execution["job"]["unresolved_questions"]
    assert execution["job"]["context_summary"]["maximum_items_per_bucket"] == 12


def test_recovery_role_needs_execute_as_specific_actions() -> None:
    primary_need = {"need_id": "p", "candidate_id": "c", "kind": "FIND_PRIMARY_ORIGINAL_EVIDENCE", "max_attempts": 1}
    independent_need = {"need_id": "i", "candidate_id": "c", "kind": "FIND_INDEPENDENT_CORROBORATION", "max_attempts": 1}
    actions = plan_research_actions(_job(needs=[primary_need, independent_need]), CONFIG)
    assert {item["action_type"] for item in actions} == {"RECOVER_PRIMARY_SOURCE", "RECOVER_INDEPENDENT_SOURCE"}
    assert all(item["priority_class"] == "P0_BLOCKING_EVIDENCE" for item in actions)


def test_recovery_need_execution_records_attempt_and_structured_output() -> None:
    need = {"need_id": "p", "candidate_id": "c", "kind": "FIND_PRIMARY_ORIGINAL_EVIDENCE", "max_attempts": 1}
    execution = execute_research_round(_job(needs=[need]), FixtureResearchAdapter({"RECOVER_PRIMARY_SOURCE": [_result("https://official.example/original", "official")]}), CONFIG)
    assert execution["actions"][0]["action_type"] == "RECOVER_PRIMARY_SOURCE"
    # The ladder includes a bounded alternate-origin GDELT strategy, so the
    # first standard round no longer exhausts every strategy at once.
    assert execution["recovery_attempts"] == []
    assert execution["observations"][0]["observation_class"] == "POTENTIAL_EVIDENCE"


def test_primary_and_independent_only_gaps_get_opposite_recovery_searches() -> None:
    independent_need = {"need_id": "i", "candidate_id": "c", "kind": "FIND_INDEPENDENT_CORROBORATION", "max_attempts": 1}
    primary_need = {"need_id": "p", "candidate_id": "c", "kind": "FIND_PRIMARY_ORIGINAL_EVIDENCE", "max_attempts": 1}
    assert plan_research_actions(_job(needs=[independent_need]), CONFIG)[0]["action_type"] == "RECOVER_INDEPENDENT_SOURCE"
    assert plan_research_actions(_job(needs=[primary_need]), CONFIG)[0]["action_type"] == "RECOVER_PRIMARY_SOURCE"


def test_role_recovery_does_not_remove_breadth_need_from_the_plan() -> None:
    role_need = {"need_id": "role", "candidate_id": "c", "kind": "FIND_INDEPENDENT_CORROBORATION", "max_attempts": 1}
    breadth_need = {"need_id": "breadth", "candidate_id": None, "kind": "NEED_DISTINCT_EVENT", "max_attempts": 1}
    actions = plan_research_actions(_job(needs=[role_need, breadth_need]), CONFIG)
    assert {item["recovery_need_id"] for item in actions} == {"role", "breadth"}


def test_global_scheduler_services_p0_then_allows_p1_breadth() -> None:
    p0 = {"need_id": "p0", "candidate_id": "c", "kind": "FIND_INDEPENDENT_CORROBORATION", "max_attempts": 1}
    p1 = {"need_id": "p1", "candidate_id": None, "kind": "NEED_WORLD_BREADTH", "max_attempts": 1, "topic_identifiers": ["world"]}
    schedule = schedule_research_actions([_job(needs=[p0]), _job(needs=[p1])], CONFIG)
    assert {item["priority_class"] for item in schedule["actions"]} >= {"P0_BLOCKING_EVIDENCE", "P1_BREADTH"}
    assert schedule["actions"][0]["priority_class"] == "P0_BLOCKING_EVIDENCE"


def test_global_scheduler_is_fair_between_multiple_p0_needs() -> None:
    needs = [
        {"need_id": f"p{index}", "candidate_id": f"c{index}", "kind": "FIND_PRIMARY_ORIGINAL_EVIDENCE", "max_attempts": 1}
        for index in range(3)
    ]
    schedule = schedule_research_actions([_job(needs=[need]) for need in needs], CONFIG)
    first_wave = [item for item in schedule["actions"] if item["strategy_index"] == 0]
    assert {item["recovery_need_id"] for item in first_wave} == {"p0", "p1", "p2"}


def test_large_p0_queue_still_reserves_a_p1_breadth_attempt() -> None:
    p0_jobs = [
        _job(needs=[{"need_id": f"p{index}", "candidate_id": f"c{index}", "kind": "FIND_PRIMARY_ORIGINAL_EVIDENCE", "max_attempts": 1}])
        for index in range(12)
    ]
    breadth = _job(needs=[{"need_id": "world", "candidate_id": None, "kind": "NEED_WORLD_BREADTH", "max_attempts": 1, "topic_identifiers": ["world"]}])
    schedule = schedule_research_actions([*p0_jobs, breadth], CONFIG)
    assert any(item["recovery_need_id"] == "world" for item in schedule["actions"])


def test_query_ladder_relaxes_zero_yield_exact_without_headline_only_dependency() -> None:
    need = {
        "need_id": "p", "candidate_id": "c", "kind": "FIND_INDEPENDENT_CORROBORATION", "max_attempts": 1,
        "topic_identifiers": ["Provider headline only"],
        "query_context": {"entities": ["Meknes"], "event_terms": ["public procurement audit"], "research_date": "2026-09-11"},
    }
    ladder = query_ladder(_job(needs=[need]), need)
    assert [item["variant"] for item in ladder] == ["CONFIGURED_ROUTE", "EXACT", "RELAX_ENTITY_DATE", "EVENT_ALTERNATIVE", "SOURCE_SPECIFIC", "RELAX_TOPIC"]
    assert "Meknes" in ladder[1]["query"] and "2026-09" in ladder[1]["query"]
    assert "procurement" in ladder[1]["query"]


def test_query_fingerprint_deduplicates_word_order_but_not_strategy() -> None:
    assert query_fingerprint("Morocco election nominations 2026", intent="A") == query_fingerprint("2026 Morocco election nominationS", intent="A")
    assert query_fingerprint("Morocco election nominations 2026", intent="A") != query_fingerprint("Morocco election nominations 2026", intent="B")


def test_one_attempt_contains_multiple_query_variants_before_exhaustion() -> None:
    need = {"need_id": "p", "candidate_id": "c", "kind": "FIND_PRIMARY_ORIGINAL_EVIDENCE", "max_attempts": 1}
    job = _job(needs=[need])
    execution = execute_research_round(job, FixtureResearchAdapter({"RECOVER_PRIMARY_SOURCE": []}), CONFIG)
    progress = execution["recovery_strategy_progress"]
    assert progress == [{"need_id": "p", "executed_variants": [0, 1, 2], "strategy_count": 5, "attempt_exhausted": False}]
    assert execution["recovery_attempts"] == []
    # A bounded strategy executes several variants, but must not claim the
    # whole recovery attempt is exhausted merely because this round hit its
    # configured search budget.
    assert len(execution["actions"]) >= 2


def test_configured_route_failure_uses_one_bounded_alternative_origin_fallback() -> None:
    need = {
        "need_id": "i", "candidate_id": "c", "kind": "FIND_INDEPENDENT_CORROBORATION", "max_attempts": 1,
        "search_constraints": {"configured_source_routes": [
            {"role": "INDEPENDENT", "origin": "blocked.example", "url": "https://blocked.example/listing"},
        ]},
    }
    execution = execute_research_round(_job(needs=[need]), FixtureResearchAdapter({
        "FETCH_CONFIGURED_SOURCE": [{"result_type": "DEAD_END", "reason": "HTTP_401"}],
        "RECOVER_INDEPENDENT_SOURCE": [_result("https://news.example/exact", "independent")],
    }), CONFIG)
    fallback = next(item for item in execution["actions"] if item["query_variant"].endswith("_FALLBACK"))
    assert fallback["action_type"] == "RECOVER_INDEPENDENT_SOURCE"
    assert fallback["discovery_channel"] == "GDELT_DOC"


def test_p3_context_defers_when_round_has_higher_priority_work() -> None:
    p0 = {"need_id": "p0", "candidate_id": "c", "kind": "FIND_PRIMARY_ORIGINAL_EVIDENCE", "max_attempts": 1}
    jobs = [_job(desk=f"desk{index}", needs=[{**p0, "need_id": f"p{index}"}]) for index in range(4)]
    jobs.extend(_job() for _ in range(8))
    schedule = schedule_research_actions(jobs, CONFIG)
    assert all(item["priority_class"] != "P3_CONTEXT" for item in schedule["actions"])


@pytest.mark.parametrize("kind", ["NEED_WORLD_BREADTH", "NEED_ACCOUNTABILITY_AND_SERVICE"])
def test_breadth_needs_execute_targeted_discovery(kind: str) -> None:
    need = {"need_id": kind, "candidate_id": None, "kind": kind, "max_attempts": 1, "topic_identifiers": ["world"]}
    execution = execute_research_round(_job(needs=[need]), FixtureResearchAdapter({"SEARCH_DISCOVERY": [_result(f"https://{kind.lower()}.example/item", "unknown")]}), CONFIG)
    assert execution["actions"][0]["action_type"] == "SEARCH_DISCOVERY"
    assert execution["recovery_attempts"] == [kind]


def test_no_news_requires_terminal_executor_effort() -> None:
    job = _job(budget="QUICK")
    assert derive_research_outcome(job) == "CONTINUE_RESEARCH"
    execution = execute_research_round(job, FixtureResearchAdapter({"SEARCH_DISCOVERY": []}), CONFIG)
    assert execution["job"]["stop_condition"] == "NO_BETTER_SOURCES"
    assert derive_research_outcome(execution["job"]) == "NO_NEWS"


def test_science_results_remain_subject_to_strict_policy_and_disabled_boundaries() -> None:
    execution = execute_research_round(_job(desk="science"), FixtureResearchAdapter({"SEARCH_DISCOVERY": [_result("https://press.example/study", "independent")]}), CONFIG)
    assert execution["observations"][0]["publication_evidence"] is False
    assert evaluate_claim_policy("SCIENCE_CLAIM", [], CONFIG)["status"] == "NOT_READY"
    assert all(item["enabled"] is False for item in science_adapter_boundary(CONFIG).values())


@pytest.mark.parametrize("geography", [["Morocco"], ["Meknes"]])
def test_morocco_meknes_leads_can_use_investigative_lead_budget(geography: list[str]) -> None:
    job = _job(budget="INVESTIGATIVE_LEAD", geography=geography)
    assert job["lead"]["investigation_scope"]["status"] == "ELIGIBLE"
    assert job["budget_class"] == "INVESTIGATIVE_LEAD"


def test_foreign_scope_cannot_create_super_investigation_execution() -> None:
    scope = evaluate_super_investigation_scope({"geography": ["France"]})
    assert scope["status"] == "NOT_ELIGIBLE"
    job = _job(budget="STANDARD")
    assert all(action["research_regime"] != "SUPER_INVESTIGATION" for action in plan_research_actions(job, CONFIG))


def _source(identifier: str, source_type: str, origin: str) -> dict:
    return {
        "id": identifier, "url": f"https://{origin}/{identifier}", "publisher": origin,
        "publication_date": "2099-01-02", "accessed_at": "2099-01-02T07:00:00Z",
        "source_type": source_type, "claim_supported": f"Evidence for {identifier}",
    }


def _candidate(identifier: str, primary: list[str], independent: list[str]) -> dict:
    issues = []
    if not primary:
        issues.append("PRIMARY_EVIDENCE_MISSING")
    if not independent:
        issues.append("INDEPENDENT_EVIDENCE_MISSING")
    return {
        "id": identifier, "rank": 1, "title": f"Distinct event {identifier}",
        "discovery_source_ids": [*primary, *independent], "verification_source_ids": [*primary, *independent],
        "primary_evidence_source_ids": primary, "independent_evidence_source_ids": independent,
        "facts": [], "claims": [], "unknowns": [], "disputed_points": [],
        "evidence_eligibility": {"status": "ELIGIBLE" if not issues else "INELIGIBLE", "issues": issues},
    }


def _otherwise_sufficient_packet() -> dict:
    sources, sections = [], []
    for index, section_id in enumerate(sorted(SECTIONS)):
        primary, independent = f"p{index}", f"i{index}"
        sources.extend([_source(primary, "primary", f"official-{index}.example"), _source(independent, "independent", f"news-{index}.example")])
        candidate = _candidate(f"c{index}", [primary], [independent])
        if section_id == "investigations":
            candidate["editorial_functions"] = [{
                "function": "ACCOUNTABILITY", "status": "VALIDATED",
                "reason": "Fixture audit finding tied to a public authority.",
                "supporting_event_facts": ["The authority completed an audit."],
                "evidence_source_ids": [primary, independent],
                "classifier_version": "editorial-functions-v1",
            }]
        elif section_id == "service":
            candidate["editorial_functions"] = [{
                "function": name, "status": "VALIDATED",
                "reason": "Fixture verified actionable public procedure.",
                "supporting_event_facts": ["Readers have a registration deadline."],
                "evidence_source_ids": [primary, independent],
                "classifier_version": "editorial-functions-v1",
            } for name in ("SERVICE", "READER_VALUE")]
        sections.append({"section_id": section_id, "status": "ACTIVE", "selected_candidate_id": candidate["id"], "candidates": [candidate]})
    return {"edition_date": "2099-01-02", "sources": sources, "sections": sections}


def test_representative_insufficient_to_ready_replay_and_article_gate() -> None:
    packet = _otherwise_sufficient_packet()
    front = next(item for item in packet["sections"] if item["section_id"] == "front")
    candidate = front["candidates"][0]
    missing = candidate["independent_evidence_source_ids"].pop()
    candidate["discovery_source_ids"].remove(missing)
    candidate["verification_source_ids"].remove(missing)
    candidate["evidence_eligibility"] = {"status": "INELIGIBLE", "issues": ["INDEPENDENT_EVIDENCE_MISSING"]}
    coverage, readiness = _coverage(), load_local_config(ROOT)["editorial_readiness"]
    initial = build_recovery_plan(packet, build_source_intelligence(packet), coverage, readiness)
    need = next(item for item in initial["needs"] if item["candidate_id"] == candidate["id"])
    job = _job(needs=[need])
    fixture = json.loads((ROOT / "tests" / "fixtures" / "deep-research-executor-insufficient-ready.json").read_text(encoding="utf-8"))
    execution = execute_research_round(job, FixtureResearchAdapter(fixture["executor_responses"]), CONFIG)
    assert execution["source_packet_patch"]["candidate_evidence_updates"]
    replay = replay_recovery_after_execution(packet, execution, coverage, readiness)
    assert replay["source_intelligence"]["status"] == fixture["expected"]["source_intelligence"]
    assert replay["recovery"]["status"] == fixture["expected"]["recovery"]
    assert replay["status"] == "READY"
    assert replay["article_generation_allowed"] is fixture["expected"]["article_generation_allowed"]


def test_exact_page_followup_promotion_closes_recovery_without_fixture_verified_marker() -> None:
    packet = _otherwise_sufficient_packet()
    front = next(item for item in packet["sections"] if item["section_id"] == "front")
    candidate = front["candidates"][0]
    missing = candidate["independent_evidence_source_ids"].pop()
    candidate["discovery_source_ids"].remove(missing)
    candidate["verification_source_ids"].remove(missing)
    candidate["evidence_eligibility"] = {"status": "INELIGIBLE", "issues": ["INDEPENDENT_EVIDENCE_MISSING"]}
    coverage, readiness = _coverage(), load_local_config(ROOT)["editorial_readiness"]
    need = next(item for item in build_recovery_plan(packet, build_source_intelligence(packet), coverage, readiness)["needs"] if item["candidate_id"] == candidate["id"])
    job = _job(needs=[need])
    action = create_research_action(job, job["branches"][0], recovery_need=need)
    adapter = FixtureResearchAdapter({
        "RECOVER_INDEPENDENT_SOURCE": [{"result_type": "LEAD", "url": "https://news-recovery.example/front", "title": "Discovery lead", "source_class": "unknown"}],
        "FETCH_URL": [{
            "url": "https://news-recovery.example/front", "canonical_url": "https://news-recovery.example/front",
            "title": candidate["title"], "text": f"{candidate['title']} independently reported with direct details.",
            "fetch_status": "FETCHED", "content_hash": "d" * 64, "source_class": "independent",
            "claim": f"Independent reporting on {candidate['title']}.", "published_at": "2099-01-02", "retrieved_at": "2099-01-02T08:00:00Z",
        }],
    })
    adapter.follow_discovery_leads = True
    execution = execute_research_round(job, adapter, CONFIG, actions=[action])
    assert any(item["verification_status"] == "VALIDATED_EVIDENCE" for item in execution["observations"])
    replay = replay_recovery_after_execution(packet, execution, coverage, readiness)
    assert replay["status"] == "READY"
    assert replay["article_generation_allowed"] is True


def test_unresolved_recovery_keeps_article_generation_blocked() -> None:
    packet = _otherwise_sufficient_packet()
    front = next(item for item in packet["sections"] if item["section_id"] == "front")
    candidate = front["candidates"][0]
    candidate["independent_evidence_source_ids"] = []
    candidate["evidence_eligibility"] = {"status": "INELIGIBLE", "issues": ["INDEPENDENT_EVIDENCE_MISSING"]}
    coverage, readiness = _coverage(), load_local_config(ROOT)["editorial_readiness"]
    need = next(item for item in build_recovery_plan(packet, build_source_intelligence(packet), coverage, readiness)["needs"] if item["candidate_id"] == candidate["id"])
    execution = execute_research_round(_job(needs=[need]), FixtureResearchAdapter({"RECOVER_INDEPENDENT_SOURCE": []}), CONFIG)
    replay = replay_recovery_after_execution(packet, execution, coverage, readiness)
    assert replay["article_generation_allowed"] is False
    assert replay["status"] == "RESEARCH_GAPS_REMAIN"


def test_fixture_verified_stronger_same_desk_candidate_can_replace_weak_selection() -> None:
    packet = _otherwise_sufficient_packet()
    front = next(item for item in packet["sections"] if item["section_id"] == "front")
    weak = front["candidates"][0]
    weak["independent_evidence_source_ids"] = []
    weak["evidence_eligibility"] = {"status": "INELIGIBLE", "issues": ["INDEPENDENT_EVIDENCE_MISSING"]}
    packet["sources"].append(_source("alternate-primary", "primary", "alternate-official.example"))
    alternate = _candidate("alternate", ["alternate-primary"], [])
    front["candidates"].append(alternate)
    execution = {"source_packet_patch": {
        "sources": [{**_source("alternate-independent", "independent", "alternate-news.example"), "verification_status": "VERIFIED_EVIDENCE"}],
        "candidate_evidence_updates": [{"candidate_id": "alternate", "source_id": "alternate-independent", "role": "INDEPENDENT"}],
    }}
    patched = apply_executor_results_to_packet(packet, execution)
    patched_front = next(item for item in patched["sections"] if item["section_id"] == "front")
    assert patched_front["selected_candidate_id"] == "alternate"
    assert patched_front["selection_reason"] == "RECOVERY_EXACT_EVIDENCE_REPLACEMENT"


def test_validated_new_event_can_replace_an_ineligible_same_desk_selection() -> None:
    packet = _otherwise_sufficient_packet()
    front = next(item for item in packet["sections"] if item["section_id"] == "front")
    weak = front["candidates"][0]
    weak["independent_evidence_source_ids"] = []
    weak["evidence_eligibility"] = {"status": "INELIGIBLE", "issues": ["INDEPENDENT_EVIDENCE_MISSING"]}
    execution = {"source_packet_patch": {
        "sources": [{
            **_source("new-official", "official", "ministry.example"),
            "title": "Ministry official service timetable", "claim_supported": "The Ministry official announces a service timetable.",
            "verification_status": "VALIDATED_EVIDENCE",
        }],
        "candidate_evidence_updates": [],
        "candidate_discoveries": [{
            "section_id": "front", "event_id": "EVT-NEW", "title": "Ministry official service timetable",
            "claim": "The Ministry official announces a service timetable.", "source_id": "new-official", "role": "PRIMARY",
            "editorial_value_reason": "SERVICE_USEFULNESS",
        }],
    }}
    patched = apply_executor_results_to_packet(packet, execution)
    patched_front = next(item for item in patched["sections"] if item["section_id"] == "front")
    assert patched_front["selected_candidate_id"] != weak["id"]
    replacement = next(item for item in patched_front["candidates"] if item["id"] == patched_front["selected_candidate_id"])
    assert replacement["discovered_by"] == "VALIDATED_DISTINCT_EVENT_RECOVERY"
    assert replacement["evidence_eligibility"]["status"] == "ELIGIBLE"
    assert patched_front["selection_reason"] == "RECOVERY_EXACT_EVIDENCE_REPLACEMENT"


def test_validated_breadth_event_routes_to_an_eligible_empty_affinity_desk() -> None:
    packet = _otherwise_sufficient_packet()
    justice = next(item for item in packet["sections"] if item["section_id"] == "3adl_7o9o9")
    justice.update({"status": "NO_NEWS", "selected_candidate_id": None, "candidates": [], "recovery_candidates": []})
    execution = {"source_packet_patch": {
        "sources": [
            {**_source("primary", "primary", "authority.example"), "verification_status": "VALIDATED_EVIDENCE"},
            {**_source("independent", "independent", "news.example"), "verification_status": "VALIDATED_EVIDENCE"},
        ], "candidate_evidence_updates": [],
        "candidate_discoveries": [{
            "section_id": "siyasa_dawla", "event_id": "EVT-INTEGRITY", "title": "Authorities sign anti-corruption memorandum",
            "claim": "Authorities sign anti-corruption memorandum.", "editorial_value_reason": "INSTITUTIONAL_ACTION",
            "recovery_need_id": "BREADTH:morocco_breadth:1", "eligible_section_ids": ["siyasa_dawla", "3adl_7o9o9"],
            "preferred_section_ids": ["3adl_7o9o9", "siyasa_dawla"],
            "source_roles": [{"source_id": "primary", "role": "PRIMARY"}, {"source_id": "independent", "role": "INDEPENDENT"}],
        }],
    }}
    patched = apply_executor_results_to_packet(packet, execution)
    justice = next(item for item in patched["sections"] if item["section_id"] == "3adl_7o9o9")
    assert justice["status"] == "ACTIVE"
    assert justice["selected_candidate_id"]


def test_low_value_new_event_cannot_create_or_close_breadth_candidate() -> None:
    packet = _otherwise_sufficient_packet()
    front = next(item for item in packet["sections"] if item["section_id"] == "front")
    before_ids = {item["id"] for item in front["candidates"]}
    execution = {"source_packet_patch": {
        "sources": [{**_source("gallery", "independent", "local.example"), "verification_status": "VALIDATED_EVIDENCE"}],
        "candidate_evidence_updates": [],
        # A bare photo/gallery item has no categorical public-interest reason.
        "candidate_discoveries": [{
            "section_id": "front", "event_id": "EVT-FILLER", "title": "Local photo gallery",
            "claim": "A local photo gallery was posted.", "source_id": "gallery", "role": "INDEPENDENT",
        }],
    }}
    patched = apply_executor_results_to_packet(packet, execution)
    patched_front = next(item for item in patched["sections"] if item["section_id"] == "front")
    assert {item["id"] for item in patched_front["candidates"]} == before_ids
    assert patched_front["selected_candidate_id"] == front["selected_candidate_id"]


def test_unknown_article_event_lead_triggers_alternative_coverage_before_promotion() -> None:
    """No candidate is injected: all states originate in fetched page records."""
    need = {
        "need_id": "BREADTH:NEED_DISTINCT_EVENT:1", "kind": "NEED_DISTINCT_EVENT", "max_attempts": 1,
        "query_context": {"research_date": "2099-01-02"},
        "search_constraints": {"must_be_distinct_event": True, "eligible_section_ids": ["service"]},
        "event_acquisition_plan": {
            "editorial_gap": "DISTINCT_EVENT_BREADTH", "candidate_event_themes": ["public service"],
            "acceptable_story_roles": ["brief", "normal"],
        },
    }
    job = _job(desk="service", needs=[need])
    initial = plan_research_actions(job, CONFIG)[0]

    def page(url: str, source_class: str, *, publisher: str | None) -> dict:
        return {
            "url": url, "canonical_url": url, "title": "Ministry signs public transport agreement",
            "title_state": "TITLE_RESOLVED", "published_at": "2099-01-02T09:00:00+00:00",
            "publication_date": {"raw": "2099-01-02T09:00:00+00:00", "normalized": "2099-01-02T09:00:00+00:00"},
            "text": "The Ministry signs a public transport agreement for a new service route. " * 8,
            "fetch_status": "FETCHED", "content_hash": ("a" if source_class == "unknown" else "b" if source_class == "official" else "c") * 64,
            "source_class": source_class, "claim": "The Ministry signs a public transport agreement.", "event_id": "EVT-TRANSPORT-NEW",
            "article_metadata": {"title_state": "TITLE_RESOLVED", "publisher": {"name": publisher, "state": "PUBLISHER_RESOLVED_ARTICLE_ROLE_PENDING" if publisher else "PUBLISHER_UNRESOLVED"}},
        }

    class FlowAdapter:
        follow_discovery_leads = True

        def execute(self, action: dict) -> list[dict]:
            if action.get("target") == "https://unknown.example/event":
                return [page(action["target"], "unknown", publisher=None)]
            if action.get("target") == "https://official.example/event":
                return [page(action["target"], "official", publisher="Ministry")]
            if action.get("target") == "https://independent.example/event":
                return [page(action["target"], "independent", publisher="Independent News")]
            if action.get("event_lead_feedback"):
                return [
                    {"result_type": "LEAD", "url": "https://official.example/event", "title": "Ministry signs public transport agreement", "source_class": "unknown"},
                    {"result_type": "LEAD", "url": "https://independent.example/event", "title": "Ministry signs public transport agreement", "source_class": "unknown"},
                ]
            return [{"result_type": "LEAD", "url": "https://unknown.example/event", "title": "Ministry signs public transport agreement", "source_class": "unknown"}]

    execution = execute_research_round(job, FlowAdapter(), CONFIG, actions=[initial])
    assert execution["source_packet_patch"]["event_leads"][0]["state"] == "EVENT_LEAD_DISCOVERY_ONLY"
    assert execution["source_packet_patch"]["event_leads"][0]["publication_evidence"] is False
    event_lead_id = execution["source_packet_patch"]["event_leads"][0]["event_lead_id"]
    feedback = next(item for item in execution["actions"] if item.get("query_intent") == "EVENT_LEAD_ALTERNATIVE_COVERAGE")
    assert feedback["originating_event_lead_id"] == event_lead_id
    # The alternative pass attaches distinct publishers to one event bundle;
    # it must create one candidate, not two headline-shaped events.
    assert len(execution["source_packet_patch"]["candidate_discoveries"]) == 1
    bundle = execution["source_packet_patch"]["event_bundles"][0]
    assert bundle["state"] == "EVENT_VALIDATED"
    assert {item["role"] for item in bundle["source_roles"]} == {"PRIMARY", "INDEPENDENT"}
    attached = [item for item in execution["observations"] if item.get("provenance", {}).get("originating_event_lead_id") == event_lead_id]
    assert len(attached) >= 2
    replay = replay_event_bundles_from_snapshot(execution["observation_snapshot"])
    assert replay["production_evidence_reuse"] is False
    assert replay["event_bundles"][0]["event_lead_id"] == event_lead_id
    packet = {"edition_date": "2099-01-02", "sources": [], "sections": [{"section_id": "service", "status": "NO_NEWS", "selected_candidate_id": None, "candidates": [], "recovery_candidates": []}]}
    patched = apply_executor_results_to_packet(packet, execution)
    section = patched["sections"][0]
    assert section["status"] == "ACTIVE"
    assert section["selected_candidate_id"]
    # The same executor-produced candidate closes genuine edition breadth in
    # an otherwise sufficient nine-section packet; no normalized candidate is
    # inserted by the test.
    closure_packet = _otherwise_sufficient_packet()
    keep = {"siyasa_dawla", "iqtisad_flous", "mojtama3", "africa_sahel", "world", "sport", "culture", "opinion", "technology"}
    for item in closure_packet["sections"]:
        if item["section_id"] not in keep:
            item.update({"status": "NO_NEWS", "selected_candidate_id": None, "candidates": [], "recovery_candidates": []})
    coverage, readiness = _coverage(), load_local_config(ROOT)["editorial_readiness"]
    before = build_recovery_plan(closure_packet, build_source_intelligence(closure_packet), coverage, readiness)
    assert any(item["need_id"].startswith("BREADTH:") for item in before["needs"])
    replay = replay_recovery_after_execution(closure_packet, execution, coverage, readiness)
    # A transport-agreement lead is concrete enough to remain a candidate,
    # but does not claim a verified reader action or formal oversight
    # mechanism.  A service desk placement alone cannot close the V5
    # semantic family.
    assert replay["status"] == "RESEARCH_GAPS_REMAIN"
    assert any(
        item["target_editorial_function"] in {"ACCOUNTABILITY", "SERVICE"}
        for item in replay["recovery"]["needs"]
        if item["kind"] == "NEED_ACCOUNTABILITY_AND_SERVICE"
    )
    assert replay["article_generation_allowed"] is False


def test_event_matcher_uses_structured_cues_across_headlines_and_languages() -> None:
    english = {
        "state": "CONCRETE_EVENT", "actor": "Morocco anti-corruption authority", "action": "sign",
        "object": "Hong Kong ICAC memorandum", "topic": "Morocco signs anti-corruption memorandum",
        "geography": ["morocco", "hong kong"], "published_at": "2099-01-02T09:00:00Z", "identifiers": ["MOU-77"],
    }
    arabic = {
        "state": "CONCRETE_EVENT", "actor": "هيئة النزاهة المغربية", "action": "يوقع",
        "object": "مذكرة تفاهم مع ICAC", "topic": "توقيع مذكرة تفاهم", "geography": ["morocco", "hong kong"],
        "published_at": "2099-01-02T14:00:00Z", "identifiers": ["MOU-77"],
    }
    different = {**arabic, "action": "announce", "published_at": "2099-01-03T14:00:00Z", "identifiers": []}
    assert match_event_skeletons(english, arabic)["state"] == "SAME_EVENT_HIGH_CONFIDENCE"
    assert match_event_skeletons(english, different)["state"] == "DIFFERENT_EVENT"


def test_observation_snapshot_is_hash_bound_and_cannot_be_live_evidence() -> None:
    snapshot = build_observation_snapshot([], [], [])
    replay = replay_event_bundles_from_snapshot(snapshot)
    assert replay == {"mode": "TEST_REPLAY_EVIDENCE", "event_bundles": [], "production_evidence_reuse": False}
    snapshot["observations"] = [{"url": "https://tampered.example"}]
    with pytest.raises(ResearchExecutorError, match="OBSERVATION_SNAPSHOT_HASH_MISMATCH"):
        replay_event_bundles_from_snapshot(snapshot)


def test_first_party_document_is_primary_only_for_its_direct_signing_claim() -> None:
    action = _job().get("branches")[0]
    skeleton = {"state": "CONCRETE_EVENT", "actor": "Institution Alpha", "action": "sign", "institution": "Institution Alpha"}
    raw = {
        "url": "https://institution-alpha.example/releases/agreement", "title": "Institution Alpha signed agreement X",
        "text": "Institution Alpha signed agreement X with its counterpart. " * 8,
        "article_metadata": {"publisher": {"name": "Institution Alpha"}, "signals": {"html_title": "Institution Alpha institutional portal"}, "jsonld_article_types": []},
        "publisher_profile": {"canonical_domain": "institution-alpha.example", "canonical_publisher_name": "Institution Alpha", "identity_state": "PUBLISHER_PROFILE_RESOLVED"},
    }
    resolved = resolve_exact_source_role(raw, action, skeleton)
    assert resolved["source_class"] == "primary"
    assert resolved["publisher_event_relation"] == "PUBLISHER_IS_EVENT_ACTOR"
    assert resolved["document_type"] == "SIGNED_DOCUMENT"


def test_newsroom_and_wire_lineage_do_not_become_primary_or_independent_automatically() -> None:
    action = _job().get("branches")[0]
    skeleton = {"state": "CONCRETE_EVENT", "actor": "Institution Alpha", "action": "sign"}
    newsroom = {
        "url": "https://news.example/a", "title": "Institution Alpha signed agreement X", "text": "Institution Alpha signed agreement X. " * 10,
        "article_metadata": {"publisher": {"name": "Newsroom"}, "jsonld_article_types": ["NewsArticle"]},
        "publisher_profile": {"canonical_domain": "news.example"},
        "article_attribution": {"author_byline": "Reporter", "article_origin_state": "ORIGINAL_UNKNOWN"},
    }
    assert resolve_exact_source_role(newsroom, action, skeleton)["source_class"] == "independent"
    wire = {**newsroom, "article_attribution": {"author_byline": "Reporter", "wire_credit": "AFP", "article_origin_state": "WIRE_REPUBLICATION"}}
    resolved_wire = resolve_exact_source_role(wire, action, skeleton)
    assert resolved_wire["source_class"] == "unknown"
    assert resolved_wire["reason"] == "ARTICLE_LINEAGE_IS_NOT_AN_INDEPENDENT_ORIGIN"


def test_profile_aliases_support_cross_language_organization_identity_without_fuzzy_matching() -> None:
    action = _job().get("branches")[0]
    raw = {
        "url": "https://authority.example/a", "title": "Authority signs an agreement", "text": "Authority signs an agreement with a counterpart. " * 10,
        "article_metadata": {"publisher": {"name": "National Integrity Authority"}, "signals": {"html_title": "Authority official portal"}, "jsonld_article_types": []},
        "publisher_profile": {"canonical_domain": "authority.example", "known_aliases": ["هيئة النزاهة", "NIA"]},
    }
    matched = resolve_exact_source_role(raw, action, {"state": "CONCRETE_EVENT", "actor": "هيئة النزاهة توقع اتفاقا", "action": "sign"})
    assert matched["source_class"] == "primary"
    ambiguous = resolve_exact_source_role(raw, action, {"state": "CONCRETE_EVENT", "actor": "هيئة وطنية أخرى", "action": "sign"})
    assert ambiguous["source_class"] == "unknown"


def test_primary_status_does_not_convert_prediction_or_audit_finding_into_broader_claim_support() -> None:
    action = _job().get("branches")[0]
    raw = {
        "url": "https://institution-alpha.example/a", "title": "Institution Alpha announces policy", "text": "Institution Alpha announces policy that may create economic benefit. " * 10,
        "article_metadata": {"publisher": {"name": "Institution Alpha"}, "signals": {"html_title": "Institution Alpha official statement"}, "jsonld_article_types": []},
        "publisher_profile": {"canonical_domain": "institution-alpha.example"},
    }
    policy = resolve_exact_source_role(raw, action, {"state": "CONCRETE_EVENT", "actor": "Institution Alpha", "action": "announce"})
    assert policy["source_class"] == "primary"
    audit = {**raw, "title": "Institution A audit report", "text": "Institution A audit report records an irregularity. " * 10}
    finding = resolve_exact_source_role(audit, action, {"state": "CONCRETE_EVENT", "actor": "Institution Alpha", "action": "report"})
    assert finding["source_class"] == "primary"
    assert finding["document_type"] == "AUDIT_REPORT"
    assert finding["publisher_event_relation"] == "PUBLISHER_IS_DOCUMENT_ISSUER"


def test_http_adapter_only_executes_direct_fetch_actions() -> None:
    job = _job()
    with pytest.raises(ResearchExecutorError, match="RESEARCH_ACTION_ADAPTER_UNAVAILABLE"):
        HttpResearchAdapter().execute(plan_research_actions(job, CONFIG)[0])


def test_pipeline_execution_stage_writes_structured_adapter_report(tmp_path: Path) -> None:
    job = _job()
    state_path = tmp_path / "deep-research" / "state.json"
    state_path.parent.mkdir(parents=True)
    state_path.write_text(json.dumps({"schema_version": 1, "status": "PLANNED", "jobs": [job]}), encoding="utf-8")
    stage = next(item for item in build_stage_definitions(
        SyntheticEditorialProvider(), research_adapter=FixtureResearchAdapter({"SEARCH_DISCOVERY": [_result("https://pipeline.example/item")]}),
    ) if item.name == "deep_research_execution")
    result = stage.runner(StageContext(ROOT, "2099-01-02", tmp_path, tmp_path, 1))
    report = json.loads(result.outputs[0].read_text(encoding="utf-8"))
    assert report["status"] == "EXECUTED"
    assert report["jobs"][0]["observations"][0]["url"] == "https://pipeline.example/item"


def test_pipeline_executes_breadth_while_p0_remains_open(tmp_path: Path) -> None:
    p0 = {"need_id": "p0", "candidate_id": "c", "kind": "FIND_INDEPENDENT_CORROBORATION", "max_attempts": 1}
    p1 = {"need_id": "p1", "candidate_id": None, "kind": "NEED_WORLD_BREADTH", "max_attempts": 1, "topic_identifiers": ["world"]}
    state_path = tmp_path / "deep-research" / "state.json"
    state_path.parent.mkdir(parents=True)
    state_path.write_text(json.dumps({"schema_version": 1, "status": "PLANNED", "jobs": [_job(needs=[p0]), _job(needs=[p1])]}), encoding="utf-8")
    stage = next(item for item in build_stage_definitions(
        SyntheticEditorialProvider(), research_adapter=FixtureResearchAdapter({"SEARCH_DISCOVERY": []}),
    ) if item.name == "deep_research_execution")
    result = stage.runner(StageContext(ROOT, "2099-01-02", tmp_path, tmp_path, 1))
    report = json.loads(result.outputs[0].read_text(encoding="utf-8"))
    attempted = {action["recovery_need_id"] for action in report["actions_planned"]}
    assert attempted >= {"p0", "p1"}
    assert all(action["publication_evidence"] is False for job in report["jobs"] for action in job["observations"])


def test_pipeline_execution_stage_fails_closed_when_no_adapter_is_supplied(tmp_path: Path) -> None:
    job = _job()
    state_path = tmp_path / "deep-research" / "state.json"
    state_path.parent.mkdir(parents=True)
    state_path.write_text(json.dumps({"schema_version": 1, "status": "PLANNED", "jobs": [job]}), encoding="utf-8")
    stage = next(item for item in build_stage_definitions(SyntheticEditorialProvider()) if item.name == "deep_research_execution")
    result = stage.runner(StageContext(ROOT, "2099-01-02", tmp_path, tmp_path, 1))
    report = json.loads(result.outputs[0].read_text(encoding="utf-8"))
    assert report["status"] == "ADAPTER_UNCONFIGURED"
    assert report["actions_planned"]
