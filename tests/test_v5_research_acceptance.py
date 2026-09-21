"""Offline contract tests for the provider-free fresh research harness."""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

import pytest

from dragon.deep_research_executor import FixtureResearchAdapter
from dragon.pipeline import build_stage_definitions
from dragon.providers import UnconfiguredEditorialProvider
from dragon.research_acceptance import (
    FORBIDDEN_STAGES,
    RESEARCH_ACCEPTANCE_MODE,
    RESEARCH_ACCEPTANCE_STAGES,
    ResearchAcceptanceError,
    audit_acceptance_environment,
    build_fresh_research_seed,
    build_research_acceptance_orchestrator,
    run_research_acceptance,
)


ROOT = Path(__file__).resolve().parents[1]
DATE = "2099-12-29"
RUN_ID = "research-acceptance-offline"


def _fixture_root(tmp_path: Path) -> Path:
    root = tmp_path / "acceptance-root"
    shutil.copytree(ROOT / "config", root / "config")
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "acceptance@example.invalid"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Acceptance Fixture"], cwd=root, check=True)
    subprocess.run(["git", "add", "config"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-m", "fixture config"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "switch", "-c", "codex/research-acceptance-test"], cwd=root, check=True, capture_output=True)
    return root


def _passing_probe(_: dict) -> dict:
    return {"status": "PASS", "endpoint": "fixture://searxng", "http_status": 200, "bytes_sampled": 1}


def test_fresh_seed_is_current_identity_empty_and_time_scoped(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    seed = build_fresh_research_seed(
        root=root, edition_date=DATE, timezone="Africa/Casablanca", run_id=RUN_ID,
        created_at="2099-12-29T07:00:00+01:00",
    )

    assert seed["edition_date"] == DATE
    assert seed["sources"] == []
    assert len(seed["sections"]) == 23
    assert all(section["status"] == "NO_NEWS" and section["candidates"] == [] for section in seed["sections"])
    metadata = seed["research_acceptance_seed"]
    assert metadata["run_id"] == RUN_ID
    assert metadata["research_window"] == {"edition_month": "2099-12", "general_search_time_range": "month"}
    assert metadata["provenance"] == "FRESH_EMPTY_SEED_NO_HISTORICAL_EVIDENCE"
    assert set(metadata["config_hashes"]) == {
        "config/local-automation.yaml", "config/general-search.yaml", "config/source-coverage.yaml",
        "config/research-budget.yaml", "config/deep-research.yaml",
    }


def test_acceptance_preflight_is_clean_development_only_and_provider_free(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    report = audit_acceptance_environment(root, edition_date=DATE, run_id=RUN_ID, service_probe=_passing_probe)

    assert report["status"] == "PASS"
    assert report["provider_requirement"] == "NOT_APPLICABLE_PROVIDER_FREE_ACCEPTANCE"
    assert report["production_preflight"] == "NOT_RUN_AND_UNMODIFIED"
    (root / "unrelated.txt").write_text("dirty", encoding="utf-8")
    with pytest.raises(ResearchAcceptanceError, match="unrelated") as caught:
        audit_acceptance_environment(root, edition_date=DATE, run_id=RUN_ID, service_probe=_passing_probe)
    assert caught.value.code == "ACCEPTANCE_WORKTREE_DIRTY"


def test_acceptance_preflight_refuses_a_late_current_edition_without_creating_a_run(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    with pytest.raises(ResearchAcceptanceError) as caught:
        run_research_acceptance(
            root=root,
            edition_date="2026-09-21",
            run_id=RUN_ID,
            service_probe=_passing_probe,
            preflight_now=datetime.fromisoformat("2026-09-21T12:30:01+00:00"),
        )
    assert caught.value.code == "ACCEPTANCE_DEADLINE_PASSED"
    assert not (root / "daily-runs" / "2026-09-21").exists()


def test_harness_runs_real_research_path_offline_and_stops_before_editorial(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    adapter = FixtureResearchAdapter({})

    orchestrator, state, report_path = run_research_acceptance(
        root=root, edition_date=DATE, run_id=RUN_ID, research_adapter=adapter,
        service_probe=_passing_probe, created_at="2099-12-29T07:00:00+01:00", use_lock=False,
    )

    assert tuple(orchestrator.stage_names) == RESEARCH_ACCEPTANCE_STAGES
    assert not (set(orchestrator.stage_names) & FORBIDDEN_STAGES)
    assert state["execution_mode"] == "START_FRESH_RUN"
    assert state["source_attempt_id"] == f"research-acceptance:{RUN_ID}"
    assert state["stages"]["deep_research"]["status"] == "COMPLETE"
    assert state["stages"]["deep_research_execution"]["status"] == "COMPLETE"
    assert state["stages"]["research_recovery"]["error_code"] == "RESEARCH_RECOVERY_REQUIRED"
    deep = json.loads((orchestrator.store.run_dir / "deep-research" / "state.json").read_text(encoding="utf-8"))
    execution = json.loads((orchestrator.store.run_dir / "deep-research" / "execution-report.json").read_text(encoding="utf-8"))
    recovery = json.loads((orchestrator.store.run_dir / "research-recovery" / "plan.json").read_text(encoding="utf-8"))
    continuity = json.loads((orchestrator.store.run_dir / "research" / "continuity-context.json").read_text(encoding="utf-8"))
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert deep["jobs"] and sum(len(job["question_tree"]) for job in deep["jobs"]) > 0
    assert execution["status"] == "EXECUTED"
    assert sum(len(job["actions"]) for job in execution["jobs"]) > 0
    assert recovery["status"] == "RECOVERY_REQUIRED"
    assert report["mode"] == RESEARCH_ACCEPTANCE_MODE
    assert report["verdict"] == "RESEARCH_RECOVERY_REQUIRED"
    assert report["not_production_readiness"] is True
    assert report["provider_calls"] == 0
    assert report["publication_status"] != "COMPLETE"
    assert report["seed_snapshot_sha256"]
    assert continuity["reason"] == "FRESH_RESEARCH_ACCEPTANCE_DOES_NOT_REUSE_HISTORICAL_CONTINUITY"


def test_harness_rejects_duplicate_identity_and_any_resume_or_retry(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    run_research_acceptance(
        root=root, edition_date=DATE, run_id=RUN_ID, research_adapter=FixtureResearchAdapter({}),
        service_probe=_passing_probe, use_lock=False,
    )
    with pytest.raises(ResearchAcceptanceError) as caught:
        build_research_acceptance_orchestrator(
            root=root, edition_date=DATE, run_id=RUN_ID, research_adapter=FixtureResearchAdapter({}),
            service_probe=_passing_probe,
        )
    assert caught.value.code == "FRESH_ACCEPTANCE_RUN_EXISTS"
    with pytest.raises(ResearchAcceptanceError) as caught:
        run_research_acceptance(root=root, edition_date=DATE, resume=True)
    assert caught.value.code == "FRESH_RUN_RESUME_OR_RETRY_UNSUPPORTED"


def test_production_registry_and_preflight_contract_are_not_replaced() -> None:
    production_names = {definition.name for definition in build_stage_definitions(UnconfiguredEditorialProvider())}
    assert FORBIDDEN_STAGES <= production_names
    local = (ROOT / "config" / "local-automation.yaml").read_text(encoding="utf-8")
    assert "expected_branch: main" in local
    assert "require_ai_provider: true" in local
