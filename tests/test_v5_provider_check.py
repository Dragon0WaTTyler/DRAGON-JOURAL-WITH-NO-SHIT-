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


def test_emit_json_is_ascii_safe_for_windows_legacy_consoles(capsys) -> None:
    dragon_provider_check._emit_json({"message": "صحافة عربية"})
    output = capsys.readouterr().out
    assert "\\u0635" in output
    assert all(ord(character) < 128 for character in output)


def test_full_trial_preserves_prior_date_evidence_in_a_new_attempt_directory(tmp_path) -> None:
    base = tmp_path / "acceptance" / "provider-trials" / "2099-01-02"
    base.mkdir(parents=True)
    prior = base / "failure.json"
    prior.write_text('{"status":"FAIL"}', encoding="utf-8")

    attempt = dragon_provider_check._trial_directory(tmp_path, "2099-01-02", full=True)

    assert attempt.parent == base / "attempts"
    assert attempt.name.startswith("attempt-")
    assert prior.read_text(encoding="utf-8") == '{"status":"FAIL"}'
    assert dragon_provider_check._trial_directory(tmp_path, "2099-01-03", full=True) == (
        tmp_path / "acceptance" / "provider-trials" / "2099-01-03"
    )


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
    assert set(value["raw_evidence"]) == {
        "acceptance/provider-trials/2099-01-02/research.raw.json"
    }
    assert len(next(iter(value["raw_evidence"].values()))) == 64
    failure = tmp_path / value["failure_evidence"]
    persisted = json.loads(failure.read_text(encoding="utf-8"))
    assert persisted["status"] == "FAIL"
    assert persisted["integration_test_status_changed"] is False
    assert "failure_evidence" not in persisted
