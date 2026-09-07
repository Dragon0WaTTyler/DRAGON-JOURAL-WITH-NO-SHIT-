"""Expose validated Windows scheduler settings without parsing YAML in PowerShell."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

# The Windows helper scripts execute this file by path so they work regardless
# of the operator's current directory. Make that supported entry mode resolve
# the sibling ``dragon`` package just like ``python -m dragon.scheduler``.
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dragon.config import load_local_config
from dragon.state import runtime_fingerprint, source_revision


def settings(root: Path) -> dict[str, object]:
    config = load_local_config(root)
    scheduler = config["scheduler"]
    return {
        "enabled": bool(scheduler["enabled"]),
        "task_name": str(scheduler["task_name"]),
        "start_time": str(scheduler["start_time"]),
        "target_deadline": str(scheduler["target_deadline"]),
        "interval_minutes": int(scheduler["watchdog_interval_minutes"]),
        "python": sys.executable,
        "watchdog": str((root / "dragon_watchdog.py").resolve()),
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
