"""Fail-closed V5 cutover evidence audit."""

from __future__ import annotations

from datetime import date, timedelta
import json
from pathlib import Path
from typing import Any

from dragon.config import load_local_config, load_mapping
from dragon.state import sha256_file


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


def _state_valid(root: Path, state: dict) -> tuple[bool, list[str]]:
    issues: list[str] = []
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
    return not issues, issues


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
    valid_runs = []
    rejected_runs = []
    for path in sorted((root / "daily-runs").glob("????-??-??/state.json")):
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
            valid, issues = _state_valid(root, state)
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
        if valid:
            valid_runs.append(entry)
        else:
            rejected_runs.append({**entry, "issues": issues})
    synthetic = [item for item in valid_runs if item["mode"] == "synthetic"]
    manual_real = [item for item in valid_runs if item["mode"] == "production" and item["trigger"] == "manual"]
    unattended = [item for item in valid_runs if item["mode"] == "production" and item["trigger"] == "watchdog"]
    required_runs = int(policy.get("required_consecutive_unattended_runs", 3))
    sequence = _consecutive([item["date"] for item in unattended], required_runs)
    archived = []
    for item in unattended + manual_real:
        receipt_path = root / "daily-runs" / item["date"] / "archive-receipt.json"
        try:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            verified = (
                item["archive"] == "COMPLETE"
                and receipt.get("status") == "COMPLETE"
                and receipt.get("verified") is True
                and receipt.get("commit") == receipt.get("remote_commit")
            )
        except (OSError, json.JSONDecodeError):
            verified = False
        if verified:
            archived.append(item)
    delivered = [item for item in unattended + manual_real if item["delivery"] == "COMPLETE"]
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
