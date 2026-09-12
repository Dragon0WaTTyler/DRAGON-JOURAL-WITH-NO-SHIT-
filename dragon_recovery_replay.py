#!/usr/bin/env python3
"""Replay preserved research without an editorial-provider call or articles."""

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
    build_event_bundles,
    build_observation_snapshot,
    build_research_yield_report,
    discovery_adapter_from_config,
    execute_research_round,
    replay_event_bundles_from_snapshot,
    replay_exact_source_roles,
    replay_recovery_after_execution,
    schedule_research_actions,
)
from dragon.provider_acceptance import OfflineReplayResearchAdapter, build_provider_seed_orchestrator
from dragon.research_recovery import build_recovery_plan
from dragon.source_coverage import load_source_coverage
from dragon.state import atomic_write_json, sha256_file, source_revision
from dragon.providers import SECTION_HEADINGS


ROOT = Path(__file__).resolve().parent


class _NoArticleProvider:
    """A guard object proving an offline seed replay cannot generate prose."""

    mode = "preserved-research-replay"
    available = True

    def articles(self, research: dict) -> list[dict]:
        raise AssertionError("PRESERVED_RESEARCH_REPLAY_MUST_NOT_GENERATE_ARTICLES")


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _emit(value: dict) -> None:
    print(json.dumps(value, ensure_ascii=True, indent=2))


def _input_paths(run_dir: Path) -> dict[str, Path]:
    return {
        "epoch0_packet": run_dir / "research" / "research-packet.json",
        "epoch0_intelligence": run_dir / "source-intelligence" / "report.json",
        "research_plan": run_dir / "research-planning" / "plan.json",
        "epoch0_state": run_dir / "deep-research" / "state.json",
        "epoch0_execution": run_dir / "deep-research" / "execution-report.json",
        "post_epoch0_packet": run_dir / "research" / "recovered-research-packet.json",
        "post_epoch0_intelligence": run_dir / "source-intelligence" / "recovered-report.json",
        "final_recovery_plan": run_dir / "research-recovery" / "plan.json",
        "historical_state": run_dir / "state.json",
    }


def replay_captured_event_observations(
    *, root: Path, edition_date: str, captured_run_id: str, output_dir: Path,
) -> dict:
    """Create a hash-bound diagnostic replay from captured observations only.

    It performs no requests and never writes to the historical run.  The
    resulting snapshot is explicitly TEST_REPLAY_EVIDENCE and is not read by
    the production pipeline as current-edition research.
    """
    run_dir = root / "daily-runs" / edition_date / "runs" / captured_run_id
    execution_path = run_dir / "deep-research" / "execution-report.json"
    packet_path = run_dir / "research" / "recovered-research-packet.json"
    if not execution_path.is_file() or not packet_path.is_file():
        raise ValueError("CAPTURED_EVENT_REPLAY_INPUT_MISSING")
    if output_dir.exists():
        raise ValueError("CAPTURED_EVENT_REPLAY_OUTPUT_ALREADY_EXISTS")
    hashes_before = {"execution": sha256_file(execution_path), "packet": sha256_file(packet_path)}
    execution, packet = _load(execution_path), _load(packet_path)
    jobs = [item for item in execution.get("jobs", []) if isinstance(item, dict)]
    observations = [item for job in jobs for item in job.get("observations", []) if isinstance(item, dict)]
    actions = [item for job in jobs for item in job.get("actions", []) if isinstance(item, dict)]
    captured_sources = [item for job in jobs for item in job.get("source_packet_patch", {}).get("sources", []) if isinstance(item, dict)]
    action_by_id = {item.get("action_id"): item for item in actions}
    role_unresolved_before = sum(
        item.get("source_class") == "unknown" and str(item.get("extraction_status")).upper() == "FETCHED"
        for item in observations
    )
    unknown_exact_ids_before = {
        item.get("observation_id") for item in observations
        if item.get("source_class") == "unknown" and str(item.get("extraction_status")).upper() == "FETCHED"
    }
    observations, resolved_sources = replay_exact_source_roles(observations, actions)
    sources = [*captured_sources, *resolved_sources]
    observations_by_id = {item.get("observation_id"): item for item in observations}
    leads = []
    for item in packet.get("discovery_event_leads", []):
        if not isinstance(item, dict) or not isinstance(item.get("event_skeleton"), dict):
            continue
        observation = observations_by_id.get(item.get("observation_id"), {})
        action = action_by_id.get((observation.get("provenance") or {}).get("action_id"), {})
        leads.append({
            **deepcopy(item),
            "event_lead_id": f"CAPTURED-{item['event_skeleton'].get('event_fingerprint')}",
            # Keep the original lead identity but let the current extractor
            # correct a captured skeleton before cross-source matching.
            "event_skeleton": deepcopy(observation.get("event_skeleton") or item["event_skeleton"]),
            "desk": action.get("desk"),
        })
    bundles, discoveries = build_event_bundles(observations, leads, sources, actions)
    snapshot = build_observation_snapshot(actions, observations, bundles)
    replay = replay_event_bundles_from_snapshot(snapshot)
    hashes_after = {"execution": sha256_file(execution_path), "packet": sha256_file(packet_path)}
    if hashes_before != hashes_after:
        raise RuntimeError("CAPTURED_EVENT_REPLAY_INPUT_MUTATED")
    replay_execution = {"source_packet_patch": {
        "sources": resolved_sources, "candidate_evidence_updates": [],
        "candidate_discoveries": discoveries, "event_leads": leads, "event_bundles": bundles,
    }}
    coverage = load_source_coverage(root / "config" / "source-coverage.yaml", {section_id for section_id, _ in SECTION_HEADINGS})
    readiness = load_local_config(root)["editorial_readiness"]
    replay_transition = replay_recovery_after_execution(packet, replay_execution, coverage, readiness)
    report = {
        "schema_version": 1, "status": "CAPTURED_EVENT_REPLAY_COMPLETE",
        "edition_date": edition_date, "captured_run_id": captured_run_id,
        "network_called": False, "provider_called": False, "article_generation_called": False,
        "historical_inputs_unchanged": True, "input_hashes": hashes_before,
        "snapshot_hash": snapshot["snapshot_hash"], "starting_event_leads": len(leads),
        "evidence_bundles": len(bundles), "validated_events": sum(item.get("state") == "EVENT_VALIDATED" for item in bundles),
        "partial_bundles": sum(item.get("state") == "EVENT_EVIDENCE_PARTIAL" for item in bundles),
        "candidate_discoveries": len(discoveries), "production_evidence_reuse": replay["production_evidence_reuse"],
        "role_unresolved_before": role_unresolved_before,
        "newly_resolved_primary_roles": sum(bool(item.get("observation_id") in unknown_exact_ids_before and item.get("source_class") == "primary") for item in observations),
        "newly_resolved_independent_roles": sum(bool(item.get("observation_id") in unknown_exact_ids_before and item.get("source_class") == "independent") for item in observations),
        "promoted_candidates": len(discoveries),
        "recovery_status_after_transition": replay_transition.get("status"),
        "remaining_needs_after_transition": replay_transition.get("recovery", {}).get("needs", []),
        "closed_need_ids": sorted({item.get("need_id") for item in build_recovery_plan(packet, _load(run_dir / "source-intelligence" / "recovered-report.json"), coverage, readiness).get("needs", [])} - {item.get("need_id") for item in replay_transition.get("recovery", {}).get("needs", [])}),
        "promoted_candidate_placements": [
            {"section_id": section.get("section_id"), "candidate_id": section.get("selected_candidate_id")}
            for section in replay_transition.get("packet", {}).get("sections", [])
            if any(candidate.get("discovered_by") == "VALIDATED_DISTINCT_EVENT_RECOVERY" and candidate.get("id") == section.get("selected_candidate_id") for candidate in section.get("candidates", []))
        ],
        "bundles": bundles,
    }
    atomic_write_json(output_dir / "observation-snapshot.json", snapshot)
    atomic_write_json(output_dir / "captured-event-replay-report.json", report)
    return report


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
    packet = _load(paths["post_epoch0_packet"])
    intelligence = _load(paths["post_epoch0_intelligence"])
    research_plan = _load(paths["research_plan"])
    epoch0_state = _load(paths["epoch0_state"])
    epoch0_execution = _load(paths["epoch0_execution"])
    config = load_deep_research_config(root / "config" / "deep-research.yaml")
    # Reuse the historical Epoch 0 result as input, then reconstruct only the
    # post-execution delta.  The local adapter makes Epoch 1 routing observable
    # without repeating network work or changing historical evidence.
    issues = validate_deep_research_state(epoch0_state)
    if issues:
        raise DeepResearchError(
            f"RECOVERY_JOB_MATERIALIZATION_FAILED:{';'.join(issues)}"
        )
    adapter = OfflineReplayResearchAdapter(
        reason="OFFLINE_PRESERVED_RUN_ROUTING_REPLAY_NO_NETWORK_OR_PROVIDER"
    )
    coverage = load_source_coverage(
        root / "config" / "source-coverage.yaml",
        {section_id for section_id, _ in SECTION_HEADINGS},
    )
    post_epoch0 = build_recovery_plan(
        packet, intelligence, coverage, load_local_config(root)["editorial_readiness"],
    )
    prior_need_ids = set(epoch0_state.get("executable_recovery_need_ids", []))
    delta_needs = [need for need in post_epoch0["needs"] if need["need_id"] not in prior_need_ids]
    state = build_deep_research_state(
        packet, intelligence, research_plan, {"needs": delta_needs, "status": post_epoch0["status"]}, config,
        run_scope_id=f"offline-replay:{source_run_id}", recovery_epoch=1, recovery_only=True,
    )
    issues = validate_deep_research_state(state)
    if issues:
        raise DeepResearchError(f"RECOVERY_JOB_MATERIALIZATION_FAILED:{';'.join(issues)}")
    schedule = schedule_research_actions(state["jobs"], config)
    actions_by_job: dict[str, list[dict]] = {}
    for action in schedule["actions"]:
        actions_by_job.setdefault(action["job_id"], []).append(action)
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
    final_recovery = build_recovery_plan(
        packet, intelligence, coverage, load_local_config(root)["editorial_readiness"],
    )
    execution["yield"] = build_research_yield_report(
        execution, recovery_before=post_epoch0, recovery_after=final_recovery,
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
        "epoch_0": {"need_count": len(prior_need_ids), "jobs": len(epoch0_state.get("recovery_job_mappings", [])), "actions": len(epoch0_execution.get("actions_planned", []))},
        "epoch_1": {"delta_need_count": len(delta_needs), "jobs": len(state["recovery_job_mappings"]), "actions": len(execution["actions_planned"])},
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


def rehearse_preserved_run_with_discovery(
    *, root: Path, edition_date: str, source_run_id: str, output_dir: Path,
) -> dict:
    """Run both bounded recovery epochs from an immutable seed with real discovery.

    The source provider packet is never invoked again.  The normal V5 pipeline
    receives its normalized seed through ``SeedResearchProvider`` and the
    configured non-generative discovery chain.  It may fetch public pages, but
    cannot generate articles, publish, schedule work, or alter the source run.
    """
    source_run = root / "daily-runs" / edition_date / "runs" / source_run_id
    paths = _input_paths(source_run)
    missing = [name for name, path in paths.items() if not path.is_file()]
    if missing:
        raise ValueError(f"PRESERVED_RECOVERY_REPLAY_INPUT_MISSING:{','.join(missing)}")
    if output_dir.exists():
        raise ValueError("PRESERVED_RECOVERY_REPLAY_OUTPUT_ALREADY_EXISTS")
    source_state = _load(paths["historical_state"])
    source_attempt_id = str(source_state.get("source_attempt_id") or "")
    raw_path = root / "acceptance" / "provider-trials" / edition_date / "attempts" / source_attempt_id / "research.raw.json"
    if not raw_path.is_file():
        raise ValueError("PRESERVED_PROVIDER_RAW_PACKET_MISSING")
    input_paths = {**paths, "raw_provider_packet": raw_path}
    input_hashes = {name: sha256_file(path) for name, path in input_paths.items()}
    adapter = discovery_adapter_from_config(root)
    if adapter is None:
        raise ValueError("DISCOVERY_ADAPTER_UNCONFIGURED")
    orchestrator = build_provider_seed_orchestrator(
        root=root,
        edition_date=edition_date,
        provider=_NoArticleProvider(),
        normalized_packet=_load(paths["epoch0_packet"]),
        raw_packet_path=raw_path,
        raw_packet_sha256=input_hashes["raw_provider_packet"],
        mode="PRESERVED_REAL_DISCOVERY_REHEARSAL",
        source_attempt_id=f"preserved-rehearsal:{source_attempt_id}",
        research_adapter=adapter,
        offline_replay=True,
    )
    state = orchestrator.run()
    run_dir = orchestrator.store.run_dir
    execution = _load(run_dir / "deep-research" / "execution-report.json")
    recovery = _load(run_dir / "research-recovery" / "plan.json")
    yield_report = _load(run_dir / "deep-research" / "yield-report.json")
    epoch1_path = run_dir / "deep-research" / "epoch-1-execution-report.json"
    epoch1 = _load(epoch1_path) if epoch1_path.is_file() else {"status": "NOT_CREATED", "jobs": []}
    input_hashes_after = {name: sha256_file(path) for name, path in input_paths.items()}
    if input_hashes != input_hashes_after:
        raise RuntimeError("PRESERVED_RECOVERY_REPLAY_INPUT_MUTATED")
    report = {
        "schema_version": 1,
        "status": "PRESERVED_REAL_DISCOVERY_REHEARSAL_COMPLETE",
        "edition_date": edition_date,
        "source_run_id": source_run_id,
        "rehearsal_run_id": orchestrator.store.run_id,
        "rehearsal_run_directory": str(run_dir.relative_to(root)).replace("\\", "/"),
        "provider_called": False,
        "network_called": True,
        "publisher_discovery_states": deepcopy(getattr(adapter, "publisher_discovery_states", {})),
        "article_generation_called": False,
        "source_git_revision": source_revision(root),
        "input_hashes": input_hashes,
        "historical_inputs_unchanged": True,
        "research_recovery_status": recovery["status"],
        "article_generation_allowed": recovery["article_generation_allowed"],
        "recovery_epochs": recovery.get("recovery_epochs", {}),
        "epoch_0_actions": len(execution.get("actions_planned", [])),
        "epoch_1_actions": len(epoch1.get("actions_planned", [])),
        "yield": yield_report,
        "remaining_recovery_needs": [item["need_id"] for item in recovery.get("needs", [])],
        "stage_status": {
            name: record.get("status") for name, record in state.get("stages", {}).items()
        },
    }
    atomic_write_json(output_dir / "rehearsal-report.json", report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True, help="preserved edition date")
    parser.add_argument("--run-id", required=True, help="preserved source run ID")
    parser.add_argument("--output", help="new, separate directory for replay evidence")
    parser.add_argument("--real-discovery", action="store_true", help="use configured read-only discovery; never calls the editorial provider")
    args = parser.parse_args()
    output = Path(args.output).resolve() if args.output else (
        ROOT / "acceptance" / ("real-source-recovery-rehearsals" if args.real_discovery else "offline-recovery-replays") / args.date
        / args.run_id / f"replay-{uuid4().hex}"
    )
    try:
        report = (
            rehearse_preserved_run_with_discovery(
                root=ROOT, edition_date=args.date, source_run_id=args.run_id, output_dir=output,
            )
            if args.real_discovery else replay_preserved_recovery(
                root=ROOT, edition_date=args.date, source_run_id=args.run_id, output_dir=output,
            )
        )
    except (DeepResearchError, ValueError, RuntimeError) as exc:
        _emit({"status": "FAIL", "error_code": str(exc)})
        return 1
    _emit({
        "status": report["status"],
        "output": str(output.relative_to(ROOT)).replace("\\", "/"),
        "recovery_need_total": report.get("recovery_need_total", len(report.get("remaining_recovery_needs", []))),
        "p0_jobs_materialized": report.get("p0_jobs_materialized"),
        "p1_jobs_materialized": report.get("p1_jobs_materialized"),
        "actions_executed_by_priority": report.get("actions_executed_by_priority"),
    })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
