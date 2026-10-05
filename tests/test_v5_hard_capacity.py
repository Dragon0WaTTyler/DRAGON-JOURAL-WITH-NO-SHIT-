"""Admission regression from the real bounded October 5 scheduling inputs."""
from copy import deepcopy
import json
from pathlib import Path

from test_v5_research_finality import case
from test_v5_hard_lane_completion import LANES, lane_jobs, run_schedule
from dragon.deep_research_executor import (
    SEARCH_ACTIONS, continue_required_research_jobs, plan_research_actions,
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


def test_optional_protocol_retains_original_exact_artifact_preference(case):
    epoch = recorded()["epochs"][0]
    selected = schedule_research_actions(epoch["jobs"], case["config"])["actions"]
    for lane in LANES:
        first = next(a for a in selected if a.get("target_editorial_function") == lane)
        assert first["lead_origin"] == "PROVIDER_EXACT"
        assert first["provider_source_role"] == "PRIMARY"


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
