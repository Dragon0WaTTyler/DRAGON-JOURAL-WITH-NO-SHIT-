#!/usr/bin/env python3
"""Validate one JSON research packet without third-party dependencies."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


REQUIRED = {
    "story_id": str,
    "proposed_title": str,
    "importance_score": (int, float),
    "what_happened": str,
    "key_facts": list,
    "primary_sources": list,
    "independent_sources": list,
    "contradictory_evidence": list,
    "uncertainty": str,
    "context": str,
    "why_it_matters": str,
    "strategic_angle": str,
    "confidence": str,
    "recommendation": str,
}
ALLOWED = {"LEAD", "PUBLISH", "BRIEF", "HOLD", "REJECT"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("packet", type=Path)
    args = parser.parse_args()
    errors: list[str] = []
    try:
        payload = json.loads(args.packet.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        print(f"PACKET FAIL: {exc}")
        return 1
    if not isinstance(payload, dict):
        print("PACKET FAIL: top-level value must be an object")
        return 1
    unknown = sorted(set(payload) - set(REQUIRED))
    if unknown:
        errors.append(f"unknown fields: {', '.join(unknown)}")
    for key, expected in REQUIRED.items():
        if key not in payload:
            errors.append(f"missing {key}")
            continue
        if not isinstance(payload[key], expected) or (key == "importance_score" and isinstance(payload[key], bool)):
            errors.append(f"{key} has wrong type")
    score = payload.get("importance_score")
    if isinstance(score, (int, float)) and not isinstance(score, bool) and not 0 <= score <= 10:
        errors.append("importance_score must be between 0 and 10")
    if payload.get("confidence") not in {"high", "medium", "low"}:
        errors.append("confidence must be high, medium, or low")
    if payload.get("recommendation") not in ALLOWED:
        errors.append("recommendation is invalid")
    for field in ("key_facts", "primary_sources", "independent_sources", "contradictory_evidence"):
        values = payload.get(field)
        if isinstance(values, list) and not all(isinstance(value, str) for value in values):
            errors.append(f"{field} must contain strings")
    if errors:
        print("PACKET FAIL")
        print("\n".join(errors))
        return 1
    print(f"PACKET PASS: {args.packet}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
