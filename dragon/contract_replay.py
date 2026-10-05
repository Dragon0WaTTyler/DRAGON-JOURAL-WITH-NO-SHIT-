"""Current-code comparison using immutable live inputs, with no execution adapter."""

from copy import deepcopy
import json
import hashlib
from pathlib import Path
import subprocess

from dragon.archive import verify_acceptance_bundle
from dragon.config import load_local_config
from dragon.deep_research import build_deep_research_state, load_deep_research_config, validate_deep_research_state
from dragon.deep_research_executor import plan_research_actions, schedule_research_actions
from dragon.providers import LocalCommandEditorialProvider, SECTION_HEADINGS, editorial_provider_from_config
from dragon.research_planning import build_research_plan, load_research_budget_config
from dragon.research_recovery import build_recovery_plan
from dragon.source_coverage import load_source_coverage
from dragon.source_intelligence import build_source_intelligence
from dragon.state import atomic_write_json, sha256_file


def replay_contract_isolation(bundle: Path, *, code_root: Path) -> dict:
    """Compare with the recorded failure, not rewrite its historical verdict.

    Unlike original-code reproduction, this intentionally uses current code.
    Its revision and hashes are recorded separately from the input manifest.
    No provider, search, retrieval, orchestrator, or publication runner exists
    in this path. Scheduler decisions are data; they are never executed.
    """
    if code_root.resolve() != Path(__file__).resolve().parents[1]:
        raise ValueError("comparison code root must identify the imported implementation")
    manifest = verify_acceptance_bundle(bundle)
    artifacts, frozen = bundle / "artifacts", bundle / "configuration"

    def read(relative):
        return json.loads((artifacts / relative).read_text(encoding="utf-8"))

    raw = read("provider-research/research.raw.json")
    request = read("provider-research/request.json")
    invocation = read("provider-research/invocation.json")
    config = load_local_config(frozen)
    provider = editorial_provider_from_config(config, require_proven=False)
    if not isinstance(provider, LocalCommandEditorialProvider):
        raise ValueError("saved provider configuration has no supported local normalizer")
    packet = provider.normalize_research_packet(manifest["edition_date"], deepcopy(raw),
        research_targeting=request["provider_input"].get("research_targeting"), retrieved_at=invocation["responded_at"])
    for source in packet["sources"]:
        source.update(verification_status="PROVIDER_REPORTED", evidence_relation=None, directness=None, provenance=None)
    packet["provider_mode"] = provider.mode
    intelligence = build_source_intelligence(packet)
    budget = load_research_budget_config(frozen / "config/research-budget.yaml")
    readiness = config["editorial_readiness"]
    plan = build_research_plan(packet, intelligence, budget, readiness)
    coverage = load_source_coverage(frozen / "config/source-coverage.yaml", {s[0] for s in SECTION_HEADINGS})
    recovery = build_recovery_plan(packet, intelligence, coverage, readiness)
    deep_config = load_deep_research_config(frozen / "config/deep-research.yaml", frozen / "config/deep-research-schema.json")
    monitoring = read("source-monitoring/report.json")
    state = build_deep_research_state(packet, intelligence, plan, recovery, deep_config,
        discovery_signals=monitoring.get("discovery_candidates", []), run_scope_id=manifest["run_id"])
    issues = validate_deep_research_state(state)
    if issues:
        raise ValueError("Replay materialization invalid: " + "; ".join(issues))
    actions = [action for job in state["jobs"] for action in plan_research_actions(job, deep_config)]
    schedule = schedule_research_actions(state["jobs"], deep_config)
    raw_candidates = {c["id"]: c for section in raw["sections"] for field in ("candidates", "recovery_candidates")
        for c in section.get(field, []) if isinstance(c, dict) and isinstance(c.get("id"), str)}
    candidate_audits = []
    for target in packet["provider_response_validation"]["hard_targets"]:
        for record in target["raw_target_results"]:
            matches = record.get("candidate_matches")
            for match in matches if isinstance(matches, list) else []:
                candidate_id = match.get("candidate_id") if isinstance(match, dict) else None
                candidate = raw_candidates.get(candidate_id, {}) if isinstance(candidate_id, str) else {}
                references = {sid for field in ("discovery_source_ids", "verification_source_ids",
                    "primary_evidence_source_ids", "independent_evidence_source_ids")
                    for sid in (candidate.get(field) if isinstance(candidate.get(field), list) else []) if isinstance(sid, str)}
                rejection = next((r for r in target["rejected_candidates"] if r["candidate_id"] == candidate_id), None)
                candidate_audits.append({"target_id": target["target_id"], "candidate_id": candidate_id,
                    "raw_match": deepcopy(match), "raw_candidate": deepcopy(candidate),
                    "source_references": [{key: s.get(key) for key in ("id", "url", "source_type", "origin")}
                        for s in raw["sources"] if s["id"] in references],
                    "contract_result": "REJECTED" if rejection or target["target_contract_status"] == "FAIL" else "PASS",
                    "rejection": rejection})
    source_hashes = {path.relative_to(code_root).as_posix(): sha256_file(path)
        for path in sorted((code_root / "dragon").glob("*.py"))}
    source_hashes["dragon_acceptance_bundle.py"] = sha256_file(code_root / "dragon_acceptance_bundle.py")
    verify_acceptance_bundle(bundle)
    return {"schema_version": 1, "mode": "CURRENT_IMPLEMENTATION_CONTRACT_ISOLATION_COMPARISON",
        "input_run_id": manifest["run_id"], "input_manifest_sha256": sha256_file(bundle / "manifest.json"),
        "input_raw_sha256": sha256_file(artifacts / "provider-research/research.raw.json"),
        "input_source_revision": manifest["source_git_revision"],
        "comparison_revision": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=code_root, text=True).strip(),
        "comparison_implementation_hashes": source_hashes,
        "provider_calls": 0, "network_calls": 0, "actions_executed": 0,
        "normalized_packet": packet, "source_intelligence": intelligence, "research_plan": plan,
        "candidate_audits": candidate_audits,
        "recovery_plan": recovery, "scheduler_inputs": state, "scheduler_configuration": deep_config,
        "materialized_actions": actions,
        "materialization_counts": {"entries": len(actions), "distinct_action_ids": len({a["action_id"] for a in actions}),
            "selected": len(schedule["actions"]), "deferred": len(schedule["deferred_actions"])},
        "scheduler_allocation": schedule, "original_failure": invocation.get("error_code")}


def preserve_contract_comparison(bundle: Path, *, code_root: Path, destination: Path | None = None) -> dict:
    """Replay twice and publish an exclusive, hash-bound derivative receipt.

    Receipts live outside the immutable input bundle. Interrupted writes stay
    explicitly incomplete and are never overwritten on an ordinary retry.
    """
    first = replay_contract_isolation(bundle, code_root=code_root)
    if first != replay_contract_isolation(bundle, code_root=code_root):
        raise ValueError("contract comparison was not deterministic")
    implementation_digest = hashlib.sha256(json.dumps(first["comparison_implementation_hashes"],
        sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    comparison = json.dumps(first, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    root = (destination or bundle.parent / "contract-comparisons").resolve()
    if root.is_relative_to(bundle.resolve()) or root.is_relative_to(code_root.resolve()):
        raise ValueError("comparison storage must be outside the immutable bundle and disposable worktree")
    report = root / f"{first['input_run_id']}-{first['input_manifest_sha256']}-{implementation_digest}"
    if report.exists():
        if (report / "INCOMPLETE").exists():
            raise ValueError("existing comparison is incomplete; refusing overwrite")
        if sha256_file(report / "receipt.json") != (report / "receipt.sha256").read_text(encoding="ascii").strip():
            raise ValueError("existing comparison receipt changed; refusing overwrite")
        receipt = json.loads((report / "receipt.json").read_text(encoding="utf-8"))
        if (receipt.get("status") != "COMPLETE" or set(receipt.get("artifacts", {})) != {"comparison.json", "report.md"}
            or receipt.get("input_manifest_sha256") != first["input_manifest_sha256"]
            or receipt.get("comparison_revision") != first["comparison_revision"]
            or receipt.get("comparison_implementation_sha256") != implementation_digest):
            raise ValueError("existing comparison receipt identity differs; refusing overwrite")
        for name, digest in receipt["artifacts"].items():
            if sha256_file(report / name) != digest:
                raise ValueError("existing comparison artifact changed; refusing overwrite")
        if (report / "comparison.json").read_text(encoding="utf-8") != comparison:
            raise ValueError("existing comparison differs; refusing overwrite")
        return {**receipt, "receipt": str(report / "receipt.json")}
    report.mkdir(parents=True, exist_ok=False)
    (report / "INCOMPLETE").write_text("No valid comparison receipt yet.\n", encoding="utf-8")
    (report / "comparison.json").write_text(comparison, encoding="utf-8")
    schedule = first["scheduler_allocation"]
    selected = {a["action_id"] for a in schedule["actions"]}
    lines = ["# Exact contract comparison", "", "Current implementation comparison; original verdict is unchanged.", "",
        f"Input manifest SHA-256: `{first['input_manifest_sha256']}`", "",
        f"Input revision: `{first['input_source_revision']}`; comparison revision: `{first['comparison_revision']}`.", "",
        "Provider calls: 0; network calls: 0; actions executed: 0. Two comparisons were exactly equal.", "",
        "## Target results", "", "| Target | Raw | Accepted | Rejected | Effective disposition | Contract |", "|---|---:|---:|---:|---|---|"]
    for target in first["normalized_packet"]["provider_response_validation"]["hard_targets"]:
        lines.append("| " + " | ".join(str(target[key]) for key in ("target_id", "raw_candidate_count", "accepted_candidate_count",
            "rejected_candidate_count", "target_disposition_effective", "target_contract_status")) + " |")
    lines += ["", "## Each raw hard-target candidate", ""]
    for audit in first["candidate_audits"]:
        candidate = audit["raw_candidate"]
        lines += [f"### {audit['candidate_id']} ({audit['target_id']})", "",
            f"Contract: {audit['contract_result']}. Rejection: {audit['rejection'] or 'None'}.", "",
            f"PRIMARY IDs: {candidate.get('primary_evidence_source_ids')}; INDEPENDENT IDs: {candidate.get('independent_evidence_source_ids')}; "
            f"exact artifact IDs: {audit['raw_match'].get('exact_artifact_source_ids') if isinstance(audit['raw_match'], dict) else None}.", ""]
        lines += [f"- {s['id']} ({s['source_type']}): {s['url']}" for s in audit["source_references"]]
        lines += [""]
    lines += ["", "## All materialized actions", "", "| Action ID | Type | Candidate | Source | Role | Lane | Decision | URL / query |", "|---|---|---|---|---|---|---|---|"]
    source_ids_by_url = {s["url"]: s["id"] for s in first["normalized_packet"]["sources"]}
    seen_ids = set()
    for action in first["materialized_actions"]:
        decision = "SELECTED" if action["action_id"] in selected else "DEFERRED"
        if action["action_id"] in seen_ids:
            decision = "DUPLICATE_" + decision + "_ID"
        seen_ids.add(action["action_id"])
        row = [action["action_id"], action["action_type"], action.get("provider_candidate_id"), source_ids_by_url.get(action.get("provider_supplied_url")),
            action.get("provider_source_role"), action.get("target_editorial_function"),
            decision, action.get("target") or action.get("query")]
        lines.append("| " + " | ".join(str(x or "").replace("|", "\\|").replace("\n", " ") for x in row) + " |")
    counts = first["materialization_counts"]
    lines += ["", f"Materialized entries: {counts['entries']}; distinct action IDs: {counts['distinct_action_ids']}; "
        f"scheduler selections: {counts['selected']}; deferred entries: {counts['deferred']}.", "",
        "Full normalized data, rejected candidates, jobs, scheduler configuration, selection order, and deferred actions are in comparison.json.",
        "Raw inputs and frozen configuration remain in the verified input bundle.", ""]
    (report / "report.md").write_text("\n".join(lines), encoding="utf-8")
    verify_acceptance_bundle(bundle)
    receipt = {"schema_version": 1, "status": "COMPLETE", "mode": first["mode"],
        "input_run_id": first["input_run_id"], "input_manifest_sha256": first["input_manifest_sha256"],
        "input_raw_sha256": first["input_raw_sha256"], "comparison_revision": first["comparison_revision"],
        "comparison_implementation_sha256": implementation_digest, "deterministic_replays": 2,
        "provider_calls": 0, "network_calls": 0, "actions_executed": 0,
        "artifacts": {name: sha256_file(report / name) for name in ("comparison.json", "report.md")}}
    atomic_write_json(report / "receipt.json", receipt)
    (report / "receipt.sha256").write_text(sha256_file(report / "receipt.json") + "\n", encoding="ascii")
    (report / "INCOMPLETE").unlink()
    return {**receipt, "receipt": str(report / "receipt.json")}
