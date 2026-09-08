"""Fail-closed V5 cutover evidence audit."""

from __future__ import annotations

from datetime import date, datetime, timedelta
import json
from pathlib import Path
from typing import Any

from dragon.config import load_local_config, load_mapping
from dragon.state import runtime_fingerprint, sha256_file


LOCAL_STAGES = (
    "preflight",
    "research",
    "source_intelligence",
    "research_planning",
    "article_generation",
    "claim_evidence_graph",
    "media_critic",
    "adversarial_review",
    "factcheck",
    "chief_editor",
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


def _archive_receipt_valid(root: Path, state: dict, receipt: dict | None) -> bool:
    if not isinstance(receipt, dict):
        return False
    edition_date = str(state.get("date", ""))
    manifest_relative = f"editions/{edition_date[:4]}/{edition_date[5:7]}/{edition_date}/manifest.json"
    manifest_path = root / manifest_relative
    expected_manifest = state.get("stages", {}).get("github_archive", {}).get(
        "input_hashes", {}
    ).get(manifest_relative)
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(manifest, dict) or not isinstance(manifest.get("artifacts"), list):
        return False
    receipt_artifacts = receipt.get("artifacts")
    if not isinstance(receipt_artifacts, list):
        return False
    required_artifacts = {
        str(item.get("path")): item.get("sha256")
        for item in manifest.get("artifacts", [])
        if isinstance(item, dict)
    }
    required_artifacts[manifest_relative] = expected_manifest
    archived = {
        str(item.get("path")): item.get("sha256")
        for item in receipt_artifacts
        if isinstance(item, dict)
    }
    return bool(
        state.get("archive_status") == "COMPLETE"
        and receipt.get("schema_version") == 5
        and receipt.get("stage") == "github_archive"
        and receipt.get("mode") == "production"
        and receipt.get("edition_date") == edition_date
        and receipt.get("runtime_fingerprint") == state.get("runtime_fingerprint")
        and receipt.get("publication_status") == "COMPLETE"
        and receipt.get("status") == "COMPLETE"
        and receipt.get("verified") is True
        and receipt.get("commit") == receipt.get("remote_commit")
        and expected_manifest
        and manifest_path.is_file()
        and sha256_file(manifest_path) == expected_manifest
        and receipt.get("manifest_sha256") == expected_manifest
        and required_artifacts
        and all(archived.get(path) == digest for path, digest in required_artifacts.items())
    )


def _delivery_receipt_valid(root: Path, state: dict, receipt: dict | None) -> bool:
    if not isinstance(receipt, dict):
        return False
    edition_date = str(state.get("date", ""))
    pdf_relative = f"editions/{edition_date[:4]}/{edition_date[5:7]}/{edition_date}/DRAGON-{edition_date}.pdf"
    expected_pdf = state.get("stages", {}).get("whatsapp_delivery", {}).get(
        "input_hashes", {}
    ).get(pdf_relative)
    pdf_path = root / pdf_relative
    recipients = receipt.get("recipients")
    return bool(
        state.get("delivery_status") == "COMPLETE"
        and receipt.get("schema_version") == 5
        and receipt.get("stage") == "whatsapp_delivery"
        and receipt.get("mode") == "production"
        and receipt.get("edition_date") == edition_date
        and receipt.get("runtime_fingerprint") == state.get("runtime_fingerprint")
        and receipt.get("publication_status") == "COMPLETE"
        and receipt.get("status") == "COMPLETE"
        and receipt.get("accepted") is True
        and expected_pdf
        and pdf_path.is_file()
        and sha256_file(pdf_path) == expected_pdf
        and receipt.get("pdf_sha256") == expected_pdf
        and isinstance(receipt.get("delivery_fingerprint"), str)
        and len(receipt["delivery_fingerprint"]) == 64
        and isinstance(recipients, list)
        and recipients
        and all(
            isinstance(item, dict)
            and item.get("status") == "ACCEPTED_BY_PROVIDER"
            and bool(item.get("recipient_hash"))
            and bool(item.get("message_id"))
            for item in recipients
        )
    )


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


def _provider_trial_evidence(
    root: Path, expected_runtime_fingerprint: str
) -> tuple[bool, list[dict[str, Any]]]:
    trial_root = root / "acceptance" / "provider-trials"
    evidence: list[dict[str, Any]] = []
    required_checks = {
        "sources",
        "factual_accuracy",
        "arabic_quality",
        "article_depth",
        "section_decisions",
    }
    for receipt_path in sorted(trial_root.glob("????-??-??/receipt.json")):
        trial_dir = receipt_path.parent
        trial_date = trial_dir.name
        issues: list[str] = []
        try:
            date.fromisoformat(trial_date)
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, ValueError):
            evidence.append({"date": trial_date, "status": "REJECTED", "issues": ["RECEIPT_INVALID"]})
            continue
        if not isinstance(receipt, dict):
            evidence.append({"date": trial_date, "status": "REJECTED", "issues": ["RECEIPT_INVALID"]})
            continue
        if (
            receipt.get("schema_version") != 5
            or receipt.get("status") != "VALIDATED_AWAITING_HUMAN_REVIEW"
            or receipt.get("edition_date") != trial_date
            or receipt.get("editorial_generation_tested") is not True
            or not str(receipt.get("source_git_revision", "")).strip()
        ):
            issues.append("TRIAL_NOT_TECHNICALLY_VALIDATED")
        try:
            created_at = datetime.fromisoformat(str(receipt["created_at"]))
            if created_at.tzinfo is None:
                raise ValueError("timezone required")
        except (KeyError, TypeError, ValueError):
            created_at = None
            issues.append("TRIAL_TIMESTAMP_INVALID")
        provider = receipt.get("provider", {})
        if (
            not isinstance(provider, dict)
            or provider.get("status") != "PASS"
            or provider.get("unattended") is not True
        ):
            issues.append("TRIAL_PROVIDER_IDENTITY_INVALID")
        if receipt.get("runtime_fingerprint") != expected_runtime_fingerprint:
            issues.append("TRIAL_RUNTIME_FINGERPRINT_MISMATCH")
        artifacts = receipt.get("artifacts")
        required_artifacts = {
            f"acceptance/provider-trials/{trial_date}/research.json",
            f"acceptance/provider-trials/{trial_date}/articles.json",
        }
        if not isinstance(artifacts, dict) or not required_artifacts.issubset(artifacts):
            issues.append("TRIAL_ARTIFACTS_INCOMPLETE")
        else:
            for relative, expected_hash in artifacts.items():
                path = (root / str(relative)).resolve()
                try:
                    path.relative_to(trial_dir.resolve())
                except ValueError:
                    issues.append("TRIAL_ARTIFACT_PATH_ESCAPE")
                    continue
                if not path.is_file() or sha256_file(path) != expected_hash:
                    issues.append(f"TRIAL_ARTIFACT_HASH_INVALID:{relative}")
        review_path = trial_dir / "review.json"
        try:
            review = json.loads(review_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            review = None
        if not isinstance(review, dict):
            issues.append("HUMAN_REVIEW_MISSING_OR_INVALID")
        else:
            checks = review.get("checks")
            try:
                reviewed_at = datetime.fromisoformat(str(review["reviewed_at"]))
                timestamp_valid = (
                    reviewed_at.tzinfo is not None
                    and created_at is not None
                    and reviewed_at >= created_at
                )
            except (KeyError, TypeError, ValueError):
                timestamp_valid = False
            if (
                review.get("schema_version") != 5
                or review.get("status") != "PASS"
                or not str(review.get("reviewed_by", "")).strip()
                or not timestamp_valid
                or review.get("receipt_sha256") != sha256_file(receipt_path)
                or not isinstance(checks, dict)
                or set(checks) != required_checks
                or any(value != "PASS" for value in checks.values())
            ):
                issues.append("HUMAN_REVIEW_MISSING_OR_INVALID")
        evidence.append(
            {
                "date": trial_date,
                "status": "PASS" if not issues else "REJECTED",
                "issues": issues,
            }
        )
    return any(item["status"] == "PASS" for item in evidence), evidence


def _review_file_evidence(
    root: Path,
    filename: str,
    required_checks: list[str],
    expected_runtime_fingerprint: str,
) -> dict[str, Any]:
    path = root / "acceptance" / "evidence" / filename
    issues: list[str] = []
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"status": "MISSING_OR_INVALID", "issues": ["REVIEW_FILE_INVALID"]}
    if not isinstance(value, dict):
        return {"status": "MISSING_OR_INVALID", "issues": ["REVIEW_FILE_INVALID"]}
    try:
        reviewed_at = datetime.fromisoformat(str(value["reviewed_at"]))
        timestamp_valid = reviewed_at.tzinfo is not None
    except (KeyError, TypeError, ValueError):
        timestamp_valid = False
    if (
        value.get("schema_version") != 5
        or value.get("status") != "PASS"
        or not str(value.get("reviewed_by", "")).strip()
        or not timestamp_valid
    ):
        issues.append("REVIEW_ATTESTATION_INVALID")
    if value.get("runtime_fingerprint") != expected_runtime_fingerprint:
        issues.append("REVIEW_RUNTIME_FINGERPRINT_MISMATCH")
    checks = value.get("checks")
    if (
        not isinstance(checks, dict)
        or set(checks) != set(required_checks)
        or any(result != "PASS" for result in checks.values())
    ):
        issues.append("REVIEW_CHECKS_INCOMPLETE")
    artifacts = value.get("evidence")
    if not isinstance(artifacts, dict) or not artifacts:
        issues.append("REVIEW_EVIDENCE_MISSING")
    else:
        for relative, expected_hash in artifacts.items():
            artifact = (root / str(relative)).resolve()
            try:
                artifact.relative_to(root.resolve())
            except ValueError:
                issues.append("REVIEW_EVIDENCE_PATH_ESCAPE")
                continue
            if artifact == path.resolve() or not artifact.is_file():
                issues.append(f"REVIEW_EVIDENCE_INVALID:{relative}")
            elif sha256_file(artifact) != expected_hash:
                issues.append(f"REVIEW_EVIDENCE_HASH_INVALID:{relative}")
    if filename == "scheduler-trial.json" and (
        value.get("provider") != "codex-local-automation"
        or not str(value.get("automation_id", "")).strip()
        or value.get("matching_active_automations") != 1
        or not str(value.get("project_id", "")).strip()
    ):
        issues.append("SCHEDULER_TASK_INVENTORY_INVALID")
    return {"status": "PASS" if not issues else "MISSING_OR_INVALID", "issues": issues}


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
        entry["archive_receipt_valid"] = _archive_receipt_valid(
            root, state, archive_receipt
        )
        entry["delivery_receipt_valid"] = _delivery_receipt_valid(
            root, state, delivery_receipt
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
    review_evidence = {}
    configured_reviews = policy.get("required_review_evidence", {})
    if isinstance(configured_reviews, list):
        configured_reviews = {str(filename): [] for filename in configured_reviews}
    if not isinstance(configured_reviews, dict):
        configured_reviews = {}
    for filename, required_checks in configured_reviews.items():
        review_evidence[str(filename)] = _review_file_evidence(
            root,
            str(filename),
            [str(check) for check in required_checks] if isinstance(required_checks, list) else [],
            expected_runtime_fingerprint,
        )
    ai = config.get("providers", {}).get("ai", {})
    provider_trial_valid, provider_trials = _provider_trial_evidence(
        root, expected_runtime_fingerprint
    )
    checks = {
        "synthetic_publication": bool(synthetic) if policy.get("require_synthetic_publication", True) else True,
        "manual_real_publication": bool(manual_real) if policy.get("require_manual_real_publication", True) else True,
        "consecutive_unattended_runs": bool(sequence),
        "verified_git_archive": bool(archived) if policy.get("require_verified_git_archive", True) else True,
        "whatsapp_delivery": bool(delivered) if policy.get("require_whatsapp_delivery", False) else True,
        "editorial_provider_proven": (
            ai.get("type") != "unconfigured"
            and ai.get("integration_test_status") == "PASS"
            and provider_trial_valid
        ),
        "review_evidence": bool(review_evidence) and all(
            value["status"] == "PASS" for value in review_evidence.values()
        ),
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
            "provider_trials": provider_trials,
        },
    }
