#!/usr/bin/env python3
"""Validate one JSON research packet without third-party dependencies."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import urlparse


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
SOURCE_FIELDS = {"url", "publisher", "publication_date", "retrieved_at", "source_type", "attribution", "claim_supported", "evidence_label", "independence"}
LABELS = {"FACT", "OFFICIAL_CLAIM", "COMPANY_CLAIM", "DISPUTED_CLAIM", "ESTIMATE", "ABSTRACT_ONLY", "INTERPRETATION", "UNKNOWN"}
HOMEPAGE_PATHS = {"", "/", "/en", "/en/"}


def validate_sources(field: str, values: object, errors: list[str]) -> None:
    if not isinstance(values, list):
        return
    for index, source in enumerate(values):
        where = f"{field}[{index}]"
        if not isinstance(source, dict):
            errors.append(f"{where} must be a source record object")
            continue
        missing = SOURCE_FIELDS - set(source)
        extra = set(source) - SOURCE_FIELDS
        if missing:
            errors.append(f"{where} missing: {', '.join(sorted(missing))}")
        if extra:
            errors.append(f"{where} unknown fields: {', '.join(sorted(extra))}")
        if any(not isinstance(source.get(k), str) or not source.get(k, "").strip() for k in SOURCE_FIELDS):
            errors.append(f"{where} fields must be non-empty strings")
            continue
        parsed = urlparse(source["url"])
        if parsed.scheme != "https" or not parsed.netloc or parsed.path in HOMEPAGE_PATHS:
            errors.append(f"{where}.url must be an exact HTTPS source page, not a homepage")
        timestamp = source["retrieved_at"]
        if not (timestamp.endswith("+01:00") or timestamp.endswith("Z")) or "T" not in timestamp:
            errors.append(f"{where}.retrieved_at must be an ISO timestamp for Africa/Casablanca")
        if source["evidence_label"] not in LABELS:
            errors.append(f"{where}.evidence_label is invalid")


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
    for field in ("key_facts", "contradictory_evidence"):
        values = payload.get(field)
        if isinstance(values, list) and not all(isinstance(value, str) for value in values):
            errors.append(f"{field} must contain strings")
    validate_sources("primary_sources", payload.get("primary_sources"), errors)
    validate_sources("independent_sources", payload.get("independent_sources"), errors)
    if payload.get("recommendation") not in {"HOLD", "REJECT"} and not payload.get("independent_sources"):
        errors.append("publishable packet requires an independent source trail")
    if errors:
        print("PACKET FAIL")
        print("\n".join(errors))
        return 1
    print(f"PACKET PASS: {args.packet}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
