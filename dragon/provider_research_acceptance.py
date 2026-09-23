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
from typing import Any, Callable, Protocol
from uuid import uuid4
from zoneinfo import ZoneInfo

from dragon.archive import DisabledGitArchiveProvider
from dragon.config import load_local_config
from dragon.deep_research_executor import ResearchAdapter, discovery_adapter_from_config
from dragon.orchestrator import Orchestrator
from dragon.pipeline import build_stage_definitions
from dragon.providers import LocalCommandEditorialProvider, ProviderError
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

    def research(self, edition_date: str, continuity: dict | None = None) -> dict:
        self.calls += 1
        if self.calls > self.call_limit:
            raise ProviderError(
                "PROVIDER_RESEARCH_CALL_LIMIT_EXCEEDED",
                "provider-backed research acceptance permits exactly one research() call",
            )
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        requested_at = datetime.now(ZoneInfo(self.timezone)).isoformat()
        request = {
            "schema_version": 1,
            "run_id": self.run_id,
            "provider_call_index": self.calls,
            "requested_at": requested_at,
            "edition_date": edition_date,
            "provider": self._identity(),
            "provider_input": deepcopy(continuity or {}),
        }
        request_path = self.artifact_dir / "request.json"
        atomic_write_json(request_path, request)
        raw_path = self.artifact_dir / "research.raw.json"
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
    audit_acceptance_environment(
        root,
        edition_date=edition_date,
        run_id=run_id,
        service_probe=kwargs.get("service_probe"),
        now=preflight_now,
        technical_validation=bool(kwargs.get("technical_validation")),
    )
    kwargs["root"] = root
    kwargs["run_id"] = run_id
    orchestrator = build_provider_research_acceptance_orchestrator(**kwargs)
    state = orchestrator.run()
    return orchestrator, state, write_provider_research_acceptance_report(orchestrator, state)
