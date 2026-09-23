"""Explicit provider-free, research-only acceptance execution boundary.

This module is deliberately separate from ``dragon_daily.py`` and the
production preflight.  It creates a new V5 *fresh* run and executes only the
existing source-monitoring through research-recovery stages.  It is useful for
proving a local research integration without granting any editorial,
publication, archive, or delivery capability.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, time
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any, Callable
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen
from uuid import uuid4
from zoneinfo import ZoneInfo

import yaml

from dragon.config import load_local_config
from dragon.deep_research import load_deep_research_config
from dragon.deep_research_executor import discovery_adapter_from_config
from dragon.orchestrator import Orchestrator
from dragon.pipeline import build_stage_definitions
from dragon.providers import SECTION_HEADINGS
from dragon.research_planning import load_research_budget_config
from dragon.source_coverage import load_source_coverage
from dragon.stages import StageContext, StageDefinition, StageFailure, StageResult
from dragon.state import EXECUTION_MODE_FRESH, atomic_write_json, sha256_file


RESEARCH_ACCEPTANCE_MODE = "RESEARCH_ACCEPTANCE_PROVIDER_FREE"
TECHNICAL_RESEARCH_ACCEPTANCE_MODE = "TECHNICAL_RESEARCH_ACCEPTANCE_PROVIDER_FREE"
RESEARCH_ACCEPTANCE_STAGES = (
    "preflight",
    "source_monitoring",
    "research",
    "source_intelligence",
    "research_planning",
    "deep_research",
    "deep_research_execution",
    "research_recovery",
)
FORBIDDEN_STAGES = frozenset(
    {
        "article_generation",
        "claim_evidence_graph",
        "media_critic",
        "science_integrity",
        "investigation_engine",
        "adversarial_review",
        "factcheck",
        "chief_editor",
        "arabic_language_qa",
        "cover_direction",
        "cover",
        "layout_direction",
        "publication_source",
        "pdf",
        "epub",
        "final_qa",
        "github_archive",
        "whatsapp_delivery",
    }
)


class ResearchAcceptanceError(RuntimeError):
    """A failed acceptance-only environment or seed validation."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


class ProviderFreeAcceptanceProvider:
    """A guard object: the seeded research stage never calls a provider."""

    mode = RESEARCH_ACCEPTANCE_MODE
    available = False

    def research(self, edition_date: str, continuity: dict | None = None) -> dict:
        raise AssertionError("research acceptance must use its immutable local seed")

    def articles(self, research: dict) -> list[dict]:
        raise AssertionError("article generation is outside research acceptance")


def _canonical_json(value: dict[str, Any]) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _config_hashes(root: Path) -> dict[str, str]:
    required = (
        "config/local-automation.yaml",
        "config/general-search.yaml",
        "config/source-coverage.yaml",
        "config/research-budget.yaml",
        "config/deep-research.yaml",
    )
    missing = [relative for relative in required if not (root / relative).is_file()]
    if missing:
        raise ResearchAcceptanceError("ACCEPTANCE_CONFIG_MISSING", ", ".join(missing))
    return {relative: sha256_file(root / relative) for relative in required}


def build_fresh_research_seed(
    *,
    root: Path,
    edition_date: str,
    timezone: str,
    run_id: str,
    created_at: str | None = None,
    acceptance_mode: str = RESEARCH_ACCEPTANCE_MODE,
) -> dict[str, Any]:
    """Make a new, evidence-empty packet for the requested edition only.

    The all-``NO_NEWS`` shape intentionally produces normal breadth recovery
    needs.  It contains no source, event, candidate, action, or evidence from
    a prior run, so it cannot inherit historical research readiness.
    """
    if acceptance_mode not in {RESEARCH_ACCEPTANCE_MODE, TECHNICAL_RESEARCH_ACCEPTANCE_MODE}:
        raise ResearchAcceptanceError("ACCEPTANCE_MODE_INVALID", str(acceptance_mode))
    parsed_date = date.fromisoformat(edition_date).isoformat()
    general = yaml.safe_load((root / "config" / "general-search.yaml").read_text(encoding="utf-8"))
    if not isinstance(general, dict) or not isinstance(general.get("time_range"), str):
        raise ResearchAcceptanceError("GENERAL_SEARCH_CONFIG_INVALID", "general search time range is unavailable")
    generated_at = created_at or datetime.now(ZoneInfo(timezone)).isoformat()
    packet = {
        "edition_date": parsed_date,
        "sources": [],
        "sections": [
            {
                "section_id": section_id,
                "status": "NO_NEWS",
                "candidates": [],
                "selected_candidate_id": None,
                "selection_reason": None,
                "no_news_reason": "بذرة قبول بحثية جديدة بلا أدلة أو أحداث موروثة؛ يلزم الاسترجاع المتحفظ.",
                "fallback_action": "DOSSIER_FOLLOW_UP",
            }
            for section_id, _ in SECTION_HEADINGS
        ],
        "research_acceptance_seed": {
            "schema_version": 1,
            "mode": acceptance_mode,
            "run_id": run_id,
            "edition_date": parsed_date,
            "timezone": timezone,
            "created_at": generated_at,
            "research_window": {
                "edition_month": parsed_date[:7],
                "general_search_time_range": general["time_range"],
            },
            "config_hashes": _config_hashes(root),
            "provenance": "FRESH_EMPTY_SEED_NO_HISTORICAL_EVIDENCE",
        },
    }
    validate_fresh_research_seed(
        packet,
        edition_date=parsed_date,
        timezone=timezone,
        run_id=run_id,
        acceptance_mode=acceptance_mode,
    )
    return packet


def validate_fresh_research_seed(
    packet: dict[str, Any],
    *,
    edition_date: str,
    timezone: str,
    run_id: str,
    acceptance_mode: str = RESEARCH_ACCEPTANCE_MODE,
) -> None:
    """Validate the acceptance seed without weakening provider packet rules."""
    if not isinstance(packet, dict) or packet.get("edition_date") != edition_date:
        raise ResearchAcceptanceError("FRESH_SEED_DATE_INVALID", "seed date must equal the requested edition date")
    if packet.get("sources") != []:
        raise ResearchAcceptanceError("FRESH_SEED_HISTORY_FORBIDDEN", "fresh acceptance seed cannot contain sources")
    expected_sections = [section_id for section_id, _ in SECTION_HEADINGS]
    sections = packet.get("sections")
    if not isinstance(sections, list) or [item.get("section_id") for item in sections if isinstance(item, dict)] != expected_sections:
        raise ResearchAcceptanceError("FRESH_SEED_SECTIONS_INVALID", "seed must contain each configured section exactly once")
    for section in sections:
        if not isinstance(section, dict) or any(
            section.get(field) != value
            for field, value in (
                ("status", "NO_NEWS"), ("candidates", []), ("selected_candidate_id", None),
                ("selection_reason", None), ("fallback_action", "DOSSIER_FOLLOW_UP"),
            )
        ):
            raise ResearchAcceptanceError("FRESH_SEED_EVIDENCE_FORBIDDEN", "fresh seed may not preselect an event or evidence")
    metadata = packet.get("research_acceptance_seed")
    if not isinstance(metadata, dict) or any(
        metadata.get(field) != value
        for field, value in (
            ("mode", acceptance_mode), ("edition_date", edition_date),
            ("timezone", timezone), ("run_id", run_id),
        )
    ):
        raise ResearchAcceptanceError("FRESH_SEED_METADATA_INVALID", "fresh seed identity metadata is incomplete")
    try:
        datetime.fromisoformat(str(metadata["created_at"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise ResearchAcceptanceError("FRESH_SEED_TIMESTAMP_INVALID", "seed execution time is invalid") from exc


def _git_output(root: Path, args: list[str]) -> str:
    try:
        result = subprocess.run(
            ["git", *args], cwd=root, capture_output=True, text=True, timeout=10, check=True
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ResearchAcceptanceError("ACCEPTANCE_GIT_UNAVAILABLE", str(exc)) from exc
    return result.stdout.strip()


def _acceptance_workspace_changes(root: Path, edition_date: str, run_id: str) -> list[str]:
    """Return pre-existing changes, excluding this freshly-created state tree only."""
    allowed_prefix = f"daily-runs/{edition_date}/runs/{run_id}/"
    changes: list[str] = []
    for line in _git_output(root, ["status", "--porcelain", "--untracked-files=all"]).splitlines():
        path = line[3:].strip().replace("\\", "/")
        if path.startswith(allowed_prefix):
            continue
        changes.append(line)
    return changes


def _probe_general_search(config: dict[str, Any]) -> dict[str, Any]:
    """Check only the private local service response; it yields no evidence."""
    base_url = str(config.get("base_url") or "")
    parsed = urlparse(base_url)
    if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ResearchAcceptanceError("GENERAL_SEARCH_ENDPOINT_UNSAFE", "acceptance requires a private local search endpoint")
    query = urlencode({"q": "DRAGON acceptance health", "format": "json", "language": config.get("language", "auto"), "categories": config.get("categories", "general")})
    endpoint = f"{base_url.rstrip('/')}/search?{query}"
    try:
        with urlopen(Request(endpoint, headers={"Accept": "application/json"}), timeout=int(config["timeout_seconds"])) as response:
            payload = response.read(min(int(config["maximum_bytes"]), 4096))
            status = getattr(response, "status", 200)
    except OSError as exc:
        raise ResearchAcceptanceError("GENERAL_SEARCH_UNHEALTHY", str(exc)) from exc
    if status != 200 or not payload:
        raise ResearchAcceptanceError("GENERAL_SEARCH_UNHEALTHY", f"HTTP {status}")
    return {"status": "PASS", "endpoint": f"{parsed.scheme}://{parsed.netloc}", "http_status": status, "bytes_sampled": len(payload)}


def audit_acceptance_environment(
    root: Path,
    *,
    edition_date: str,
    run_id: str,
    service_probe: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    now: datetime | None = None,
    technical_validation: bool = False,
) -> dict[str, Any]:
    """Acceptance-specific preflight.  It deliberately never checks AI providers."""
    root = root.resolve()
    requested_date = date.fromisoformat(edition_date)
    config = load_local_config(root)
    timezone = str(config["timezone"])
    current = now or datetime.now(ZoneInfo(timezone))
    if current.tzinfo is None:
        current = current.replace(tzinfo=ZoneInfo(timezone))
    else:
        current = current.astimezone(ZoneInfo(timezone))
    try:
        deadline = time.fromisoformat(str(config["scheduler"]["target_deadline"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise ResearchAcceptanceError("ACCEPTANCE_DEADLINE_CONFIG_INVALID", "scheduler target deadline is invalid") from exc
    acceptance_mode = (
        TECHNICAL_RESEARCH_ACCEPTANCE_MODE if technical_validation else RESEARCH_ACCEPTANCE_MODE
    )
    if requested_date < current.date():
        raise ResearchAcceptanceError(
            "ACCEPTANCE_EDITION_DATE_PAST",
            f"requested {requested_date.isoformat()} but local acceptance date is {current.date().isoformat()}",
        )
    if technical_validation and requested_date != current.date():
        raise ResearchAcceptanceError(
            "TECHNICAL_ACCEPTANCE_DATE_NOT_CURRENT",
            f"technical acceptance requires the actual local date {current.date().isoformat()}, got {requested_date.isoformat()}",
        )
    deadline_missed = current.timetz().replace(tzinfo=None) > deadline
    if not technical_validation and requested_date == current.date() and deadline_missed:
        raise ResearchAcceptanceError(
            "ACCEPTANCE_DEADLINE_PASSED",
            f"current local time {current.isoformat()} is after configured deadline {deadline.isoformat(timespec='minutes')} {timezone}",
        )
    branch = _git_output(root, ["branch", "--show-current"])
    if not branch.startswith("codex/"):
        raise ResearchAcceptanceError("ACCEPTANCE_BRANCH_UNAUTHORIZED", f"expected a codex development branch, got {branch or 'DETACHED'}")
    changes = _acceptance_workspace_changes(root, edition_date, run_id)
    if changes:
        raise ResearchAcceptanceError("ACCEPTANCE_WORKTREE_DIRTY", "\n".join(changes[:20]))
    general_path = root / "config" / "general-search.yaml"
    try:
        general = yaml.safe_load(general_path.read_text(encoding="utf-8"))
        if not isinstance(general, dict) or general.get("enabled") is not True or general.get("integration_test_status") != "PASS":
            raise ValueError("general search is not enabled and verified")
        load_source_coverage(root / "config" / "source-coverage.yaml", {section_id for section_id, _ in SECTION_HEADINGS})
        load_research_budget_config(root / "config" / "research-budget.yaml")
        load_deep_research_config(root / "config" / "deep-research.yaml", root / "config" / "deep-research-schema.json")
    except Exception as exc:  # configuration parsers provide detailed deterministic failures
        raise ResearchAcceptanceError("ACCEPTANCE_RESEARCH_CONFIG_INVALID", str(exc)) from exc
    probe = (service_probe or _probe_general_search)(general)
    if not isinstance(probe, dict) or probe.get("status") != "PASS":
        raise ResearchAcceptanceError("GENERAL_SEARCH_UNHEALTHY", "acceptance service probe did not pass")
    if discovery_adapter_from_config(root) is None:
        raise ResearchAcceptanceError("RESEARCH_ADAPTER_UNAVAILABLE", "no configured local discovery adapter")
    return {
        "status": "PASS",
        "mode": acceptance_mode,
        "edition_date": edition_date,
        "checked_at": current.isoformat(),
        "target_deadline": f"{deadline.isoformat(timespec='minutes')} {timezone}",
        "production_deadline_status": "PRODUCTION_DEADLINE_MISSED" if deadline_missed else "PRODUCTION_DEADLINE_NOT_MISSED",
        "technical_validation": technical_validation,
        "on_time_production_readiness": "NOT_APPLICABLE_TECHNICAL_VALIDATION" if technical_validation else "NOT_EVALUATED",
        "branch": branch,
        "workspace_clean_before_run": True,
        "provider_requirement": "NOT_APPLICABLE_PROVIDER_FREE_ACCEPTANCE",
        "production_preflight": "NOT_RUN_AND_UNMODIFIED",
        "research_configuration": "PASS",
        "local_search": probe,
        "config_hashes": _config_hashes(root),
    }


def _acceptance_preflight_stage(
    *,
    root: Path,
    seed: dict[str, Any],
    run_id: str,
    service_probe: Callable[[dict[str, Any]], dict[str, Any]] | None,
    technical_validation: bool,
    preflight_now: datetime | None,
) -> StageDefinition:
    def run(context: StageContext) -> StageResult:
        path = context.run_dir / "preflight.json"
        try:
            audit = audit_acceptance_environment(
                root,
                edition_date=context.edition_date,
                run_id=run_id,
                service_probe=service_probe,
                technical_validation=technical_validation,
                now=preflight_now,
            )
            validate_fresh_research_seed(
                seed,
                edition_date=context.edition_date,
                timezone=seed["research_acceptance_seed"]["timezone"],
                run_id=run_id,
                acceptance_mode=seed["research_acceptance_seed"]["mode"],
            )
        except ResearchAcceptanceError as exc:
            atomic_write_json(
                path,
                {
                    "status": "FAIL",
                    "mode": seed["research_acceptance_seed"]["mode"],
                    "code": exc.code,
                    "detail": exc.detail,
                },
            )
            raise StageFailure(exc.code, exc.detail, outputs=(path,)) from exc
        snapshot_path = context.run_dir / "research" / "acceptance-seed.json"
        snapshot = {"seed": seed, "sha256": hashlib.sha256(_canonical_json(seed)).hexdigest(), "immutable": True}
        atomic_write_json(snapshot_path, snapshot)
        audit["seed_snapshot"] = {"path": str(snapshot_path.relative_to(context.run_dir)), "sha256": snapshot["sha256"], "immutable": True}
        atomic_write_json(path, audit)
        return StageResult(outputs=(path, snapshot_path))

    return StageDefinition("preflight", (), run)


def build_research_acceptance_orchestrator(
    *,
    root: Path,
    edition_date: str,
    run_id: str | None = None,
    research_adapter=None,
    service_probe: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    created_at: str | None = None,
    use_lock: bool = True,
    technical_validation: bool = False,
    preflight_now: datetime | None = None,
) -> Orchestrator:
    """Build a new, non-resumable research-only V5 orchestrator."""
    root = root.resolve()
    config = load_local_config(root)
    timezone = str(config["timezone"])
    normalized_date = date.fromisoformat(edition_date).isoformat()
    acceptance_mode = (
        TECHNICAL_RESEARCH_ACCEPTANCE_MODE if technical_validation else RESEARCH_ACCEPTANCE_MODE
    )
    if technical_validation and created_at is not None:
        raise ResearchAcceptanceError(
            "TECHNICAL_ACCEPTANCE_TIMESTAMP_OVERRIDE_FORBIDDEN",
            "technical acceptance records its actual execution time and cannot accept a created_at override",
        )
    if technical_validation and preflight_now is not None:
        raise ResearchAcceptanceError(
            "TECHNICAL_ACCEPTANCE_TIME_OVERRIDE_FORBIDDEN",
            "technical acceptance uses the actual local execution time and cannot accept a preflight_now override",
        )
    identifier = run_id or f"research-acceptance-{uuid4()}"
    run_dir = root / "daily-runs" / normalized_date / "runs" / identifier
    if run_dir.exists():
        raise ResearchAcceptanceError("FRESH_ACCEPTANCE_RUN_EXISTS", str(run_dir))
    seed = build_fresh_research_seed(root=root, edition_date=normalized_date, timezone=timezone, run_id=identifier, created_at=created_at, acceptance_mode=acceptance_mode)
    adapter = research_adapter if research_adapter is not None else discovery_adapter_from_config(root)
    definitions = build_stage_definitions(
        ProviderFreeAcceptanceProvider(),
        research_adapter=adapter,
        seed_research_packet=deepcopy(seed),
        offline_replay=True,
        continuity_context={
            "schema_version": 1,
            "status": "NOT_APPLICABLE",
            "reason": "FRESH_RESEARCH_ACCEPTANCE_DOES_NOT_REUSE_HISTORICAL_CONTINUITY",
            "prior_edition": None,
            "continuity_items": [],
        },
    )
    selected = [definition for definition in definitions if definition.name in RESEARCH_ACCEPTANCE_STAGES]
    if tuple(definition.name for definition in selected) != RESEARCH_ACCEPTANCE_STAGES:
        raise ResearchAcceptanceError("ACCEPTANCE_STAGE_BOUNDARY_INVALID", "production research stage registry changed")
    selected[0] = _acceptance_preflight_stage(
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
        source_attempt_id=f"research-acceptance:{identifier}",
        use_lock=use_lock,
        target_deadline=None,
    )
    orchestrator.acceptance_mode = acceptance_mode
    orchestrator.technical_validation = technical_validation
    return orchestrator


def write_research_acceptance_report(orchestrator: Orchestrator, state: dict[str, Any]) -> Path:
    """Persist an operator-facing verdict even when recovery correctly fails closed."""
    run_dir = orchestrator.store.run_dir
    stage_records = state.get("stages", {})
    recovery = stage_records.get("research_recovery", {})
    if recovery.get("status") == "COMPLETE":
        verdict = "RESEARCH_EXECUTION_COMPLETE_NOT_PUBLICATION_ACCEPTED"
    elif recovery.get("error_code") == "RESEARCH_RECOVERY_REQUIRED":
        verdict = "RESEARCH_RECOVERY_REQUIRED"
    else:
        verdict = "RESEARCH_ACCEPTANCE_BLOCKED"
    preflight_path = run_dir / "preflight.json"
    snapshot_path = run_dir / "research" / "acceptance-seed.json"
    preflight = json.loads(preflight_path.read_text(encoding="utf-8")) if preflight_path.is_file() else None
    report = {
        "schema_version": 1,
        "mode": getattr(orchestrator, "acceptance_mode", RESEARCH_ACCEPTANCE_MODE),
        "verdict": verdict,
        "not_production_readiness": True,
        "on_time_production_readiness": (
            "NOT_APPLICABLE_TECHNICAL_VALIDATION"
            if getattr(orchestrator, "technical_validation", False)
            else "NOT_EVALUATED"
        ),
        "production_deadline_status": (preflight or {}).get("production_deadline_status", "NOT_EVALUATED"),
        "edition_date": orchestrator.edition_date,
        "timezone": orchestrator.timezone,
        "run_id": orchestrator.store.run_id,
        "source_attempt_id": state.get("source_attempt_id"),
        "run_directory": str(run_dir),
        "execution_mode": state.get("execution_mode"),
        "publication_status": state.get("publication_status"),
        "provider_calls": 0,
        "allowed_stages": list(RESEARCH_ACCEPTANCE_STAGES),
        "forbidden_stages_absent": sorted(FORBIDDEN_STAGES - set(stage_records)),
        "stage_statuses": {name: record.get("status") for name, record in stage_records.items()},
        "preflight": preflight,
        "seed_snapshot_sha256": sha256_file(snapshot_path) if snapshot_path.is_file() else None,
        "recovery_error_code": recovery.get("error_code"),
    }
    path = run_dir / "research-acceptance-report.json"
    atomic_write_json(path, report)
    return path


def run_research_acceptance(**kwargs: Any) -> tuple[Orchestrator, dict[str, Any], Path]:
    """Run exactly one fresh attempt; callers receive no resume or retry path."""
    if {"resume", "retry_stage", "from_stage"} & set(kwargs):
        raise ResearchAcceptanceError("FRESH_RUN_RESUME_OR_RETRY_UNSUPPORTED", "research acceptance only creates new run identities")
    root = Path(kwargs["root"]).resolve()
    edition_date = str(kwargs["edition_date"])
    run_id = str(kwargs.get("run_id") or f"research-acceptance-{uuid4()}")
    preflight_now = kwargs.get("preflight_now")
    if kwargs.get("technical_validation") and preflight_now is not None:
        raise ResearchAcceptanceError(
            "TECHNICAL_ACCEPTANCE_TIME_OVERRIDE_FORBIDDEN",
            "technical acceptance uses the actual local execution time and cannot accept a preflight_now override",
        )
    # Check the authorized execution window before StateStore can create a
    # fresh run identity.  The stage repeats this audit after initialization
    # so its persisted preflight report remains hash-bound to the run.
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
    orchestrator = build_research_acceptance_orchestrator(**kwargs)
    state = orchestrator.run()
    return orchestrator, state, write_research_acceptance_report(orchestrator, state)
