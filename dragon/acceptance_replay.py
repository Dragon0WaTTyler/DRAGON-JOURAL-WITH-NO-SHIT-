"""Provider-free replay from a verified, immutable research acceptance bundle."""

from copy import deepcopy
import json
from pathlib import Path
import subprocess

from dragon.archive import ArchiveError, verify_acceptance_bundle
from dragon.config import load_local_config
from dragon.deep_research import build_deep_research_state, load_deep_research_config
from dragon.deep_research_executor import schedule_research_actions, continue_required_research_jobs, merge_required_research_continuations
from dragon.providers import LocalCommandEditorialProvider, ProviderError, SECTION_HEADINGS, editorial_provider_from_config
from dragon.research_planning import build_research_plan, load_research_budget_config
from dragon.research_recovery import build_recovery_plan
from dragon.source_coverage import load_source_coverage
from dragon.source_intelligence import build_source_intelligence
from dragon.state import sha256_file
from dragon.hard_acquisition import candidate_claim_contexts


def replay_acceptance_bundle(bundle: Path, *, code_root: Path) -> dict:
    manifest = verify_acceptance_bundle(bundle, require_complete=False)
    raw_path = bundle / "artifacts/provider-research/research.raw.json"
    invocation_path = bundle / "artifacts/provider-research/invocation.json"
    if not raw_path.is_file() and invocation_path.is_file():
        invocation = json.loads(invocation_path.read_text(encoding="utf-8"))
        if (invocation.get("failure_classification") == "PROVIDER_REQUEST_SCHEMA_REJECTED_PRE_MODEL"
            or "invalid_json_schema" in invocation.get("error_detail", "")):
            return {"schema_version": 1, "run_id": manifest["run_id"],
                "provider_calls": 0, "network_calls": 0, "checks": {"failure_classification": "PROVIDER_REQUEST_SCHEMA_REJECTED_PRE_MODEL"},
                "FRESH_LIVE_REPLAY": "NOT_APPLICABLE_NO_PROVIDER_PACKET"}
    manifest = verify_acceptance_bundle(bundle)
    revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=code_root,
        capture_output=True, text=True, timeout=10, check=True).stdout.strip()
    if revision != manifest["source_git_revision"]:
        raise ArchiveError("ACCEPTANCE_REPLAY_REVISION_MISMATCH", "checkout the manifest's implementation commit before replay")
    for relative, digest in manifest.get("implementation_hashes", {}).items():
        if not (code_root / relative).is_file() or sha256_file(code_root / relative) != digest:
            raise ArchiveError("ACCEPTANCE_REPLAY_IMPLEMENTATION_MISMATCH", relative)
    artifacts, config_root = bundle / "artifacts", bundle / "configuration"

    def read(relative):
        return json.loads((artifacts / relative).read_text(encoding="utf-8"))

    mandatory_lanes = tuple(sorted({t["semantic_lane"] for t in read("research/targeting-request.json").get("unresolved_targets", [])
        if t.get("hard") and t.get("mandatory") and t.get("semantic_lane") in {"ACCOUNTABILITY", "SERVICE"}})) if (artifacts / "research/targeting-request.json").is_file() else ()

    config = load_local_config(config_root)
    provider = editorial_provider_from_config(config, require_proven=False)
    if not isinstance(provider, LocalCommandEditorialProvider):
        raise ArchiveError("ACCEPTANCE_REPLAY_CONFIGURATION_INVALID", "saved provider normalizer configuration is unavailable")
    invocation = read("provider-research/invocation.json")
    request = read("provider-research/request.json")
    targeting = request["provider_input"].get("research_targeting")
    results = {}
    normalization = None
    expected_normalization = None
    expected_error = invocation.get("error_code")
    try:
        raw = read("provider-research/research.raw.json")
        if (artifacts / "provider-research/normalized-research-packet.json").is_file():
            expected_normalization = read("provider-research/normalized-research-packet.json")
            retrieved_at = expected_normalization["sources"][0]["accessed_at"]
        else:
            retrieved_at = invocation.get("responded_at")
        normalization = provider.normalize_research_packet(manifest["edition_date"], deepcopy(raw),
            research_targeting=targeting, retrieved_at=retrieved_at)
        for source in normalization.get("sources", []):
            source.update(verification_status="PROVIDER_REPORTED", evidence_relation=None, directness=None, provenance=None)
        results["normalization"] = "PASS" if normalization == expected_normalization else "FAIL"
        results["hard_target_dispositions"] = "PASS" if normalization.get("hard_target_results") == (expected_normalization or {}).get("hard_target_results") else "FAIL"
    except (ProviderError, json.JSONDecodeError) as exc:
        actual = getattr(exc, "code", "AI_PROVIDER_RESPONSE_INVALID")
        results["normalization"] = "PASS" if expected_error == actual and expected_normalization is None else "FAIL"
        results["hard_target_dispositions"] = results["normalization"]
        results["reproduced_failure"] = actual

    epoch_results = []
    if (artifacts / "deep-research/state.json").is_file():
        packet = read("research/research-packet.json")
        intelligence = build_source_intelligence(packet)
        results["candidate_classification"] = "PASS" if intelligence == read("source-intelligence/report.json") else "FAIL"
        readiness = config["editorial_readiness"]
        coverage = load_source_coverage(config_root / "config/source-coverage.yaml", {item[0] for item in SECTION_HEADINGS})
        budget = load_research_budget_config(config_root / "config/research-budget.yaml")
        plan = build_research_plan(packet, intelligence, budget, readiness)
        results["research_planning"] = "PASS" if plan == read("research-planning/plan.json") else "FAIL"
        deep_config = load_deep_research_config(config_root / "config/deep-research.yaml", config_root / "config/deep-research-schema.json")
        recovery = build_recovery_plan(packet, intelligence, coverage, readiness, mandatory_research_lanes=mandatory_lanes)
        monitoring = read("source-monitoring/report.json")
        recreated = build_deep_research_state(packet, intelligence, plan, recovery, deep_config,
            discovery_signals=monitoring.get("discovery_candidates", []), run_scope_id=manifest["run_id"])
        states = [(0, recreated, "deep-research/state.json", "deep-research/scheduler-allocation.json")]
        if (artifacts / "deep-research/epoch-1-state.json").is_file():
            inputs = read("deep-research/epoch-1-inputs.json")
            recreated1 = build_deep_research_state(inputs["packet"], inputs["intelligence"], plan,
                inputs["recovery_plan"], deep_config, run_scope_id=manifest["run_id"], recovery_epoch=1, recovery_only=True)
            continuations = continue_required_research_jobs(recreated, read("deep-research/execution-report.json"), deep_config, mandatory_lanes)
            open_lanes = {n.get("target_editorial_function") for n in inputs["recovery_plan"].get("needs", [])}
            continuations = [j for j in continuations if any(a.get("target_editorial_function") in open_lanes for a in j["required_continuation_actions"])]
            if continuations:
                recreated1 = merge_required_research_continuations(recreated1, continuations, inputs["recovery_plan"]["needs"])
            states.append((1, recreated1, "deep-research/epoch-1-state.json", "deep-research/epoch-1-scheduler-allocation.json"))
        for epoch, recreated, state_path, schedule_path in states:
            prior_general = epoch == 1 and any(not a.get("target_editorial_function")
                for j in read("deep-research/execution-report.json").get("jobs", []) for a in j.get("actions", []))
            expected_schedule = read(schedule_path)
            staged = 'hard_acquisition' in expected_schedule
            previous_budget = read('deep-research/execution-report.json').get('round_execution_budget', {}) if epoch else {}
            schedule = schedule_research_actions(recreated['jobs'], deep_config, mandatory_lanes=mandatory_lanes,
                general_opportunity_executed=prior_general,
                acquisition_receipt=(previous_budget.get('hard_acquisition') or {}) if staged else None,
                remaining_total_actions=(1 if epoch else 2) * deep_config['executor']['maximum_actions_per_round'],
                candidate_claim_contexts=candidate_claim_contexts(packet) if staged and not epoch else None)
            selected = [item["action_id"] for item in schedule["actions"]]
            allocation = schedule["budget_allocation"]
            epoch_results.append({
                "epoch": epoch, "action_materialization": "PASS" if recreated == read(state_path) else "FAIL",
                "scheduler_allocation": "PASS" if schedule == expected_schedule else "FAIL",
                "selected_actions": selected,
                "deferred_actions": [item["action_id"] for item in schedule["deferred_actions"]],
                "budget": "PASS" if len(selected) <= allocation["round_cap"] == 8 and allocation["budget_increased"] is False else "FAIL",
                "budget_allocation": allocation,
            })
        results["action_materialization"] = "PASS" if all(item["action_materialization"] == "PASS" for item in epoch_results) else "FAIL"
        results["scheduling"] = "PASS" if all(item["scheduler_allocation"] == "PASS" for item in epoch_results) else "FAIL"
        results["budget_accounting"] = "PASS" if all(item["budget"] == "PASS" for item in epoch_results) else "FAIL"
    else:
        for name in ("candidate_classification", "action_materialization", "scheduling", "budget_accounting"):
            results[name] = "NOT_REACHED" if expected_error else "FAIL"
    passed = all(value in {"PASS", "NOT_REACHED"} for key, value in results.items() if key != "reproduced_failure")
    # Re-read hashes after replay too. No archived artifact is rewritten.
    verify_acceptance_bundle(bundle)
    return {"schema_version": 1, "run_id": manifest["run_id"], "source_git_revision": revision,
        "provider_calls": 0, "network_calls": 0, "checks": results, "epochs": epoch_results,
        "FRESH_LIVE_REPLAY": "PASS" if passed else "FAIL"}
