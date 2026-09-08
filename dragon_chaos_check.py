#!/usr/bin/env python3
"""Run the required V5 failure-injection suite and persist reviewable evidence."""

from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Callable
from uuid import uuid4
from xml.etree import ElementTree
from zoneinfo import ZoneInfo

from dragon.config import load_local_config
from dragon.state import atomic_write_json, runtime_fingerprint, sha256_file, source_revision


ROOT = Path(__file__).resolve().parent
TEST_TARGETS = (
    "tests/test_v5_chaos.py",
    "tests/test_v5_recovery.py",
    "tests/test_v5_orchestrator.py",
    "tests/test_v5_lock_watchdog.py",
    "tests/test_v5_editorial_provider.py",
)
SCENARIO_MARKERS = {
    "process_interruption": "test_abrupt_process_interrupt_leaves_running_state",
    "network_timeout": "test_orchestrator_retries_transient_stage_only_until_success",
    "epub_corruption": "test_corrupt_epub_is_rebuilt_without_touching_valid_pdf",
    "pdf_failure": "[pdf]",
    "git_push_failure": "test_archive_failure_preserves_local_publication",
    "whatsapp_failure": "[whatsapp_delivery]",
    "stale_lock": "test_live_stale_owner_is_never_duplicated",
    "invalid_article_output": "test_provider_retries_invalid_article_output_once_with_exact_feedback",
}
Runner = Callable[..., subprocess.CompletedProcess[str]]


def run_check(root: Path = ROOT, runner: Runner = subprocess.run) -> dict:
    root = root.resolve()
    config = load_local_config(root)
    timezone = str(config["timezone"])
    output_dir = root / "acceptance" / "machine" / "failure-injection"
    output_dir.mkdir(parents=True, exist_ok=True)
    junit_path = output_dir / "junit.xml"
    temporary = output_dir / f".junit.{uuid4().hex}.tmp"
    command = [
        sys.executable,
        "-m",
        "pytest",
        *TEST_TARGETS,
        "-q",
        f"--junitxml={temporary}",
    ]
    started_at = datetime.now(ZoneInfo(timezone))
    try:
        result = runner(
            command,
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=900,
        )
        passed_names: list[str] = []
        total = 0
        if temporary.is_file():
            document = ElementTree.parse(temporary)
            cases = list(document.iter("testcase"))
            total = len(cases)
            passed_names = [
                f"{case.get('classname', '')}::{case.get('name', '')}"
                for case in cases
                if not any(case.find(tag) is not None for tag in ("failure", "error", "skipped"))
            ]
            os.replace(temporary, junit_path)
        scenario_results = {
            scenario: "PASS" if any(marker in name for name in passed_names) else "FAIL"
            for scenario, marker in SCENARIO_MARKERS.items()
        }
        status = (
            "PASS"
            if result.returncode == 0
            and total > 0
            and all(value == "PASS" for value in scenario_results.values())
            else "FAIL"
        )
        ended_at = datetime.now(ZoneInfo(timezone))
        receipt = {
            "schema_version": 5,
            "status": status,
            "started_at": started_at.isoformat(),
            "ended_at": ended_at.isoformat(),
            "duration_seconds": round((ended_at - started_at).total_seconds(), 3),
            "runtime_fingerprint": runtime_fingerprint(root),
            "source_git_revision": source_revision(root),
            "command": ["python", "-m", "pytest", *TEST_TARGETS, "-q", "--junitxml=<temporary>"],
            "exit_code": result.returncode,
            "tests_observed": total,
            "scenarios": scenario_results,
            "junit": (
                {
                    "path": str(junit_path.relative_to(root)).replace("\\", "/"),
                    "sha256": sha256_file(junit_path),
                }
                if junit_path.is_file()
                else None
            ),
            "output_tail": (result.stdout + "\n" + result.stderr)[-4000:],
            "human_review_status": "NOT_REVIEWED",
        }
        atomic_write_json(output_dir / "receipt.json", receipt)
        return receipt
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    receipt = run_check()
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0 if receipt["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
