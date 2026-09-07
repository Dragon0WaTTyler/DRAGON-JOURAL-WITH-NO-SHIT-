"""Durable state model and atomic persistence for DRAGON V5."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any, Iterable
from uuid import uuid4
from zoneinfo import ZoneInfo


STAGE_STATES = {"PENDING", "RUNNING", "COMPLETE", "FAILED", "BLOCKED", "DEGRADED"}
FINAL_STATES = {"PENDING", "COMPLETE", "FAILED", "BLOCKED", "DEGRADED"}
RUN_SUBDIRECTORIES = (
    "logs",
    "research",
    "articles",
    "editorial",
    "factcheck",
    "qa",
    "recovery",
)


def now_iso(timezone: str) -> str:
    return datetime.now(ZoneInfo(timezone)).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_revision(root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() or None


def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    """Write JSON using same-directory replace and retain one previous-good copy."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    backup = path.with_suffix(path.suffix + ".bak")
    # Stage mapping order is part of the schema and must survive persistence.
    payload = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        # Prove the temporary file is readable before preserving/replacing state.
        json.loads(temporary.read_text(encoding="utf-8"))
        if path.exists():
            shutil.copy2(path, backup)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def stage_record(name: str, prerequisites: Iterable[str]) -> dict[str, Any]:
    return {
        "name": name,
        "prerequisites": list(prerequisites),
        "inputs": [],
        "outputs": [],
        "status": "PENDING",
        "started_at": None,
        "ended_at": None,
        "attempt_count": 0,
        "error_code": None,
        "error_detail": None,
        "artifact_hashes": {},
        "recovery_history": [],
    }


def new_state(
    *,
    edition_date: str,
    timezone: str,
    stages: list[str],
    root: Path,
) -> dict[str, Any]:
    timestamp = now_iso(timezone)
    records: dict[str, Any] = {}
    for index, name in enumerate(stages):
        records[name] = stage_record(name, stages[index - 1 : index] if index else [])
    return {
        "schema_version": 5,
        "date": edition_date,
        "timezone": timezone,
        "run_id": str(uuid4()),
        "source_git_revision": source_revision(root),
        "started_at": timestamp,
        "updated_at": timestamp,
        "last_successful_checkpoint": None,
        "failure_history": [],
        "output_paths": {},
        "hashes": {},
        "publication_status": "PENDING",
        "archive_status": "PENDING",
        "delivery_status": "PENDING",
        "stages": records,
    }


def validate_state(value: dict[str, Any], expected_stages: Iterable[str]) -> list[str]:
    issues: list[str] = []
    if value.get("schema_version") != 5:
        issues.append("STATE_SCHEMA_INVALID")
    records = value.get("stages")
    if not isinstance(records, dict):
        return issues + ["STATE_STAGES_INVALID"]
    expected = list(expected_stages)
    if list(records) != expected:
        issues.append("STATE_STAGE_ORDER_INVALID")
    for name in expected:
        record = records.get(name)
        if not isinstance(record, dict):
            issues.append(f"STATE_STAGE_MISSING:{name}")
            continue
        if record.get("status") not in STAGE_STATES:
            issues.append(f"STATE_STAGE_STATUS_INVALID:{name}")
        if not isinstance(record.get("attempt_count"), int) or record["attempt_count"] < 0:
            issues.append(f"STATE_STAGE_ATTEMPTS_INVALID:{name}")
    for field in ("publication_status", "archive_status", "delivery_status"):
        if value.get(field) not in FINAL_STATES:
            issues.append(f"STATE_FINAL_STATUS_INVALID:{field}")
    return issues


class StateStore:
    def __init__(self, root: Path, edition_date: str, timezone: str, stages: list[str]):
        self.root = root.resolve()
        self.edition_date = edition_date
        self.timezone = timezone
        self.stages = stages
        self.run_dir = self.root / "daily-runs" / edition_date
        self.path = self.run_dir / "state.json"
        self.backup_path = self.run_dir / "state.json.bak"

    def ensure_directories(self) -> None:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        for name in RUN_SUBDIRECTORIES:
            (self.run_dir / name).mkdir(exist_ok=True)

    def initialize(self) -> dict[str, Any]:
        self.ensure_directories()
        if self.path.exists():
            return self.load()
        value = new_state(
            edition_date=self.edition_date,
            timezone=self.timezone,
            stages=self.stages,
            root=self.root,
        )
        legacy = self.run_dir / "status.json"
        if legacy.exists():
            value["legacy_status"] = {
                "path": str(legacy.relative_to(self.root)).replace("\\", "/"),
                "sha256": sha256_file(legacy),
                "imported_as_checkpoint": False,
            }
        self.save(value)
        return value

    def load(self) -> dict[str, Any]:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            issues = validate_state(value, self.stages)
            if issues:
                raise ValueError(", ".join(issues))
            return value
        except (OSError, json.JSONDecodeError, ValueError) as primary:
            if not self.backup_path.exists():
                raise ValueError(f"STATE_CORRUPT: {self.path}: {primary}") from primary
            try:
                recovered = json.loads(self.backup_path.read_text(encoding="utf-8"))
                issues = validate_state(recovered, self.stages)
                if issues:
                    raise ValueError(", ".join(issues))
            except (OSError, json.JSONDecodeError, ValueError) as backup:
                raise ValueError(
                    f"STATE_AND_BACKUP_CORRUPT: {self.path}: {primary}; {backup}"
                ) from backup
            quarantine = self.path.with_name("state.json.corrupt")
            suffix = 1
            while quarantine.exists():
                quarantine = self.path.with_name(f"state.json.corrupt.{suffix}")
                suffix += 1
            os.replace(self.path, quarantine)
            recovered.setdefault("state_recovery_history", []).append(
                {
                    "at": now_iso(self.timezone),
                    "action": "RESTORED_FROM_BACKUP",
                    "corrupt_copy": str(quarantine.relative_to(self.root)).replace("\\", "/"),
                }
            )
            # The corrupt primary has been quarantined, so this write cannot
            # replace the known-good backup with corrupt bytes.
            atomic_write_json(self.path, recovered)
            return recovered

    def save(self, value: dict[str, Any]) -> None:
        # Preserve object identity because the orchestrator may hold a reference
        # to one stage record while persisting the containing state.
        value["updated_at"] = now_iso(self.timezone)
        candidate = deepcopy(value)
        issues = validate_state(candidate, self.stages)
        if issues:
            raise ValueError("STATE_INVALID: " + ", ".join(issues))
        atomic_write_json(self.path, candidate)

    def verify_checkpoint(self, record: dict[str, Any]) -> bool:
        hashes = record.get("artifact_hashes")
        if not isinstance(hashes, dict) or not hashes:
            return False
        for relative, expected in hashes.items():
            path = (self.root / relative).resolve()
            try:
                path.relative_to(self.root)
            except ValueError:
                return False
            if not path.is_file() or sha256_file(path) != expected:
                return False
        return True
