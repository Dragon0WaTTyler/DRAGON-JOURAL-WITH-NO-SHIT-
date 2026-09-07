"""Redacted incident packet creation for exhausted or unsafe failures."""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from dragon.redaction import redact, redact_text
from dragon.state import atomic_write_json, source_revision


class IncidentWriter:
    def __init__(self, root: Path, run_dir: Path, timezone: str):
        self.root = root.resolve()
        self.run_dir = run_dir.resolve()
        self.timezone = timezone

    def create(
        self,
        *,
        stage: str,
        state: dict[str, Any],
        error_code: str,
        error_detail: str,
        traceback_text: str | None = None,
        attempted_fixes: Iterable[dict[str, Any]] = (),
        test_results: str = "NOT_RUN",
        relevant_files: Iterable[Path] = (),
    ) -> Path:
        recovery = self.run_dir / "recovery"
        recovery.mkdir(parents=True, exist_ok=True)
        number = 1
        while (recovery / f"incident-{number:03d}").exists():
            number += 1
        target = recovery / f"incident-{number:03d}"
        target.mkdir()

        safe_files: list[str] = []
        for value in relevant_files:
            resolved = value.resolve()
            try:
                relative = resolved.relative_to(self.root)
            except ValueError:
                continue
            safe_files.append(str(relative).replace("\\", "/"))

        timestamp = datetime.now(ZoneInfo(self.timezone)).isoformat()
        packet = {
            "schema_version": 5,
            "incident_id": f"incident-{number:03d}",
            "created_at": timestamp,
            "date": state.get("date"),
            "run_id": state.get("run_id"),
            "stage": stage,
            "error_code": error_code,
            "error_detail": redact_text(error_detail),
            "source_git_revision": source_revision(self.root),
            "stage_state": redact(state.get("stages", {}).get(stage, {})),
            "relevant_files": sorted(set(safe_files)),
            "secrets_redacted": True,
        }
        atomic_write_json(target / "incident.json", packet)
        atomic_write_json(target / "attempted-fixes.json", {"attempts": redact(list(attempted_fixes))})
        atomic_write_json(target / "relevant-files.json", {"paths": packet["relevant_files"]})
        (target / "traceback.txt").write_text(
            redact_text(traceback_text or "NOT_AVAILABLE") + "\n", encoding="utf-8"
        )
        (target / "test-results.txt").write_text(
            redact_text(test_results) + "\n", encoding="utf-8"
        )
        (target / "context.md").write_text(
            "# DRAGON production incident\n\n"
            f"- Stage: `{stage}`\n"
            f"- Error: `{error_code}`\n"
            f"- Created: `{timestamp}`\n"
            f"- Source revision: `{packet['source_git_revision'] or 'UNKNOWN'}`\n\n"
            "Inspect `incident.json`, `traceback.txt`, `attempted-fixes.json`, "
            "`test-results.txt`, and `relevant-files.json`. Secrets are redacted.\n",
            encoding="utf-8",
        )
        return target
