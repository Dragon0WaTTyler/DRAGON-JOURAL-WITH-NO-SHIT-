#!/usr/bin/env python3
"""Run the deterministic gates around a Cloud-edited newspaper edition.

Research and editorial writing remain Codex roles. This runner owns the
reproducible mechanics after those roles have written their packets and
reports: validate, render, validate again, and optionally persist to GitHub.
It deliberately refuses dirty worktrees, force pushes, enabled schedules, or
missing verification reports.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESEARCH_ROLES = (
    "ai",
    "history",
    "investigations",
    "literature-culture",
    "meknes",
    "morocco",
    "palestine",
    "science",
    "world",
)


def run(command: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run a command without exposing environment variables or credentials."""
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    if check and result.returncode:
        details = (result.stdout + result.stderr).strip()
        raise RuntimeError(f"command failed ({result.returncode}): {' '.join(command)}\n{details}")
    return result


def target(edition_date: str) -> Path:
    parsed = date.fromisoformat(edition_date)
    return ROOT / "editions" / f"{parsed:%Y}" / f"{parsed:%m}" / edition_date


def check_clean_worktree() -> None:
    result = run(["git", "status", "--porcelain=v1"])
    if result.stdout.strip():
        raise RuntimeError("working tree must be clean before starting the pipeline")


def check_schedule_disabled() -> None:
    import yaml

    config = yaml.safe_load((ROOT / "config/schedule.yaml").read_text(encoding="utf-8"))
    if config.get("enabled") is not False:
        raise RuntimeError("schedule.yaml must remain enabled: false for this runner")
    if config.get("hard_requirement") != "cloud-only":
        raise RuntimeError("schedule.yaml must declare hard_requirement: cloud-only")


def validate_packets(edition_date: str) -> int:
    packet_paths = [ROOT / "research" / edition_date / f"{role}.json" for role in RESEARCH_ROLES]
    missing = [str(path.relative_to(ROOT)) for path in packet_paths if not path.is_file()]
    if missing:
        raise RuntimeError("missing research packets: " + ", ".join(missing))
    for path in packet_paths:
        run([sys.executable, "scripts/validate_story_packet.py", str(path)])
    return len(packet_paths)


def validate_reports(edition_date: str) -> None:
    report_dir = ROOT / "research" / edition_date
    fact_path = report_dir / "fact-check-report.json"
    language_path = report_dir / "language-gate-report.json"
    for path in (fact_path, language_path):
        if not path.is_file():
            raise RuntimeError(f"missing sequential gate report: {path.relative_to(ROOT)}")
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"invalid gate report: {path.relative_to(ROOT)}: {exc}") from exc
        if not isinstance(report, dict) or report.get("status") != "passed":
            raise RuntimeError(f"blocking gate did not pass: {path.relative_to(ROOT)}")
        if report.get("blocking_issues"):
            raise RuntimeError(f"blocking issues remain: {path.relative_to(ROOT)}")
    language = json.loads(language_path.read_text(encoding="utf-8"))
    if language.get("arabic_script_characters") != 0:
        raise RuntimeError("Darija gate reports Arabic-script characters")
    if language.get("full_english_or_french_paragraphs") != 0:
        raise RuntimeError("Darija gate reports full English/French paragraphs")
    if language.get("meaning_changed") is True:
        raise RuntimeError("Darija gate reports changed meaning")


def validate_edition(edition_date: str) -> None:
    run([
        sys.executable,
        "scripts/validate_edition.py",
        "--date",
        edition_date,
        "--mode",
        "preproduction",
    ])


def render(edition_date: str) -> None:
    run([sys.executable, "scripts/publish_preproduction_edition.py", "--date", edition_date])


def git_add(edition_date: str, extra_paths: list[str]) -> None:
    parsed = date.fromisoformat(edition_date)
    paths = [
        f"editions/{parsed:%Y}/{parsed:%m}/{edition_date}",
        f"research/{edition_date}",
        "README.md",
        *extra_paths,
    ]
    run(["git", "add", "--", *paths])
    if not run(["git", "diff", "--cached", "--quiet"], check=False).returncode == 1:
        raise RuntimeError("pipeline produced no staged changes")


def commit_and_push(message: str) -> str:
    run(["git", "commit", "-m", message])
    local_sha = run(["git", "rev-parse", "HEAD"]).stdout.strip()
    run(["git", "push", "origin", f"HEAD:refs/heads/main"])
    remote_sha = run(["git", "ls-remote", "origin", "refs/heads/main"]).stdout.split()[0]
    if local_sha != remote_sha:
        raise RuntimeError(f"remote SHA mismatch: local {local_sha}, remote {remote_sha}")
    return local_sha


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True, help="edition date in YYYY-MM-DD form")
    parser.add_argument("--dry-run", action="store_true", help="run all content gates without rendering or GitHub writes")
    parser.add_argument("--commit-message", help="commit subject; defaults to preproduction: YYYY-MM-DD")
    parser.add_argument("--stage-path", action="append", default=[], help="additional repository path to stage, repeatable")
    args = parser.parse_args()

    try:
        date.fromisoformat(args.date)
        if not target(args.date).is_dir():
            raise RuntimeError(f"edition directory does not exist: {target(args.date).relative_to(ROOT)}")
        check_clean_worktree()
        check_schedule_disabled()
        run([sys.executable, "scripts/validate_configuration.py"])
        packet_count = validate_packets(args.date)
        validate_reports(args.date)
        if args.dry_run:
            validate_edition(args.date)
            print(f"PIPELINE DRY-RUN PASS: {args.date}; {packet_count} research packets and sequential gates passed")
            return 0

        render(args.date)
        validate_edition(args.date)
        git_add(args.date, args.stage_path)
        sha = commit_and_push(args.commit_message or f"preproduction: {args.date}")
        print(f"PIPELINE PASS: {args.date}; persisted commit {sha}")
        return 0
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"PIPELINE FAIL: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
