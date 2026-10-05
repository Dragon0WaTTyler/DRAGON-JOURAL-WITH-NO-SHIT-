"""Manual entry point for one fresh provider-free research acceptance run."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from dragon.research_acceptance import ResearchAcceptanceError, run_research_acceptance


_RUN_RESULTS = frozenset({"ALREADY_PUBLISHED", "BLOCKED", "COMPLETE", "DEGRADED", "FAILED", "INCOMPLETE"})


def _emit_error(code: str, detail: str) -> int:
    print(json.dumps({"status": "ERROR", "code": code, "detail": detail}, ensure_ascii=False))
    return 2


def _report_result(orchestrator, state: object, report: object) -> int:
    """Render the persisted execution result without changing run state."""
    result = state.get("run_result") if isinstance(state, dict) else None
    run_id = getattr(getattr(orchestrator, "store", None), "run_id", None)
    if not isinstance(result, str) or result not in _RUN_RESULTS:
        return _emit_error("ACCEPTANCE_RESULT_INVALID", "persisted run_result is missing or invalid")
    if not isinstance(run_id, str) or not run_id:
        return _emit_error("ACCEPTANCE_RESULT_INVALID", "orchestrator run_id is missing or invalid")
    if not isinstance(report, Path):
        return _emit_error("ACCEPTANCE_RESULT_INVALID", "acceptance report path is missing or invalid")
    print(json.dumps({"status": result, "run_id": run_id, "report": str(report)}, ensure_ascii=False))
    return 0 if result == "COMPLETE" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one fresh DRAGON V5 research-only acceptance attempt.")
    parser.add_argument("--date", required=True, help="Explicit edition date in YYYY-MM-DD; no implicit current-date reuse.")
    parser.add_argument(
        "--technical-validation", action="store_true",
        help="Explicit provider-free technical validation; records any missed production deadline and never grants production readiness.",
    )
    args = parser.parse_args()
    try:
        orchestrator, state, report = run_research_acceptance(
            root=Path(__file__).resolve().parent,
            edition_date=args.date,
            technical_validation=args.technical_validation,
        )
    except (ResearchAcceptanceError, ValueError) as exc:
        return _emit_error(getattr(exc, "code", "INVALID_ARGUMENT"), str(exc))
    except Exception as exc:
        return _emit_error("ACCEPTANCE_EXECUTION_FAILED", f"{type(exc).__name__}: {exc}")
    return _report_result(orchestrator, state, report)


if __name__ == "__main__":
    raise SystemExit(main())
