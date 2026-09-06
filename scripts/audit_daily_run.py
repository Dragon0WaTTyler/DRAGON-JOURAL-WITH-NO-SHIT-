#!/usr/bin/env python3
"""Fail visibly when the scheduled daily newspaper did not finish on time."""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
TZ = ZoneInfo("Africa/Casablanca")
REQUIRED_STAGES = ("current_research", "deep_research", "editorial", "cover", "publishing")


def audit(root: Path, edition_date: str, *, after_deadline: bool = True) -> list[str]:
    """Return actionable completion errors for one daily edition."""
    if not after_deadline:
        return []
    run = root / "daily-runs" / edition_date
    status_path = run / "status.json"
    if not status_path.is_file():
        return [f"MISSING_DAILY_STATUS: {status_path.relative_to(root).as_posix()}"]
    try:
        status = json.loads(status_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"INVALID_DAILY_STATUS: {exc}"]
    errors = []
    if status.get("date") != edition_date or status.get("timezone") != "Africa/Casablanca":
        errors.append("STATUS_DATE_OR_TIMEZONE_MISMATCH")
    for stage in REQUIRED_STAGES:
        if status.get(stage) != "COMPLETE":
            detail = status.get(f"{stage}_blocking_reason") or status.get("blocking_reason") or "no reason recorded"
            errors.append(f"{stage.upper()}_NOT_COMPLETE: {detail}")
    if status.get("final_publication_status") != "COMPLETE" or status.get("overall_status") != "COMPLETE":
        errors.append("FINAL_PUBLICATION_NOT_COMPLETE")
    if status.get("binary_artifacts") != "COMPLETE" or status.get("github_binary_read_back") != "PASS":
        errors.append("BINARY_ARCHIVE_NOT_VERIFIED")
    paths = status.get("final_binary_paths")
    if not isinstance(paths, dict) or not all(isinstance(paths.get(kind), str) for kind in ("pdf", "epub")):
        errors.append("MISSING_FINAL_BINARY_PATHS")
    else:
        for kind in ("pdf", "epub"):
            if not (root / paths[kind]).is_file():
                errors.append(f"MISSING_FINAL_{kind.upper()}: {paths[kind]}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date")
    parser.add_argument("--deadline-hour", type=int, default=11)
    args = parser.parse_args()
    now = datetime.now(TZ)
    edition_date = args.date or now.date().isoformat()
    errors = audit(ROOT, edition_date, after_deadline=now.hour >= args.deadline_hour or bool(args.date))
    if errors:
        print("DRAGON DAILY COMPLETION FAIL")
        print("\n".join(errors))
        return 1
    print(f"DRAGON DAILY COMPLETION PASS: {edition_date}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
