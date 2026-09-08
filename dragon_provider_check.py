#!/usr/bin/env python3
"""Run the configured local editorial provider's unattended health check."""

from __future__ import annotations

import argparse
from dataclasses import is_dataclass, replace
from datetime import datetime
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from dragon.config import load_local_config
from dragon.providers import LocalCommandEditorialProvider, ProviderError, editorial_provider_from_config
from dragon.state import atomic_write_json, runtime_fingerprint, sha256_file, source_revision


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
    edition_date = args.date or datetime.now(
        ZoneInfo(str(config["timezone"]))
    ).date().isoformat()
    trial_dir = ROOT / "acceptance" / "provider-trials" / edition_date
    if args.full and is_dataclass(provider) and hasattr(provider, "capture_directory"):
        provider = replace(provider, capture_directory=trial_dir)
    try:
        health = provider.healthcheck()
        if not args.full:
            print(json.dumps({"status": "PASS", "provider": health}, ensure_ascii=False, indent=2))
            return 0
        research = provider.research(
            edition_date,
            {"edition_count": 0, "editions": [], "trial": True},
        )
        articles = provider.articles(research)
    except ProviderError as exc:
        failure = {"status": "FAIL", "error_code": exc.code, "detail": exc.detail}
        raw_files = sorted(trial_dir.glob("*.raw.json")) if args.full else []
        if raw_files:
            failure["raw_evidence"] = [
                str(path.relative_to(ROOT)).replace("\\", "/") for path in raw_files
            ]
        print(json.dumps(failure, ensure_ascii=False, indent=2))
        return 1
    research_path = trial_dir / "research.json"
    articles_path = trial_dir / "articles.json"
    atomic_write_json(research_path, research)
    atomic_write_json(articles_path, {"articles": articles})
    active = [item for item in articles if item.get("status") == "ACTIVE"]
    receipt = {
        "schema_version": 5,
        "status": "VALIDATED_AWAITING_HUMAN_REVIEW",
        "edition_date": edition_date,
        "created_at": datetime.now(ZoneInfo(str(config["timezone"]))).isoformat(),
        "provider": health,
        "editorial_generation_tested": True,
        "runtime_fingerprint": runtime_fingerprint(ROOT),
        "source_git_revision": source_revision(ROOT),
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
