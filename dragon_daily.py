#!/usr/bin/env python3
"""Single local entry point for DRAGON Version 5 production."""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dragon.archive import DisabledGitArchiveProvider, archive_provider_from_config
from dragon.config import load_local_config
from dragon.lock import DuplicateRunError
from dragon.orchestrator import Orchestrator
from dragon.pipeline import build_stage_definitions
from dragon.providers import SyntheticEditorialProvider, editorial_provider_from_config
from dragon.recovery import RecoveryEngine, RecoveryPolicy
from dragon.whatsapp import DisabledWhatsAppProvider, whatsapp_provider_from_config


ROOT = Path(__file__).resolve().parent


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--date", help="Casablanca edition date YYYY-MM-DD")
    mode = value.add_mutually_exclusive_group()
    mode.add_argument("--resume", action="store_true")
    mode.add_argument("--retry", metavar="STAGE")
    mode.add_argument("--from", dest="from_stage", metavar="STAGE")
    mode.add_argument("--status", action="store_true")
    value.add_argument(
        "--synthetic",
        action="store_true",
        help="run deterministic test fixtures; requires an explicit --date",
    )
    return value


def build_orchestrator(edition_date: str, *, synthetic: bool = False, root: Path = ROOT) -> Orchestrator:
    config = load_local_config(root)
    timezone = config["timezone"]
    provider = SyntheticEditorialProvider() if synthetic else editorial_provider_from_config(config)
    archive_provider = (
        DisabledGitArchiveProvider("SYNTHETIC_EXTERNAL_SIDE_EFFECTS_DISABLED")
        if synthetic
        else archive_provider_from_config(config)
    )
    whatsapp_provider = (
        DisabledWhatsAppProvider("SYNTHETIC_EXTERNAL_SIDE_EFFECTS_DISABLED")
        if synthetic
        else whatsapp_provider_from_config(config)
    )
    definitions = build_stage_definitions(
        provider,
        synthetic=synthetic,
        archive_provider=archive_provider,
        whatsapp_provider=whatsapp_provider,
    )
    return Orchestrator(
        root=root,
        edition_date=edition_date,
        timezone=timezone,
        stages=definitions,
        recovery_engine=RecoveryEngine(
            RecoveryPolicy.load(root / "config" / "recovery-policy.yaml"),
            sleeper=time.sleep,
        ),
    )


def main() -> int:
    args = parser().parse_args()
    if args.synthetic and not args.date:
        parser().error("--synthetic requires an explicit --date")
    config = load_local_config(ROOT)
    timezone = config["timezone"]
    edition_date = args.date or datetime.now(ZoneInfo(timezone)).date().isoformat()
    orchestrator = build_orchestrator(edition_date, synthetic=args.synthetic)
    if args.status:
        state = orchestrator.status()
        print(json.dumps(state, ensure_ascii=False, indent=2))
        return 0
    try:
        state = orchestrator.run(
            resume=args.resume,
            retry_stage=args.retry,
            from_stage=args.from_stage,
        )
    except DuplicateRunError as exc:
        print(json.dumps({"status": "BLOCKED", "error_code": "DUPLICATE_RUN", "detail": str(exc)}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(state, ensure_ascii=False, indent=2))
    failed = any(
        record["status"] in {"FAILED", "BLOCKED"}
        for record in state["stages"].values()
    )
    return 1 if failed or state.get("run_result") in {"FAILED", "BLOCKED"} else 0


if __name__ == "__main__":
    raise SystemExit(main())
