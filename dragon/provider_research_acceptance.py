"""Explicit provider-backed, research-only acceptance boundary.

This module deliberately reuses the production research stages while making a
provider call an explicit, one-shot acceptance action.  It never includes an
editorial or publication stage.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace
from datetime import date, datetime
import json
from pathlib import Path
import subprocess
from typing import Any, Callable, Protocol
from uuid import uuid4
from zoneinfo import ZoneInfo

from dragon.archive import (
    ArchiveError, DisabledGitArchiveProvider, LocalAcceptanceArchive,
    acceptance_archive_root, verify_acceptance_bundle,
)
from dragon.config import load_local_config
from dragon.deep_research_executor import ResearchAdapter, discovery_adapter_from_config, searxng_search_adapter_from_config
from dragon.orchestrator import Orchestrator
from dragon.pipeline import build_stage_definitions
from dragon.providers import LocalCommandEditorialProvider, ProviderError
from dragon.redaction import redact_text
from dragon.research_acceptance import (
    FORBIDDEN_STAGES,
    PROVIDER_RESEARCH_ACCEPTANCE_MODE,
    RESEARCH_ACCEPTANCE_STAGES,
    TECHNICAL_PROVIDER_RESEARCH_ACCEPTANCE_MODE,
    ResearchAcceptanceError,
    _acceptance_preflight_stage,
    audit_acceptance_environment,
    build_fresh_research_seed,
)
from dragon.state import EXECUTION_MODE_FRESH, atomic_write_json, sha256_file
from dragon.whatsapp import DisabledWhatsAppProvider


class ResearchProvider(Protocol):
    mode: str

    def research(self, edition_date: str, continuity: dict | None = None) -> dict: ...


@dataclass
class OneShotProviderResearch:
    """Capture one provider research call without giving it execution control."""

    delegate: ResearchProvider
    artifact_dir: Path
    run_id: str
    timezone: str
    call_limit: int = 1
    calls: int = 0
    artifact_checkpoint: Callable[[], None] | None = None

    @property
    def mode(self) -> str:
        return self.delegate.mode

    @property
    def available(self) -> bool:
        return bool(getattr(self.delegate, "available", True))

    def articles(self, research: dict) -> list[dict]:
        raise AssertionError("provider-backed research acceptance cannot generate articles")

    def _identity(self) -> dict[str, Any]:
        command = getattr(self.delegate, "command", None)
        return {
            "adapter_class": type(self.delegate).__name__,
            "mode": getattr(self.delegate, "mode", None),
            "command": list(command) if isinstance(command, tuple) else command,
        }

    def _write_invocation(self, value: dict[str, Any]) -> None:
        atomic_write_json(self.artifact_dir / "invocation.json", value)
        if self.artifact_checkpoint is not None:
            self.artifact_checkpoint()

    def research(self, edition_date: str, continuity: dict | None = None) -> dict:
        if self.calls >= self.call_limit or (self.artifact_dir / "invocation.json").exists():
            raise ProviderError(
                "PROVIDER_RESEARCH_CALL_LIMIT_EXCEEDED",
                "provider-backed research acceptance permits exactly one research() call",
            )
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        requested_at = datetime.now(ZoneInfo(self.timezone)).isoformat()
        request = {
            "schema_version": 1,
            "run_id": self.run_id,
            "provider_call_index": 1,
            "requested_at": requested_at,
            "edition_date": edition_date,
            "provider": self._identity(),
            "provider_input": deepcopy(continuity or {}),
        }
        request_path = self.artifact_dir / "request.json"
        atomic_write_json(request_path, request)
        self._write_invocation({**request, "status": "ARMED", "provider_calls": 0})
        raw_path = self.artifact_dir / "research.raw.json"
        self.calls += 1
        try:
            packet = self.delegate.research(edition_date, continuity)
        except Exception as exc:
            self._write_invocation(
                {
                    "schema_version": 1,
                    "status": "FAILED",
                    "run_id": self.run_id,
                    "provider_call_index": self.calls,
                    "requested_at": requested_at,
                    "responded_at": datetime.now(ZoneInfo(self.timezone)).isoformat(),
                    "provider": self._identity(),
                    "request": {"path": str(request_path), "sha256": sha256_file(request_path)},
                    "raw_response": (
                        {"path": str(raw_path), "sha256": sha256_file(raw_path)}
                        if raw_path.is_file()
                        else None
                    ),
                    "error_code": getattr(exc, "code", type(exc).__name__),
                    "error_detail": redact_text(str(exc)),
                    "diagnostics": getattr(exc, "diagnostics", {}),
                }
            )
            raise
        if not raw_path.is_file():
            error = ProviderError(
                "PROVIDER_RAW_EVIDENCE_MISSING",
                "provider research returned without a raw response captured before normalization",
            )
            self._write_invocation(
                {
                    "schema_version": 1,
                    "status": "FAILED",
                    "run_id": self.run_id,
                    "provider_call_index": self.calls,
                    "requested_at": requested_at,
                    "responded_at": datetime.now(ZoneInfo(self.timezone)).isoformat(),
                    "provider": self._identity(),
                    "request": {"path": str(request_path), "sha256": sha256_file(request_path)},
                    "raw_response": None,
                    "error_code": error.code,
                }
            )
            raise error
        # A provider can describe an alleged source verification, but it has
        # not independently retrieved anything.  Clamp any supplied evidence
        # status before the ordinary source-intelligence stage sees it.
        # Executor-added sources retain their own validated provenance later.
        packet = deepcopy(packet)
        for source in packet.get("sources", []):
            if isinstance(source, dict):
                source["verification_status"] = "PROVIDER_REPORTED"
                source["evidence_relation"] = None
                source["directness"] = None
                source["provenance"] = None
        normalized_path = self.artifact_dir / "normalized-research-packet.json"
        atomic_write_json(normalized_path, packet)
        invocation = {
            "schema_version": 1,
            "status": "NORMALIZED",
            "run_id": self.run_id,
            "provider_call_index": self.calls,
            "requested_at": requested_at,
            "responded_at": datetime.now(ZoneInfo(self.timezone)).isoformat(),
            "provider": self._identity(),
            "request": {"path": str(request_path), "sha256": sha256_file(request_path)},
            "raw_response": {"path": str(raw_path), "sha256": sha256_file(raw_path)},
            "normalized_packet": {"path": str(normalized_path), "sha256": sha256_file(normalized_path)},
            "provider_reported_source_urls": [
                item.get("url") for item in packet.get("sources", [])
                if isinstance(item, dict) and isinstance(item.get("url"), str)
            ],
            "evidence_status": "PROVIDER_REPORTED_UNVERIFIED",
        }
        self._write_invocation(invocation)
        # The normal production research stage hash-binds the returned packet.
        # Retaining this pointer within it links that ordinary stage artifact to
        # the pre-normalization response without treating provider material as
        # independently verified evidence.
        packet["provider_research_acceptance_provenance"] = {
            "invocation_path": str(self.artifact_dir / "invocation.json"),
            "invocation_sha256": sha256_file(self.artifact_dir / "invocation.json"),
            "raw_response_sha256": invocation["raw_response"]["sha256"],
            "normalized_packet_sha256": invocation["normalized_packet"]["sha256"],
            "evidence_status": "PROVIDER_REPORTED_UNVERIFIED",
        }
        return packet


def _provider_preflight_stage(
    *,
    root: Path,
    seed: dict[str, Any],
    run_id: str,
    service_probe: Callable[[dict[str, Any]], dict[str, Any]] | None,
    technical_validation: bool,
    preflight_now: datetime | None,
):
    stage = _acceptance_preflight_stage(
        root=root,
        seed=seed,
        run_id=run_id,
        service_probe=service_probe,
        technical_validation=technical_validation,
        preflight_now=preflight_now,
    )

    def run(context):
        result = stage.runner(context)
        path = context.run_dir / "preflight.json"
        value = json.loads(path.read_text(encoding="utf-8"))
        value.update(
            {
                "mode": seed["research_acceptance_seed"]["mode"],
                "provider_requirement": "EXPLICIT_PROVIDER_RESEARCH_AUTHORIZATION",
                "provider_authorization": "AUTHORIZED_ONE_RESEARCH_CALL_ONLY",
                "production_preflight": "NOT_RUN_AND_UNMODIFIED",
            }
        )
        atomic_write_json(path, value)
        return result

    from dragon.stages import StageDefinition

    return StageDefinition("preflight", (), run)


def build_provider_research_acceptance_orchestrator(
    *,
    root: Path,
    edition_date: str,
    provider: ResearchProvider,
    provider_authorized: bool,
    run_id: str | None = None,
    research_adapter: ResearchAdapter | None = None,
    service_probe: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    technical_validation: bool = False,
    created_at: str | None = None,
    preflight_now: datetime | None = None,
    use_lock: bool = True,
    artifact_checkpoint: Callable[[], None] | None = None,
) -> Orchestrator:
    """Create a fresh provider-backed run containing only research stages."""
    if not provider_authorized:
        raise ResearchAcceptanceError(
            "PROVIDER_RESEARCH_AUTHORIZATION_REQUIRED",
            "pass explicit provider-backed research authorization before any provider call",
        )
    if technical_validation and (created_at is not None or preflight_now is not None):
        raise ResearchAcceptanceError(
            "TECHNICAL_ACCEPTANCE_TIME_OVERRIDE_FORBIDDEN",
            "technical provider acceptance records its actual local execution time",
        )
    root = root.resolve()
    config = load_local_config(root)
    timezone = str(config["timezone"])
    normalized_date = date.fromisoformat(edition_date).isoformat()
    mode = (
        TECHNICAL_PROVIDER_RESEARCH_ACCEPTANCE_MODE
        if technical_validation
        else PROVIDER_RESEARCH_ACCEPTANCE_MODE
    )
    identifier = run_id or f"provider-research-acceptance-{uuid4()}"
    run_dir = root / "daily-runs" / normalized_date / "runs" / identifier
    if run_dir.exists():
        raise ResearchAcceptanceError("FRESH_ACCEPTANCE_RUN_EXISTS", str(run_dir))
    seed = build_fresh_research_seed(
        root=root,
        edition_date=normalized_date,
        timezone=timezone,
        run_id=identifier,
        created_at=created_at,
        acceptance_mode=mode,
    )
    # The production adapter captures its raw response before normalization.
    # Rebinding only its acceptance capture directory keeps that immutable raw
    # material inside this fresh run without changing provider configuration.
    capture_provider = (
        replace(provider, capture_directory=run_dir / "provider-research")
        if isinstance(provider, LocalCommandEditorialProvider)
        else provider
    )
    guarded_provider = OneShotProviderResearch(
        delegate=capture_provider,
        artifact_dir=run_dir / "provider-research",
        run_id=identifier,
        timezone=timezone,
        artifact_checkpoint=artifact_checkpoint,
    )
    definitions = build_stage_definitions(
        guarded_provider,
        archive_provider=DisabledGitArchiveProvider(),
        whatsapp_provider=DisabledWhatsAppProvider(),
        research_adapter=research_adapter or discovery_adapter_from_config(root),
    )
    selected = [definition for definition in definitions if definition.name in RESEARCH_ACCEPTANCE_STAGES]
    if tuple(definition.name for definition in selected) != RESEARCH_ACCEPTANCE_STAGES:
        raise ResearchAcceptanceError("ACCEPTANCE_STAGE_BOUNDARY_INVALID", "production research stage registry changed")
    selected[0] = _provider_preflight_stage(
        root=root,
        seed=seed,
        run_id=identifier,
        service_probe=service_probe,
        technical_validation=technical_validation,
        preflight_now=preflight_now,
    )
    orchestrator = Orchestrator(
        root=root,
        edition_date=normalized_date,
        timezone=timezone,
        stages=selected,
        execution_mode=EXECUTION_MODE_FRESH,
        run_id=identifier,
        source_attempt_id=f"provider-research-acceptance:{identifier}",
        use_lock=use_lock,
        target_deadline=None,
    )
    orchestrator.acceptance_mode = mode
    orchestrator.technical_validation = technical_validation
    orchestrator.provider_research = guarded_provider
    return orchestrator


def _retrieved_sources(run_dir: Path) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for name in ("execution-report.json", "epoch-1-execution-report.json"):
        path = run_dir / "deep-research" / name
        if not path.is_file():
            continue
        report = json.loads(path.read_text(encoding="utf-8"))
        for job in report.get("jobs", []):
            for source in job.get("source_packet_patch", {}).get("sources", []):
                if isinstance(source, dict):
                    values.append({
                        "url": source.get("url"),
                        "source_type": source.get("source_type"),
                        "verification_status": source.get("verification_status"),
                    })
    return values


def write_provider_research_acceptance_report(orchestrator: Orchestrator, state: dict[str, Any]) -> Path:
    """Report persisted research result without translating it into publication success."""
    run_dir = orchestrator.store.run_dir
    stages = state.get("stages", {})
    recovery = stages.get("research_recovery", {})
    if recovery.get("status") == "COMPLETE":
        verdict = "RESEARCH_ACCEPTANCE_COMPLETE"
    elif recovery.get("error_code") == "RESEARCH_RECOVERY_REQUIRED":
        verdict = "RESEARCH_RECOVERY_REQUIRED"
    else:
        verdict = "RESEARCH_ACCEPTANCE_BLOCKED"
    invocation_path = run_dir / "provider-research" / "invocation.json"
    invocation = json.loads(invocation_path.read_text(encoding="utf-8")) if invocation_path.is_file() else None
    preflight_path = run_dir / "preflight.json"
    report = {
        "schema_version": 1,
        "mode": orchestrator.acceptance_mode,
        "verdict": verdict,
        "not_production_readiness": True,
        "on_time_production_readiness": "NOT_APPLICABLE_TECHNICAL_VALIDATION" if orchestrator.technical_validation else "NOT_EVALUATED",
        "production_deadline_status": (json.loads(preflight_path.read_text(encoding="utf-8")) if preflight_path.is_file() else {}).get("production_deadline_status", "NOT_EVALUATED"),
        "edition_date": orchestrator.edition_date,
        "timezone": orchestrator.timezone,
        "run_id": orchestrator.store.run_id,
        "source_attempt_id": state.get("source_attempt_id"),
        "execution_mode": state.get("execution_mode"),
        "publication_status": state.get("publication_status"),
        "run_result": state.get("run_result"),
        "provider_research_calls": orchestrator.provider_research.calls,
        "provider_call_limit": orchestrator.provider_research.call_limit,
        "provider_invocation": invocation,
        "independently_retrieved_sources": _retrieved_sources(run_dir),
        "allowed_stages": list(RESEARCH_ACCEPTANCE_STAGES),
        "forbidden_stages_absent": sorted(FORBIDDEN_STAGES - set(stages)),
        "stage_statuses": {name: record.get("status") for name, record in stages.items()},
        "recovery_error_code": recovery.get("error_code"),
    }
    path = run_dir / "provider-research-acceptance-report.json"
    atomic_write_json(path, report)
    return path


def audit_live_provider_gates(root: Path, provider: ResearchProvider) -> dict:
    """Pre-call checks use search and CLI authentication, never AI generation."""
    try:
        containers = subprocess.run(["docker", "ps", "--filter", "publish=8088", "--format", "{{.ID}}"],
            capture_output=True, text=True, timeout=20, check=True).stdout.splitlines()
        if not containers:
            raise ValueError("no running container publishes the required local port 8088")
        runtime = json.loads(subprocess.run(["docker", "inspect", containers[0]],
            capture_output=True, text=True, timeout=20, check=True).stdout)[0]
        health = runtime["State"].get("Health", {}).get("Status")
        if not runtime["State"]["Running"] or health in {"unhealthy", "starting"}:
            raise ValueError("local SearXNG runtime is unhealthy")
        adapter = searxng_search_adapter_from_config(root / "config" / "general-search.yaml")
        if adapter is None or adapter.base_url != "http://127.0.0.1:8088":
            raise ValueError("required private search adapter is unavailable")
        query = "Maroc service public avis officiel"
        results = adapter.execute({"action_type": "SEARCH_DISCOVERY", "query": query})
        parsed = [item for item in results if item.get("result_type") == "LEAD"]
        if not parsed:
            raise ValueError("DRAGON adapter parsed no bounded real search result")
        provider_health = provider.healthcheck()
    except Exception as exc:
        raise ResearchAcceptanceError("BLOCKED_PRE_PROVIDER", redact_text(str(exc))) from exc
    return {
        "status": "PASS", "checked_at": datetime.now().astimezone().isoformat(),
        "searxng": {"status": "PASS", "container_id": runtime["Id"], "container": runtime["Name"], "health": health or "RUNNING_AND_HTTP_VERIFIED"},
        "search_adapter": {"status": "PASS", "query": query, "parsed_results": len(parsed), "maximum_results": adapter.maximum_results, "results": results},
        "provider_auth": provider_health, "provider_calls": 0,
        "one_call_limit": 1, "provider_retries": 0,
        "research_only": True, "editorial_enabled": False, "publication_enabled": False,
    }


def required_acceptance_artifacts(run_dir: Path, state: dict, calls: int) -> list[str]:
    required = ["state.json", "preflight.json", "provider-research-acceptance-report.json", "live-preflight.json"]
    if calls:
        required.extend(["provider-research/request.json", "provider-research/research.request.json",
            "provider-research/invocation.json", "provider-research/research.raw.json"])
    invocation_path = run_dir / "provider-research" / "invocation.json"
    invocation = json.loads(invocation_path.read_text(encoding="utf-8")) if invocation_path.is_file() else {}
    if invocation.get("status") == "NORMALIZED":
        required.append("provider-research/normalized-research-packet.json")
    stage_outputs = {
        "research": ["research/research-packet.json", "research/continuity-context.json"],
        "source_intelligence": ["source-intelligence/report.json"],
        "research_planning": ["research-planning/plan.json"],
        "deep_research": ["deep-research/state.json"],
        "deep_research_execution": ["deep-research/execution-report.json", "deep-research/scheduler-allocation.json"],
    }
    for stage, paths in stage_outputs.items():
        if state.get("stages", {}).get(stage, {}).get("status") == "COMPLETE":
            required.extend(paths)
    recovery = state.get("stages", {}).get("research_recovery", {})
    if recovery.get("status") == "COMPLETE" or recovery.get("error_code") == "RESEARCH_RECOVERY_REQUIRED":
        required.append("research-recovery/plan.json")
    if (run_dir / "deep-research" / "epoch-1-state.json").is_file():
        required.extend(["deep-research/epoch-1-state.json", "deep-research/epoch-1-inputs.json",
            "deep-research/epoch-1-scheduler-allocation.json", "deep-research/epoch-1-execution-report.json"])
    return sorted(set(required))


def run_provider_research_acceptance(**kwargs: Any) -> tuple[Orchestrator, dict[str, Any], Path]:
    """Run one non-resumable, explicitly authorized provider research attempt."""
    if {"resume", "retry_stage", "from_stage"} & set(kwargs):
        raise ResearchAcceptanceError("FRESH_RUN_RESUME_OR_RETRY_UNSUPPORTED", "provider research acceptance only creates new run identities")
    if not kwargs.get("provider_authorized"):
        raise ResearchAcceptanceError("PROVIDER_RESEARCH_AUTHORIZATION_REQUIRED", "explicit provider-backed research authorization is required")
    root = Path(kwargs["root"]).resolve()
    edition_date = str(kwargs["edition_date"])
    run_id = str(kwargs.get("run_id") or f"provider-research-acceptance-{uuid4()}")
    preflight_now = kwargs.get("preflight_now")
    if kwargs.get("technical_validation") and preflight_now is not None:
        raise ResearchAcceptanceError("TECHNICAL_ACCEPTANCE_TIME_OVERRIDE_FORBIDDEN", "technical provider acceptance cannot override time")
    durable = kwargs.pop("require_durable_archive", False)
    destination = kwargs.pop("durable_archive_root", None)
    archive = None
    if durable:
        destination = acceptance_archive_root(root, destination)
        try:
            proof = json.loads((destination / "provider-free-durability-proof.json").read_text(encoding="utf-8"))
            proven = verify_acceptance_bundle(Path(proof["bundle"]))
            if proof.get("status") != "PASS" or proof.get("provider_calls") != 0 or not proof.get("source_removed") or not proof.get("discovery"):
                raise ValueError("provider-free archival proof did not pass")
            if (proof.get("tamper"), proof.get("overwrite"), proof.get("missing_required")) != ("ACCEPTANCE_HASH_MISMATCH", "ACCEPTANCE_BUNDLE_EXISTS", "ACCEPTANCE_BUNDLE_INCOMPLETE"):
                raise ValueError("archival failure injection proof is incomplete")
            if sha256_file(Path(proof["bundle"]) / "manifest.json") != proof["manifest_sha256"]:
                raise ValueError("archival proof identity differs")
            archive = LocalAcceptanceArchive(root=root, run_dir=root / "daily-runs" / edition_date / "runs" / run_id,
                run_id=run_id, edition_date=edition_date, destination=destination)
            if proven["source_git_revision"] != archive.manifest["source_git_revision"]:
                raise ValueError("rerun archival proof for the current implementation commit")
        except (OSError, KeyError, ValueError, ArchiveError) as exc:
            raise ResearchAcceptanceError("BLOCKED_PRE_PROVIDER", f"durable archive readiness: {exc}") from exc
    live_gates = None
    try:
        audit_acceptance_environment(root, edition_date=edition_date, run_id=run_id,
            service_probe=kwargs.get("service_probe"), now=preflight_now,
            technical_validation=bool(kwargs.get("technical_validation")))
        if archive is not None:
            live_gates = audit_live_provider_gates(root, kwargs["provider"])
            live_gates["durable_archive"] = {"status": "PASS", "bundle": str(archive.bundle), "manifest_initialized": True}
    except Exception as exc:
        if archive is not None:
            atomic_write_json(archive.run_dir / "live-preflight.json", {"status": "BLOCKED_PRE_PROVIDER", "run_id": run_id,
                "code": getattr(exc, "code", type(exc).__name__), "detail": redact_text(str(exc)), "provider_calls": 0})
            archive.finalize(required=["live-preflight.json"], provider_calls=0, run_result="BLOCKED_PRE_PROVIDER")
            raise ResearchAcceptanceError("BLOCKED_PRE_PROVIDER", f"{exc}; preserved at {archive.bundle}") from exc
        raise
    kwargs["root"] = root
    kwargs["run_id"] = run_id
    if archive is not None:
        kwargs["artifact_checkpoint"] = archive.snapshot
    orchestrator = build_provider_research_acceptance_orchestrator(**kwargs)
    if archive is not None:
        atomic_write_json(archive.run_dir / "live-preflight.json", live_gates)
        archive.snapshot()
    try:
        state = orchestrator.run()
        report = write_provider_research_acceptance_report(orchestrator, state)
        if archive is not None:
            archive.finalize(required=required_acceptance_artifacts(archive.run_dir, state, orchestrator.provider_research.calls),
                provider_calls=orchestrator.provider_research.calls, run_result=state.get("run_result", "UNKNOWN"))
            orchestrator.acceptance_archive = archive.bundle
        return orchestrator, state, report
    except Exception:
        if archive is not None and archive.manifest["completion_state"] not in {"COMPLETE", "INCOMPLETE"}:
            archive.snapshot()
        raise
