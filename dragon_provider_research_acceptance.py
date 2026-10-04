"""Manual entry point for one explicitly authorized provider-backed research-only run."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from dragon.config import load_local_config
from dragon.provider_research_acceptance import run_provider_research_acceptance
from dragon.providers import LocalCommandEditorialProvider, editorial_provider_from_config
from dragon.research_acceptance import ResearchAcceptanceError


_RUN_RESULTS = frozenset({"ALREADY_PUBLISHED", "BLOCKED", "COMPLETE", "DEGRADED", "FAILED", "INCOMPLETE"})


def _error(code: str, detail: str) -> int:
    print(json.dumps({"status": "ERROR", "code": code, "detail": detail}, ensure_ascii=False))
    return 2


def _report(orchestrator, state: object, report: object) -> int:
    result = state.get("run_result") if isinstance(state, dict) else None
    run_id = getattr(getattr(orchestrator, "store", None), "run_id", None)
    if not isinstance(result, str) or result not in _RUN_RESULTS or not isinstance(run_id, str) or not isinstance(report, Path):
        return _error("ACCEPTANCE_RESULT_INVALID", "persisted run_result, run identity, or report is missing or invalid")
    value = {"status": result, "run_id": run_id, "report": str(report)}
    if getattr(orchestrator, "acceptance_archive", None) is not None:
        value["durable_bundle"] = str(orchestrator.acceptance_archive)
        value["ACCEPTANCE_ARTIFACT_DURABILITY"] = orchestrator.acceptance_artifact_durability
        value["ACCEPTANCE_BUNDLE_COMPLETENESS"] = orchestrator.acceptance_bundle_completeness
    print(json.dumps(value, ensure_ascii=False))
    return 0 if result == "COMPLETE" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True)
    parser.add_argument("--technical-validation", action="store_true")
    parser.add_argument("--archive-root", type=Path, help="Durable acceptance storage outside this worktree; default shared Git directory or DRAGON_ACCEPTANCE_ARCHIVE_ROOT.")
    parser.add_argument("--authorize-provider-research", action="store_true", help="Required: permits one research() call only; never article generation.")
    args = parser.parse_args()
    if not args.authorize_provider_research:
        return _error("PROVIDER_RESEARCH_AUTHORIZATION_REQUIRED", "pass --authorize-provider-research to permit one research() call")
    root = Path(__file__).resolve().parent
    config = load_local_config(root)
    provider = editorial_provider_from_config(config, require_proven=False)
    if not isinstance(provider, LocalCommandEditorialProvider):
        return _error("AI_PROVIDER_UNCONFIGURED", getattr(provider, "reason", "local command provider unavailable"))
    try:
        orchestrator, state, report = run_provider_research_acceptance(
            root=root,
            edition_date=args.date,
            provider=provider,
            provider_authorized=True,
            technical_validation=args.technical_validation,
            require_durable_archive=True,
            durable_archive_root=args.archive_root,
        )
    except (ResearchAcceptanceError, ValueError) as exc:
        return _error(getattr(exc, "code", "INVALID_ARGUMENT"), str(exc))
    except Exception as exc:
        return _error("ACCEPTANCE_EXECUTION_FAILED", f"{type(exc).__name__}: {exc}")
    return _report(orchestrator, state, report)


if __name__ == "__main__":
    raise SystemExit(main())
