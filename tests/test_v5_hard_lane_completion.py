"""Execution opportunity is bounded; no fixture supplies live evidence."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import socket

import pytest

from test_v5_research_finality import case, finality, DATE, TIME
from dragon.deep_research_executor import (FixtureResearchAdapter, HttpResearchAdapter, RoundActionBudget,
    continue_required_research_jobs, execute_research_round, plan_research_actions,
    reconcile_discovery_leads, schedule_research_actions)
from dragon.discovery import FetchResponse
from dragon.pipeline import build_stage_definitions
from dragon.providers import LocalCommandEditorialProvider
from dragon.research_acceptance import ProviderFreeAcceptanceProvider
from dragon.stages import StageContext
from dragon.state import atomic_write_json
from dragon.source_intelligence import build_source_intelligence
from dragon.research_finality import build_research_finality

ROOT = Path(__file__).resolve().parents[1]
LANES = ("ACCOUNTABILITY", "SERVICE")

@pytest.fixture(autouse=True)
def forbid_live(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Hard-lane fixture attempted a live call")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(LocalCommandEditorialProvider, "_invoke", forbidden)

def lane_jobs(case):
    return deepcopy(case["epochs"][0]["state"]["jobs"])

class EmptyAdapter:
    follow_discovery_leads = False
    def execute(self, action):
        if action["action_type"] in {"FETCH_URL", "FETCH_CONFIGURED_SOURCE"}:
            return [{"url": action["target"], "text": "Institutional directory without an event or current operational notice. " * 8,
                "title": "Institutional directory", "content_hash": "directory-proof", "fetch_status": "FETCHED", "observed_at": TIME}]
        return [{"result_type": "DEAD_END", "reason": "SEARXNG_NO_MATCHES", "observed_at": TIME}]

def run_schedule(jobs, config, schedule, adapter=None):
    budget = RoundActionBudget(8, schedule["actions"])
    executions = []
    for job in jobs:
        actions = [a for a in schedule["actions"] if a["job_id"] == job["job_id"]]
        if actions:
            executions.append(execute_research_round(job, adapter or EmptyAdapter(), config, actions=actions, round_budget=budget))
    return {"status": "EXECUTED", "jobs": executions, "deferred_actions": schedule["deferred_actions"],
            "round_execution_budget": budget.report()}

def test_required_ladders_get_all_eight_slots_when_general_already_had_opportunity(case):
    jobs = lane_jobs(case)
    schedule = schedule_research_actions(jobs, case["config"], mandatory_lanes=LANES, general_opportunity_executed=True)
    native = [a for j in jobs for a in plan_research_actions(j, case["config"])]
    assert {a["action_id"] for a in schedule["actions"]} == {a["action_id"] for a in native}
    assert len(schedule["actions"]) == 8 and not schedule["budget_allocation"]["budget_increased"]
    assert all(a["required_protocol"] for a in schedule["actions"])

def test_optional_general_wave_cannot_displace_required_ladder_and_gets_capacity(case):
    jobs = lane_jobs(case)[:1]
    for index in range(5):
        general = deepcopy(jobs[0])
        general["job_id"] = "general-" + str(index)
        general["research_lane"] = "GENERAL_DISCOVERY"
        general["recovery_needs"] = []
        for branch in general["branches"]:
            branch["branch_id"] += str(index)
        jobs.append(general)
    schedule = schedule_research_actions(jobs, case["config"], mandatory_lanes=("ACCOUNTABILITY",))
    selected = schedule["actions"]
    required = plan_research_actions(jobs[0], case["config"])
    assert {a["action_id"] for a in required}.issubset({a["action_id"] for a in selected})
    assert any(not a.get("target_editorial_function") for a in selected)
    assert len(selected) == 5 and len(selected) <= 8

def test_true_scarcity_keeps_budget_block_with_general_opportunity(case):
    jobs = lane_jobs(case)
    general = deepcopy(jobs[0]); general.update(job_id="general", research_lane="GENERAL_DISCOVERY", recovery_needs=[])
    jobs.append(general)
    schedule = schedule_research_actions(jobs, case["config"], mandatory_lanes=LANES)
    execution = run_schedule(jobs, case["config"], schedule)
    case["epochs"][0]["state"]["jobs"] = jobs
    case["epochs"][0]["execution"] = execution
    result = finality(case)
    assert len(schedule["actions"]) == 8
    assert any(not a.get("target_editorial_function") for a in schedule["actions"])
    assert "BLOCKED_BUDGET_BEFORE_REQUIRED_SEARCH" in {l["state"] for l in result["lanes"].values()}

def test_partial_ladder_carries_exact_ids_counters_and_progress(case):
    jobs = lane_jobs(case)[:1]
    native = plan_research_actions(jobs[0], case["config"])
    schedule = {"actions": [native[0]], "deferred_actions": native[1:]}
    execution = run_schedule(jobs, case["config"], schedule)
    carry = continue_required_research_jobs({"jobs": jobs}, execution, case["config"], LANES)
    assert len(carry) == 1
    pending = plan_research_actions(carry[0], case["config"])
    assert pending == native[1:]
    assert carry[0]["executor_state"]["search_actions"] == 1
    later = run_schedule(carry, case["config"], {"actions": pending, "deferred_actions": []})
    assert later["jobs"][0]["recovery_strategy_progress"][0]["attempt_exhausted"]
    assert later["jobs"][0]["budget_consumed"]["search_actions"] == 4
    assert later["jobs"][0]["job"]["round"] == 2

def test_production_epoch_one_admits_unchanged_partially_executed_hard_need(case, tmp_path, monkeypatch):
    shutil.copytree(ROOT / "config", tmp_path / "config")
    monkeypatch.setattr("dragon.pipeline.load_local_config", lambda root: {"editorial_readiness": case["readiness"]})
    run = tmp_path / "runs/partial"
    initial = deepcopy(case["epochs"][0]["state"])
    initial["jobs"][1]["action_deferral_reason"] = "PROVIDER_NO_RESULT_REQUIRES_RECOVERY_EPOCH"
    first = plan_research_actions(initial["jobs"][0], case["config"])[0]
    execution = run_schedule(initial["jobs"], case["config"], {"actions": [first], "deferred_actions": []})
    for name, value in {"research/research-packet.json": case["packet"], "research/targeting-request.json": case["targeting"],
        "source-intelligence/report.json": build_source_intelligence(case["packet"]), "research-planning/plan.json": {"lanes": []},
        "deep-research/state.json": initial, "deep-research/execution-report.json": execution}.items():
        atomic_write_json(run / name, value)
    stages = {s.name: s for s in build_stage_definitions(ProviderFreeAcceptanceProvider(), research_adapter=EmptyAdapter())}
    stages["research_recovery"].runner(StageContext(tmp_path, DATE, run, tmp_path / "edition", 1))
    second = json.loads((run / "deep-research/epoch-1-execution-report.json").read_text(encoding="utf-8"))
    account = [a for j in second["jobs"] for a in j["actions"] if a.get("target_editorial_function") == "ACCOUNTABILITY"]
    required = plan_research_actions(initial["jobs"][0], case["config"])[1:]
    assert {a["action_id"] for a in required}.issubset({a["action_id"] for a in account})
    assert first["action_id"] not in {a["action_id"] for a in account}
    assert not list(run.glob("**/epoch-2*"))
    assert len(second["actions_planned"]) <= 8
    assert not (run / "articles").exists()

def dynamic_execution(case, fallback):
    job = lane_jobs(case)[1]
    action = next(a for a in plan_research_actions(job, case["config"]) if a["action_type"] == "FETCH_CONFIGURED_SOURCE")
    action["required_protocol"] = True
    adapter = HttpResearchAdapter(fallback_extractor=fallback)
    adapter.source_transport = lambda url, *_: FetchResponse(url, 200, "text/html", b'<html><body><div id="app"></div><script src="app.js"></script></body></html>')
    budget = RoundActionBudget(8, [action])
    return execute_research_round(job, adapter, case["config"], actions=[action], round_budget=budget)

def test_dynamic_signal_materializes_one_supported_recovery_and_normal_evaluation(case):
    calls = []
    def extractor(response, reason):
        calls.append(response.url)
        return {"url": response.url, "title": "Public service registration opens", "date": DATE,
            "text": "The public service operator opens registration and states a current deadline. " * 12,
            "extraction_method": "fixture-browser"}
    execution = dynamic_execution(case, extractor)
    assert len(calls) == 1
    assert len(execution["actions"]) == 2
    assert execution["actions"][1]["dynamic_recovery"]
    assert execution["actions"][1]["extraction_route"] == "DYNAMIC"
    recovered = execution["observations"][-1]
    assert recovered["extraction_status"] == "FETCHED" and recovered["extraction_method"] == "fixture-browser"
    assert recovered["source_role_resolution"]  # ordinary exact-page qualification ran
    assert recovered["validation_state"] != "VALIDATED_EVIDENCE"  # text alone supplies no role proof

@pytest.mark.parametrize("fallback,reason", [(None, "SOURCE_DYNAMIC_ADAPTER_UNAVAILABLE"),
    (lambda *_: None, "SOURCE_EXTRACTION_FALLBACK_INVALID")])
def test_failed_or_unconfigured_dynamic_recovery_stays_technical(case, fallback, reason):
    execution = dynamic_execution(case, fallback)
    assert len(execution["actions"]) == 2
    assert execution["observations"][-1]["kind"] == "DEAD_END"
    assert execution["observations"][-1]["discovery_reason"] == reason
    assert len(execution["dynamic_recovery_actions"]) == 1

def lead_case(case):
    execution = case["epochs"][0]["execution"]["jobs"][1]
    search = next(a for a in execution["actions"] if a["action_type"] == "SEARCH_DISCOVERY")
    fetch = next(a for a in execution["actions"] if a["action_type"] == "FETCH_CONFIGURED_SOURCE")
    lead = {"observation_id": "search-lead", "kind": "LEAD", "observation_class": "LEAD", "url": fetch["target"],
            "title": "Directory discovery", "provenance": {"action_id": search["action_id"]}}
    execution["observations"].append(lead)
    return execution, lead

def test_pending_lead_forbids_negative_closure_until_content_bound_rejection(case):
    execution, lead = lead_case(case)
    assert finality(case)["lanes"]["SERVICE"]["state"] == "UNRESOLVED"
    records = reconcile_discovery_leads(execution["observations"], execution["actions"])
    assert records[0]["state"] == "INSPECTED_REJECTED" and records[0]["proof"]
    assert lead["kind"] == "LEAD" and lead.get("validation_state") != "VALIDATED_EVIDENCE"
    assert finality(case)["lanes"]["SERVICE"]["state"] == "VERIFIED_NO_QUALIFYING_EVENT"

def test_duplicate_resolution_requires_identical_exact_page_proof(case):
    execution, lead = lead_case(case)
    execution["observations"].append({**deepcopy(lead), "observation_id": "duplicate"})
    records = reconcile_discovery_leads(execution["observations"], execution["actions"])
    assert records[1]["state"] == "DEDUPLICATED_ALREADY_EVALUATED"
    assert records[1]["proof"] == records[0]["proof"]

def test_same_origin_different_url_does_not_deduplicate(case):
    execution, lead = lead_case(case)
    lead["url"] += "/different-event"
    record = reconcile_discovery_leads(execution["observations"], execution["actions"])[0]
    assert record["state"] == "BLOCKED_BUDGET_BEFORE_REQUIRED_SEARCH"
    assert finality(case)["lanes"]["SERVICE"]["state"] == "UNRESOLVED"

def test_out_of_window_requires_inspected_page_temporal_proof(case):
    execution, lead = lead_case(case)
    for o in execution["observations"]:
        if o.get("extracted_text"):
            o["temporal_relevance"] = {"active_on_edition_date": False}
    record = reconcile_discovery_leads(execution["observations"], execution["actions"])[0]
    assert record["state"] == "OUTSIDE_TARGET_SCOPE" and record["proof"]

def test_required_lead_failures_and_unavailable_capacity_have_explicit_states(case):
    execution, lead = lead_case(case)
    lead["url"] = "https://127.0.0.1/unsafe"
    assert reconcile_discovery_leads(execution["observations"], execution["actions"])[0]["state"] == "BLOCKED_CONTRACT_FAILURE"
    lead["url"] = "https://lead.example/uninspected"
    assert reconcile_discovery_leads(execution["observations"], execution["actions"])[0]["state"] == "BLOCKED_BUDGET_BEFORE_REQUIRED_SEARCH"

def test_required_core_actions_execute_before_recursive_optional_expansions(case):
    jobs = lane_jobs(case)[:1]
    schedule = schedule_research_actions(jobs, case["config"], mandatory_lanes=("ACCOUNTABILITY",))
    execution = run_schedule(jobs, case["config"], schedule)
    core = [a["action_id"] for a in schedule["actions"]]
    assert [a["action_id"] for a in execution["jobs"][0]["actions"][:len(core)]] == core
    assert len(execution["round_execution_budget"]["executed_action_ids"]) <= 8

def test_every_uninspected_required_lead_gets_an_explicit_capacity_request(case):
    class LeadAdapter(EmptyAdapter):
        follow_discovery_leads = True
        def execute(self, action):
            if action["action_type"] == "SEARCH_DISCOVERY":
                return [{"result_type": "LEAD", "url": f"https://publisher{i}.example/notice", "title": "Public service registration notice",
                         "observed_at": TIME} for i in range(8)]
            return super().execute(action)
    jobs = lane_jobs(case)[1:]
    schedule = schedule_research_actions(jobs, case["config"], mandatory_lanes=("SERVICE",))
    execution = run_schedule(jobs, case["config"], schedule, LeadAdapter())
    result = execution["jobs"][0]
    assert len(result["lead_evaluations"]) >= 8
    blocked = [r for r in result["lead_evaluations"] if r["state"] == "BLOCKED_BUDGET_BEFORE_REQUIRED_SEARCH"]
    assert blocked
    deferred = execution["round_execution_budget"]["dynamic_actions_deferred"]
    assert all(any(d["action"].get("required_lead_inspection") and d["action"].get("target") == lead["url"] for d in deferred) for lead in blocked)
    inspections = [d["action"] for d in deferred if d["action"].get("required_lead_inspection")]
    assert len(inspections) == len({(a["query_fingerprint"], a["target"]) for a in inspections})
    case["epochs"][0]["state"]["jobs"] = jobs
    case["epochs"][0]["execution"] = execution
    assert finality(case)["lanes"]["SERVICE"]["state"] == "BLOCKED_BUDGET_BEFORE_REQUIRED_SEARCH"

def test_cross_epoch_exact_inspection_resolves_parent_without_mutating_checkpoint(case):
    execution, lead = lead_case(case)
    fetch = next(a for a in execution["actions"] if a["action_type"] == "FETCH_CONFIGURED_SOURCE")
    fetch["required_protocol"] = True
    page = next(o for o in execution["observations"] if o.get("provenance", {}).get("action_id") == fetch["action_id"])
    execution["observations"].remove(page)
    execution["actions"].remove(fetch)
    case["epochs"].append({"epoch": 0, "state": {"jobs": []}, "execution": {"status": "EXECUTED", "jobs": [{"actions": [fetch], "observations": [page]}]}})
    # Its actual timestamp is later than the search in this explicit fixture.
    page["observed_at"] = DATE + "T11:00:00+00:00"
    before = deepcopy(case["epochs"])
    record = finality(case)
    assert record["lanes"]["SERVICE"]["state"] == "VERIFIED_NO_QUALIFYING_EVENT"
    assert case["epochs"] == before
    assert record["lead_evaluations"][0]["proof"]

def test_dynamic_failure_blocks_finality_and_success_resolves_only_same_exact_request(case):
    execution = dynamic_execution(case, None)
    new_epoch = {"epoch": 0, "state": {"jobs": []}, "execution": {"status": "EXECUTED", "jobs": [execution]}}
    case["epochs"].insert(0, new_epoch)
    assert finality(case)["lanes"]["SERVICE"]["state"] == "BLOCKED_TECHNICAL_FAILURE"

def test_fetched_lead_with_failed_extraction_records_technical_failure(case):
    execution, lead = lead_case(case)
    for page in execution["observations"]:
        if page.get("url") == lead["url"] and page.get("extracted_text"):
            page.update(kind="DEAD_END", extracted_text=None, content_hash=None, extraction_status="FAILED", discovery_reason="SOURCE_EXTRACTION_FAILED")
    assert reconcile_discovery_leads(execution["observations"], execution["actions"])[0]["state"] == "BLOCKED_TECHNICAL_FAILURE"

def test_unproven_factory_extractor_cannot_silently_enable_backend(case):
    from dragon.deep_research_executor import discovery_adapter_from_config
    from dragon.discovery import DiscoveryError
    with pytest.raises(DiscoveryError) as caught:
        discovery_adapter_from_config(ROOT, fallback_extractor=lambda *_: {})
    assert caught.value.code == "SOURCE_DYNAMIC_ADAPTER_UNAVAILABLE"

def test_dynamic_success_clears_extraction_failure_without_granting_event_evidence(case):
    execution = dynamic_execution(case, lambda response, _: {"url": response.url, "title": "Institutional directory",
        "text": "Institutional directory without an event or operational notice. " * 12, "extraction_method": "fixture-browser"})
    case["epochs"].insert(0, {"epoch": 0, "state": {"jobs": []}, "execution": {"status": "EXECUTED", "jobs": [execution]}})
    record = finality(case)
    assert not record["lanes"]["SERVICE"]["failures"]
    assert record["lanes"]["SERVICE"]["resolved_failures"]
    assert record["combined_event_coverage"]["count"] == 0

def test_saved_october_four_audit_plans_missing_searches_but_cannot_invent_responses():
    import subprocess
    from dragon.research_finality_acceptance import preserved_inputs
    from dragon.hard_lane_completion_acceptance import audit_completion_inputs
    common = Path(subprocess.check_output(["git", "rev-parse", "--git-common-dir"], cwd=ROOT, text=True).strip()).resolve()
    archive = common / "dragon/research-acceptance"
    names = ["provider-research-acceptance-f1bd0998-d792-4d28-851c-b1c60bfa1f99",
        "retrieval-acceptance-1f48cf07-184b-4cad-a05a-d9a4386ff17d", "retrieval-evidence-review-5333ed4a-38da-4fdd-93e8-1b74baecc416"]
    if not all((archive / n).exists() for n in names):
        pytest.skip("Task's sealed October 4 bundles unavailable")
    inputs = preserved_inputs(*(archive / n for n in names))
    result = audit_completion_inputs(inputs)
    assert result == audit_completion_inputs(deepcopy(inputs))
    initial = result["prospective_initial_allocation"]
    account = [a for a in initial["schedule"]["actions"] if a.get("target_editorial_function") == "ACCOUNTABILITY"]
    assert len(account) == 6 and len(initial["schedule"]["actions"]) == 8
    assert len([a for a in initial["response_availability"] if a["response_state"] == "NO_EXACT_PRESERVED_RESPONSE" and a["lane"] == "ACCOUNTABILITY"]) == 3
    assert len(result["actual_service_lead_audit"]) == 8
    assert all(r["state"] == "BLOCKED_BUDGET_BEFORE_REQUIRED_SEARCH" for r in result["actual_service_lead_audit"])
    assert result["historical_replay"]["verdicts"]["RESEARCH_FINALITY"] == "BLOCKED"
    assert not result["historical_replay"]["verdicts"]["EDITORIAL_HANDOFF_ELIGIBLE"]

def test_production_initial_stage_binds_actual_request_and_reserves_protocol(case, tmp_path):
    shutil.copytree(ROOT / "config", tmp_path / "config")
    run = tmp_path / "runs/initial"
    state = deepcopy(case["epochs"][0]["state"])
    state["jobs"] = state["jobs"][:1]
    atomic_write_json(run / "deep-research/state.json", state)
    atomic_write_json(run / "research/research-packet.json", case["packet"])
    atomic_write_json(run / "research/targeting-request.json", case["targeting"])
    stages = {s.name: s for s in build_stage_definitions(ProviderFreeAcceptanceProvider(), research_adapter=EmptyAdapter())}
    result = stages["deep_research_execution"].runner(StageContext(tmp_path, DATE, run, tmp_path / "edition", 1))
    assert run / "research/targeting-request.json" in result.inputs
    execution = json.loads((run / "deep-research/execution-report.json").read_text(encoding="utf-8"))
    assert execution["hard_lane_reservation"]["completion_policy"] == "MANDATORY_PROTOCOL_BEFORE_OPTIONAL_WAVES"
    native_ids = {a["action_id"] for a in plan_research_actions(state["jobs"][0], case["config"])}
    assert native_ids.issubset({a["action_id"] for a in execution["actions_planned"]})

def test_exhausted_job_round_cannot_reopen_as_continuation(case):
    jobs = lane_jobs(case)[:1]
    native = plan_research_actions(jobs[0], case["config"])
    execution = run_schedule(jobs, case["config"], {"actions": [native[0]], "deferred_actions": native[1:]})
    execution["jobs"][0]["job"]["round"] = 2
    assert continue_required_research_jobs({"jobs": jobs}, execution, case["config"], LANES) == []

def test_renumbered_need_retains_old_request_lineage_as_auxiliary_work(case, tmp_path, monkeypatch):
    from dragon.research_recovery import build_recovery_plan as original_plan
    from dragon.stages import StageFailure
    shutil.copytree(ROOT / "config", tmp_path / "config")
    monkeypatch.setattr("dragon.pipeline.load_local_config", lambda root: {"editorial_readiness": case["readiness"]})
    def changed_plan(*args, **kwargs):
        result = original_plan(*args, **kwargs)
        if kwargs.get("attempts_by_need") is not None:
            result["needs"] = [n for n in result["needs"] if n.get("target_editorial_function") == "SERVICE"]
            result["needs"][0]["need_id"] = "BREADTH:accountability_and_service:1"
        return result
    monkeypatch.setattr("dragon.pipeline.build_recovery_plan", changed_plan)
    run = tmp_path / "runs/renumbered"
    initial = deepcopy(case["epochs"][0]["state"])
    first = plan_research_actions(initial["jobs"][1], case["config"])[0]
    execution = run_schedule(initial["jobs"], case["config"], {"actions": [first], "deferred_actions": []})
    for name, value in {"research/research-packet.json": case["packet"], "research/targeting-request.json": case["targeting"],
        "source-intelligence/report.json": build_source_intelligence(case["packet"]), "research-planning/plan.json": {"lanes": []},
        "deep-research/state.json": initial, "deep-research/execution-report.json": execution}.items():
        atomic_write_json(run / name, value)
    stages = {s.name: s for s in build_stage_definitions(ProviderFreeAcceptanceProvider(), research_adapter=EmptyAdapter())}
    with pytest.raises(StageFailure) as caught:
        stages["research_recovery"].runner(StageContext(tmp_path, DATE, run, tmp_path / "edition", 1))
    assert caught.value.code != "RECOVERY_JOB_MATERIALIZATION_FAILED"
    state = json.loads((run / "deep-research/epoch-1-state.json").read_text(encoding="utf-8"))
    aliases = state["required_continuation_mappings"]
    assert aliases and "BREADTH:accountability_and_service:2" in aliases[0]["original_need_ids"]
    assert first["action_id"] not in aliases[0]["action_ids"]
    assert not list(run.glob("**/epoch-2*"))
