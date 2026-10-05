from __future__ import annotations

import json
from pathlib import Path

from dragon.live_readiness import (
    NOT_READY,
    PROMOTION_REQUIRED,
    READY,
    REVIEW_REQUIRED,
    evaluate_final_live_readiness,
)
from dragon.state import runtime_fingerprint, sha256_file


def _config() -> dict:
    return {
        "version": 5,
        "mode": "build-behind",
        "scheduler": {
            "entries": 1,
            "provider": "codex-local-automation",
            "kind": "cron",
            "destination": "local",
            "execution_environment": "local",
            "enabled": False,
            "task_name": "DRAGON V5 Daily Newspaper",
            "start_time": "07:00",
            "canonical_command": "python dragon_watchdog.py",
        },
        "providers": {"ai": {"type": "local-command", "paid_service_auto_enable": False, "integration_test_status": "NOT_RUN"}},
        "cutover": {"legacy_v4_fallback_enabled": True, "local_scheduler_enabled": False, "competing_github_production_disabled": False},
    }


def _automation(root: Path) -> dict:
    return {
        "id": "dragon-v5-daily-newspaper",
        "kind": "cron",
        "name": "DRAGON V5 Daily Newspaper",
        "status": "PAUSED",
        "rrule": "FREQ=DAILY;BYHOUR=7;BYMINUTE=0",
        "prompt": "Run python dragon_watchdog.py once.",
        "execution_environment": "local",
        "target": {"type": "project", "project_id": "project-1"},
        "cwds": [str(root)],
    }


def _evaluate(root: Path, config: dict | None = None, automation: dict | None = None) -> dict:
    return evaluate_final_live_readiness(root, config or _config(), automation=automation if automation is not None else _automation(root))


def test_ready_state_allows_exactly_one_new_trial(tmp_path: Path) -> None:
    result = _evaluate(tmp_path)
    assert result["status"] == READY
    assert result["allows_new_trial"] is True


def test_non_build_behind_state_is_not_ready(tmp_path: Path) -> None:
    config = _config(); config["mode"] = "production"
    assert _evaluate(tmp_path, config)["status"] == NOT_READY


def test_multiple_scheduler_entries_are_not_ready(tmp_path: Path) -> None:
    config = _config(); config["scheduler"]["entries"] = 2
    assert "SINGLE_PAUSED_LOCAL_SCHEDULER_REQUIRED" in _evaluate(tmp_path, config)["issues"]


def test_enabled_scheduler_is_not_ready(tmp_path: Path) -> None:
    config = _config(); config["scheduler"]["enabled"] = True
    assert _evaluate(tmp_path, config)["status"] == NOT_READY


def test_cutover_flags_must_remain_pre_cutover(tmp_path: Path) -> None:
    config = _config(); config["cutover"]["legacy_v4_fallback_enabled"] = False
    assert "PRE_CUTOVER_SAFETY_FLAGS_REQUIRED" in _evaluate(tmp_path, config)["issues"]


def test_paid_auto_enable_is_not_ready(tmp_path: Path) -> None:
    config = _config(); config["providers"]["ai"]["paid_service_auto_enable"] = True
    assert _evaluate(tmp_path, config)["status"] == NOT_READY


def test_promoted_provider_is_not_a_new_trial_state(tmp_path: Path) -> None:
    config = _config(); config["providers"]["ai"]["integration_test_status"] = "PASS"
    assert _evaluate(tmp_path, config)["status"] == NOT_READY


def test_missing_scheduler_record_is_not_ready(tmp_path: Path) -> None:
    result = evaluate_final_live_readiness(tmp_path, _config(), automation=None)
    assert result["status"] == NOT_READY
    assert "SCHEDULER_RECORD_MISSING" in result["issues"]


def test_active_scheduler_is_not_ready(tmp_path: Path) -> None:
    automation = _automation(tmp_path); automation["status"] = "ACTIVE"
    assert _evaluate(tmp_path, automation=automation)["status"] == NOT_READY


def test_scheduler_command_must_be_canonical(tmp_path: Path) -> None:
    automation = _automation(tmp_path); automation["prompt"] = "python dragon_daily.py"
    assert "SCHEDULER_COMMAND_INVALID" in _evaluate(tmp_path, automation=automation)["issues"]


def test_technically_valid_trial_requires_human_review_before_another_trial(tmp_path: Path) -> None:
    trial = tmp_path / "acceptance" / "provider-trials" / "2099-01-02"; trial.mkdir(parents=True)
    research, articles = trial / "research.json", trial / "articles.json"
    research.write_text("{}", encoding="utf-8"); articles.write_text("{}", encoding="utf-8")
    receipt = {"schema_version": 5, "status": "VALIDATED_AWAITING_HUMAN_REVIEW", "edition_date": "2099-01-02", "created_at": "2099-01-02T11:00:00+01:00", "editorial_generation_tested": True, "runtime_fingerprint": runtime_fingerprint(tmp_path), "source_git_revision": "abc", "provider": {"status": "PASS", "unattended": True}, "artifacts": {"acceptance/provider-trials/2099-01-02/research.json": sha256_file(research), "acceptance/provider-trials/2099-01-02/articles.json": sha256_file(articles)}}
    (trial / "receipt.json").write_text(json.dumps(receipt), encoding="utf-8")
    assert _evaluate(tmp_path)["status"] == REVIEW_REQUIRED


def test_reviewed_trial_requires_manual_provider_promotion_not_another_trial(tmp_path: Path) -> None:
    trial = tmp_path / "acceptance" / "provider-trials" / "2099-01-02"; trial.mkdir(parents=True)
    research, articles = trial / "research.json", trial / "articles.json"
    research.write_text("{}", encoding="utf-8"); articles.write_text("{}", encoding="utf-8")
    receipt = {"schema_version": 5, "status": "VALIDATED_AWAITING_HUMAN_REVIEW", "edition_date": "2099-01-02", "created_at": "2099-01-02T11:00:00+01:00", "editorial_generation_tested": True, "runtime_fingerprint": runtime_fingerprint(tmp_path), "source_git_revision": "abc", "provider": {"status": "PASS", "unattended": True}, "artifacts": {"acceptance/provider-trials/2099-01-02/research.json": sha256_file(research), "acceptance/provider-trials/2099-01-02/articles.json": sha256_file(articles)}}
    receipt_path = trial / "receipt.json"; receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    review = {"schema_version": 5, "status": "PASS", "reviewed_by": "Editor", "reviewed_at": "2099-01-02T12:00:00+01:00", "receipt_sha256": sha256_file(receipt_path), "checks": {"sources": "PASS", "factual_accuracy": "PASS", "arabic_quality": "PASS", "article_depth": "PASS", "section_decisions": "PASS"}}
    (trial / "review.json").write_text(json.dumps(review), encoding="utf-8")
    assert _evaluate(tmp_path)["status"] == PROMOTION_REQUIRED
