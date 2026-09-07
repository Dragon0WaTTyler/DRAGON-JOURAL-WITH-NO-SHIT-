from __future__ import annotations

import json
import sys

import dragon_provider_check


class TrialProvider:
    def healthcheck(self):
        return {"status": "PASS", "unattended": True, "provider": "test"}

    def research(self, edition_date, continuity):
        return {"edition_date": edition_date, "sources": [{"id": "s1"}], "sections": []}

    def articles(self, research):
        return [
            {"section_id": "front", "status": "ACTIVE", "body": ["كلمة " * 10]},
            {"section_id": "world", "status": "SKIPPED"},
        ]


def test_full_trial_persists_reviewable_evidence_without_promoting_config(
    tmp_path, monkeypatch, capsys
) -> None:
    monkeypatch.setattr(dragon_provider_check, "ROOT", tmp_path)
    monkeypatch.setattr(
        dragon_provider_check,
        "load_local_config",
        lambda root: {"timezone": "Africa/Casablanca"},
    )
    monkeypatch.setattr(
        dragon_provider_check,
        "editorial_provider_from_config",
        lambda config, require_proven: TrialProvider(),
    )
    monkeypatch.setattr(
        dragon_provider_check,
        "LocalCommandEditorialProvider",
        TrialProvider,
    )
    monkeypatch.setattr(sys, "argv", ["dragon_provider_check.py", "--full", "--date", "2099-01-02"])

    assert dragon_provider_check.main() == 0

    value = json.loads(capsys.readouterr().out)
    assert value["status"] == "VALIDATED_AWAITING_HUMAN_REVIEW"
    assert value["integration_test_status_changed"] is False
    trial = tmp_path / "acceptance" / "provider-trials" / "2099-01-02"
    assert (trial / "research.json").is_file()
    assert (trial / "articles.json").is_file()
    assert (trial / "receipt.json").is_file()
