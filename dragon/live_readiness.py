"""Evaluate whether one *new* editorial-provider trial may be authorized.

This is deliberately separate from :func:`dragon.acceptance.audit_cutover`.
Cutover evidence includes real editions, human reviews, archive receipts, and
an active scheduler.  Those facts are outputs of a successful live trial, so
requiring them before authorizing that trial is a sequencing error.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from dragon.acceptance import _provider_trial_evidence
from dragon.config import load_local_config
from dragon.state import runtime_fingerprint


READY = "READY_FOR_FINAL_LIVE_AUTHORIZATION"
NOT_READY = "NOT_READY_FOR_FINAL_LIVE_AUTHORIZATION"
REVIEW_REQUIRED = "HUMAN_REVIEW_REQUIRED"
PROMOTION_REQUIRED = "PROVIDER_PROMOTION_REQUIRED"


def _as_mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _automation_issues(
    root: Path, scheduler: Mapping[str, Any], automation: Mapping[str, Any] | None
) -> list[str]:
    """Validate a supplied local Codex automation record without activating it."""
    if automation is None:
        return ["SCHEDULER_RECORD_MISSING"]
    target = _as_mapping(automation.get("target"))
    cwds = automation.get("cwds")
    expected_time = str(scheduler.get("start_time", ""))
    expected_command = str(scheduler.get("canonical_command", ""))
    rrule = str(automation.get("rrule", ""))
    prompt = str(automation.get("prompt", ""))
    issues: list[str] = []
    if automation.get("id") != "dragon-v5-daily-newspaper":
        issues.append("SCHEDULER_ID_INVALID")
    if automation.get("kind") != "cron" or automation.get("name") != scheduler.get("task_name"):
        issues.append("SCHEDULER_IDENTITY_INVALID")
    if automation.get("status") != "PAUSED":
        issues.append("SCHEDULER_NOT_PAUSED")
    if automation.get("execution_environment") != "local" or target.get("type") != "project":
        issues.append("SCHEDULER_EXECUTION_SCOPE_INVALID")
    if not str(target.get("project_id", "")).strip():
        issues.append("SCHEDULER_PROJECT_ID_MISSING")
    if not isinstance(cwds, list) or str(root) not in [str(value) for value in cwds]:
        issues.append("SCHEDULER_PROJECT_PATH_INVALID")
    hour, minute = expected_time.split(":", 1) if ":" in expected_time else ("", "")
    try:
        expected_hour, expected_minute = int(hour), int(minute)
    except ValueError:
        expected_hour, expected_minute = -1, -1
    if (
        f"BYHOUR={expected_hour}" not in rrule
        or f"BYMINUTE={expected_minute}" not in rrule
    ):
        issues.append("SCHEDULER_SCHEDULE_INVALID")
    if expected_command not in prompt:
        issues.append("SCHEDULER_COMMAND_INVALID")
    return issues


def _configuration_issues(config: Mapping[str, Any]) -> list[str]:
    scheduler = _as_mapping(config.get("scheduler"))
    providers = _as_mapping(config.get("providers"))
    ai = _as_mapping(providers.get("ai"))
    cutover = _as_mapping(config.get("cutover"))
    issues: list[str] = []
    if config.get("version") != 5 or config.get("mode") != "build-behind":
        issues.append("BUILD_BEHIND_MODE_REQUIRED")
    if (
        scheduler.get("entries") != 1
        or scheduler.get("provider") != "codex-local-automation"
        or scheduler.get("kind") != "cron"
        or scheduler.get("destination") != "local"
        or scheduler.get("execution_environment") != "local"
        or scheduler.get("enabled") is not False
        or scheduler.get("canonical_command") != "python dragon_watchdog.py"
    ):
        issues.append("SINGLE_PAUSED_LOCAL_SCHEDULER_REQUIRED")
    if (
        cutover.get("legacy_v4_fallback_enabled") is not True
        or cutover.get("local_scheduler_enabled") is not False
        or cutover.get("competing_github_production_disabled") is not False
    ):
        issues.append("PRE_CUTOVER_SAFETY_FLAGS_REQUIRED")
    if (
        ai.get("type") != "local-command"
        or ai.get("paid_service_auto_enable") is not False
        or ai.get("integration_test_status") != "NOT_RUN"
    ):
        issues.append("UNPROMOTED_LOCAL_PROVIDER_REQUIRED")
    return issues


def evaluate_final_live_readiness(
    root: Path,
    config: Mapping[str, Any],
    *,
    automation: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Return the pre-live state; never treats post-trial evidence as a prerequisite."""
    root = root.resolve()
    scheduler = _as_mapping(config.get("scheduler"))
    issues = _configuration_issues(config)
    issues.extend(_automation_issues(root, scheduler, automation))
    fingerprint = runtime_fingerprint(root)
    provider_proven, trials = _provider_trial_evidence(root, fingerprint)

    if provider_proven:
        status = PROMOTION_REQUIRED
        issues.append("CURRENT_TRIAL_ALREADY_REVIEWED")
    elif any(
        item.get("status") == "REJECTED"
        and set(item.get("issues", [])) == {"HUMAN_REVIEW_MISSING_OR_INVALID"}
        for item in trials
    ):
        status = REVIEW_REQUIRED
        issues.append("CURRENT_TRIAL_AWAITS_HUMAN_REVIEW")
    elif issues:
        status = NOT_READY
    else:
        status = READY

    return {
        "schema_version": 5,
        "status": status,
        "allows_new_trial": status == READY,
        "pre_live_checks": {
            "configuration": "PASS" if not _configuration_issues(config) else "FAIL",
            "paused_local_scheduler": "PASS"
            if not _automation_issues(root, scheduler, automation)
            else "FAIL",
            "no_current_trial_requiring_review": "PASS"
            if status not in {REVIEW_REQUIRED, PROMOTION_REQUIRED}
            else "FAIL",
        },
        "issues": sorted(set(issues)),
        "evidence": {"runtime_fingerprint": fingerprint, "provider_trials": trials},
        "post_trial_requirements": [
            "A technically validated provider receipt still requires hash-bound human review.",
            "A reviewed provider trial still requires a manual production edition, archive read-back, unattended runs, and cutover audit before activation.",
            "The local scheduler remains paused and V4 remains enabled until READY_FOR_CUTOVER.",
        ],
    }


def audit_final_live_readiness(
    root: Path, *, automation: Mapping[str, Any] | None
) -> dict[str, Any]:
    """Load repository configuration and evaluate the separate pre-live gate."""
    return evaluate_final_live_readiness(root, load_local_config(root), automation=automation)
