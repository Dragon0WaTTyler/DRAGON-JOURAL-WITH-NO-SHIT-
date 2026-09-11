#!/usr/bin/env python3
"""Audit whether one new DRAGON editorial-provider trial may be authorized."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import tomllib

from dragon.live_readiness import READY, audit_final_live_readiness


ROOT = Path(__file__).resolve().parent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--automation-file",
        type=Path,
        required=True,
        help="Local Codex automation.toml record to verify without changing it.",
    )
    args = parser.parse_args()
    try:
        automation = tomllib.loads(args.automation_file.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        print(json.dumps({"status": "NOT_READY_FOR_FINAL_LIVE_AUTHORIZATION", "issues": [f"SCHEDULER_RECORD_INVALID: {exc}"]}, indent=2))
        return 1
    result = audit_final_live_readiness(ROOT, automation=automation)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == READY else 1


if __name__ == "__main__":
    raise SystemExit(main())
