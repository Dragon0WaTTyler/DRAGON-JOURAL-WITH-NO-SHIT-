"""Mandatory research is distinct from event existence. All tests are offline."""

from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import socket
import json
import shutil
import subprocess

import pytest

from dragon.config import load_local_config
from dragon.deep_research import build_deep_research_state, load_deep_research_config
from dragon.deep_research_executor import FixtureResearchAdapter, plan_research_actions
from dragon.editorial_functions import classify_event_functions
from dragon.providers import LocalCommandEditorialProvider, ProviderError, SECTION_HEADINGS
from dragon.provider_targeting import build_research_targeting
from dragon.research_finality import apply_research_finality, build_research_finality, validate_research_finality
from dragon.research_finality_acceptance import preserved_inputs, evaluate
from dragon.research_recovery import build_recovery_plan, validate_recovery_plan
from dragon.source_coverage import load_source_coverage
from dragon.source_intelligence import build_source_intelligence
from dragon.pipeline import build_stage_definitions
from dragon.research_acceptance import ProviderFreeAcceptanceProvider
from dragon.stages import StageContext
from dragon.state import atomic_write_json


ROOT = Path(__file__).resolve().parents[1]
DATE = "2026-10-04"
TIME = DATE + "T10:00:00+00:00"


@pytest.fixture(autouse=True)
def no_live_calls(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Finality task attempted provider or network execution")
    monkeypatch.setattr(LocalCommandEditorialProvider, "_invoke", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)


@pytest.fixture
def case():
    readiness = {"coverage_rules": [{"id": "accountability_and_service", "minimum_active": 2,
                                    "sections": ["investigations", "opinion", "service"]}]}
    targeting = build_research_targeting(DATE, readiness)
    config = load_deep_research_config(ROOT / "config/deep-research.yaml", ROOT / "config/deep-research-schema.json")
    coverage = load_source_coverage(ROOT / "config/source-coverage.yaml", {s for s, _ in SECTION_HEADINGS})
    packet = {"edition_date": DATE, "sources": [], "sections": [],
              "hard_target_results": [{"target_id": "HARD:" + lane, "status": "NO_QUALIFYING_CANDIDATE_FOUND",
                "search_intent": "Current " + lane + " research", "search_attempts": [{"query": lane, "purpose": "Current exact artifacts"}],
                "no_qualifying_reason": "No current candidate survived discovery", "candidate_matches": []} for lane in ("ACCOUNTABILITY", "SERVICE")],
              "provider_response_validation": {"status": "PASS", "hard_targets": [
                  {"target_id": "HARD:" + lane, "target_contract_status": "PASS", "target_error": None,
                   "target_disposition_effective": "NO_QUALIFYING_CANDIDATE_FOUND", "accepted_candidate_count": 0}
                  for lane in ("ACCOUNTABILITY", "SERVICE")]}}
    intelligence = build_source_intelligence(packet)
    plan = build_recovery_plan(packet, intelligence, coverage, readiness)
    state = build_deep_research_state(packet, intelligence, {"lanes": []}, plan, config,
        run_scope_id="deterministic-negative-fixture", recovery_epoch=1, recovery_only=True)
    jobs = []
    for job in state["jobs"]:
        actions = plan_research_actions(job, config)
        observations = []
        for action in actions:
            fetch = action["action_type"] == "FETCH_CONFIGURED_SOURCE"
            observations.append({"observation_id": "OBS-" + action["action_id"], "provenance": {"action_id": action["action_id"]},
                "kind": "LEAD" if fetch else "DEAD_END", "title": "Directory" if fetch else "SEARXNG_NO_MATCHES",
                "discovery_reason": None if fetch else "SEARXNG_NO_MATCHES", "extraction_status": "FETCHED" if fetch else "NOT_RETRIEVED",
                "extracted_text": "A directory of institutional links without an event or operational notice." if fetch else None,
                "content_hash": "fixture-directory-hash" if fetch else None, "observed_at": TIME,
                "url": action.get("target"), "relevance_status": "REJECTED"})
        jobs.append({"job": deepcopy(job), "actions": actions, "observations": observations, "recovery_strategy_progress": []})
    epochs = [{"epoch": 1, "state": state, "execution": {"status": "EXECUTED", "jobs": jobs, "deferred_actions": [],
               "round_execution_budget": {"maximum_actions_per_round": 8, "budget_increased": False}}}]
    return {"packet": packet, "targeting": targeting, "config": config, "epochs": epochs, "closed_at": TIME,
            "plan": plan, "coverage": coverage, "readiness": readiness}


def finality(case, **changes):
    return build_research_finality(case["packet"], **{k: case[k] for k in ("targeting", "config", "epochs", "closed_at")}, **changes)


def add_validated_event(case, lane="ACCOUNTABILITY"):
    title = "Public regulator publishes audit findings" if lane == "ACCOUNTABILITY" else "Public service registration opens"
    text = "Public authority publishes an audit report documenting oversight findings." if lane == "ACCOUNTABILITY" else "The public service operator opens registration and states the current deadline."
    ids = ["p-" + lane, "i-" + lane]
    sources = [{"id": sid, "url": "https://" + origin + "/artifact", "publisher": origin, "source_type": role,
                "publication_date": DATE, "accessed_at": TIME, "claim_supported": text}
               for sid, role, origin in zip(ids, ("primary", "independent"), ("authority.example", "reporter.example"))]
    case["packet"]["sources"].extend(sources)
    functions = classify_event_functions(title=title, facts=[text], evidence_source_ids=ids, exact_page_validated=True)
    candidate = {"id": "valid-" + lane, "title": title, "rank": 1, "facts": [text], "claims": [], "unknowns": [], "disputed_points": [],
        "discovery_source_ids": ids, "verification_source_ids": ids, "primary_evidence_source_ids": ids[:1], "independent_evidence_source_ids": ids[1:],
        "evidence_eligibility": {"status": "ELIGIBLE", "issues": []}, "editorial_functions": functions}
    case["packet"]["sections"].append({"section_id": "investigations" if lane == "ACCOUNTABILITY" else "service", "status": "ACTIVE",
        "selected_candidate_id": candidate["id"], "candidates": [candidate]})
    job = {"actions": [], "observations": []}
    case["epochs"].insert(0, {"epoch": 0, "state": {"jobs": []}, "execution": {"status": "EXECUTED", "jobs": [job],
                             "round_execution_budget": {"maximum_actions_per_round": 8, "budget_increased": False}}})
    for sid, role, origin in zip(ids, ("PRIMARY", "INDEPENDENT"), ("authority.example", "reporter.example")):
        job["actions"].append({"action_id": "FETCH-" + sid, "action_type": "FETCH_URL", "job_id": "validated-fixture", "target_editorial_function": lane, "target": "https://" + origin + "/artifact"})
        job["observations"].append({"observation_id": "O-" + sid, "source_id": sid, "kind": "POTENTIAL_EVIDENCE",
            "provenance": {"action_id": "FETCH-" + sid}, "url": "https://" + origin + "/artifact",
            "title": title, "extracted_text": text, "content_hash": "fixture-" + sid, "origin": origin, "extraction_status": "FETCHED",
            "validation_state": "VALIDATED_EVIDENCE", "temporal_relevance": {"active_on_edition_date": True},
            "source_role_resolution": {"evidence_role": role, "independence_state": "INDEPENDENT_ORIGINAL_REPORTING" if role == "INDEPENDENT" else "NOT_APPLICABLE_PRIMARY"},
            "evidence_relation": "SUPPORTS", "directness": "DIRECT_STATEMENT"})


def test_validated_event_consumes_existing_gates(case):
    add_validated_event(case)
    record = finality(case)
    assert record["lanes"]["ACCOUNTABILITY"]["state"] == "VALIDATED_EVENT"
    assert record["combined_event_coverage"]["count"] == 1


def test_explicit_no_result_and_complete_native_ladders_close_negatively(case):
    record = finality(case)
    assert all(lane["state"] == "VERIFIED_NO_QUALIFYING_EVENT" for lane in record["lanes"].values())
    assert all(all(lane["conditions"].values()) for lane in record["lanes"].values())
    assert validate_research_finality(record, case["packet"]) == []


def test_omitted_target_is_contract_block_not_negative(case):
    case["packet"]["hard_target_results"].pop()
    assert finality(case)["lanes"]["SERVICE"]["state"] == "BLOCKED_CONTRACT_FAILURE"


@pytest.mark.parametrize("code", ["PROVIDER_TIMEOUT", "PROVIDER_PACKET_INVALID"])
def test_provider_or_schema_failure_precedes_no_result(case, code):
    record = finality(case, provider_failure={"code": code})
    assert all(lane["state"] == "BLOCKED_TECHNICAL_FAILURE" for lane in record["lanes"].values())


def test_semantic_rejection_needs_completed_recovery(case):
    disposition = case["packet"]["hard_target_results"][0]
    disposition.update(status="CANDIDATES_PRODUCED", no_qualifying_reason=None, candidate_matches=[{"candidate_id": "routine"}])
    case["packet"]["provider_response_validation"]["hard_targets"][0].update(target_disposition_effective="CANDIDATES_PRODUCED", accepted_candidate_count=1)
    job = case["epochs"][0]["execution"]["jobs"][0]
    action = deepcopy(job["actions"][0])
    action.update(action_id="routine-exact", target="https://authority.example/routine", target_editorial_function="ACCOUNTABILITY", action_type="FETCH_URL", provider_candidate_id="investigations:routine")
    exact_job = {"actions": [action], "observations": [{"observation_id": "routine-page", "provenance": {"action_id": "routine-exact"}, "kind": "LEAD",
        "extraction_status": "FETCHED", "title": "Routine concentration notification", "extracted_text": "Public regulator received a projet de concentration concerning acquisition.", "content_hash": "routine-hash"}]}
    case["epochs"].insert(0, {"epoch": 0, "state": {"jobs": []}, "execution": {"status": "EXECUTED", "jobs": [exact_job],
                           "round_execution_budget": {"maximum_actions_per_round": 8, "budget_increased": False}}})
    lane = finality(case)["lanes"]["ACCOUNTABILITY"]
    assert lane["state"] == "VERIFIED_NO_QUALIFYING_EVENT"
    assert lane["candidate_audit"][0]["state"] == "SEMANTICALLY_REJECTED"
    case["epochs"] = []
    assert finality(case)["lanes"]["ACCOUNTABILITY"]["state"] == "UNRESOLVED"


def test_candidate_without_recovery_is_unresolved(case):
    case["packet"]["hard_target_results"][0].update(status="CANDIDATES_PRODUCED", no_qualifying_reason=None, candidate_matches=[{"candidate_id": "untested"}])
    case["packet"]["provider_response_validation"]["hard_targets"][0].update(target_disposition_effective="CANDIDATES_PRODUCED", accepted_candidate_count=1)
    case["epochs"] = []
    assert finality(case)["lanes"]["ACCOUNTABILITY"]["state"] == "UNRESOLVED"


def test_search_infrastructure_failure_is_technical(case):
    job = case["epochs"][0]["execution"]["jobs"][0]
    job["observations"][0].update(title="SEARXNG_UNAVAILABLE", discovery_reason="SEARXNG_UNAVAILABLE")
    assert finality(case)["lanes"]["ACCOUNTABILITY"]["state"] == "BLOCKED_TECHNICAL_FAILURE"


def test_round_cap_cannot_be_called_search_exhaustion(case):
    job = case["epochs"][0]["execution"]["jobs"][0]
    removed = job["actions"].pop()
    job["observations"] = [o for o in job["observations"] if o["provenance"]["action_id"] != removed["action_id"]]
    case["epochs"][0]["execution"]["deferred_actions"].append({**removed, "deferred_reason": "ROUND_BUDGET_PRIORITY_AND_FAIRNESS"})
    lane = finality(case)["lanes"]["ACCOUNTABILITY"]
    assert lane["state"] == "BLOCKED_BUDGET_BEFORE_REQUIRED_SEARCH"
    assert not lane["conditions"]["required_search_capacity_available"]


def test_mixed_positive_negative_has_one_real_event(case):
    add_validated_event(case)
    record = finality(case)
    assert record["combined_research_coverage_complete"] is True
    assert record["combined_event_coverage"]["count"] == 1
    assert record["combined_event_coverage"]["by_lane"]["SERVICE"] == []
    assert [item["lane"] for item in record["editorial_absence_plan"]] == ["SERVICE"]


def test_all_negative_complete_without_manufacturing_events(case):
    before = deepcopy(case["packet"])
    record = finality(case)
    plan = apply_research_finality(case["plan"], record)
    assert record["combined_event_coverage"]["count"] == 0
    assert plan["status"] == "PASS" and plan["editorial_handoff_eligible"] is True
    assert plan["event_coverage_needs"] == case["plan"]["needs"]
    assert validate_recovery_plan(plan) == []
    assert case["packet"] == before


def test_other_breadth_and_primary_needs_still_block(case):
    base = deepcopy(case["plan"])
    base["needs"].append({**deepcopy(base["needs"][0]), "need_id": "P0:other", "kind": "FIND_PRIMARY_ORIGINAL_EVIDENCE", "missing_evidence_role": "PRIMARY"})
    plan = apply_research_finality(base, finality(case))
    assert not plan["editorial_handoff_eligible"]
    assert [n["need_id"] for n in plan["needs"]] == ["P0:other"]


@pytest.mark.parametrize("defect", ["temporal", "primary", "independence", "source_family", "directness", "semantic"])
def test_no_positive_upgrade_from_failed_evidence_gate(case, defect):
    add_validated_event(case)
    if defect in {"independence", "source_family"}:
        case["packet"]["sections"][0]["candidates"][0]["claims"] = ["The audit documents alleged misconduct."]
    observations = case["epochs"][0]["execution"]["jobs"][0]["observations"]
    primary, independent = observations[-2:]
    if defect == "temporal": primary["temporal_relevance"]["active_on_edition_date"] = False
    elif defect == "primary": primary["validation_state"] = "SOURCE_UNKNOWN"
    elif defect == "independence": independent["source_role_resolution"]["independence_state"] = "WIRE_REPUBLICATION"
    elif defect == "source_family":
        primary["publisher_profile"] = independent["publisher_profile"] = {"canonical_domain": "same-publisher.example"}
    elif defect == "directness": primary["directness"] = "INFERENCE_REQUIRED"
    else: case["packet"]["sections"][0]["candidates"][0]["editorial_functions"] = []
    assert finality(case)["lanes"]["ACCOUNTABILITY"]["state"] not in {"VALIDATED_EVENT", "VERIFIED_NO_QUALIFYING_EVENT"}


def test_decision_tampering_or_packet_change_is_rejected(case):
    record = finality(case)
    record["lanes"]["SERVICE"]["conditions"]["normalization_succeeded"] = False
    assert validate_research_finality(record, case["packet"])
    record = finality(case)
    case["packet"]["edition_date"] = "2026-10-05"
    assert validate_research_finality(record, case["packet"])


def test_unexecuted_strategy_cannot_be_replaced_by_dynamic_fetch(case):
    job = case["epochs"][0]["execution"]["jobs"][0]
    original = job["actions"].pop()
    job["observations"] = [o for o in job["observations"] if o["provenance"]["action_id"] != original["action_id"]]
    substitute = {**original, "action_id": "different-dynamic", "lead_followup": True}
    job["actions"].append(substitute)
    job["observations"].append({"observation_id": "dynamic", "provenance": {"action_id": "different-dynamic"}, "kind": "DEAD_END", "discovery_reason": "RSS_NO_MATCHES"})
    assert finality(case)["lanes"]["ACCOUNTABILITY"]["state"] == "UNRESOLVED"


def test_article_guard_accepts_honest_absence_but_retains_edition_floors(case):
    record = finality(case)
    packet = deepcopy(case["packet"])
    packet["research_recovery"] = apply_research_finality(case["plan"], record)
    provider = LocalCommandEditorialProvider(command=(), minimum_active_sections=0, minimum_edition_words=0,
        coverage_requirements=(("accountability_and_service", ("investigations", "opinion", "service"), 2),))
    provider._ensure_research_sufficient_for_articles(packet)
    provider = replace(provider, minimum_active_sections=1)
    with pytest.raises(ProviderError, match="selected section"):
        provider._ensure_research_sufficient_for_articles(packet)
    provider = replace(provider, minimum_active_sections=0)
    packet["research_recovery"]["research_finality"]["combined_research_coverage_complete"] = False
    with pytest.raises(ProviderError) as error:
        provider._ensure_research_sufficient_for_articles(packet)
    assert error.value.code == "RESEARCH_FINALITY_NOT_ACCEPTED"


def test_new_obligations_do_not_redefine_legacy_combined_event_metric(case):
    add_validated_event(case)
    second = deepcopy(case["packet"]["sections"][0])
    second.update(section_id="opinion", selected_candidate_id="second")
    second["candidates"][0].update(id="second", title="A distinct public authority oversight audit", facts=["A second independent audit of a different ministry."])
    for source in deepcopy(case["packet"]["sources"]):
        source.update(id="second-" + source["id"], url=source["url"] + "/second")
        case["packet"]["sources"].append(source)
    for field in ("discovery_source_ids", "verification_source_ids", "primary_evidence_source_ids", "independent_evidence_source_ids"):
        second["candidates"][0][field] = ["second-" + sid for sid in second["candidates"][0][field]]
    for function in second["candidates"][0]["editorial_functions"]:
        function["evidence_source_ids"] = ["second-" + sid for sid in function["evidence_source_ids"]]
    case["packet"]["sections"].append(second)
    intelligence = build_source_intelligence(case["packet"])
    legacy = build_recovery_plan(case["packet"], intelligence, case["coverage"], case["readiness"])
    current = build_recovery_plan(case["packet"], intelligence, case["coverage"], case["readiness"], mandatory_research_lanes=("ACCOUNTABILITY", "SERVICE"))
    assert legacy["editorial_function_coverage"] == current["editorial_function_coverage"]
    assert not legacy["needs"]
    assert [n["target_editorial_function"] for n in current["needs"]] == ["SERVICE"]


def test_exact_october_four_review_has_no_false_negative_closure():
    common = Path(subprocess.check_output(["git", "rev-parse", "--git-common-dir"], cwd=ROOT, text=True).strip()).resolve()
    archive = common / "dragon/research-acceptance"
    paths = [archive / name for name in ("provider-research-acceptance-f1bd0998-d792-4d28-851c-b1c60bfa1f99",
        "retrieval-acceptance-1f48cf07-184b-4cad-a05a-d9a4386ff17d", "retrieval-evidence-review-5333ed4a-38da-4fdd-93e8-1b74baecc416")]
    if not all(p.exists() for p in paths):
        pytest.skip("Task's sealed October 4 bundles are unavailable on this checkout")
    inputs = preserved_inputs(*paths)
    first, second = evaluate(inputs), evaluate(deepcopy(inputs))
    assert first == second
    lanes = first["finality"]["lanes"]
    assert lanes["SERVICE"]["state"] == "BLOCKED_TECHNICAL_FAILURE"
    assert any(f["code"] == "SOURCE_DYNAMIC_ROUTE_REQUIRED" for f in lanes["SERVICE"]["failures"])
    assert lanes["ACCOUNTABILITY"]["state"] == "BLOCKED_BUDGET_BEFORE_REQUIRED_SEARCH"
    missing = set(lanes["ACCOUNTABILITY"]["missing_action_ids"])
    core_ids = {identity for epoch in lanes["ACCOUNTABILITY"]["recovery_epochs"] for identity in epoch["required_core_actions"]}
    assert len(missing & core_ids) == 3
    assert len(missing) == 3
    assert len(lanes["ACCOUNTABILITY"]["deferred_optional_expansions"]) == 1
    assert first["verdicts"]["COMBINED_EVENT_COVERAGE"]["count"] == 0
    assert first["verdicts"]["EDITORIAL_HANDOFF_ELIGIBLE"] is False


def test_production_recovery_stage_can_finish_empty_research_without_editorial(case, tmp_path, monkeypatch):
    shutil.copytree(ROOT / "config", tmp_path / "config")
    monkeypatch.setattr("dragon.pipeline.load_local_config", lambda _root: {"editorial_readiness": case["readiness"]})
    run_dir = tmp_path / "runs/empty-research"
    intelligence = build_source_intelligence(case["packet"])
    initial_state = build_deep_research_state(case["packet"], intelligence, {"lanes": []}, case["plan"], case["config"],
        run_scope_id=run_dir.name, recovery_epoch=0)
    for relative, value in {
        "research/research-packet.json": case["packet"], "research/targeting-request.json": case["targeting"],
        "source-intelligence/report.json": intelligence, "research-planning/plan.json": {"lanes": []},
        "deep-research/state.json": initial_state,
        "deep-research/execution-report.json": {"schema_version": 1, "status": "EXECUTED", "jobs": [], "actions_planned": []},
    }.items(): atomic_write_json(run_dir / relative, value)

    class EmptyProtocolAdapter:
        follow_discovery_leads = False
        def execute(self, action):
            if action["action_type"] == "FETCH_CONFIGURED_SOURCE":
                return [{"result_type": "SOURCE", "url": action["target"], "title": "Institutional directory",
                    "text": "This directory lists institutional offices and their navigation links. It contains no event notice.",
                    "content_hash": "fixture-directory", "fetch_status": "FETCHED", "source_class": "unknown", "observed_at": TIME}]
            return [{"result_type": "DEAD_END", "reason": "SEARXNG_NO_MATCHES", "observed_at": TIME}]

    stages = {s.name: s for s in build_stage_definitions(ProviderFreeAcceptanceProvider(), research_adapter=EmptyProtocolAdapter())}
    context = StageContext(tmp_path, DATE, run_dir, tmp_path / "edition", 1)
    result = stages["research_recovery"].runner(context)
    report = json.loads((run_dir / "research-recovery/plan.json").read_text(encoding="utf-8"))
    assert report["status"] == "PASS" and report["editorial_handoff_eligible"]
    assert set(report["hard_lane_research_closure_state"].values()) == {"VERIFIED_NO_QUALIFYING_EVENT"}
    assert run_dir / "research-recovery/finality.json" in result.outputs
    assert not (run_dir / "articles").exists()
    assert not list(run_dir.glob("**/epoch-2*"))


def test_absence_gets_no_story_budget_and_cannot_activate_a_desk(case):
    case["packet"]["sections"] = [{"section_id": "service", "status": "ACTIVE", "selected_candidate_id": "generic",
        "candidates": [{"id": "generic", "title": "Generic background", "facts": [], "discovery_source_ids": []}]}]
    packet = deepcopy(case["packet"])
    packet["research_recovery"] = apply_research_finality(case["plan"], finality(case))
    provider = LocalCommandEditorialProvider(command=(), minimum_active_sections=0, minimum_edition_words=0)
    with pytest.raises(ProviderError) as error:
        provider._article_budget_contract(packet)
    assert error.value.code == "RESEARCH_BUDGET_INSUFFICIENT"
    with pytest.raises(ProviderError, match="cannot become an active article"):
        provider._validate_articles([{"section_id": "service", "status": "ACTIVE"}], packet, budget_contract={"articles": []})


def test_missing_request_receipt_never_grants_completion(case):
    case["targeting"] = {}
    record = finality(case)
    assert record["research_finality"] == "BLOCKED"
    assert not record["combined_research_coverage_complete"]


def test_deferred_required_dynamic_fetch_blocks_absence(case):
    execution = case["epochs"][0]["execution"]
    action = {**execution["jobs"][0]["actions"][0], "action_id": "unfetched-required-detail", "action_type": "FETCH_URL",
              "target": "https://authority.example/detail", "lead_followup": True, "query_intent": "LISTING_TO_DETAIL_EXACT_ARTIFACT"}
    execution["round_execution_budget"]["dynamic_actions_deferred"] = [{"action": action, "reason": "ROUND_CAP_PRESERVES_SELECTED_ACTIONS"}]
    assert finality(case)["lanes"]["ACCOUNTABILITY"]["state"] == "BLOCKED_BUDGET_BEFORE_REQUIRED_SEARCH"


def test_combined_research_complete_does_not_hide_other_research_failure(case):
    record = finality(case, other_research_need_ids=["BREADTH:morocco:1"])
    assert record["combined_research_coverage_complete"] is True
    assert record["research_finality"] == "BLOCKED"
    assert record["editorial_handoff_eligible"] is False


def test_successful_later_identical_search_resolves_technical_failure(case):
    job = case["epochs"][0]["execution"]["jobs"][0]
    failed = job["observations"][0]
    failed.update(kind="DEAD_END", discovery_reason="SEARXNG_UNAVAILABLE")
    action = {**job["actions"][0], "action_id": "successful-bounded-retry"}
    later = {**deepcopy(failed), "observation_id": "retry-empty", "provenance": {"action_id": action["action_id"]},
             "discovery_reason": "SEARXNG_NO_MATCHES", "observed_at": DATE + "T11:00:00+00:00"}
    case["epochs"].append({"epoch": 2, "state": {"jobs": []}, "execution": {"status": "EXECUTED", "jobs": [{"actions": [action], "observations": [later]}]}})
    lane = finality(case)["lanes"]["ACCOUNTABILITY"]
    assert lane["state"] == "VERIFIED_NO_QUALIFYING_EVENT"
    assert lane["failures"] == [] and len(lane["resolved_failures"]) == 1
    later["observed_at"] = DATE + "T09:00:00+00:00"
    assert finality(case)["lanes"]["ACCOUNTABILITY"]["state"] == "BLOCKED_TECHNICAL_FAILURE"


def test_validated_bundle_and_its_selected_placement_count_one_event(case):
    add_validated_event(case)
    candidate = case["packet"]["sections"][0]["candidates"][0]
    candidate["event_id"] = "native-bundle-event"
    observations = case["epochs"][0]["execution"]["jobs"][0]["observations"]
    case["packet"]["event_evidence_bundles"] = [{"state": "EVENT_VALIDATED", "event_lead_id": candidate["event_id"],
        "observations": [o["observation_id"] for o in observations], "evidence_ids": candidate["verification_source_ids"],
        "editorial_functions": candidate["editorial_functions"], "evidence_policy": {"required_roles": ["PRIMARY"]},
        "source_roles": [{"role": "PRIMARY", "publisher_family": "authority.example"},
                         {"role": "INDEPENDENT", "publisher_family": "reporter.example", "independence_state": "INDEPENDENT_ORIGINAL_REPORTING"}]}]
    assert finality(case)["combined_event_coverage"]["count"] == 1


def test_closure_requires_a_recorded_timestamp(case):
    case["closed_at"] = "unknown"
    assert finality(case)["lanes"]["SERVICE"]["state"] == "UNRESOLVED"


def test_optional_expansion_is_audited_and_does_not_replace_core_obligations(case):
    execution = case["epochs"][0]["execution"]
    optional = {**execution["jobs"][0]["actions"][0], "action_id": "optional-route-expansion", "action_type": "FETCH_URL",
                "target": "https://authority.example/other-directory", "query_intent": "DIRECT_SOURCE_ROUTE_DISCOVERY"}
    execution["round_execution_budget"]["dynamic_actions_deferred"] = [{"action": optional, "reason": "ROUND_CAP_PRESERVES_SELECTED_ACTIONS"}]
    lane = finality(case)["lanes"]["ACCOUNTABILITY"]
    assert lane["state"] == "VERIFIED_NO_QUALIFYING_EVENT"
    assert len(lane["deferred_optional_expansions"]) == 1
    execution["jobs"][0]["actions"].pop()
    assert finality(case)["lanes"]["ACCOUNTABILITY"]["state"] == "UNRESOLVED"
