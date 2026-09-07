"""Exclusive daily run lock with heartbeat and ownership verification."""

from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import socket
from typing import Any, Callable
from uuid import uuid4
from zoneinfo import ZoneInfo


class DuplicateRunError(RuntimeError):
    pass


def process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def read_lock(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError) as exc:
        return {"valid": False, "error": str(exc)}
    if not isinstance(value, dict) or not isinstance(value.get("pid"), int):
        return {"valid": False, "error": "invalid lock schema"}
    return {"valid": True, **value}


class RunLock:
    def __init__(
        self,
        path: Path,
        timezone: str,
        *,
        pid: int | None = None,
        alive: Callable[[int], bool] = process_alive,
    ):
        self.path = path
        self.timezone = timezone
        self.pid = pid or os.getpid()
        self.alive = alive
        self.token = uuid4().hex
        self.payload: dict[str, Any] | None = None

    def _timestamp(self) -> str:
        return datetime.now(ZoneInfo(self.timezone)).isoformat()

    def acquire(self) -> "RunLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        timestamp = self._timestamp()
        payload = {
            "schema_version": 5,
            "token": self.token,
            "pid": self.pid,
            "hostname": socket.gethostname(),
            "run_id": None,
            "acquired_at": timestamp,
            "heartbeat_at": timestamp,
        }
        try:
            with self.path.open("x", encoding="utf-8", newline="\n") as stream:
                json.dump(payload, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
        except FileExistsError as exc:
            existing = read_lock(self.path)
            detail = "existing lock is unreadable"
            if existing and existing.get("valid"):
                state = "alive" if self.alive(int(existing["pid"])) else "dead"
                detail = f"pid {existing['pid']} is {state}; watchdog must arbitrate"
            raise DuplicateRunError(f"DUPLICATE_RUN: {detail}") from exc
        self.payload = payload
        return self

    def _write_owned(self) -> None:
        if self.payload is None:
            raise RuntimeError("LOCK_NOT_ACQUIRED")
        current = read_lock(self.path)
        if not current or current.get("token") != self.token:
            raise RuntimeError("LOCK_OWNERSHIP_LOST")
        temporary = self.path.with_name(f".{self.path.name}.{self.token}.tmp")
        try:
            with temporary.open("w", encoding="utf-8", newline="\n") as stream:
                json.dump(self.payload, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)

    def set_run_id(self, run_id: str) -> None:
        if self.payload is None:
            raise RuntimeError("LOCK_NOT_ACQUIRED")
        self.payload["run_id"] = run_id
        self.payload["heartbeat_at"] = self._timestamp()
        self._write_owned()

    def heartbeat(self, *, stage: str | None = None) -> None:
        if self.payload is None:
            raise RuntimeError("LOCK_NOT_ACQUIRED")
        self.payload["heartbeat_at"] = self._timestamp()
        self.payload["stage"] = stage
        self._write_owned()

    def release(self) -> None:
        if self.payload is None:
            return
        current = read_lock(self.path)
        if current and current.get("token") == self.token:
            self.path.unlink(missing_ok=True)
        self.payload = None

    def __enter__(self) -> "RunLock":
        return self.acquire()

    def __exit__(self, *_: object) -> None:
        self.release()
