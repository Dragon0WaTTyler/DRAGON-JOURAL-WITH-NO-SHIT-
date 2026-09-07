#!/usr/bin/env python3
"""Scheduled watchdog entry for DRAGON Version 5."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from dragon.config import load_local_config
from dragon.watchdog import assess, recover


ROOT = Path(__file__).resolve().parent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date")
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    config = load_local_config(ROOT)
    day = args.date or datetime.now(ZoneInfo(config["timezone"])).date().isoformat()
    assessment = assess(ROOT, day)
    value = {**assessment.__dict__} if args.check_only else recover(ROOT, day, assessment=assessment)
    print(json.dumps(value, ensure_ascii=False, indent=2))
    return 0 if assessment.action != "NO_ACTION" or "requires intervention" not in assessment.reason else 1


if __name__ == "__main__":
    raise SystemExit(main())
