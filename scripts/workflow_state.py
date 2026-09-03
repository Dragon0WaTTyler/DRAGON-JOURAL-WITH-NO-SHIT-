"""Production-run state initialization and tested Scheduled Work invariants."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

STAGE_FIELDS = ("current_research", "deep_research", "editorial", "publishing", "cover")
ALLOWED_STAGE_VALUES = {"PENDING", "RUNNING", "COMPLETE", "BLOCKED", "FAILED"}

EDITORIAL_FILES = ("edition.md", "sources.json", "manifest.json")
PUBLICATION_SOURCE_FILES = ("edition.html", "print.css", "epub-content.xhtml")
PUBLICATION_REPORT = "publishing-report.json"
COVER_BRIEF = "cover-brief.json"

PDF_BINARY_STATE = "NOT_GENERATED_NO_RUNTIME"
EPUB_BINARY_STATE = "NOT_GENERATED_NO_RUNTIME"
BINARY_ARTIFACTS_STATE = "PENDING_MANUAL_CODEX_RENDER"
GITHUB_IMAGE_ARCHIVE_STATE = "UNSUPPORTED_BY_CONNECTOR"
COVER_BINARY_ARCHIVE_STATE = "PENDING_MANUAL_ARCHIVE"


def edition_relative_dir(edition_date: str) -> str:
    parsed = date.fromisoformat(edition_date)
    return f"editions/{parsed:%Y}/{parsed:%m}/{edition_date}"


def required_remote_paths(edition_date: str, stage: str) -> tuple[str, ...]:
    if stage == "current_research":
        return (f"daily-runs/{edition_date}/current-news.json",)
    if stage == "deep_research":
        return (f"daily-runs/{edition_date}/deep-features.json",)
    if stage == "editorial":
        base = edition_relative_dir(edition_date)
        return tuple(f"{base}/{name}" for name in EDITORIAL_FILES) + (
            f"daily-runs/{edition_date}/editorial-report.json",
        )
    if stage == "publishing":
        base = edition_relative_dir(edition_date)
        return tuple(f"{base}/{name}" for name in PUBLICATION_SOURCE_FILES) + (
            f"daily-runs/{edition_date}/{PUBLICATION_REPORT}",
        )
    if stage == "cover":
        return (f"daily-runs/{edition_date}/{COVER_BRIEF}",)
    raise ValueError(f"unknown workflow stage: {stage}")


def fresh_production_status(edition_date: str, *, last_updated: str | None = None) -> dict[str, Any]:
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
        "publication_source_package": "PENDING",
        "pdf_binary": PDF_BINARY_STATE,
        "epub_binary": EPUB_BINARY_STATE,
        "binary_artifacts": BINARY_ARTIFACTS_STATE,
        "ready_for_codex_rendering": False,
        "image_generation_status": "PENDING",
        "visual_qa_status": "PENDING",
        "github_image_archive": GITHUB_IMAGE_ARCHIVE_STATE,
        "cover_binary_archive": COVER_BINARY_ARCHIVE_STATE,
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


def _local_paths(directory: Path | None, names: Iterable[str]) -> set[str]:
    if directory is None:
        return set()
    return {
        name for name in names
        if (directory / name).is_file() and (directory / name).stat().st_size > 0
    }


def _report_gate_passed(report: Mapping[str, Any] | None) -> bool:
    if not report:
        return False
    status = str(report.get("status", report.get("validation_status", ""))).upper()
    if status not in {"PASS", "PASSED", "COMPLETE"}:
        return False
    for key in ("fact_check_status", "darija_status", "sources_resolve_status"):
        if key in report and str(report[key]).upper() not in {"PASS", "PASSED", "COMPLETE"}:
            return False
    if "arabic_script_count" in report and report.get("arabic_script_count") != 0:
        return False
    language = report.get("language")
    if isinstance(language, Mapping) and language.get("arabic_script_characters") not in (None, 0):
        return False
    return True


def validate_state(
    status: Mapping[str, Any],
    edition_date: str,
    *,
    edition_dir: Path | None = None,
    run_dir: Path | None = None,
    remote_paths: Iterable[str] = (),
    editorial_gates_passed: bool | None = None,
    publication_source_valid: bool | None = None,
    editorial_report: Mapping[str, Any] | None = None,
) -> list[str]:
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
        if status.get(field) not in ALLOWED_STAGE_VALUES:
            errors.append(f"{field} has invalid status {status.get(field)!r}")

    required_state_fields = (
        "publication_source_package", "pdf_binary", "epub_binary", "binary_artifacts",
        "ready_for_codex_rendering", "image_generation_status", "visual_qa_status",
        "github_image_archive", "cover_binary_archive",
    )
    for field in required_state_fields:
        if field not in status:
            errors.append(f"status missing required field {field}")

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
        arabic_count = status.get("arabic_script_count")
        if arabic_count is None and isinstance(editorial_report, Mapping):
            arabic_count = editorial_report.get("arabic_script_count")
            language = editorial_report.get("language")
            if arabic_count is None and isinstance(language, Mapping):
                arabic_count = language.get("arabic_script_characters")
        if arabic_count != 0:
            errors.append("editorial COMPLETE requires arabic_script_count == 0")
        if not gates_pass:
            errors.append("editorial COMPLETE requires passing editorial gates")

    if publishing in {"RUNNING", "COMPLETE"} and editorial != "COMPLETE":
        errors.append("publishing cannot be RUNNING or COMPLETE unless editorial is COMPLETE")
    if publishing == "COMPLETE":
        source_valid = publication_source_valid
        if source_valid is None:
            source_valid = status.get("publication_source_package") == "COMPLETE"
        if not source_valid:
            errors.append("publishing COMPLETE requires publication_source_package COMPLETE")
        missing_local = sorted(set(PUBLICATION_SOURCE_FILES) - _local_paths(edition_dir, PUBLICATION_SOURCE_FILES))
        if missing_local:
            errors.append("publishing COMPLETE requires local publication-source files: " + ", ".join(missing_local))
        if run_dir is not None and PUBLICATION_REPORT not in _local_paths(run_dir, (PUBLICATION_REPORT,)):
            errors.append("publishing COMPLETE requires local publishing-report.json")
        missing_remote = sorted(set(required_remote_paths(edition_date, "publishing")) - remote)
        if missing_remote:
            errors.append("publishing COMPLETE requires remote text read-back: " + ", ".join(missing_remote))
        expected = {
            "pdf_binary": PDF_BINARY_STATE,
            "epub_binary": EPUB_BINARY_STATE,
            "binary_artifacts": BINARY_ARTIFACTS_STATE,
        }
        for field, value in expected.items():
            if status.get(field) != value:
                errors.append(f"publishing COMPLETE requires {field} == {value}")
        if status.get("ready_for_codex_rendering") is not True:
            errors.append("publishing COMPLETE requires ready_for_codex_rendering == true")

    if cover in {"RUNNING", "COMPLETE"} and publishing != "COMPLETE":
        errors.append("cover cannot be RUNNING or COMPLETE unless publishing is COMPLETE")
    if cover == "COMPLETE":
        if run_dir is not None and COVER_BRIEF not in _local_paths(run_dir, (COVER_BRIEF,)):
            errors.append("cover COMPLETE requires local cover-brief.json")
        missing_remote = sorted(set(required_remote_paths(edition_date, "cover")) - remote)
        if missing_remote:
            errors.append("cover COMPLETE requires cover brief remote read-back: " + ", ".join(missing_remote))
        if status.get("image_generation_status") != "PASS":
            errors.append("cover COMPLETE requires image_generation_status == PASS")
        if status.get("visual_qa_status") != "PASS":
            errors.append("cover COMPLETE requires visual_qa_status == PASS")
        if status.get("github_image_archive") != GITHUB_IMAGE_ARCHIVE_STATE:
            errors.append("cover COMPLETE requires github_image_archive == UNSUPPORTED_BY_CONNECTOR")
        if status.get("cover_binary_archive") != COVER_BINARY_ARCHIVE_STATE:
            errors.append("cover COMPLETE requires cover_binary_archive == PENDING_MANUAL_ARCHIVE")

    if editorial in {"BLOCKED", "FAILED"}:
        if publishing == "COMPLETE":
            errors.append("blocked or failed editorial cannot leave publishing COMPLETE")
        if cover == "COMPLETE":
            errors.append("blocked or failed editorial cannot leave cover COMPLETE")

    if status.get("overall_status") == "COMPLETE":
        if any(status.get(field) != "COMPLETE" for field in STAGE_FIELDS):
            errors.append("overall_status COMPLETE requires every scheduled production stage COMPLETE")
        if errors:
            errors.append("overall_status COMPLETE is impossible with invalid scheduled prerequisites")
    return errors


def validate_report_consistency(
    status: Mapping[str, Any],
    edition_date: str,
    *,
    edition_dir: Path | None = None,
    run_dir: Path | None = None,
    editorial_report: Mapping[str, Any] | None = None,
    publishing_report: Mapping[str, Any] | None = None,
) -> list[str]:
    remote_paths: set[str] = set()
    for source in (status, editorial_report or {}, publishing_report or {}):
        read_back = source.get("remote_read_back") if isinstance(source, Mapping) else None
        if isinstance(read_back, Mapping):
            remote_paths.update(str(path) for path in read_back.get("paths", []) if isinstance(path, str))
        if isinstance(source, Mapping):
            remote_paths.update(str(path) for path in source.get("remote_read_back_paths", []) if isinstance(path, str))

    errors = validate_state(
        status,
        edition_date,
        edition_dir=edition_dir,
        run_dir=run_dir,
        remote_paths=remote_paths,
        editorial_report=editorial_report,
        editorial_gates_passed=status.get("editorial_gates_passed") if "editorial_gates_passed" in status else None,
        publication_source_valid=status.get("publication_source_package") == "COMPLETE",
    )

    if editorial_report and editorial_report.get("required_editorial_files_exist") == "PASS":
        missing_local = sorted(set(EDITORIAL_FILES) - _local_paths(edition_dir, EDITORIAL_FILES))
        missing_remote = sorted(set(required_remote_paths(edition_date, "editorial")) - remote_paths)
        if missing_local or missing_remote:
            errors.append("editorial report cannot claim required_editorial_files_exist PASS without canonical files and remote read-back")

    if publishing_report and publishing_report.get("github_text_persistence") == "PASS":
        needed = set(required_remote_paths(edition_date, "publishing"))
        if not needed.issubset(remote_paths):
            errors.append("publishing report cannot claim github_text_persistence PASS without exact source-package read-back")

    if status.get("publishing") == "COMPLETE" and publishing_report:
        if publishing_report.get("github_text_persistence") != "PASS":
            errors.append("publishing COMPLETE requires github_text_persistence PASS")
        for forbidden in ("github_binary_persistence", "pdf_binary_generated", "epub_binary_generated"):
            if str(publishing_report.get(forbidden, "")).upper() in {"PASS", "TRUE", "GENERATED"}:
                errors.append(f"Scheduled Publication Builder must not claim {forbidden}")

    return errors
