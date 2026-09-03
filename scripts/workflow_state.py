"""Production-run state initialization and persistence invariants.

This module treats a connected GitHub read-back as the only evidence of remote
persistence. Local/runtime files are useful for validation, but never replace
that read-back.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping


STAGE_FIELDS = ("current_research", "deep_research", "editorial", "publishing", "cover")
ALLOWED_STAGE_VALUES = {"PENDING", "RUNNING", "COMPLETE", "BLOCKED", "FAILED"}
EDITORIAL_FILES = ("edition.md", "sources.json", "manifest.json")
PUBLISHING_FILES = EDITORIAL_FILES + ("edition.pdf", "edition.epub")
COVER_FILES = ("cover.webp",)


def edition_relative_dir(edition_date: str) -> str:
    parsed = date.fromisoformat(edition_date)
    return f"editions/{parsed:%Y}/{parsed:%m}/{edition_date}"


def required_remote_paths(edition_date: str, stage: str) -> tuple[str, ...]:
    if stage == "current_research":
        return (f"daily-runs/{edition_date}/current-news.json",)
    if stage == "deep_research":
        return (f"daily-runs/{edition_date}/deep-features.json",)
    if stage == "editorial":
        return tuple(f"{edition_relative_dir(edition_date)}/{name}" for name in EDITORIAL_FILES)
    if stage == "publishing":
        return tuple(f"{edition_relative_dir(edition_date)}/{name}" for name in PUBLISHING_FILES)
    if stage == "cover":
        return tuple(f"{edition_relative_dir(edition_date)}/{name}" for name in COVER_FILES)
    raise ValueError(f"unknown workflow stage: {stage}")


def fresh_production_status(edition_date: str, *, last_updated: str | None = None) -> dict[str, Any]:
    """Return a clean status; previous same-date state is intentionally ignored."""
    date.fromisoformat(edition_date)
    return {
        "date": edition_date,
        "timezone": "Africa/Casablanca",
        "current_research": "PENDING",
        "deep_research": "PENDING",
        "editorial": "PENDING",
        "publishing": "PENDING",
        "cover": "PENDING",
        "overall_status": "PENDING",
        "last_updated": last_updated or datetime.now().astimezone().isoformat(timespec="seconds"),
        "blocking_reason": None,
    }


def initialize_production_run(
    status_path: Path,
    edition_date: str,
    *,
    resume: bool = False,
    remote_paths: Iterable[str] = (),
    last_updated: str | None = None,
) -> dict[str, Any]:
    """Create fresh state, or explicitly resume only after remote validation."""
    if not resume:
        status = fresh_production_status(edition_date, last_updated=last_updated)
    else:
        existing = json.loads(status_path.read_text(encoding="utf-8"))
        root = status_path.parents[2]
        parsed = date.fromisoformat(edition_date)
        edition_dir = root / "editions" / f"{parsed:%Y}" / f"{parsed:%m}" / edition_date
        errors = validate_state(existing, edition_date, edition_dir=edition_dir, remote_paths=set(remote_paths))
        if errors:
            raise ValueError("explicit resume refused: " + "; ".join(errors))
        status = dict(existing)
        status["last_updated"] = last_updated or datetime.now().astimezone().isoformat(timespec="seconds")
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(json.dumps(status, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return status


def _local_paths(edition_dir: Path | None, names: Iterable[str]) -> set[str]:
    if edition_dir is None:
        return set()
    return {name for name in names if (edition_dir / name).is_file() and (edition_dir / name).stat().st_size > 0}


def _report_gate_passed(report: Mapping[str, Any] | None) -> bool:
    if not report:
        return False
    status = str(report.get("status", "")).upper()
    if status not in {"PASS", "PASSED", "COMPLETE"}:
        return False
    for key in ("fact_check_status", "darija_status", "sources_resolve_status", "internal_backend_reader_facing_prose"):
        if key in report and str(report[key]).upper() not in {"PASS", "PASSED", "COMPLETE"}:
            return False
    hard_minimums = report.get("hard_minimums")
    if isinstance(hard_minimums, Mapping):
        if any(str(item.get("status", "")).upper() not in {"PASS", "PASSED", "PASS_WITH_THIN_NEWS_EXCEPTION"} for item in hard_minimums.values() if isinstance(item, Mapping)):
            return False
    return True


def validate_state(
    status: Mapping[str, Any],
    edition_date: str,
    *,
    edition_dir: Path | None = None,
    remote_paths: Iterable[str] = (),
    editorial_gates_passed: bool | None = None,
    publishing_artifacts_valid: bool | None = None,
    cover_artifact_valid: bool | None = None,
    editorial_report: Mapping[str, Any] | None = None,
) -> list[str]:
    """Validate stage dependencies and completion claims for one production run."""
    errors: list[str] = []
    try:
        date.fromisoformat(edition_date)
    except ValueError:
        return [f"invalid edition date: {edition_date}"]
    if status.get("date") != edition_date:
        errors.append("status date does not match the production run")
    if status.get("timezone") != "Africa/Casablanca":
        errors.append("status timezone must be Africa/Casablanca")
    for field in STAGE_FIELDS + ("overall_status",):
        value = status.get(field)
        if value not in ALLOWED_STAGE_VALUES:
            errors.append(f"{field} has invalid status {value!r}")

    remote = set(remote_paths)
    current = status.get("current_research")
    deep = status.get("deep_research")
    editorial = status.get("editorial")
    publishing = status.get("publishing")
    cover = status.get("cover")

    gates_pass = editorial_gates_passed
    if gates_pass is None:
        gates_pass = status.get("editorial_gates_passed") is True or _report_gate_passed(editorial_report)
    if editorial == "COMPLETE":
        if current != "COMPLETE" or deep != "COMPLETE":
            errors.append("editorial COMPLETE requires current_research and deep_research COMPLETE")
        missing_local = sorted(set(EDITORIAL_FILES) - _local_paths(edition_dir, EDITORIAL_FILES))
        if missing_local:
            errors.append("editorial COMPLETE requires local canonical files: " + ", ".join(missing_local))
        missing_remote = sorted(set(required_remote_paths(edition_date, "editorial")) - remote)
        if missing_remote:
            errors.append("editorial COMPLETE requires remote read-back: " + ", ".join(missing_remote))
        if not gates_pass:
            errors.append("editorial COMPLETE requires passing editorial gates")

    if publishing in {"RUNNING", "COMPLETE"} and editorial != "COMPLETE":
        errors.append("publishing cannot be RUNNING or COMPLETE unless editorial is COMPLETE")
    if publishing == "COMPLETE":
        valid = publishing_artifacts_valid if publishing_artifacts_valid is not None else status.get("publishing_artifacts_valid") is True
        missing_local = sorted(set(PUBLISHING_FILES) - _local_paths(edition_dir, PUBLISHING_FILES))
        if missing_local:
            errors.append("publishing COMPLETE requires local artifacts: " + ", ".join(missing_local))
        missing_remote = sorted(set(required_remote_paths(edition_date, "publishing")) - remote)
        if missing_remote:
            errors.append("publishing COMPLETE requires remote read-back: " + ", ".join(missing_remote))
        if not valid:
            errors.append("publishing COMPLETE requires passing artifact validation")

    if cover == "COMPLETE" and editorial != "COMPLETE":
        errors.append("cover cannot be COMPLETE unless editorial is COMPLETE")
    if cover == "COMPLETE":
        valid = cover_artifact_valid if cover_artifact_valid is not None else status.get("cover_artifact_valid") is True
        missing_local = sorted(set(COVER_FILES) - _local_paths(edition_dir, COVER_FILES))
        if missing_local:
            errors.append("cover COMPLETE requires local artifact: " + ", ".join(missing_local))
        missing_remote = sorted(set(required_remote_paths(edition_date, "cover")) - remote)
        if missing_remote:
            errors.append("cover COMPLETE requires remote read-back: " + ", ".join(missing_remote))
        if not valid:
            errors.append("cover COMPLETE requires passing cover validation")

    if editorial in {"BLOCKED", "FAILED"}:
        if publishing == "COMPLETE":
            errors.append("blocked or failed editorial cannot leave publishing COMPLETE")
        if cover == "COMPLETE":
            errors.append("blocked or failed editorial cannot leave cover COMPLETE")

    if status.get("overall_status") == "COMPLETE":
        if any(status.get(field) != "COMPLETE" for field in STAGE_FIELDS):
            errors.append("overall_status COMPLETE requires every production stage COMPLETE")
        if errors:
            errors.append("overall_status COMPLETE is impossible with invalid prerequisites")
    return errors


def validate_report_consistency(
    status: Mapping[str, Any],
    edition_date: str,
    *,
    edition_dir: Path | None = None,
    editorial_report: Mapping[str, Any] | None = None,
    publishing_report: Mapping[str, Any] | None = None,
) -> list[str]:
    """Reject reports that claim PASS from local/runtime existence alone."""
    remote_paths: set[str] = set()
    status_read_back = status.get("remote_read_back")
    if isinstance(status_read_back, Mapping):
        remote_paths.update(str(path) for path in status_read_back.get("paths", []) if isinstance(path, str))
    remote_paths.update(str(path) for path in status.get("remote_read_back_paths", []) if isinstance(path, str))
    for report in (editorial_report, publishing_report):
        if not isinstance(report, Mapping):
            continue
        read_back = report.get("remote_read_back")
        if isinstance(read_back, Mapping):
            remote_paths.update(str(path) for path in read_back.get("paths", []) if isinstance(path, str))
        remote_paths.update(str(path) for path in report.get("remote_read_back_paths", []) if isinstance(path, str))

    errors = validate_state(
        status,
        edition_date,
        edition_dir=edition_dir,
        remote_paths=remote_paths,
        editorial_report=editorial_report,
        editorial_gates_passed=status.get("editorial_gates_passed") if "editorial_gates_passed" in status else None,
        publishing_artifacts_valid=status.get("publishing_artifacts_valid") if "publishing_artifacts_valid" in status else None,
        cover_artifact_valid=status.get("cover_artifact_valid") if "cover_artifact_valid" in status else None,
    )
    canonical_remote = set(required_remote_paths(edition_date, "editorial"))
    if editorial_report and editorial_report.get("required_editorial_files_exist") == "PASS":
        missing_local = sorted(set(EDITORIAL_FILES) - _local_paths(edition_dir, EDITORIAL_FILES))
        missing_remote = sorted(canonical_remote - remote_paths)
        if missing_local or missing_remote:
            errors.append("editorial report cannot claim required_editorial_files_exist PASS without local and remote canonical files")
    if publishing_report and publishing_report.get("github_text_persistence") == "PASS":
        if not canonical_remote.issubset(remote_paths):
            errors.append("publishing report cannot claim github_text_persistence PASS without exact remote read-back")
    if status.get("editorial") in {"BLOCKED", "FAILED"} and editorial_report and str(editorial_report.get("status", "")).upper() in {"PASS", "PASSED", "COMPLETE"}:
        errors.append("editorial report status contradicts blocked/failed workflow state")
    if status.get("publishing") == "COMPLETE" and publishing_report:
        if publishing_report.get("github_text_persistence") != "PASS":
            errors.append("publishing COMPLETE requires github_text_persistence PASS")
        if publishing_report.get("github_binary_persistence") != "PASS":
            errors.append("publishing COMPLETE requires binary persistence PASS")
    if status.get("cover") == "COMPLETE" and publishing_report and publishing_report.get("github_binary_persistence") != "PASS":
        errors.append("cover COMPLETE requires a recorded cover persistence result")
    if status.get("publishing") == "COMPLETE":
        for report in (status, publishing_report or {}):
            for field in ("binary_artifacts", "cover_binary_archive"):
                if field in report and report.get(field) not in {"PASS", "PASSED", "COMPLETE"}:
                    errors.append(f"{field} cannot be pending when publishing is COMPLETE")
    return errors
