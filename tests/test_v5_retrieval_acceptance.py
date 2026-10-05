"""Research-only retrieval checkpoint, production cap and deferred-lane coverage."""

from copy import deepcopy
import json
from pathlib import Path
import socket
import shutil
import subprocess
import tempfile

import pytest

from dragon.deep_research_executor import FixtureResearchAdapter, RoundActionBudget, execute_research_round
from dragon.editorial_functions import classify_event_functions
from dragon.providers import LocalCommandEditorialProvider
from dragon.research_acceptance import ProviderFreeAcceptanceProvider
from dragon.retrieval_acceptance import prepare_retrieval, seed_run, run_research_stages, RecordingResearchAdapter, replay_retrieval, evidence_decisions
from dragon.archive import LocalAcceptanceArchive
from dragon.state import atomic_write_json

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def replay(monkeypatch):
    common = Path(subprocess.check_output(["git", "rev-parse", "--git-common-dir"], cwd=ROOT, text=True).strip()).resolve()
    archive = common / "dragon/research-acceptance"
    parent = archive / "provider-research-acceptance-f1bd0998-d792-4d28-851c-b1c60bfa1f99"
    receipts = list((archive / "contract-comparisons").glob("*ed732755*/receipt.json"))
    if not parent.is_dir() or not receipts:
        pytest.skip("task's preserved parent and baseline comparison are unavailable on this checkout")
    def forbidden(*args, **kwargs): pytest.fail("offline preparation attempted provider/network execution")
    monkeypatch.setattr(LocalCommandEditorialProvider, "_invoke", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    return prepare_retrieval(parent, receipts[0], root=ROOT)


def test_fixed_initial_plan_preserves_exact_pair_and_original_date(replay):
    assert replay["retrieval_preflight"]["parent_artifact_count"] == 67
    assert [a["action_id"] for a in replay["scheduler_allocation"]["actions"]] == [
        "ACT-156391587BBA", "ACT-7A2D5D43557D", "ACT-EBB9846FF233", "ACT-A692E56FD7B2",
        "ACT-FF6D6F3F70A8", "ACT-7F6A275C60AF", "ACT-9DD35F8F134E", "ACT-DEE6900C64A7"]
    for action in replay["scheduler_allocation"]["actions"]:
        assert action["event_context"]["research_date"] == "2026-10-04"
    pair = [a for a in replay["scheduler_allocation"]["actions"] if a.get("provider_candidate_id") == "investigations:inv-itrane"]
    assert {a["provider_source_role"] for a in pair} == {"PRIMARY", "INDEPENDENT"}
    assert all(a["target"] == a["provider_supplied_url"] for a in pair)
    assert not any(a.get("provider_candidate_id") == "investigations:inv-rotork" for a in replay["materialized_actions"])


def test_global_execution_cap_blocks_dynamic_actions_without_losing_selected(replay):
    selected = deepcopy(replay["scheduler_allocation"]["actions"])
    config = replay["scheduler_configuration"]
    budget = RoundActionBudget(8, selected)
    adapter = FixtureResearchAdapter({"SEARCH_DISCOVERY": [{"result_type": "DEAD_END", "reason": "BACKEND_EMPTY"}]})
    executions = []
    for job in replay["scheduler_inputs"]["jobs"]:
        actions = [a for a in selected if a["job_id"] == job["job_id"]]
        if actions:
            executions += execute_research_round(job, adapter, config, actions=actions, round_budget=budget)["actions"]
    assert len(executions) == len(adapter.executed_actions) == 8
    assert {a["action_id"] for a in executions} == {a["action_id"] for a in selected}
    assert budget.report()["remaining_capacity"] == 0
    assert budget.report()["dynamic_actions_deferred"]


def test_unchanged_service_need_is_attempted_in_existing_recovery_epoch(replay, tmp_path):
    shutil.copytree(ROOT / "config", tmp_path / "config")
    run_dir = tmp_path / "retrieval-fixture"
    seed_run(run_dir, replay)
    adapter = FixtureResearchAdapter({})
    result = run_research_stages(tmp_path, run_dir, "2026-10-04", adapter)
    assert result["research_recovery"]["error_code"] in {"RESEARCH_RECOVERY_REQUIRED", "RESEARCH_INSUFFICIENT"}
    report = json.loads((run_dir / "deep-research/epoch-1-execution-report.json").read_text(encoding="utf-8"))
    assert any(a.get("target_editorial_function") == "SERVICE" for a in report["actions_planned"])
    assert len(report["actions_planned"]) <= 8
    assert report["round_execution_budget"]["maximum_actions_per_round"] == 8
    assert not report["round_execution_budget"]["budget_increased"]
    assert not list(run_dir.glob("**/epoch-2*"))


def test_round_budget_reserves_pending_actions_and_allows_only_real_spare_capacity():
    budget = RoundActionBudget(3, [{"action_id": "one"}, {"action_id": "two"}])
    assert budget.admit({"action_id": "followup"})
    assert not budget.admit({"action_id": "extra"})
    assert budget.admit({"action_id": "one"})
    assert budget.admit({"action_id": "two"})
    assert not budget.admit({"action_id": "one"})
    assert len(budget.executed) == 3


@pytest.mark.parametrize("method", ["research", "articles"])
def test_zero_provider_guard(method):
    with pytest.raises(AssertionError): getattr(ProviderFreeAcceptanceProvider(), method)("2026-10-04")


@pytest.mark.parametrize("routine", ["projet de concentration", "merger notification", "مشروع تركيز اقتصادي"])
def test_routine_concentration_is_not_accountability(routine):
    values = classify_event_functions(title="Official regulatory notice", facts=[f"Public authority received a {routine} concerning acquisition."],
        evidence_source_ids=["primary", "independent"], exact_page_validated=True)
    assert "ACCOUNTABILITY" not in {v["function"] for v in values}


def test_actual_enforcement_on_transaction_can_still_qualify():
    values = classify_event_functions(title="Official sanction", facts=["Public regulator imposes an amende after investigation of a projet de concentration."],
        evidence_source_ids=["primary", "independent"], exact_page_validated=True)
    assert "ACCOUNTABILITY" in {v["function"] for v in values}


def test_preserved_empty_retrieval_replays_all_production_decisions_exactly(replay, tmp_path):
    with tempfile.TemporaryDirectory(prefix="retrieval-fixture-", dir=ROOT) as directory:
        run_dir = Path(directory)
        archive = LocalAcceptanceArchive(root=ROOT, run_dir=run_dir, run_id=run_dir.name,
            edition_date="2026-10-04", destination=tmp_path)
        archive.manifest["provider_call_limit"] = 0
        seed_run(run_dir, replay)
        atomic_write_json(run_dir / "retrieval/execution-replay.json", replay)
        adapter = RecordingResearchAdapter(FixtureResearchAdapter({}), run_dir, archive)
        run_research_stages(ROOT, run_dir, "2026-10-04", adapter, archive.snapshot)
        decisions = evidence_decisions(run_dir)
        assert decisions["verdicts"]["TECHNICAL_RESEARCH_ACCEPTANCE"] == "PASS"
        assert decisions["verdicts"]["ACCOUNTABILITY_PRIMARY_RETRIEVAL"] == "FAIL"
        assert decisions["verdicts"]["CURRENT_SERVICE_EVENT_VALIDATED"] == "FAIL"
        archive.finalize(required=["retrieval/execution-replay.json", "deep-research/execution-report.json",
            "deep-research/epoch-1-execution-report.json", "research-recovery/plan.json"], provider_calls=0, run_result="RESEARCH_RECOVERY_REQUIRED")
    result = replay_retrieval(archive.bundle, root=ROOT)
    assert result["status"] == "PASS"
    assert result["provider_calls"] == result["network_calls"] == 0
    assert 8 <= result["actions_replayed"] <= 16


def test_comparison_tampering_stops_before_network(replay, tmp_path):
    common = Path(subprocess.check_output(["git", "rev-parse", "--git-common-dir"], cwd=ROOT, text=True).strip()).resolve()
    archive = common / "dragon/research-acceptance"
    parent = archive / replay["input_run_id"]
    original = next((archive / "contract-comparisons").glob("*ed732755*/receipt.json")).parent
    shutil.copytree(original, tmp_path / "receipt")
    (tmp_path / "receipt/comparison.json").write_text("tampered", encoding="utf-8")
    with pytest.raises(ValueError, match="comparison artifact hash differs"):
        prepare_retrieval(parent, tmp_path / "receipt/receipt.json", root=ROOT)
