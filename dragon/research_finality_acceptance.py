"""Offline finality review of sealed provider/retrieval evidence. No adapters."""

from copy import deepcopy
import json
from pathlib import Path
import shutil
import tempfile
from uuid import uuid4

from dragon.archive import LocalAcceptanceArchive, verify_acceptance_bundle
from dragon.deep_research import load_deep_research_config
from dragon.research_finality import apply_research_finality, build_research_finality, digest, validate_research_finality
from dragon.research_recovery import validate_recovery_plan
from dragon.state import atomic_write_json, sha256_file


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def preserved_inputs(provider: Path, retrieval: Path, review: Path) -> dict:
    manifests = [verify_acceptance_bundle(p) for p in (provider, retrieval, review)]
    provider_sha, retrieval_sha, review_sha = [sha256_file(p / "manifest.json") for p in (provider, retrieval, review)]
    if (manifests[1].get("parent_provider_bundle_id") != manifests[0]["run_id"]
        or manifests[1].get("parent_manifest_sha256") != provider_sha
        or manifests[2].get("parent_provider_bundle_id") != manifests[0]["run_id"]
        or manifests[2].get("parent_retrieval_bundle_id") != manifests[1]["run_id"]
        or manifests[2].get("parent_retrieval_manifest_sha256") != retrieval_sha
        or len({m["edition_date"] for m in manifests}) != 1):
        raise ValueError("FINALITY_PARENT_LINEAGE_INVALID")
    artifacts = review / "artifacts"
    epochs = [{"epoch": 0, "state": _read(artifacts / "deep-research/state.json"),
               "execution": _read(artifacts / "deep-research/execution-report.json")}]
    if (artifacts / "deep-research/epoch-1-state.json").exists():
        epochs.append({"epoch": 1, "state": _read(artifacts / "deep-research/epoch-1-state.json"),
                       "execution": _read(artifacts / "deep-research/epoch-1-execution-report.json")})
    packet = _read(artifacts / "research/recovered-research-packet.json")
    targeting = _read(provider / "artifacts/provider-research/request.json")["provider_input"]["research_targeting"]
    config = load_deep_research_config(review / "configuration/config/deep-research.yaml",
                                       review / "configuration/config/deep-research-schema.json")
    timestamps = [o["observed_at"] for e in epochs for j in e["execution"].get("jobs", []) for o in j.get("observations", []) if o.get("observed_at")]
    # Every corrected observation is tied to an original response action.
    original_records = [_read(p) for p in sorted((retrieval / "artifacts/retrieval/actions").glob("*.json"))]
    reviewed_records = [_read(p) for p in sorted((artifacts / "retrieval/actions").glob("*.json"))]
    if original_records != reviewed_records:
        raise ValueError("FINALITY_RAW_ACTION_RESPONSES_CHANGED")
    executed = [a for e in epochs for j in e["execution"].get("jobs", []) for a in j.get("actions", [])]
    dispatch = lambda a: {k: v for k, v in a.items() if k != "actual_information_gain"}
    # This single field is written after execution. Every dispatch input,
    # including exact URL and provider/source lineage, must match byte-for-byte.
    if [dispatch(r["action"]) for r in original_records] != [dispatch(a) for a in executed]:
        raise ValueError("FINALITY_EXECUTION_REQUESTS_CHANGED")
    return {"packet": packet, "targeting": targeting, "epochs": epochs, "config": config,
            "closed_at": max(timestamps), "base_recovery_plan": _read(artifacts / "research-recovery/plan.json"),
            "parents": [{"run_id": m["run_id"], "manifest_sha256": s, "artifact_count": len(m["artifacts"])}
                        for m, s in zip(manifests, (provider_sha, retrieval_sha, review_sha))],
            "raw_provider_sha256": sha256_file(provider / "artifacts/provider-research/research.raw.json"),
            "raw_request_sha256": sha256_file(provider / "artifacts/provider-research/request.json"),
            "executed_request_sha256": digest([dispatch(a) for a in executed]), "action_response_sha256": digest(original_records),
            "post_execution_fields_excluded_from_request_comparison": ["actual_information_gain"]}


def evaluate(inputs: dict) -> dict:
    record = build_research_finality(inputs["packet"], **{k: inputs[k] for k in ("targeting", "epochs", "config", "closed_at")},
        other_research_need_ids=[n["need_id"] for n in inputs["base_recovery_plan"]["needs"] if n.get("kind") != "NEED_ACCOUNTABILITY_AND_SERVICE"])
    plan = apply_research_finality(inputs["base_recovery_plan"], record)
    issues = validate_research_finality(record, inputs["packet"]) + validate_recovery_plan(plan)
    if issues:
        raise ValueError(",".join(issues))
    return {"finality": record, "recovery_plan": plan,
        "verdicts": {"SERVICE_NEGATIVE_CLOSURE": record["lanes"]["SERVICE"]["state"] == "VERIFIED_NO_QUALIFYING_EVENT",
            "ACCOUNTABILITY_NEGATIVE_CLOSURE": record["lanes"]["ACCOUNTABILITY"]["state"] == "VERIFIED_NO_QUALIFYING_EVENT",
            "COMBINED_RESEARCH_COVERAGE_COMPLETE": record["combined_research_coverage_complete"],
            "COMBINED_EVENT_COVERAGE": deepcopy(record["combined_event_coverage"]),
            "RESEARCH_FINALITY": record["research_finality"],
            "EDITORIAL_HANDOFF_ELIGIBLE": plan["editorial_handoff_eligible"]}}


def preserve_finality_review(provider: Path, retrieval: Path, review: Path, *, root: Path) -> dict:
    inputs = preserved_inputs(provider, retrieval, review)
    first, second = evaluate(inputs), evaluate(deepcopy(inputs))
    if first != second:
        raise ValueError("FINALITY_REPLAY_NONDETERMINISTIC")
    run_id = "research-finality-review-" + str(uuid4())
    with tempfile.TemporaryDirectory(prefix="dragon-finality-review-") as temporary:
        run_dir = Path(temporary)
        atomic_write_json(run_dir / "finality/inputs.json", inputs)
        atomic_write_json(run_dir / "finality/decision.json", first)
        receipt = {"schema_version": 1, "run_id": run_id, "parents": inputs["parents"],
                   "provider_calls": 0, "network_calls": 0, "publication_status": "NOT_ENTERED",
                   "inputs_sha256": digest(inputs), "decision_sha256": digest(first),
                   "immediate_deterministic_replay": "PASS"}
        atomic_write_json(run_dir / "finality/replay.json", receipt)
        # Keep primary raw bytes in this new derivative as well as the sealed parents.
        for name in ("request.json", "research.raw.json"):
            shutil.copyfile(provider / "artifacts/provider-research" / name, run_dir / "finality" / name)
        archive = LocalAcceptanceArchive(root=root, run_dir=run_dir, run_id=run_id,
                                         edition_date=inputs["packet"]["edition_date"])
        archive.manifest.update(bundle_type="OFFLINE_RESEARCH_FINALITY_REVIEW", provider_call_limit=0,
                                network_calls=0, parent_bundles=inputs["parents"])
        archive.finalize(required=["finality/inputs.json", "finality/decision.json", "finality/replay.json",
                                   "finality/request.json", "finality/research.raw.json"],
                         provider_calls=0, run_result="FINALITY_REVIEW_COMPLETE")
        sealed = replay_finality_review(archive.bundle)
        atomic_write_json(archive.destination / "finality-replays" / f"{run_id}.json", sealed)
        # Verify primary parents again after creating the derivative.
        for path in (provider, retrieval, review):
            verify_acceptance_bundle(path)
        return {**receipt, "bundle": str(archive.bundle), "manifest_sha256": sha256_file(archive.bundle / "manifest.json"),
                "sealed_replay": sealed["status"], "verdicts": first["verdicts"]}


def replay_finality_review(bundle: Path) -> dict:
    manifest = verify_acceptance_bundle(bundle)
    if manifest.get("bundle_type") != "OFFLINE_RESEARCH_FINALITY_REVIEW":
        raise ValueError("FINALITY_BUNDLE_TYPE_INVALID")
    artifacts = bundle / "artifacts/finality"
    inputs = _read(artifacts / "inputs.json")
    decision = _read(artifacts / "decision.json")
    replayed = evaluate(inputs)
    if replayed != decision or replayed != evaluate(deepcopy(inputs)):
        raise ValueError("FINALITY_SEALED_REPLAY_MISMATCH")
    receipt = _read(artifacts / "replay.json")
    if receipt["inputs_sha256"] != digest(inputs) or receipt["decision_sha256"] != digest(decision):
        raise ValueError("FINALITY_RECEIPT_HASH_MISMATCH")
    return {"status": "PASS", "run_id": manifest["run_id"], "manifest_sha256": sha256_file(bundle / "manifest.json"),
            "provider_calls": 0, "network_calls": 0, "decision_sha256": digest(decision), "verdicts": replayed["verdicts"]}
