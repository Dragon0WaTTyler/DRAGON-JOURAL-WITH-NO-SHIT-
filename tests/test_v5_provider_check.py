from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import sys
from zoneinfo import ZoneInfo

import dragon_provider_check


@dataclass(frozen=True)
class TrialProvider:
    capture_directory: object = None
    mode: str = "production"

    def healthcheck(self):
        return {"status": "PASS", "unattended": True, "provider": "test"}

    def research(self, edition_date, continuity):
        self.capture_directory.mkdir(parents=True, exist_ok=True)
        (self.capture_directory / "research.raw.json").write_text("{}", encoding="utf-8")
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
    class CompletedOrchestrator:
        class store:
            run_dir = tmp_path / "daily-runs" / "2099-01-02" / "runs" / "fresh-run"
            path = run_dir / "state.json"

        def run(self):
            articles = self.store.run_dir / "articles" / "articles.json"
            articles.parent.mkdir(parents=True, exist_ok=True)
            articles.write_text(json.dumps({"articles": TrialProvider().articles({})}), encoding="utf-8")
            self.store.path.parent.mkdir(parents=True, exist_ok=True)
            self.store.path.write_text("{}", encoding="utf-8")
            return {"stages": {"article_generation": {"status": "COMPLETE"}}}

    monkeypatch.setattr(
        dragon_provider_check,
        "build_provider_seed_orchestrator",
        lambda **kwargs: CompletedOrchestrator(),
    )
    monkeypatch.setattr(sys, "argv", ["dragon_provider_check.py", "--full", "--date", "2099-01-02"])

    assert dragon_provider_check.main() == 0

    value = json.loads(capsys.readouterr().out)
    assert value["status"] == "VALIDATED_AWAITING_HUMAN_REVIEW"
    assert value["integration_test_status_changed"] is False
    assert value["editorial_generation_tested"] is True
    assert value["research_counts"]["provider_selected_sections"] == 0
    assert len(value["runtime_fingerprint"]) == 64
    assert value["edition_date"] == "2099-01-02"
    created_at = datetime.fromisoformat(value["created_at"])
    assert created_at.tzinfo is not None
    expected_offset = datetime.fromtimestamp(
        created_at.timestamp(), ZoneInfo("Africa/Casablanca")
    ).utcoffset()
    assert created_at.utcoffset() == expected_offset
    trial = tmp_path / "acceptance" / "provider-trials" / "2099-01-02"
    assert (trial / "research.json").is_file()
    assert (trial / "articles.json").is_file()
    assert (trial / "receipt.json").is_file()


def test_full_trial_binds_provider_attempt_to_fresh_run_identity(tmp_path, monkeypatch, capsys) -> None:
    captured = {}
    prior = tmp_path / "acceptance" / "provider-trials" / "2099-01-02"
    prior.mkdir(parents=True)
    (prior / "failure.json").write_text('{"status":"FAIL"}', encoding="utf-8")
    monkeypatch.setattr(dragon_provider_check, "ROOT", tmp_path)
    monkeypatch.setattr(dragon_provider_check, "load_local_config", lambda root: {"timezone": "Africa/Casablanca"})
    monkeypatch.setattr(
        dragon_provider_check,
        "editorial_provider_from_config",
        lambda config, require_proven: TrialProvider(),
    )
    monkeypatch.setattr(dragon_provider_check, "LocalCommandEditorialProvider", TrialProvider)

    class FailedFreshRun:
        class store:
            run_id = "fresh-run"
            run_dir = tmp_path / "daily-runs" / "2099-01-02" / "runs" / run_id
            path = run_dir / "state.json"

        def run(self):
            self.store.path.parent.mkdir(parents=True, exist_ok=True)
            self.store.path.write_text("{}", encoding="utf-8")
            return {
                "run_id": self.store.run_id,
                "run_result": "BLOCKED",
                "error_code": "RUNTIME_FINGERPRINT_MISMATCH",
                "stages": {},
            }

    def builder(**kwargs):
        captured.update(kwargs)
        return FailedFreshRun()

    monkeypatch.setattr(dragon_provider_check, "build_provider_seed_orchestrator", builder)
    monkeypatch.setattr(sys, "argv", ["dragon_provider_check.py", "--full", "--date", "2099-01-02"])

    assert dragon_provider_check.main() == 1
    output = json.loads(capsys.readouterr().out)
    assert captured["source_attempt_id"].startswith("attempt-")
    assert output["error_code"] == "RUNTIME_FINGERPRINT_MISMATCH"
    assert output["pipeline_diagnostics"]["run_state"].endswith("runs/fresh-run/state.json")


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
