"""Expose the single Codex local-automation contract."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

# The Windows helper scripts execute this file by path so they work regardless
# of the operator's current directory. Make that supported entry mode resolve
# the sibling ``dragon`` package just like ``python -m dragon.scheduler``.
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dragon.config import load_local_config
from dragon.state import runtime_fingerprint, source_revision


def current_edition_date(timezone: str, now: datetime | None = None) -> str:
    zone = ZoneInfo(timezone)
    instant = now or datetime.now(zone)
    if instant.tzinfo is None:
        raise ValueError("SCHEDULER_TIME_MUST_BE_TIMEZONE_AWARE")
    return instant.astimezone(zone).date().isoformat()


def settings(root: Path) -> dict[str, object]:
    config = load_local_config(root)
    scheduler = config["scheduler"]
    return {
        "enabled": bool(scheduler["enabled"]),
        "provider": str(scheduler["provider"]),
        "kind": str(scheduler["kind"]),
        "destination": str(scheduler["destination"]),
        "execution_environment": str(scheduler["execution_environment"]),
        "entries": int(scheduler["entries"]),
        "task_name": str(scheduler["task_name"]),
        "start_time": str(scheduler["start_time"]),
        "target_deadline": str(scheduler["target_deadline"]),
        "canonical_command": str(scheduler["canonical_command"]),
        "working_directory": str(root.resolve()),
        "runtime_fingerprint": runtime_fingerprint(root),
        "source_git_revision": source_revision(root),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(settings(args.root), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
