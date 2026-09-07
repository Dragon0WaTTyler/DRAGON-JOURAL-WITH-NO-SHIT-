"""Immutable per-edition continuity snapshots for subsequent V5 research."""

from __future__ import annotations

from datetime import date
import json
from pathlib import Path


def build_snapshot(edition_date: str, mode: str, decisions: list[dict]) -> dict:
    covered = []
    skipped = []
    watch_items = []
    for item in decisions:
        if item["status"] == "SKIPPED":
            skipped.append(
                {
                    "section_id": item["section_id"],
                    "reason": item["skip_reason"],
                }
            )
            continue
        covered.append(
            {
                "article_id": item["id"],
                "section_id": item["section_id"],
                "headline": item["headline"],
                "source_urls": list(item.get("source_urls", [])),
            }
        )
        elements = item.get("editorial_elements", {})
        next_steps = elements.get("next_steps")
        if next_steps:
            values = next_steps if isinstance(next_steps, list) else [next_steps]
            watch_items.extend(
                {
                    "article_id": item["id"],
                    "section_id": item["section_id"],
                    "description": str(value),
                }
                for value in values
            )
    return {
        "schema_version": 5,
        "date": edition_date,
        "mode": mode,
        "covered_stories": covered,
        "skipped_sections": skipped,
        "watch_items": watch_items,
    }


def prior_context(root: Path, edition_date: str, *, limit: int = 30) -> dict:
    cutoff = date.fromisoformat(edition_date)
    snapshots = []
    for path in (root / "editions").glob("????/??/????-??-??/continuity.json"):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            value_date = date.fromisoformat(str(value["date"]))
        except (OSError, json.JSONDecodeError, KeyError, ValueError):
            continue
        if (
            value.get("schema_version") == 5
            and value.get("mode") == "production"
            and value_date < cutoff
        ):
            snapshots.append(value)
    snapshots.sort(key=lambda item: item["date"], reverse=True)
    selected = snapshots[:limit]
    return {
        "schema_version": 5,
        "before_date": edition_date,
        "edition_count": len(selected),
        "editions": selected,
    }
