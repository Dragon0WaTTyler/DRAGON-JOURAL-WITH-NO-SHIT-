"""Deterministic CLI contract tests for research-only acceptance results."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import dragon_research_acceptance as cli
from dragon.research_acceptance import ResearchAcceptanceError


def _orchestrator(run_id: str = "research-acceptance-test"):
    return SimpleNamespace(store=SimpleNamespace(run_id=run_id))


def _invoke(monkeypatch, capsys, result, *, state=None, report=None):
    if callable(result):
        monkeypatch.setattr(cli, "run_research_acceptance", result)
    else:
        monkeypatch.setattr(cli, "run_research_acceptance", lambda **_: result)
    monkeypatch.setattr("sys.argv", ["dragon_research_acceptance.py", "--date", "2099-12-29"])
    code = cli.main()
    return code, json.loads(capsys.readouterr().out)


def test_cli_reports_successful_persisted_completion(monkeypatch, capsys, tmp_path: Path) -> None:
    report = tmp_path / "research-acceptance-report.json"
    code, output = _invoke(monkeypatch, capsys, (_orchestrator(), {"run_result": "COMPLETE"}, report))

    assert code == 0
    assert output == {"status": "COMPLETE", "run_id": "research-acceptance-test", "report": str(report)}


def test_cli_reports_recovery_required_execution_as_failed(monkeypatch, capsys, tmp_path: Path) -> None:
    report = tmp_path / "research-acceptance-report.json"
    code, output = _invoke(monkeypatch, capsys, (_orchestrator(), {"run_result": "FAILED"}, report))

    assert code == 1
    assert output["status"] == "FAILED"
    assert output["report"] == str(report)


def test_cli_reports_blocked_preflight_without_creating_or_overwriting_state(monkeypatch, capsys, tmp_path: Path) -> None:
    persisted = tmp_path / "state.json"
    original = '{"run_result":"BLOCKED","error_code":"ACCEPTANCE_WORKTREE_DIRTY"}'
    persisted.write_text(original, encoding="utf-8")

    def blocked(**_):
        raise ResearchAcceptanceError("ACCEPTANCE_WORKTREE_DIRTY", "fixture is dirty")

    code, output = _invoke(monkeypatch, capsys, blocked)

    assert code == 2
    assert output == {"status": "ERROR", "code": "ACCEPTANCE_WORKTREE_DIRTY", "detail": "fixture is dirty"}
    assert persisted.read_text(encoding="utf-8") == original


def test_cli_reports_unexpected_execution_failure(monkeypatch, capsys) -> None:
    def unexpected(**_):
        raise RuntimeError("fixture failure")

    code, output = _invoke(monkeypatch, capsys, unexpected)

    assert code == 2
    assert output == {
        "status": "ERROR",
        "code": "ACCEPTANCE_EXECUTION_FAILED",
        "detail": "RuntimeError: fixture failure",
    }


@pytest.mark.parametrize("state", [{}, {"run_result": ""}, {"run_result": "NOT_A_RUN_RESULT"}])
def test_cli_rejects_missing_or_malformed_persisted_result_without_mutating_it(monkeypatch, capsys, tmp_path: Path, state: dict) -> None:
    report = tmp_path / "research-acceptance-report.json"
    original = json.loads(json.dumps(state))
    code, output = _invoke(monkeypatch, capsys, (_orchestrator(), state, report))

    assert code == 2
    assert output["status"] == "ERROR"
    assert output["code"] == "ACCEPTANCE_RESULT_INVALID"
    assert state == original


@pytest.mark.parametrize(
    ("orchestrator", "report"),
    [(_orchestrator(""), Path("report.json")), (_orchestrator(), None)],
)
def test_cli_rejects_other_missing_required_reporting_fields(monkeypatch, capsys, orchestrator, report) -> None:
    code, output = _invoke(monkeypatch, capsys, (orchestrator, {"run_result": "COMPLETE"}, report))

    assert code == 2
    assert output["code"] == "ACCEPTANCE_RESULT_INVALID"
