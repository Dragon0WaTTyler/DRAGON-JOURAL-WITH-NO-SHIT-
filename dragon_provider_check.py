#!/usr/bin/env python3
"""Run the configured local editorial provider's unattended health check."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from dragon.config import load_local_config
from dragon.providers import LocalCommandEditorialProvider, ProviderError, editorial_provider_from_config
from dragon.state import atomic_write_json, sha256_file


ROOT = Path(__file__).resolve().parent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--full",
        action="store_true",
        help="consume provider usage and validate a live research/articles trial",
    )
    parser.add_argument("--date", help="edition date for --full (defaults to local today)")
    args = parser.parse_args()
    config = load_local_config(ROOT)
    provider = editorial_provider_from_config(
        config, require_proven=False
    )
    if not isinstance(provider, LocalCommandEditorialProvider):
        print(json.dumps({"status": "FAIL", "error_code": provider.reason}, indent=2))
        return 1
    try:
        health = provider.healthcheck()
        if not args.full:
            print(json.dumps({"status": "PASS", "provider": health}, ensure_ascii=False, indent=2))
            return 0
        edition_date = args.date or datetime.now(
            ZoneInfo(str(config["timezone"]))
        ).date().isoformat()
        research = provider.research(
            edition_date,
            {"edition_count": 0, "editions": [], "trial": True},
        )
        articles = provider.articles(research)
    except ProviderError as exc:
        print(json.dumps({"status": "FAIL", "error_code": exc.code, "detail": exc.detail}, ensure_ascii=False, indent=2))
        return 1
    trial_dir = ROOT / "acceptance" / "provider-trials" / edition_date
    research_path = trial_dir / "research.json"
    articles_path = trial_dir / "articles.json"
    atomic_write_json(research_path, research)
    atomic_write_json(articles_path, {"articles": articles})
    active = [item for item in articles if item.get("status") == "ACTIVE"]
    receipt = {
        "schema_version": 5,
        "status": "VALIDATED_AWAITING_HUMAN_REVIEW",
        "edition_date": edition_date,
        "provider": health,
        "active_sections": len(active),
        "skipped_sections": len(articles) - len(active),
        "edition_words": sum(
            len(" ".join(item.get("body", [])).split()) for item in active
        ),
        "artifacts": {
            str(research_path.relative_to(ROOT)).replace("\\", "/"): sha256_file(research_path),
            str(articles_path.relative_to(ROOT)).replace("\\", "/"): sha256_file(articles_path),
        },
        "integration_test_status_changed": False,
        "next_action": "Human-review facts, sources, Arabic, depth, and skips before setting PASS.",
    }
    receipt_path = trial_dir / "receipt.json"
    atomic_write_json(receipt_path, receipt)
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
