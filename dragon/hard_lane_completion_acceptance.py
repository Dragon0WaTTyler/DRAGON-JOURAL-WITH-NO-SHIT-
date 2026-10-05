"""Pure sealed replay plus prospective allocation audit; no live adapters."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
from uuid import uuid4

from dragon.archive import LocalAcceptanceArchive, verify_acceptance_bundle
from dragon.deep_research_executor import continue_required_research_jobs, schedule_research_actions, reconcile_discovery_leads
from dragon.research_finality_acceptance import evaluate, preserved_inputs
from dragon.research_finality import digest
from dragon.state import atomic_write_json, sha256_file


def audit_completion_inputs(inputs: dict) -> dict:
    historical = evaluate(inputs)
    lanes = tuple(historical["finality"]["required_lanes"])
    epochs = inputs["epochs"]
    recorded = {a["action_id"]: a for e in epochs for j in e["execution"].get("jobs", []) for a in j.get("actions", [])}
    def allocation(jobs, *, previous_general=False):
        schedule = schedule_research_actions(jobs, inputs["config"], mandatory_lanes=lanes,
                                             general_opportunity_executed=previous_general)
        availability = []
        for a in schedule["actions"]:
            # The explicit new policy marker and post-response yield are not
            # dispatch material. Every other original field must match.
            dispatch = lambda item: {k: v for k, v in item.items() if k not in {"required_protocol", "actual_information_gain"}}
            old = recorded.get(a["action_id"])
            available = old is not None and dispatch(a) == dispatch(old)
            availability.append({"action_id": a["action_id"], "lane": a.get("target_editorial_function"),
                "response_state": "EXACT_PRESERVED_RESPONSE_AVAILABLE" if available else "NO_EXACT_PRESERVED_RESPONSE"})
        return {"schedule": schedule, "response_availability": availability,
                "execution_status": "PLANNING_ONLY_NO_NEW_RESEARCH_EXECUTED"}
    initial = allocation(epochs[0]["state"]["jobs"])
    carries = continue_required_research_jobs(epochs[0]["state"], epochs[0]["execution"], inputs["config"], lanes)
    second_jobs = [*epochs[1]["state"]["jobs"], *carries] if len(epochs) > 1 else carries
    general = any(not a.get("target_editorial_function") for j in epochs[0]["execution"].get("jobs", []) for a in j.get("actions", []))
    continuation = allocation(second_jobs, previous_general=general)
    observations = deepcopy([o for e in epochs for j in e["execution"].get("jobs", []) for o in j.get("observations", [])])
    lead_audit = reconcile_discovery_leads(observations, list(recorded.values()))
    service_actions = {a["action_id"] for a in recorded.values() if a.get("target_editorial_function") == "SERVICE"}
    service_leads = [r for r in lead_audit if r["parent_action_id"] in service_actions]
    return {"schema_version": 1, "provider_calls": 0, "network_calls": 0, "publication_status": "NOT_ENTERED",
        "parents": inputs["parents"], "historical_replay": historical,
        "prospective_initial_allocation": initial, "prospective_continuation_from_actual_checkpoint": continuation,
        "actual_service_lead_audit": service_leads,
        "limits": {"round_cap": 8, "maximum_epochs": 2, "edition_action_ceiling": 16, "budget_increased": False},
        "limitation": "Prospective plans are not executed research. Uncaptured responses remain unknown; original finality stays blocked."}


def replay_completion_review(bundle: Path) -> dict:
    manifest = verify_acceptance_bundle(bundle)
    if manifest.get("bundle_type") != "OFFLINE_HARD_LANE_COMPLETION_REVIEW":
        raise ValueError("HARD_LANE_REVIEW_BUNDLE_INVALID")
    directory = bundle / "artifacts/completion"
    inputs = json.loads((directory / "inputs.json").read_text(encoding="utf-8"))
    saved = json.loads((directory / "decision.json").read_text(encoding="utf-8"))
    result = audit_completion_inputs(inputs)
    if result != saved or result != audit_completion_inputs(deepcopy(inputs)):
        raise ValueError("HARD_LANE_COMPLETION_REPLAY_MISMATCH")
    receipt = json.loads((directory / "replay.json").read_text(encoding="utf-8"))
    if receipt["inputs_sha256"] != digest(inputs) or receipt["decision_sha256"] != digest(saved):
        raise ValueError("HARD_LANE_COMPLETION_RECEIPT_MISMATCH")
    return {"status": "PASS", "run_id": manifest["run_id"], "provider_calls": 0, "network_calls": 0,
        "manifest_sha256": sha256_file(bundle / "manifest.json"), "decision_sha256": digest(result),
        "historical_verdicts": result["historical_replay"]["verdicts"]}


def preserve_completion_review(provider: Path, retrieval: Path, evidence_review: Path, *, root: Path) -> dict:
    inputs = preserved_inputs(provider, retrieval, evidence_review)
    result = audit_completion_inputs(inputs)
    if result != audit_completion_inputs(deepcopy(inputs)):
        raise ValueError("HARD_LANE_COMPLETION_NONDETERMINISTIC")
    run_id = "hard-lane-completion-review-" + str(uuid4())
    with tempfile.TemporaryDirectory(prefix="dragon-hard-lane-completion-") as temporary:
        run = Path(temporary)
        atomic_write_json(run / "completion/inputs.json", inputs)
        atomic_write_json(run / "completion/decision.json", result)
        atomic_write_json(run / "completion/replay.json", {"status": "PASS", "inputs_sha256": digest(inputs),
            "decision_sha256": digest(result), "provider_calls": 0, "network_calls": 0})
        for name in ("request.json", "research.raw.json"):
            path = run / "completion" / name
            path.write_bytes((provider / "artifacts/provider-research" / name).read_bytes())
        archive = LocalAcceptanceArchive(root=root, run_dir=run, run_id=run_id, edition_date=inputs["packet"]["edition_date"])
        archive.manifest.update(bundle_type="OFFLINE_HARD_LANE_COMPLETION_REVIEW", parent_bundles=inputs["parents"], network_calls=0, provider_call_limit=0)
        archive.finalize(required=["completion/inputs.json", "completion/decision.json", "completion/replay.json",
            "completion/request.json", "completion/research.raw.json"], provider_calls=0, run_result="OFFLINE_COMPLETION_REVIEW_COMPLETE")
        receipt = replay_completion_review(archive.bundle)
        for parent in (provider, retrieval, evidence_review):
            verify_acceptance_bundle(parent)
        atomic_write_json(archive.destination / "completion-replays" / (run_id + ".json"), receipt)
        return {**receipt, "bundle": str(archive.bundle)}
