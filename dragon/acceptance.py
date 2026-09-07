"""Fail-closed V5 cutover evidence audit."""

from __future__ import annotations

from datetime import date, timedelta
import json
from pathlib import Path
from typing import Any

from dragon.config import load_local_config, load_mapping
from dragon.state import runtime_fingerprint, sha256_file


LOCAL_STAGES = (
    "preflight",
    "research",
    "article_generation",
    "chief_editor",
    "factcheck",
    "arabic_language_qa",
    "cover",
    "publication_source",
    "pdf",
    "epub",
    "final_qa",
)


def _state_valid(
    root: Path, state: dict, *, expected_runtime_fingerprint: str | None = None
) -> tuple[bool, list[str]]:
    issues: list[str] = []
    expected_runtime_fingerprint = expected_runtime_fingerprint or runtime_fingerprint(root)
    recorded_runtime = state.get("runtime_fingerprint")
    if not recorded_runtime:
        issues.append("RUNTIME_FINGERPRINT_MISSING")
    elif recorded_runtime != expected_runtime_fingerprint:
        issues.append("RUNTIME_FINGERPRINT_MISMATCH")
    if state.get("schema_version") != 5 or state.get("publication_status") != "COMPLETE":
        issues.append("PUBLICATION_NOT_COMPLETE")
    for name in LOCAL_STAGES:
        record = state.get("stages", {}).get(name, {})
        if record.get("status") != "COMPLETE":
            issues.append(f"STAGE_NOT_COMPLETE:{name}")
            continue
        hashes = record.get("artifact_hashes", {})
        if not hashes:
            issues.append(f"CHECKPOINT_HAS_NO_HASHES:{name}")
        for relative, expected in hashes.items():
            path = (root / relative).resolve()
            try:
                path.relative_to(root.resolve())
            except ValueError:
                issues.append(f"ARTIFACT_PATH_ESCAPE:{name}")
                continue
            if not path.is_file() or sha256_file(path) != expected:
                issues.append(f"ARTIFACT_HASH_INVALID:{name}:{relative}")
    report_relative = f"daily-runs/{state.get('date', '')}/run-report.json"
    report_path = root / report_relative
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        issues.append("RUN_REPORT_MISSING_OR_INVALID")
    else:
        if report_relative not in state.get("report_paths", []):
            issues.append("RUN_REPORT_NOT_DECLARED")
        if (
            report.get("schema_version") != 5
            or report.get("date") != state.get("date")
            or report.get("run_id") != state.get("run_id")
            or report.get("runtime_fingerprint") != recorded_runtime
            or report.get("publication") != "COMPLETE"
        ):
            issues.append("RUN_REPORT_STATE_MISMATCH")
    return not issues, issues


def _checkpointed_receipt(root: Path, state: dict, stage_name: str, filename: str) -> dict | None:
    relative = f"daily-runs/{state.get('date', '')}/{filename}"
    record = state.get("stages", {}).get(stage_name, {})
    expected = record.get("artifact_hashes", {}).get(relative)
    path = root / relative
    if record.get("status") != "COMPLETE" or not expected or not path.is_file():
        return None
    if sha256_file(path) != expected:
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _mode(root: Path, state: dict) -> str:
    parsed = date.fromisoformat(state["date"])
    path = root / "editions" / f"{parsed:%Y}" / f"{parsed:%m}" / state["date"] / "manifest.json"
    try:
        return str(json.loads(path.read_text(encoding="utf-8")).get("mode", "unknown"))
    except (OSError, json.JSONDecodeError):
        return "unknown"


def _consecutive(dates: list[str], required: int) -> list[str]:
    parsed = sorted({date.fromisoformat(value) for value in dates})
    best: list[date] = []
    current: list[date] = []
    for value in parsed:
        if current and value != current[-1] + timedelta(days=1):
            current = []
        current.append(value)
        if len(current) > len(best):
            best = list(current)
    return [value.isoformat() for value in best[-required:]] if len(best) >= required else []


def audit_cutover(root: Path) -> dict[str, Any]:
    root = root.resolve()
    config = load_local_config(root)
    policy = load_mapping(root / "config" / "cutover-acceptance.yaml")
    expected_runtime_fingerprint = runtime_fingerprint(root)
    valid_runs = []
    rejected_runs = []
    for path in sorted((root / "daily-runs").glob("????-??-??/state.json")):
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
            valid, issues = _state_valid(
                root, state, expected_runtime_fingerprint=expected_runtime_fingerprint
            )
        except (OSError, json.JSONDecodeError, KeyError, ValueError) as exc:
            rejected_runs.append({"path": str(path.relative_to(root)).replace("\\", "/"), "issues": [str(exc)]})
            continue
        entry = {
            "date": state["date"],
            "mode": _mode(root, state),
            "trigger": state.get("trigger", "unknown"),
            "archive": state.get("archive_status"),
            "delivery": state.get("delivery_status"),
        }
        archive_receipt = _checkpointed_receipt(
            root, state, "github_archive", "archive-receipt.json"
        )
        delivery_receipt = _checkpointed_receipt(
            root, state, "whatsapp_delivery", "delivery-receipt.json"
        )
        entry["archive_receipt_valid"] = bool(
            state.get("archive_status") == "COMPLETE"
            and archive_receipt
            and archive_receipt.get("status") == "COMPLETE"
            and archive_receipt.get("verified") is True
            and archive_receipt.get("commit") == archive_receipt.get("remote_commit")
        )
        entry["delivery_receipt_valid"] = bool(
            state.get("delivery_status") == "COMPLETE"
            and delivery_receipt
            and delivery_receipt.get("status") == "COMPLETE"
            and delivery_receipt.get("accepted") is True
            and delivery_receipt.get("publication_status") == "COMPLETE"
        )
        if valid:
            valid_runs.append(entry)
        else:
            rejected_runs.append({**entry, "issues": issues})
    synthetic = [item for item in valid_runs if item["mode"] == "synthetic"]
    manual_real = [item for item in valid_runs if item["mode"] == "production" and item["trigger"] == "manual"]
    unattended = [item for item in valid_runs if item["mode"] == "production" and item["trigger"] == "watchdog"]
    required_runs = int(policy.get("required_consecutive_unattended_runs", 3))
    sequence = _consecutive([item["date"] for item in unattended], required_runs)
    archived = [item for item in unattended + manual_real if item["archive_receipt_valid"]]
    delivered = [item for item in unattended + manual_real if item["delivery_receipt_valid"]]
    evidence_dir = root / "acceptance" / "evidence"
    review_evidence = {}
    for filename in policy.get("required_review_evidence", []):
        path = evidence_dir / str(filename)
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            passed = value.get("status") == "PASS" and bool(value.get("reviewed_by"))
        except (OSError, json.JSONDecodeError):
            passed = False
        review_evidence[str(filename)] = "PASS" if passed else "MISSING_OR_INVALID"
    ai = config.get("providers", {}).get("ai", {})
    checks = {
        "synthetic_publication": bool(synthetic) if policy.get("require_synthetic_publication", True) else True,
        "manual_real_publication": bool(manual_real) if policy.get("require_manual_real_publication", True) else True,
        "consecutive_unattended_runs": bool(sequence),
        "verified_git_archive": bool(archived) if policy.get("require_verified_git_archive", True) else True,
        "whatsapp_delivery": bool(delivered) if policy.get("require_whatsapp_delivery", False) else True,
        "editorial_provider_proven": ai.get("type") != "unconfigured" and ai.get("integration_test_status") == "PASS",
        "review_evidence": all(value == "PASS" for value in review_evidence.values()),
    }
    cutover = config.get("cutover", {})
    completion_checks = {
        "local_scheduler_enabled": bool(cutover.get("local_scheduler_enabled")) and bool(config.get("scheduler", {}).get("enabled")),
        "legacy_v4_fallback_disabled": not bool(cutover.get("legacy_v4_fallback_enabled", True)),
        "competing_github_production_disabled": bool(cutover.get("competing_github_production_disabled")),
    }
    ready = all(checks.values())
    complete = ready and all(completion_checks.values())
    return {
        "schema_version": 5,
        "status": "CUTOVER_COMPLETE" if complete else "READY_FOR_CUTOVER" if ready else "BLOCKED",
        "checks": checks,
        "completion_checks": completion_checks,
        "evidence": {
            "valid_runs": valid_runs,
            "rejected_runs": rejected_runs,
            "consecutive_unattended_dates": sequence,
            "review_files": review_evidence,
        },
    }
