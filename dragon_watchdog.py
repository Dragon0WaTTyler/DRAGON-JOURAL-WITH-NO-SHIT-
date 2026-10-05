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
    parser.add_argument(
        "--synthetic",
        action="store_true",
        help="exercise the watchdog with deterministic fixtures; requires --date",
    )
    args = parser.parse_args()
    if args.synthetic and not args.date:
        parser.error("--synthetic requires an explicit --date")
    config = load_local_config(ROOT)
    day = args.date or current_edition_date(config["timezone"])
    assessment = assess(ROOT, day)
    value = (
        {**assessment.__dict__}
        if args.check_only
        else recover(ROOT, day, assessment=assessment, synthetic=args.synthetic)
    )
    print(json.dumps(value, ensure_ascii=False, indent=2))
    return 1 if assessment.action == "ATTENTION" else 0


if __name__ == "__main__":
    raise SystemExit(main())
