#!/usr/bin/env python3
"""Audit whether DRAGON V5 has enough evidence for local-production cutover."""

from __future__ import annotations

import json
from pathlib import Path

from dragon.acceptance import audit_cutover


ROOT = Path(__file__).resolve().parent


def main() -> int:
    result = audit_cutover(ROOT)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] in {"READY_FOR_CUTOVER", "CUTOVER_COMPLETE"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
