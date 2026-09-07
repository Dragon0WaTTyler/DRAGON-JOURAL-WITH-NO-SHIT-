"""Dead-process and abandoned-lock recovery for the single local run."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Callable
from zoneinfo import ZoneInfo

from dragon.config import load_local_config
from dragon.lock import process_alive, read_lock
from dragon.state import atomic_write_json


@dataclass(frozen=True)
class WatchdogAssessment:
    action: str
    reason: str
    stage: str | None
    pid: int | None
    lock_path: str


def _age_seconds(value: str, now: datetime) -> float:
    parsed = datetime.fromisoformat(value)
    return max(0.0, (now - parsed).total_seconds())


def assess(
    root: Path,
    edition_date: str,
    *,
    now: datetime | None = None,
    alive: Callable[[int], bool] = process_alive,
) -> WatchdogAssessment:
    root = root.resolve()
    config = load_local_config(root)
    timezone = config["timezone"]
    now = now or datetime.now(ZoneInfo(timezone))
    run_dir = root / "daily-runs" / edition_date
    state_path = run_dir / "state.json"
    lock_path = run_dir / "run.lock"
    relative_lock = str(lock_path.relative_to(root)).replace("\\", "/")
    lock = read_lock(lock_path)
    if not state_path.exists():
        if lock and lock.get("valid"):
            pid = int(lock["pid"])
            if alive(pid):
                return WatchdogAssessment("NO_ACTION", "live lock exists before state initialization", None, pid, relative_lock)
            return WatchdogAssessment("RESUME", "lock owner died before state initialization", None, pid, relative_lock)
        if lock:
            return WatchdogAssessment("ATTENTION", "unreadable lock requires intervention", None, None, relative_lock)
        return WatchdogAssessment("START", "no V5 state exists for today", None, None, relative_lock)
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        pid = lock.get("pid") if lock and lock.get("valid") else None
        if pid is not None and alive(int(pid)):
            return WatchdogAssessment("ATTENTION", f"state unreadable while owner is alive: {exc}", None, int(pid), relative_lock)
        if (run_dir / "state.json.bak").is_file() and (not lock or lock.get("valid")):
            return WatchdogAssessment("RESUME", "primary state unreadable; backup is available", None, int(pid) if pid is not None else None, relative_lock)
        return WatchdogAssessment("ATTENTION", f"state unreadable and no safe recovery copy: {exc}", None, int(pid) if pid is not None else None, relative_lock)
    running = [name for name, record in state.get("stages", {}).items() if record.get("status") == "RUNNING"]
    pending = [name for name, record in state.get("stages", {}).items() if record.get("status") == "PENDING"]
    recoverable_failed = [
        name
        for name, record in state.get("stages", {}).items()
        if record.get("status") == "FAILED"
        and record.get("repair_status") != "REQUIRES_INTERVENTION"
    ]
    intervention_failed = [
        name
        for name, record in state.get("stages", {}).items()
        if record.get("status") in {"FAILED", "BLOCKED"}
        and record.get("repair_status") == "REQUIRES_INTERVENTION"
    ]
    if len(running) > 1:
        return WatchdogAssessment("ATTENTION", "multiple RUNNING stages require intervention", None, lock.get("pid") if lock else None, relative_lock)
    stage = running[0] if running else None
    if lock and lock.get("valid"):
        pid = int(lock["pid"])
        if alive(pid):
            heartbeat = lock.get("heartbeat_at") or lock.get("acquired_at")
            timeout = int(config.get("watchdog", {}).get("stage_timeouts_seconds", {}).get(stage, config.get("watchdog", {}).get("default_stage_timeout_seconds", 7200)))
            if heartbeat and _age_seconds(str(heartbeat), now) > timeout:
                return WatchdogAssessment("ATTENTION", "live process has stale heartbeat; diagnose without duplicate restart", stage, pid, relative_lock)
            return WatchdogAssessment("NO_ACTION", "orchestrator process is alive", stage, pid, relative_lock)
        if stage:
            return WatchdogAssessment("RESUME", "RUNNING stage has dead lock owner", stage, pid, relative_lock)
        if pending or recoverable_failed:
            next_stage = recoverable_failed[0] if recoverable_failed else pending[0]
            return WatchdogAssessment(
                "RESUME",
                "lock owner died with resumable work remaining",
                next_stage,
                pid,
                relative_lock,
            )
        return WatchdogAssessment("QUARANTINE_LOCK", "lock owner is dead and no resumable work remains", None, pid, relative_lock)
    if lock and not lock.get("valid"):
        return WatchdogAssessment("ATTENTION", "unreadable lock requires intervention", stage, None, relative_lock)
    if stage:
        return WatchdogAssessment("RESUME", "RUNNING stage has no lock owner", stage, None, relative_lock)
    if recoverable_failed:
        return WatchdogAssessment(
            "RESUME",
            "failed stage was interrupted before recovery completed",
            recoverable_failed[0],
            None,
            relative_lock,
        )
    if pending:
        return WatchdogAssessment(
            "RESUME",
            "pending work remains with no orchestrator owner",
            pending[0],
            None,
            relative_lock,
        )
    if intervention_failed:
        return WatchdogAssessment(
            "ATTENTION",
            "failed or blocked stage requires intervention",
            intervention_failed[0],
            None,
            relative_lock,
        )
    return WatchdogAssessment("NO_ACTION", "run is not actively RUNNING", None, None, relative_lock)


def _quarantine_lock(root: Path, lock_relative: str) -> Path | None:
    path = (root / lock_relative).resolve()
    path.relative_to(root.resolve())
    if not path.exists():
        return None
    stem = f"run.lock.abandoned.{datetime.now().strftime('%Y%m%d%H%M%S')}"
    target = path.with_name(stem)
    suffix = 1
    while target.exists():
        target = path.with_name(f"{stem}.{suffix}")
        suffix += 1
    os.replace(path, target)
    return target


def launch_orchestrator(root: Path, edition_date: str, *, resume: bool) -> int:
    command = [sys.executable, str(root / "dragon_daily.py"), "--date", edition_date]
    if resume:
        command.append("--resume")
    environment = os.environ.copy()
    environment["DRAGON_TRIGGER"] = "watchdog"
    kwargs: dict[str, Any] = {"cwd": root, "env": environment}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    process = subprocess.Popen(command, **kwargs)
    return process.pid


def recover(
    root: Path,
    edition_date: str,
    *,
    launcher: Callable[[Path, str], int] | None = None,
    assessment: WatchdogAssessment | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    config = load_local_config(root)
    timezone = config["timezone"]
    result = assessment or assess(root, edition_date)
    run_dir = root / "daily-runs" / edition_date
    (run_dir / "recovery").mkdir(parents=True, exist_ok=True)
    quarantined = None
    launched_pid = None
    if result.action in {"RESUME", "QUARANTINE_LOCK"}:
        quarantined = _quarantine_lock(root, result.lock_path)
    if result.action in {"START", "RESUME"}:
        if launcher:
            launched_pid = launcher(root, edition_date)
        else:
            launched_pid = launch_orchestrator(root, edition_date, resume=result.action == "RESUME")
    report = {
        "timestamp": datetime.now(ZoneInfo(timezone)).isoformat(),
        "date": edition_date,
        **asdict(result),
        "quarantined_lock": str(quarantined.relative_to(root)).replace("\\", "/") if quarantined else None,
        "launched_pid": launched_pid,
    }
    target = run_dir / "recovery" / "watchdog-latest.json"
    atomic_write_json(target, report)
    return report
