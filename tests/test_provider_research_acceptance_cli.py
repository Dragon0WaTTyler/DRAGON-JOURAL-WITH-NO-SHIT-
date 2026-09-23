from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import dragon_provider_research_acceptance as cli
from dragon.providers import LocalCommandEditorialProvider


def test_cli_requires_explicit_provider_research_authorization(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["dragon_provider_research_acceptance.py", "--date", "2099-12-28"])

    assert cli.main() == 2
    assert json.loads(capsys.readouterr().out)["code"] == "PROVIDER_RESEARCH_AUTHORIZATION_REQUIRED"


def test_cli_reports_authoritative_persisted_result(monkeypatch, capsys, tmp_path: Path):
    report = tmp_path / "report.json"
    monkeypatch.setattr(
        cli,
        "run_provider_research_acceptance",
        lambda **_kwargs: (SimpleNamespace(store=SimpleNamespace(run_id="provider-run")), {"run_result": "FAILED"}, report),
    )
    monkeypatch.setattr(
        cli,
        "editorial_provider_from_config",
        lambda *_args, **_kwargs: LocalCommandEditorialProvider(command=("fixture-provider",)),
    )
    monkeypatch.setattr(sys, "argv", [
        "dragon_provider_research_acceptance.py", "--date", "2099-12-28", "--authorize-provider-research",
    ])

    assert cli.main() == 1
    value = json.loads(capsys.readouterr().out)
    assert value == {"status": "FAILED", "run_id": "provider-run", "report": str(report)}
