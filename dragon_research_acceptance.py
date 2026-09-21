"""Manual entry point for one fresh provider-free research acceptance run."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from dragon.research_acceptance import ResearchAcceptanceError, run_research_acceptance


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one fresh DRAGON V5 research-only acceptance attempt.")
    parser.add_argument("--date", required=True, help="Explicit edition date in YYYY-MM-DD; no implicit current-date reuse.")
    args = parser.parse_args()
    try:
        orchestrator, state, report = run_research_acceptance(root=Path(__file__).resolve().parent, edition_date=args.date)
    except (ResearchAcceptanceError, ValueError) as exc:
        print(json.dumps({"status": "ERROR", "code": getattr(exc, "code", "INVALID_ARGUMENT"), "detail": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps({"status": state["run_status"], "run_id": orchestrator.store.run_id, "report": str(report)}, ensure_ascii=False))
    return 0 if state["run_status"] == "COMPLETE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
