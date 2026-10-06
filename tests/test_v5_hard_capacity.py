"""Admission regression from the real bounded October 5 scheduling inputs."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import pytest

from test_v5_research_finality import case
from test_v5_hard_lane_completion import LANES, lane_jobs, run_schedule
from dragon.deep_research_executor import (
    SEARCH_ACTIONS, FixtureResearchAdapter, RoundActionBudget,
    continue_required_research_jobs, execute_research_round, plan_research_actions,
    schedule_research_actions,
)

FIXTURE = Path(__file__).parent / "fixtures/hard-capacity-2026-10-05.json"


def recorded():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def core(action):
    return bool(action.get("recovery_need_id") and not action.get("lead_followup")
                and not action.get("dynamic_recovery") and not action.get("actor_first_search")
                and action.get("lead_origin") != "PROVIDER_EXACT")


def native(jobs, config):
    return [a for j in jobs for a in plan_research_actions(j, config)]


def test_recorded_epoch_zero_preserves_core_order_and_general_opportunity(case):
    epoch = recorded()["epochs"][0]
    actions = native(epoch["jobs"], case["config"])
    by_id = {a["action_id"]: a for a in actions}
    before = [by_id[i] for i in epoch["previous_selected_ids"]]
    assert sum(core(a) for a in before) == 3
    assert sum(a.get("lead_origin") == "PROVIDER_EXACT" for a in before) == 5
    after = schedule_research_actions(epoch["jobs"], case["config"], mandatory_lanes=LANES)
    selected = after["actions"]
    assert len(selected) == 8
    assert sum(core(a) for a in selected) == 7
    assert any(not a.get("target_editorial_function") for a in selected)
    assert all(core(a) or not a.get("target_editorial_function") for a in selected)
    for lane in LANES:
        admitted = [a for a in selected if core(a) and a.get("target_editorial_function") == lane]
        expected = [a for a in actions if core(a) and a.get("target_editorial_function") == lane]
        assert [a["action_id"] for a in admitted] == [
            a["action_id"] for a in sorted(expected, key=lambda a: a["strategy_index"])[:len(admitted)]]
    assert after["actions"] == schedule_research_actions(
        list(reversed(epoch["jobs"])), case["config"], mandatory_lanes=LANES)["actions"]


def test_recorded_recovery_children_cannot_displace_remaining_core(case):
    epoch = recorded()["epochs"][1]
    actions = native(epoch["jobs"], case["config"])
    by_id = {a["action_id"]: a for a in actions}
    before = [by_id[i] for i in epoch["previous_selected_ids"]]
    assert all(a.get("lead_followup") and not core(a) for a in before)
    assert not any(a["action_type"] in SEARCH_ACTIONS for a in before)
    after = schedule_research_actions(epoch["jobs"], case["config"], mandatory_lanes=LANES,
                                      general_opportunity_executed=True)
    expected = {a["action_id"] for a in actions if core(a)}
    selected = after["actions"]
    assert {a["action_id"] for a in selected[:len(expected)]} == expected
    assert all(core(a) for a in selected[:len(expected)])
    assert any(a.get("lead_followup") for a in selected[len(expected):])
    assert not after["budget_allocation"]["budget_increased"]
    assert after["budget_allocation"]["round_cap"] == 8
    for lane in LANES:
        ordered = [a["strategy_index"] for a in selected if core(a) and a.get("target_editorial_function") == lane]
        assert ordered == sorted(ordered)


def test_two_epochs_complete_core_without_resetting_job_caps(case):
    jobs = lane_jobs(case)
    general = deepcopy(jobs[0])
    general.update(job_id="general-opportunity", research_lane="GENERAL_DISCOVERY", recovery_needs=[])
    jobs.append(general)
    initial = schedule_research_actions(jobs, case["config"], mandatory_lanes=LANES)
    first = run_schedule(jobs, case["config"], initial)
    carries = continue_required_research_jobs({"jobs": jobs}, first, case["config"], LANES)
    assert carries
    second_schedule = schedule_research_actions(carries, case["config"], mandatory_lanes=LANES,
                                                general_opportunity_executed=True)
    second = run_schedule(carries, case["config"], second_schedule)
    executed = [a for e in (first, second) for j in e["jobs"] for a in j["actions"]]
    for lane in LANES:
        expected = [a for a in native(jobs, case["config"]) if a.get("target_editorial_function") == lane]
        actual = [a for a in executed if a.get("target_editorial_function") == lane]
        assert [a["action_id"] for a in actual] == [a["action_id"] for a in expected]
        assert len({a["action_id"] for a in actual}) == len(actual)
    assert sum(len(e["round_execution_budget"]["executed_action_ids"]) for e in (first, second)) <= 16
    for j in second["jobs"]:
        assert j["job"]["round"] == 2
        assert j["budget_consumed"]["search_actions"] <= 4
        assert j["budget_consumed"]["fetches"] <= 4


@pytest.mark.parametrize("mandatory_lanes", [LANES, ("ACCOUNTABILITY",), ("SERVICE",), ()])
def test_core_preference_applies_only_to_each_mandatory_lane(case, mandatory_lanes):
    epoch = recorded()["epochs"][0]
    config_before = deepcopy(case["config"])
    jobs_before = deepcopy(epoch["jobs"])
    schedule = schedule_research_actions(epoch["jobs"], case["config"], mandatory_lanes=mandatory_lanes)
    selected = schedule["actions"]
    for lane in LANES:
        admitted = [a for a in selected if a.get("target_editorial_function") == lane]
        if lane in mandatory_lanes:
            assert core(admitted[0])
            assert all(a.get("required_protocol") for a in admitted)
            core_indices = [a["strategy_index"] for a in admitted if core(a)]
            assert core_indices == sorted(core_indices)
            if any(not core(a) for a in admitted):
                expected_core = [a for a in native(epoch["jobs"], case["config"])
                                 if core(a) and a.get("target_editorial_function") == lane]
                assert len(core_indices) == len(expected_core)
        else:
            assert admitted[0]["lead_origin"] == "PROVIDER_EXACT"
            assert admitted[0]["provider_source_role"] == "PRIMARY"
            assert admitted[1]["lead_origin"] == "PROVIDER_EXACT"
            assert admitted[1]["provider_source_role"] == "INDEPENDENT"
            assert admitted[1]["provider_candidate_id"] == admitted[0]["provider_candidate_id"]
            assert not any(a.get("required_protocol") for a in admitted)
    assert len(selected) == schedule["budget_allocation"]["round_cap"] == 8
    assert not schedule["budget_allocation"]["budget_increased"]
    assert len(selected) + len(schedule["deferred_actions"]) == len(native(epoch["jobs"], case["config"]))
    assert case["config"] == config_before
    assert epoch["jobs"] == jobs_before


def test_lane_without_core_cannot_spend_other_lanes_core_reservation(case):
    epoch = recorded()["epochs"][1]
    jobs = deepcopy(epoch["jobs"])
    for job in jobs:
        if any(a.get("target_editorial_function") == "ACCOUNTABILITY" for a in job["required_continuation_actions"]):
            job["required_continuation_actions"] = [a for a in job["required_continuation_actions"] if not core(a)]
    selected = schedule_research_actions(jobs, case["config"], mandatory_lanes=LANES,
                                         general_opportunity_executed=True)["actions"]
    expected = [a for a in native(jobs, case["config"]) if core(a)]
    assert [a["action_id"] for a in selected[:len(expected)]] == [a["action_id"] for a in expected]
    assert any(a.get("target_editorial_function") == "ACCOUNTABILITY" for a in selected[len(expected):])


def test_current_event_without_publication_date_keeps_unknown_role_and_bounded_feedback():
    from test_v5_deep_research_executor import _job, _result, CONFIG
    job = _job()
    action = plan_research_actions(job, CONFIG)[0]
    action.update(action_type="FETCH_URL", target="https://unknown.example/current-notice",
                  expected_result_type="EXTRACTED_SOURCE")
    action["event_context"]["research_date"] = "2099-01-02"
    raw = _result(action["target"], "unknown", published_at=None, event_date="2099-01-02",
                  title="Morocco public operator opens registration",
                  text="Morocco public operator opens registration on 2099-01-02. " * 8,
                  fetch_status="FETCHED")
    adapter = FixtureResearchAdapter({"FETCH_URL": [raw]})
    budget = RoundActionBudget(8, [action])
    result = execute_research_round(job, adapter, CONFIG, actions=[action], round_budget=budget)
    observation = result["observations"][0]
    assert observation["event_skeleton"]["state"] == "CONCRETE_EVENT"
    assert observation["event_skeleton"]["published_at"] is None
    assert observation["temporal_relevance"]["active_on_edition_date"] is True
    assert observation["validation_state"] != "VALIDATED_EVIDENCE"
    assert (observation.get("source_role_resolution") or {}).get("evidence_role") not in {"PRIMARY", "INDEPENDENT"}
    feedback = next(a for a in result["actions"] if a.get("event_lead_feedback"))
    assert "None" not in feedback["query"]
    assert "2099-01" not in feedback["query"]
    assert len(budget.executed) == 2 and not budget.report()["budget_increased"]


def test_pipeline_dispatches_all_mandatory_core_and_preserves_deferred_general(case, tmp_path):
    from test_v5_hard_lane_completion import EmptyAdapter
    from test_v5_research_finality import ROOT, DATE
    from dragon.pipeline import build_stage_definitions
    from dragon.research_acceptance import ProviderFreeAcceptanceProvider
    from dragon.stages import StageContext
    from dragon.state import atomic_write_json
    shutil.copytree(ROOT / "config", tmp_path / "config")
    jobs = lane_jobs(case)
    general = deepcopy(jobs[0])
    general.update(job_id="general-first-in-materialization", research_lane="GENERAL_DISCOVERY", recovery_needs=[])
    jobs.insert(0, general)
    run = tmp_path / "runs/dispatch-order"
    atomic_write_json(run / "deep-research/state.json", {"jobs": jobs})
    atomic_write_json(run / "research/research-packet.json", case["packet"])
    atomic_write_json(run / "research/targeting-request.json", case["targeting"])
    stages = {s.name:s for s in build_stage_definitions(ProviderFreeAcceptanceProvider(), research_adapter=EmptyAdapter())}
    stages["deep_research_execution"].runner(StageContext(tmp_path, DATE, run, tmp_path / "edition", 1))
    schedule = json.loads((run / "deep-research/scheduler-allocation.json").read_text(encoding="utf-8"))
    execution = json.loads((run / "deep-research/execution-report.json").read_text(encoding="utf-8"))
    expected = list(dict.fromkeys(a["job_id"] for a in schedule["actions"]))
    assert [j["job"]["job_id"] for j in execution["jobs"]] == expected
    assert execution["jobs"][0]["actions"][0]["target_editorial_function"] == "ACCOUNTABILITY"
    assert all(j['job']['job_id'] != general['job_id'] for j in execution['jobs'])
    assert execution['general_opportunity']['job_id'] == general['job_id']
    assert any(r['action']['job_id']==general['job_id'] and
               r['reason']=='GENERAL_PREEMPTED_BY_MANDATORY_ACQUISITION'
               for r in execution['round_execution_budget']['dynamic_actions_deferred'])
    assert all(core(a) for j in execution['jobs'] for a in j['actions'])
    assert len(execution["round_execution_budget"]["executed_action_ids"]) <= 8
