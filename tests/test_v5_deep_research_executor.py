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
    build_research_yield_report,
    create_research_action,
    execute_research_round,
    plan_research_actions,
    replay_recovery_after_execution,
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


def test_followup_fetch_inspects_rss_leads_within_the_existing_fetch_budget() -> None:
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
    assert execution["budget_consumed"]["fetches"] >= 1


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
    assert [item["action_type"] for item in actions[:2]] == ["RECOVER_PRIMARY_SOURCE", "RECOVER_INDEPENDENT_SOURCE"]


def test_recovery_need_execution_records_attempt_and_structured_output() -> None:
    need = {"need_id": "p", "candidate_id": "c", "kind": "FIND_PRIMARY_ORIGINAL_EVIDENCE", "max_attempts": 1}
    execution = execute_research_round(_job(needs=[need]), FixtureResearchAdapter({"RECOVER_PRIMARY_SOURCE": [_result("https://official.example/original", "official")]}), CONFIG)
    assert execution["actions"][0]["action_type"] == "RECOVER_PRIMARY_SOURCE"
    assert execution["recovery_attempts"] == ["p"]
    assert execution["observations"][0]["observation_class"] == "POTENTIAL_EVIDENCE"


def test_primary_and_independent_only_gaps_get_opposite_recovery_searches() -> None:
    independent_need = {"need_id": "i", "candidate_id": "c", "kind": "FIND_INDEPENDENT_CORROBORATION", "max_attempts": 1}
    primary_need = {"need_id": "p", "candidate_id": "c", "kind": "FIND_PRIMARY_ORIGINAL_EVIDENCE", "max_attempts": 1}
    assert plan_research_actions(_job(needs=[independent_need]), CONFIG)[0]["action_type"] == "RECOVER_INDEPENDENT_SOURCE"
    assert plan_research_actions(_job(needs=[primary_need]), CONFIG)[0]["action_type"] == "RECOVER_PRIMARY_SOURCE"


def test_role_recovery_defers_breadth_need_in_the_same_job() -> None:
    role_need = {"need_id": "role", "candidate_id": "c", "kind": "FIND_INDEPENDENT_CORROBORATION", "max_attempts": 1}
    breadth_need = {"need_id": "breadth", "candidate_id": None, "kind": "NEED_DISTINCT_EVENT", "max_attempts": 1}
    actions = plan_research_actions(_job(needs=[role_need, breadth_need]), CONFIG)
    assert [item["recovery_need_id"] for item in actions] == ["role"]


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
