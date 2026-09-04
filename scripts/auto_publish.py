#!/usr/bin/env python3
"""Idempotent binary-only publisher. No research, model calls, or API keys."""
from __future__ import annotations
import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.publication_inputs import canonical_date, validate_inputs
from scripts.publication_renderer import read_json, write_json, render

ROOT = Path(__file__).resolve().parents[1]

def git(root, *args, binary=False):
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=not binary, timeout=120)
    if result.returncode:
        raise RuntimeError("git " + args[0] + " failed; no completion recorded")
    return result.stdout if binary else result.stdout.strip()

def verify_remote(root, hashes, ref):
    if not hashes:
        raise ValueError("empty remote read-back set")
    for path, expected in hashes.items():
        data = git(root, "show", f"{ref}:{path}", binary=True)
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError(f"remote read-back mismatch: {path}")

def candidates(root, now):
    # Recovery window catches a package that crosses Casablanca midnight.
    for age in (1, 0):
        day = (now.date() - timedelta(days=age)).isoformat()
        status_path = root / "daily-runs" / day / "status.json"
        if status_path.is_file():
            status = read_json(status_path)
            if all(status.get(k) == "COMPLETE" for k in ("current_research", "deep_research", "editorial", "cover", "publishing")):
                yield day

def commit_push(root, paths, message, branch):
    git(root, "add", "--", *paths)
    if git(root, "diff", "--cached", "--name-only"):
        git(root, "commit", "-m", message)
        git(root, "push", "origin", f"HEAD:refs/heads/{branch}")
    git(root, "fetch", "origin", branch)
    # Concurrent writes are never force-pushed, merged over, or silently ignored.
    if git(root, "rev-parse", "HEAD") != git(root, "rev-parse", "FETCH_HEAD"):
        raise RuntimeError("remote changed during publication; next scheduled run will retry")
    return git(root, "rev-parse", "FETCH_HEAD")

def publish(root, day, branch="main"):
    canonical_date(day)
    edition, cover, inputs = validate_inputs(root, day)
    run = root / "daily-runs" / day
    report_path = run / "binary-render-report.json"
    git(root, "fetch", "origin", branch)
    remote = git(root, "rev-parse", "FETCH_HEAD")
    if remote != git(root, "rev-parse", "HEAD"):
        raise RuntimeError("checkout is stale; retry from latest branch")
    if report_path.exists():
        prior = read_json(report_path)
        if prior.get("input_sha256") == inputs and prior.get("final_publication_status") == "COMPLETE":
            verify_remote(root, inputs | prior["binary_sha256"], remote)
            return "ALREADY_PUBLISHED"
    receipt = render(root, day)
    binary_paths = list(receipt["binary_sha256"])
    receipt_path = str(report_path.relative_to(root)).replace("\\", "/")
    phase_one = binary_paths + [receipt_path]
    for path in (edition / "manifest.json", run / "publishing-report.json", run / "status.json"):
        value = read_json(path)
        value.update(final_publication_status="PENDING", overall_status="PENDING", binary_artifacts="PENDING_REMOTE_READBACK", github_binary_read_back="PENDING", ready_for_codex_rendering=False)
        write_json(path, value)
        phase_one.append(str(path.relative_to(root)).replace("\\", "/"))
    # Phase 1 archives binaries with a PENDING receipt, not a publication claim.
    binary_commit = commit_push(root, phase_one, f"Archive DRAGON binaries for {day}", branch)
    validate_inputs(root, day)
    verify_remote(root, receipt["input_sha256"] | receipt["binary_sha256"], binary_commit)
    final_fields = {"pdf_binary": "GENERATED_VALIDATED", "epub_binary": "GENERATED_VALIDATED", "binary_artifacts": "COMPLETE", "ready_for_codex_rendering": False, "final_publication_status": "COMPLETE", "overall_status": "COMPLETE", "github_binary_read_back": "PASS", "binary_archive_commit": binary_commit, "binary_sha256": receipt["binary_sha256"], "final_binary_paths": {"pdf": binary_paths[0], "epub": binary_paths[1]}, "publication_completed_at": datetime.now(ZoneInfo("Africa/Casablanca")).isoformat()}
    changed = [receipt_path]
    for path in (edition / "manifest.json", run / "publishing-report.json", run / "status.json"):
        value = read_json(path)
        value.update(final_fields)
        write_json(path, value)
        changed.append(str(path.relative_to(root)).replace("\\", "/"))
    receipt.update(final_fields)
    write_json(report_path, receipt)
    # One append/update keyed by date: retries cannot duplicate published memory.
    memory_path = root / "memory" / "publication-ledger.json"
    ledger = read_json(memory_path) if memory_path.exists() else {}
    editorial = read_json(run / "editorial-report.json")
    ledger[day] = {"status": "PUBLISHED", "binary_archive_commit": binary_commit, "topics": {key: editorial[key] for key in ("history_topic_id", "literature_topic_id", "science_topic_id", "lead_story_id") if editorial.get(key)}}
    write_json(memory_path, ledger)
    changed.append("memory/publication-ledger.json")
    final_commit = commit_push(root, changed, f"Verify DRAGON publication for {day}", branch)
    from scripts.publication_inputs import digest
    verify_remote(root, {path: digest(root / path) for path in changed}, final_commit)
    return "PUBLISHED"

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date")
    parser.add_argument("--check", action="store_true", help="Read-only ready-date discovery")
    parser.add_argument("--branch", default="main")
    args = parser.parse_args()
    now = datetime.now(ZoneInfo("Africa/Casablanca"))
    days = [canonical_date(args.date)] if args.date else list(candidates(ROOT, now))
    if any(day > now.date().isoformat() for day in days):
        raise ValueError("future editions cannot be published")
    if args.check:
        print(json.dumps(days))
        return
    if git(ROOT, "status", "--porcelain"):
        raise RuntimeError("publisher requires a clean checkout")
    results, failed = {}, False
    for day in days:
        try:
            results[day] = publish(ROOT, day, args.branch)
        except Exception as exc:
            results[day] = {"status": "FAILED", "reason": str(exc)}
            failed = True
            # Do not publish another edition on top of unpushed/partial state.
            break
    print(json.dumps(results, indent=2))
    if failed:
        raise SystemExit(1)

if __name__ == "__main__":
    main()
