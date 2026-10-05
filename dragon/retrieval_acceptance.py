"""Provider-free live execution of a verified immutable research checkpoint."""

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import tempfile
from uuid import uuid4

from dragon.archive import LocalAcceptanceArchive, verify_acceptance_bundle
from dragon.contract_replay import replay_contract_isolation
from dragon.deep_research_executor import discovery_adapter_from_config
from dragon.discovery import default_transport
from dragon.editorial_functions import classify_event_functions
from dragon.lock import RunLock
from dragon.pipeline import build_stage_definitions
from dragon.research_acceptance import ProviderFreeAcceptanceProvider
from dragon.recovery import ErrorClassifier, RecoveryPolicy
from dragon.stages import StageContext, StageFailure
from dragon.state import atomic_write_json, sha256_file


ALLOWED_STAGES = ("deep_research_execution", "research_recovery")


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def prepare_retrieval(bundle: Path, receipt_path: Path, *, root: Path) -> dict:
    """No network: verify all upstream bytes and reproduce selection twice."""
    manifest = verify_acceptance_bundle(bundle)
    receipt = read(receipt_path)
    if sha256_file(receipt_path) != receipt_path.with_name("receipt.sha256").read_text(encoding="ascii").strip():
        raise ValueError("comparison receipt hash differs")
    if receipt.get("status") != "COMPLETE" or receipt.get("input_run_id") != manifest["run_id"] or receipt.get("input_manifest_sha256") != sha256_file(bundle / "manifest.json"):
        raise ValueError("comparison receipt parent identity differs")
    if set(receipt.get("artifacts", {})) != {"comparison.json", "report.md"}:
        raise ValueError("comparison receipt inventory differs")
    for name, digest in receipt["artifacts"].items():
        if sha256_file(receipt_path.parent / name) != digest:
            raise ValueError("comparison artifact hash differs: " + name)
    previous = read(receipt_path.parent / "comparison.json")
    current = replay_contract_isolation(bundle, code_root=root)
    if current != replay_contract_isolation(bundle, code_root=root):
        raise ValueError("execution plan replay is nondeterministic")
    if current["input_raw_sha256"] != receipt["input_raw_sha256"]:
        raise ValueError("raw packet hash differs")
    if previous["normalized_packet"] != current["normalized_packet"]:
        raise ValueError("fixed normalized upstream packet changed")
    before = deepcopy(previous["scheduler_allocation"])
    after = deepcopy(current["scheduler_allocation"])
    # The only permitted initial action change is the missing temporal frame.
    for schedule in (before, after):
        for action in schedule["actions"]:
            action.get("event_context", {}).pop("research_date", None)
        for record in schedule["deferred_actions"]:
            if isinstance(record.get("action"), dict):
                record["action"].get("event_context", {}).pop("research_date", None)
    # Telemetry may contain copies of actions; identity and exact route are
    # checked separately, while allocation counts and full inputs are archived.
    if before["actions"] != after["actions"]:
        raise ValueError("initial selected actions differ beyond temporal metadata")
    for relative, digest in manifest["configuration_hashes"].items():
        if sha256_file(root / relative) != digest:
            raise ValueError("frozen configuration differs: " + relative)
    current["retrieval_preflight"] = {
        "status": "PASS", "parent_artifact_count": len(manifest["artifacts"]),
        "comparison_receipt_sha256": sha256_file(receipt_path),
        "comparison_artifact_sha256": sha256_file(receipt_path.parent / "comparison.json"),
        "selected_action_ids_match": True, "deterministic_replays": 2,
        "documented_changes": ["Exact candidate jobs now retain edition_date as event_context.research_date.",
            "Shared execution ceiling protects all selected actions from dynamic follow-ups.",
            "Unchanged provider-no-result needs enter the existing bounded recovery epoch."],
        "edition_date": manifest["edition_date"], "provider_calls": 0, "network_calls": 0,
    }
    return current


def seed_run(run_dir: Path, replay: dict) -> None:
    for name, key in (("research/research-packet.json", "normalized_packet"),
        ("source-intelligence/report.json", "source_intelligence"),
        ("research-planning/plan.json", "research_plan"),
        ("deep-research/state.json", "scheduler_inputs"),
        ("research-recovery/initial-plan.json", "recovery_plan")):
        atomic_write_json(run_dir / name, replay[key])


class RecordingResearchAdapter:
    """Observe the ordinary adapter and transports; never inject evidence."""

    def __init__(self, adapter, run_dir: Path, archive: LocalAcceptanceArchive):
        self.adapter, self.run_dir, self.archive = adapter, run_dir, archive
        self.follow_discovery_leads = getattr(adapter, "follow_discovery_leads", False)
        self.records, self.network = [], []
        self.current_action = None
        self.classifier = ErrorClassifier(RecoveryPolicy.load(archive.root / "config/recovery-policy.yaml").code_categories)
        for backend in getattr(adapter, "adapters", [adapter]):
            if hasattr(backend, "transport"):
                backend.transport = self._transport(backend.transport, "SEARCH", getattr(backend, "adapter_id", None))
            backend.source_transport = self._transport(default_transport, "DIRECT_FETCH", getattr(backend, "adapter_id", None))

    def _transport(self, delegate, kind, backend):
        def call(url, timeout_seconds, maximum_bytes):
            index = len(self.network)
            record = {"index": index, "action_id": self.current_action, "kind": kind, "backend": backend,
                "url": url, "requested_at": datetime.now(timezone.utc).isoformat(),
                "timeout_seconds": timeout_seconds, "maximum_bytes": maximum_bytes, "state": "REQUESTED"}
            self.network.append(record)
            prefix = self.run_dir / "retrieval/network" / f"{index:03d}"
            atomic_write_json(prefix.with_suffix(".json"), record)
            self.archive.snapshot()
            try:
                response = delegate(url, timeout_seconds, maximum_bytes)
                body = prefix.with_suffix(".body")
                body.write_bytes(response.body)
                record.update(state="RESPONDED", final_url=response.url, http_status=response.status,
                    content_type=response.content_type, redirect_count=response.redirect_count,
                    body_sha256=sha256_file(body), bytes=len(response.body))
                return response
            except Exception as exc:
                record.update(state="FAILED", error_code=getattr(exc, "code", type(exc).__name__), detail=str(exc))
                raise
            finally:
                record["responded_at"] = datetime.now(timezone.utc).isoformat()
                atomic_write_json(prefix.with_suffix(".json"), record)
                self.archive.snapshot()
        return call

    def execute(self, action):
        self.current_action = action["action_id"]
        index = len(self.records)
        record = {"index": index, "action": deepcopy(action), "state": "REQUESTED",
            "requested_at": datetime.now(timezone.utc).isoformat()}
        self.records.append(record)
        path = self.run_dir / "retrieval/actions" / f"{index:03d}-{action['action_id']}.json"
        atomic_write_json(path, record)
        self.archive.snapshot()
        try:
            results = self.adapter.execute(action)
            timestamp = datetime.now(timezone.utc).isoformat()
            for item in results:
                item.setdefault("retrieved_at", timestamp)
            record.update(state="RESPONDED", results=deepcopy(results), failure_classifications=[
                {"result_index": i, "code": item.get("reason") or "UNKNOWN",
                    "category": self.classifier.classify(str(item.get("reason") or "UNKNOWN")).value}
                for i, item in enumerate(results) if item.get("result_type") == "DEAD_END"])
            return results
        except Exception as exc:
            record.update(state="FAILED", error_code=getattr(exc, "code", type(exc).__name__), detail=str(exc))
            raise
        finally:
            record["responded_at"] = datetime.now(timezone.utc).isoformat()
            atomic_write_json(path, record)
            self.archive.snapshot()


def run_research_stages(root: Path, run_dir: Path, edition_date: str, adapter, checkpoint=lambda: None) -> dict:
    """Execute only the two production research runners; no editorial runner."""
    stages = {stage.name: stage for stage in build_stage_definitions(ProviderFreeAcceptanceProvider(), research_adapter=adapter)}
    context = StageContext(root, edition_date, run_dir, run_dir / "forbidden-edition", 1)
    states = {}
    for name in ALLOWED_STAGES:
        try:
            result = stages[name].runner(context)
            issues = stages[name].validator(context, result)
            if issues:
                raise StageFailure("RETRIEVAL_OUTPUT_INVALID", "; ".join(issues))
            states[name] = {"status": "COMPLETE", "outputs": [str(path.relative_to(run_dir)) for path in result.outputs]}
        except StageFailure as exc:
            states[name] = {"status": "FAILED", "error_code": exc.code, "detail": exc.detail}
            if exc.code not in {"RESEARCH_RECOVERY_REQUIRED", "RESEARCH_INSUFFICIENT"}:
                raise
        finally:
            atomic_write_json(run_dir / "retrieval/stage-results.json", states)
            checkpoint()
    return states


def replay_retrieval(bundle: Path, *, root: Path, require_complete: bool = True) -> dict:
    manifest = verify_acceptance_bundle(bundle, require_complete=require_complete)
    artifacts = bundle / "artifacts"
    records = [read(path) for path in sorted((artifacts / "retrieval/actions").glob("*.json"))]

    class SavedAdapter:
        follow_discovery_leads = True
        def __init__(self): self.index = 0
        def execute(self, action):
            if self.index >= len(records):
                raise ValueError("replay attempted an unrecorded action")
            record = records[self.index]
            if record["action"] != action or record["state"] != "RESPONDED":
                raise ValueError("replay request differs from preserved action")
            self.index += 1
            return deepcopy(record["results"])

    # A matching directory basename retains recovery action identities.
    with tempfile.TemporaryDirectory(prefix="dragon-retrieval-replay-") as directory:
        replay_root = Path(directory)
        shutil.copytree(bundle / "configuration/config", replay_root / "config")
        run_dir = replay_root / "runs" / manifest["run_id"]
        seed_run(run_dir, read(artifacts / "retrieval/execution-replay.json"))
        adapter = SavedAdapter()
        run_research_stages(replay_root, run_dir, manifest["edition_date"], adapter)
        if adapter.index != len(records):
            raise ValueError("replay did not consume every preserved action")
        compared = []
        for name in ("deep-research/execution-report.json", "deep-research/epoch-1-inputs.json",
            "deep-research/epoch-1-state.json", "deep-research/epoch-1-scheduler-allocation.json",
            "deep-research/epoch-1-execution-report.json", "research/recovered-research-packet.json",
            "source-intelligence/recovered-report.json", "research-recovery/plan.json", "deep-research/yield-report.json"):
            original, replayed = artifacts / name, run_dir / name
            if original.exists() != replayed.exists() or (original.exists() and read(original) != read(replayed)):
                raise ValueError("deterministic retrieval replay differs: " + name)
            if original.exists(): compared.append(name)
    return {"status": "PASS", "run_id": manifest["run_id"], "manifest_sha256": sha256_file(bundle / "manifest.json"),
        "provider_calls": 0, "network_calls": 0, "actions_replayed": len(records), "exact_artifacts_compared": compared}


def evidence_decisions(run_dir: Path) -> dict:
    reports = [read(run_dir / "deep-research/execution-report.json")]
    if (run_dir / "deep-research/epoch-1-execution-report.json").exists():
        reports.append(read(run_dir / "deep-research/epoch-1-execution-report.json"))
    plan = read(run_dir / "research-recovery/plan.json")
    observations = [o for r in reports for job in r["jobs"] for o in job["observations"]]
    bundles = [b for r in reports for job in r["jobs"] for b in job["source_packet_patch"]["event_bundles"]]
    itrane = {}
    for role, identity in (("PRIMARY", "ACT-156391587BBA"), ("INDEPENDENT", "ACT-EBB9846FF233")):
        matching = [o for o in observations if o["provenance"]["action_id"] == identity]
        functions = [f for o in matching if o.get("extracted_text") for f in classify_event_functions(
            title=o.get("title"), facts=[o["extracted_text"]], evidence_source_ids=[o.get("source_id")], exact_page_validated=True)]
        itrane[role] = {"action_id": identity, "observations": matching,
            "retrieval": "PASS" if any(o["extraction_status"] == "FETCHED" for o in matching) else "FAIL",
            "semantic_content_functions": functions,
            "semantic_assessed": any(o.get("extracted_text") for o in matching)}
    primary, independent = itrane["PRIMARY"], itrane["INDEPENDENT"]
    coverage = plan["editorial_function_coverage"]
    account = coverage.get("ACCOUNTABILITY", {}).get("count", 0) > 0
    service = coverage.get("SERVICE", {}).get("count", 0) > 0
    matched_pair = [b for b in bundles if b.get("state") == "EVENT_VALIDATED"
        and "investigations:inv-itrane" in b.get("provider_candidate_ids", [])
        and any(f.get("function") == "ACCOUNTABILITY" for f in b.get("editorial_functions", []))]
    independent_valid = any((o.get("source_role_resolution") or {}).get("independence_state") == "INDEPENDENT_ORIGINAL_REPORTING" for o in independent["observations"])
    semantic_valid = all(any(f.get("function") == "ACCOUNTABILITY" for f in a["semantic_content_functions"]) for a in (primary, independent))
    temporal_valid = all(any((o.get("temporal_relevance") or {}).get("active_on_edition_date") is True for o in a["observations"]) for a in (primary, independent))
    initial_ids = {a["action_id"] for a in read(run_dir / "deep-research/scheduler-allocation.json")["actions"]}
    executed_ids = {a["action_id"] for job in reports[0]["jobs"] for a in job["actions"]}
    budgets_valid = all(len(r["actions_planned"]) <= r["round_execution_budget"]["maximum_actions_per_round"] for r in reports)
    mark = lambda value: "PASS" if value else "FAIL"
    return {"itrane": itrane, "editorial_function_coverage": coverage, "event_bundles": bundles,
        "final_needs": plan["needs"], "research_status": plan["status"],
        "recovery_service_actions": [a for r in reports[1:] for a in r["actions_planned"] if a.get("target_editorial_function") == "SERVICE"],
        "verdicts": {
            "PARENT_PROVIDER_BUNDLE_VALID": "PASS", "EXECUTION_PLAN_REPLAY": "PASS", "PROVIDER_CALLS_ZERO": "PASS",
            "ACCOUNTABILITY_PRIMARY_RETRIEVAL": primary["retrieval"],
            "ACCOUNTABILITY_INDEPENDENT_RETRIEVAL": independent["retrieval"],
            "ACCOUNTABILITY_SOURCE_INDEPENDENCE": mark(independent_valid),
            "ACCOUNTABILITY_SEMANTIC_VALIDITY": mark(semantic_valid),
            "ACCOUNTABILITY_TEMPORAL_VALIDITY": mark(temporal_valid),
            "ACCOUNTABILITY_EVIDENCE_BUNDLE": mark(bool(matched_pair)),
            "SERVICE_PROVIDER_DISPOSITION_PRESERVED": "PASS", "SERVICE_RECOVERY": mark(service),
            "CURRENT_ACCOUNTABILITY_EVENT_VALIDATED": mark(account), "CURRENT_SERVICE_EVENT_VALIDATED": mark(service),
            "COMBINED_COVERAGE_SATISFIED": mark(account and service), "RESEARCH_RECOVERY_REQUIRED": bool(plan["needs"]),
            "ROUND_BUDGET_UNCHANGED": mark(budgets_valid), "RETRIEVAL_ACCEPTANCE_ARTIFACT_DURABILITY": "PENDING_SEAL",
            "TECHNICAL_RESEARCH_ACCEPTANCE": mark(budgets_valid and initial_ids == executed_ids),
            "PHASE_2_ACCEPTANCE": "PENDING_REPLAY_AND_SEAL",
        }}


def run_live_retrieval(bundle: Path, receipt: Path, *, root: Path) -> dict:
    replay = prepare_retrieval(bundle, receipt, root=root)
    run_id = "retrieval-acceptance-" + str(uuid4())
    run_dir = root / "daily-runs" / replay["retrieval_preflight"]["edition_date"] / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    archive = LocalAcceptanceArchive(root=root, run_dir=run_dir, run_id=run_id, edition_date=replay["retrieval_preflight"]["edition_date"])
    archive.manifest.update(provider_call_limit=0, bundle_type="RETRIEVAL_ACCEPTANCE",
        parent_provider_bundle_id=replay["input_run_id"], parent_manifest_sha256=replay["input_manifest_sha256"],
        parent_raw_sha256=replay["input_raw_sha256"], comparison_receipt_sha256=sha256_file(receipt))
    seed_run(run_dir, replay)
    atomic_write_json(run_dir / "state.json", {"run_id": run_id, "allowed_stages": list(ALLOWED_STAGES), "provider_calls": 0})
    atomic_write_json(run_dir / "retrieval/execution-replay.json", replay)
    shutil.copyfile(receipt, run_dir / "retrieval/parent-comparison-receipt.json")
    archive.snapshot()
    adapter = RecordingResearchAdapter(discovery_adapter_from_config(bundle / "configuration"), run_dir, archive)
    with RunLock(archive.destination / "retrieval-acceptance.lock", "Africa/Casablanca") as lock:
        lock.set_run_id(run_id)
        states = run_research_stages(root, run_dir, replay["retrieval_preflight"]["edition_date"], adapter, archive.snapshot)
    final_plan = read(run_dir / "research-recovery/plan.json")
    result = {"schema_version": 1, "run_id": run_id, "parent_provider_bundle_id": replay["input_run_id"],
        "provider_calls": 0, "stage_results": states, "research_status": final_plan["status"],
        "executed_actions": len(adapter.records), "direct_fetch_requests": sum(r["kind"] == "DIRECT_FETCH" for r in adapter.network),
        "search_requests": sum(r["kind"] == "SEARCH" for r in adapter.network), "network_requests": len(adapter.network),
        "network_failures": [r for r in adapter.network if r["state"] == "FAILED"],
        "publication_status": "NOT_ENTERED", "bundle": str(archive.bundle)}
    atomic_write_json(run_dir / "retrieval/final-result.json", result)
    decisions = evidence_decisions(run_dir)
    atomic_write_json(run_dir / "retrieval/evidence-decisions.json", decisions)
    archive.snapshot()
    immediate_replay = replay_retrieval(archive.bundle, root=root, require_complete=False)
    atomic_write_json(run_dir / "retrieval/immediate-replay.json", immediate_replay)
    decisions["verdicts"]["RETRIEVAL_ACCEPTANCE_ARTIFACT_DURABILITY"] = "PASS"
    decisions["verdicts"]["PHASE_2_ACCEPTANCE"] = decisions["verdicts"]["TECHNICAL_RESEARCH_ACCEPTANCE"]
    atomic_write_json(run_dir / "retrieval/evidence-decisions.json", decisions)
    required = ["state.json", "retrieval/execution-replay.json", "retrieval/parent-comparison-receipt.json",
        "retrieval/stage-results.json", "retrieval/final-result.json", "deep-research/state.json",
        "deep-research/scheduler-allocation.json", "deep-research/execution-report.json", "research-recovery/plan.json"]
    required += [path.relative_to(run_dir).as_posix() for path in (run_dir / "retrieval").rglob("*") if path.is_file()]
    archive.finalize(required=required, provider_calls=0, run_result=final_plan["status"])
    verify_acceptance_bundle(bundle)
    sealed_replay = replay_retrieval(archive.bundle, root=root)
    replay_path = archive.destination / "retrieval-replays" / f"{run_id}-{sealed_replay['manifest_sha256']}.json"
    atomic_write_json(replay_path, sealed_replay)
    return {**result, "manifest_sha256": sha256_file(archive.bundle / "manifest.json")}
