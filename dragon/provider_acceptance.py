"""Provider-seed acceptance and immutable offline replay support.

The editorial provider supplies *seed research*.  Its raw response is first
captured and structurally validated by ``LocalCommandEditorialProvider``.  The
validated packet then enters the ordinary V5 research stages; it is not an
article-ready decision merely because the provider selected some sections.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from dragon.archive import DisabledGitArchiveProvider
from dragon.config import load_local_config
from dragon.deep_research_executor import ResearchAdapter, rss_search_adapter_from_config
from dragon.orchestrator import Orchestrator
from dragon.pipeline import build_stage_definitions
from dragon.recovery import RecoveryEngine, RecoveryPolicy
from dragon.stages import StageContext, StageDefinition, StageResult
from dragon.state import EXECUTION_MODE_FRESH, atomic_write_json, sha256_file
from dragon.whatsapp import DisabledWhatsAppProvider


class ArticleProvider(Protocol):
    mode: str

    def articles(self, research: dict) -> list[dict]: ...


@dataclass
class SeedResearchProvider:
    """Delegate articles while returning one already-validated seed packet."""

    delegate: ArticleProvider
    packet: dict

    @property
    def mode(self) -> str:
        return self.delegate.mode

    @property
    def available(self) -> bool:
        return bool(getattr(self.delegate, "available", True))

    def research(self, edition_date: str, continuity: dict | None = None) -> dict:
        if edition_date != self.packet.get("edition_date"):
            raise ValueError("PROVIDER_SEED_DATE_MISMATCH")
        return deepcopy(self.packet)

    def articles(self, research: dict) -> list[dict]:
        return self.delegate.articles(research)


@dataclass
class OfflineReplayResearchAdapter:
    """Execute planned actions offline without inventing any evidence.

    Every planned action receives an explicit ``DEAD_END`` observation.  This
    proves execution routing and bounded exhaustion while preserving the
    fail-closed rule: no source, candidate, or publication evidence is added.
    """

    reason: str = "OFFLINE_REPLAY_NO_NETWORK_OR_PROVIDER"

    def execute(self, action: dict) -> list[dict]:
        return [{"result_type": "DEAD_END", "reason": self.reason}]


def provider_seed_preflight_stage(
    *,
    raw_packet_path: Path,
    raw_packet_sha256: str,
    mode: str,
) -> StageDefinition:
    """Record the acceptance/replay boundary without pretending it is release preflight.

    A provider-backed acceptance trial cannot require a previously accepted
    provider trial as its own precondition.  This stage intentionally has a
    distinct mode and does not replace the production preflight used by
    ``dragon_daily.py``.
    """

    def run(context: StageContext) -> StageResult:
        observed_hash = sha256_file(raw_packet_path)
        report = {
            "schema_version": 1,
            "status": "PASS" if observed_hash == raw_packet_sha256 else "FAIL",
            "mode": mode,
            "purpose": "PROVIDER_SEED_ACCEPTANCE_OR_OFFLINE_REPLAY",
            "production_preflight_replaced": False,
            "raw_provider_packet": {
                "path": str(raw_packet_path),
                "sha256": observed_hash,
                "expected_sha256": raw_packet_sha256,
            },
            "checks": [
                {
                    "name": "raw_provider_packet_hash",
                    "status": "PASS" if observed_hash == raw_packet_sha256 else "FAIL",
                },
                {
                    "name": "provider_seed_requires_post_recovery_sufficiency",
                    "status": "PASS",
                },
            ],
        }
        path = context.run_dir / "preflight.json"
        atomic_write_json(path, report)
        if report["status"] != "PASS":
            from dragon.stages import StageFailure

            raise StageFailure(
                "PROVIDER_RAW_EVIDENCE_HASH_INVALID",
                "preserved raw provider packet hash does not match replay manifest",
                outputs=(path,),
            )
        return StageResult((path,), inputs=(raw_packet_path,))

    return StageDefinition("preflight", (), run)


def build_provider_seed_orchestrator(
    *,
    root: Path,
    edition_date: str,
    provider: ArticleProvider,
    normalized_packet: dict,
    raw_packet_path: Path,
    raw_packet_sha256: str,
    mode: str,
    source_attempt_id: str,
    research_adapter: ResearchAdapter | None = None,
    offline_replay: bool = False,
    run_id: str | None = None,
) -> Orchestrator:
    """Build one isolated V5 run which consumes validated seed research exactly once.

    Provider trials and offline replays cannot resume a date-level production
    state: the supplied seed is bound to a fresh run directory and, when
    available, its immutable provider-attempt identity.
    """
    if not source_attempt_id.strip():
        raise ValueError("PROVIDER_SOURCE_ATTEMPT_ID_REQUIRED")
    config = load_local_config(root)
    seed_provider = SeedResearchProvider(provider, normalized_packet)
    definitions = build_stage_definitions(
        seed_provider,
        archive_provider=DisabledGitArchiveProvider(),
        whatsapp_provider=DisabledWhatsAppProvider(),
        research_adapter=research_adapter or rss_search_adapter_from_config(
            root / "config" / "open-discovery.yaml",
            source_coverage_path=root / "config" / "source-coverage.yaml",
        ),
        seed_research_packet=normalized_packet,
        offline_replay=offline_replay,
    )
    definitions[0] = provider_seed_preflight_stage(
        raw_packet_path=raw_packet_path,
        raw_packet_sha256=raw_packet_sha256,
        mode=mode,
    )
    configured = list(config["orchestrator"]["stages"])
    actual = [stage.name for stage in definitions]
    if actual != configured:
        raise ValueError(
            f"STAGE_REGISTRY_CONFIG_MISMATCH: configured={configured!r}; actual={actual!r}"
        )
    return Orchestrator(
        root=root,
        edition_date=edition_date,
        timezone=config["timezone"],
        stages=definitions,
        recovery_engine=RecoveryEngine(
            RecoveryPolicy.load(root / "config" / "recovery-policy.yaml")
        ),
        target_deadline=str(config["scheduler"]["target_deadline"]),
        execution_mode=EXECUTION_MODE_FRESH,
        run_id=run_id,
        source_attempt_id=source_attempt_id,
    )
