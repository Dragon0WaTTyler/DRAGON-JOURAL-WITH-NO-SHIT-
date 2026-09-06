#!/usr/bin/env python3
"""Validate the structural evidence required for a V4 current-news handoff."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit


RECOMMENDATIONS = {"LEAD", "PUBLISH", "BRIEF"}
GENERIC_PATHS = {"", "/", "/general", "/news-2", "/tag/h24", "/sports/soccer"}


def _records(candidate: dict) -> list[dict]:
    records = []
    for key in ("PRIMARY_SOURCES", "INDEPENDENT_SOURCES"):
        value = candidate.get(key, [])
        if isinstance(value, list):
            records.extend(item for item in value if isinstance(item, dict))
    return records


def _exact_url(url: object) -> bool:
    if not isinstance(url, str):
        return False
    parsed = urlsplit(url)
    return parsed.scheme in {"https", "http"} and bool(parsed.netloc) and parsed.path.rstrip("/") not in GENERIC_PATHS


def _candidates(packet: dict) -> list[dict]:
    values: list[dict] = []
    sections = packet.get("section_packets", {})
    if isinstance(sections, dict):
        for section_id, desk in sections.items():
            if not isinstance(desk, dict):
                continue
            for candidate in desk.get("candidates", []):
                if isinstance(candidate, dict):
                    copy = dict(candidate)
                    copy.setdefault("SECTION_ID", section_id)
                    values.append(copy)
    for candidate in packet.get("additional_publishable_candidates", []):
        if isinstance(candidate, dict):
            values.append(candidate)
    return values


def validate(packet: dict) -> list[str]:
    errors: list[str] = []
    gate = packet.get("quality_gate")
    if not isinstance(gate, dict):
        return ["missing quality_gate"]
    for key, minimum in (("publishable_candidate_count", 30), ("lead_capable_candidate_count", 4), ("brief_capable_candidate_count", 20)):
        value = gate.get(key)
        if not isinstance(value, int) or value < minimum:
            errors.append(f"quality_gate.{key} must be an integer >= {minimum}")

    candidates = _candidates(packet)
    publishable = [item for item in candidates if str(item.get("RECOMMENDATION", "")).upper() in RECOMMENDATIONS]
    story_ids = [item.get("STORY_ID") for item in publishable]
    if len(publishable) < 30:
        errors.append("packet has fewer than 30 publishable candidates")
    if len(story_ids) != len(set(story_ids)) or any(not isinstance(story_id, str) or not story_id for story_id in story_ids):
        errors.append("publishable candidates require unique nonempty STORY_ID values")
    for candidate in publishable:
        identifier = candidate.get("STORY_ID", "<unknown>")
        if not isinstance(candidate.get("SECTION_ID"), str) or not candidate["SECTION_ID"]:
            errors.append(f"{identifier}: missing SECTION_ID")
            continue
        evidence = _records(candidate)
        if not evidence and _exact_url(candidate.get("url")):
            evidence = [{"url": candidate["url"]}]
        if not any(_exact_url(source.get("url")) for source in evidence):
            errors.append(f"{identifier}: requires an exact article or document URL, not a section/tag/home URL")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packet", type=Path)
    args = parser.parse_args()
    try:
        payload = json.loads(args.packet.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"invalid current-news packet: {exc}") from exc
    errors = validate(payload)
    if errors:
        raise SystemExit("CURRENT_NEWS_HANDOFF_INVALID: " + "; ".join(errors))
    print("CURRENT_NEWS_HANDOFF_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
