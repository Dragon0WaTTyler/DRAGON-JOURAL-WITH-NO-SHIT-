"""Expose validated Windows scheduler settings without parsing YAML in PowerShell."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from dragon.config import load_local_config


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
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(settings(args.root), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
