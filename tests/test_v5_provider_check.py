from __future__ import annotations

from dataclasses import dataclass
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


@dataclass(frozen=True)
class FailingTrialProvider:
    capture_directory: object = None

    def healthcheck(self):
        return {"status": "PASS", "unattended": True, "provider": "test"}

    def research(self, edition_date, continuity):
        self.capture_directory.mkdir(parents=True, exist_ok=True)
        (self.capture_directory / "research.raw.json").write_text("{}", encoding="utf-8")
        from dragon.providers import ProviderError

        raise ProviderError("RESEARCH_PACKET_INVALID", "missing=['world']")


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
    assert value["editorial_generation_tested"] is True
    assert len(value["runtime_fingerprint"]) == 64
    assert value["created_at"].endswith("+01:00")
    trial = tmp_path / "acceptance" / "provider-trials" / "2099-01-02"
    assert (trial / "research.json").is_file()
    assert (trial / "articles.json").is_file()
    assert (trial / "receipt.json").is_file()


def test_failed_full_trial_reports_persisted_raw_evidence(
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
        lambda config, require_proven: FailingTrialProvider(),
    )
    monkeypatch.setattr(
        dragon_provider_check,
        "LocalCommandEditorialProvider",
        FailingTrialProvider,
    )
    monkeypatch.setattr(
        sys, "argv", ["dragon_provider_check.py", "--full", "--date", "2099-01-02"]
    )

    assert dragon_provider_check.main() == 1
    value = json.loads(capsys.readouterr().out)
    assert value["error_code"] == "RESEARCH_PACKET_INVALID"
    assert value["raw_evidence"] == [
        "acceptance/provider-trials/2099-01-02/research.raw.json"
    ]
