#!/usr/bin/env python3
"""Single local entry point for DRAGON Version 5 production."""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dragon.builtin_stages import preflight_stage
from dragon.config import load_local_config
from dragon.lock import DuplicateRunError
from dragon.orchestrator import Orchestrator
from dragon.recovery import RecoveryEngine, RecoveryPolicy
from dragon.stages import unavailable_stage


ROOT = Path(__file__).resolve().parent


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--date", help="Casablanca edition date YYYY-MM-DD")
    mode = value.add_mutually_exclusive_group()
    mode.add_argument("--resume", action="store_true")
    mode.add_argument("--retry", metavar="STAGE")
    mode.add_argument("--from", dest="from_stage", metavar="STAGE")
    mode.add_argument("--status", action="store_true")
    return value


def build_orchestrator(edition_date: str) -> Orchestrator:
    config = load_local_config(ROOT)
    timezone = config["timezone"]
    names = config["orchestrator"]["stages"]
    definitions = []
    for index, name in enumerate(names):
        stage = preflight_stage() if name == "preflight" else unavailable_stage(name)
        definitions.append(
            type(stage)(
                name=stage.name,
                prerequisites=tuple(names[index - 1 : index] if index else []),
                runner=stage.runner,
                validator=stage.validator,
            )
        )
    return Orchestrator(
        root=ROOT,
        edition_date=edition_date,
        timezone=timezone,
        stages=definitions,
        recovery_engine=RecoveryEngine(
            RecoveryPolicy.load(ROOT / "config" / "recovery-policy.yaml"),
            sleeper=time.sleep,
        ),
    )


def main() -> int:
    args = parser().parse_args()
    config = load_local_config(ROOT)
    timezone = config["timezone"]
    edition_date = args.date or datetime.now(ZoneInfo(timezone)).date().isoformat()
    orchestrator = build_orchestrator(edition_date)
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
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
