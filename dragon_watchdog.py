#!/usr/bin/env python3
"""Scheduled watchdog entry for DRAGON Version 5."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from dragon.config import load_local_config
from dragon.scheduler import current_edition_date
from dragon.watchdog import assess, recover


ROOT = Path(__file__).resolve().parent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date")
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    config = load_local_config(ROOT)
    day = args.date or current_edition_date(config["timezone"])
    assessment = assess(ROOT, day)
    value = {**assessment.__dict__} if args.check_only else recover(ROOT, day, assessment=assessment)
    print(json.dumps(value, ensure_ascii=False, indent=2))
    return 1 if assessment.action == "ATTENTION" else 0


if __name__ == "__main__":
    raise SystemExit(main())
