#!/usr/bin/env python3
"""Replay one preserved recovery boundary without a provider, network, or articles."""

from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
from uuid import uuid4

from dragon.config import load_local_config
from dragon.deep_research import (
    DeepResearchError,
    build_deep_research_state,
    load_deep_research_config,
    validate_deep_research_state,
)
from dragon.deep_research_executor import (
    build_research_yield_report,
    execute_research_round,
    schedule_research_actions,
)
from dragon.provider_acceptance import OfflineReplayResearchAdapter
from dragon.research_recovery import build_recovery_plan
from dragon.source_coverage import load_source_coverage
from dragon.state import atomic_write_json, sha256_file, source_revision
from dragon.providers import SECTION_HEADINGS


ROOT = Path(__file__).resolve().parent


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _emit(value: dict) -> None:
    print(json.dumps(value, ensure_ascii=True, indent=2))


def _input_paths(run_dir: Path) -> dict[str, Path]:
    return {
        "recovered_packet": run_dir / "research" / "recovered-research-packet.json",
        "recovered_intelligence": run_dir / "source-intelligence" / "recovered-report.json",
        "research_plan": run_dir / "research-planning" / "plan.json",
        "recovery_plan": run_dir / "research-recovery" / "plan.json",
        "historical_state": run_dir / "state.json",
    }


def replay_preserved_recovery(
    *, root: Path, edition_date: str, source_run_id: str, output_dir: Path,
) -> dict:
    """Materialize and execute a bounded, all-dead-end routing replay.

    The source run is read-only.  No patch is applied back to its research
    packet, and the adapter deliberately returns only ``DEAD_END`` records.
    """
    source_run = root / "daily-runs" / edition_date / "runs" / source_run_id
    paths = _input_paths(source_run)
    missing = [name for name, path in paths.items() if not path.is_file()]
    if missing:
        raise ValueError(f"PRESERVED_RECOVERY_REPLAY_INPUT_MISSING:{','.join(missing)}")
    if output_dir.resolve().is_relative_to(source_run.resolve()):
        raise ValueError("PRESERVED_RECOVERY_REPLAY_OUTPUT_MUST_BE_SEPARATE")
    if output_dir.exists():
        raise ValueError("PRESERVED_RECOVERY_REPLAY_OUTPUT_ALREADY_EXISTS")

    input_hashes_before = {name: sha256_file(path) for name, path in paths.items()}
    packet = _load(paths["recovered_packet"])
    intelligence = _load(paths["recovered_intelligence"])
    research_plan = _load(paths["research_plan"])
    recovery_plan = _load(paths["recovery_plan"])
    config = load_deep_research_config(root / "config" / "deep-research.yaml")
    state = build_deep_research_state(
        packet, intelligence, research_plan, recovery_plan, config,
        run_scope_id=f"offline-replay:{source_run_id}",
    )
    issues = validate_deep_research_state(state)
    if issues:
        raise DeepResearchError(
            f"RECOVERY_JOB_MATERIALIZATION_FAILED:{';'.join(issues)}"
        )
    schedule = schedule_research_actions(state["jobs"], config)
    actions_by_job: dict[str, list[dict]] = {}
    for action in schedule["actions"]:
        actions_by_job.setdefault(action["job_id"], []).append(action)
    adapter = OfflineReplayResearchAdapter(
        reason="OFFLINE_PRESERVED_RUN_ROUTING_REPLAY_NO_NETWORK_OR_PROVIDER"
    )
    executions = [
        execute_research_round(job, adapter, config, actions=actions_by_job[job["job_id"]])
        for job in state["jobs"] if job["job_id"] in actions_by_job
    ]
    execution = {
        "schema_version": 1,
        "status": "OFFLINE_REPLAY_EXECUTED",
        "jobs": executions,
        "actions_planned": [action for item in executions for action in item["actions"]],
        "deferred_actions": schedule["deferred_actions"],
    }
    coverage = load_source_coverage(
        root / "config" / "source-coverage.yaml",
        {section_id for section_id, _ in SECTION_HEADINGS},
    )
    final_recovery = build_recovery_plan(
        packet, intelligence, coverage, load_local_config(root)["editorial_readiness"],
    )
    execution["yield"] = build_research_yield_report(
        execution, recovery_before=recovery_plan, recovery_after=final_recovery,
    )
    executed_by_need: dict[str, list[str]] = {}
    for action in execution["actions_planned"]:
        if isinstance(action.get("recovery_need_id"), str):
            executed_by_need.setdefault(action["recovery_need_id"], []).append(action["action_id"])
    scheduled_by_need: dict[str, list[str]] = {}
    for action in schedule["actions"]:
        if isinstance(action.get("recovery_need_id"), str):
            scheduled_by_need.setdefault(action["recovery_need_id"], []).append(action["action_id"])
    mappings = [
        {
            **mapping,
            "scheduled_action_ids": scheduled_by_need.get(mapping["recovery_need_id"], []),
            "executed_action_ids": executed_by_need.get(mapping["recovery_need_id"], []),
            "execution_state": (
                "EXECUTED" if executed_by_need.get(mapping["recovery_need_id"])
                else "SCHEDULED" if scheduled_by_need.get(mapping["recovery_need_id"])
                else "DEFERRED"
            ),
            "final_recovery_state": "OPEN",
        }
        for mapping in state["recovery_job_mappings"]
    ]
    input_hashes_after = {name: sha256_file(path) for name, path in paths.items()}
    if input_hashes_before != input_hashes_after:
        raise RuntimeError("PRESERVED_RECOVERY_REPLAY_INPUT_MUTATED")
    report = {
        "schema_version": 1,
        "status": "OFFLINE_RECOVERY_ROUTING_REPLAY_COMPLETE",
        "edition_date": edition_date,
        "source_run_id": source_run_id,
        "source_run_status": _load(paths["historical_state"]).get("stages", {}).get("research_recovery", {}).get("status"),
        "provider_called": False,
        "network_called": False,
        "article_generation_called": False,
        "source_git_revision": source_revision(root),
        "input_hashes": input_hashes_before,
        "historical_inputs_unchanged": True,
        "recovery_need_total": len(state["executable_recovery_need_ids"]),
        "recovery_needs_by_priority": dict(sorted(Counter(
            item["priority"] for item in state["recovery_job_mappings"]
        ).items())),
        "jobs_total": len(state["jobs"]),
        "p0_jobs_materialized": sum(item["priority"] == "P0_BLOCKING_EVIDENCE" for item in mappings),
        "p1_jobs_materialized": sum(item["priority"].startswith("P1_") for item in mappings),
        "actions_scheduled_by_priority": dict(sorted(Counter(
            item["priority_class"] for item in schedule["actions"]
        ).items())),
        "actions_executed_by_priority": dict(sorted(Counter(
            item["priority_class"] for item in execution["actions_planned"]
        ).items())),
        "final_offline_research_state": final_recovery["status"],
        "final_recovery_need_total": len(final_recovery["needs"]),
        "recovery_job_mappings": mappings,
        "yield": execution["yield"],
    }
    atomic_write_json(output_dir / "deep-research-state.json", state)
    atomic_write_json(output_dir / "execution-report.json", execution)
    atomic_write_json(output_dir / "replay-report.json", report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True, help="preserved edition date")
    parser.add_argument("--run-id", required=True, help="preserved source run ID")
    parser.add_argument("--output", help="new, separate directory for replay evidence")
    args = parser.parse_args()
    output = Path(args.output) if args.output else (
        ROOT / "acceptance" / "offline-recovery-replays" / args.date
        / args.run_id / f"replay-{uuid4().hex}"
    )
    try:
        report = replay_preserved_recovery(
            root=ROOT, edition_date=args.date, source_run_id=args.run_id,
            output_dir=output,
        )
    except (DeepResearchError, ValueError, RuntimeError) as exc:
        _emit({"status": "FAIL", "error_code": str(exc)})
        return 1
    _emit({
        "status": report["status"],
        "output": str(output.relative_to(ROOT)).replace("\\", "/"),
        "recovery_need_total": report["recovery_need_total"],
        "p0_jobs_materialized": report["p0_jobs_materialized"],
        "p1_jobs_materialized": report["p1_jobs_materialized"],
        "actions_executed_by_priority": report["actions_executed_by_priority"],
    })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
