"""Durability and replay failure injection without external provider calls."""

from copy import deepcopy
import json
from pathlib import Path
import shutil
from uuid import uuid4

import pytest

from dragon.acceptance_replay import replay_acceptance_bundle
from dragon.archive import ArchiveError, LocalAcceptanceArchive, discover_acceptance_bundles, prove_acceptance_archive, verify_acceptance_bundle
from dragon.provider_acceptance import OfflineReplayResearchAdapter
from dragon.provider_research_acceptance import OneShotProviderResearch, run_provider_research_acceptance
from dragon.providers import LocalCommandEditorialProvider, SECTION_HEADINGS
from dragon.research_acceptance import ResearchAcceptanceError
from dragon.state import atomic_write_json

ROOT = Path(__file__).resolve().parents[1]
DATE = "2099-12-29"


def test_storage_proof_survives_source_deletion_and_detects_all_failure_cases(tmp_path):
    result = prove_acceptance_archive(ROOT, tmp_path / "archive")
    assert result["provider_calls"] == 0
    assert result["source_removed"] is True
    assert result["discovery"] is True
    assert result["tamper"] == "ACCEPTANCE_HASH_MISMATCH"
    assert result["overwrite"] == "ACCEPTANCE_BUNDLE_EXISTS"
    assert result["missing_required"] == "ACCEPTANCE_BUNDLE_INCOMPLETE"
    assert verify_acceptance_bundle(Path(result["bundle"]))["completion_state"] == "COMPLETE"


def test_manifest_tamper_and_missing_archived_file_fail_verification(tmp_path):
    result = prove_acceptance_archive(ROOT, tmp_path / "archive")
    bundle = Path(result["bundle"])
    manifest = bundle / "manifest.json"
    original = manifest.read_bytes()
    manifest.write_bytes(original + b" ")
    with pytest.raises(ArchiveError) as caught:
        verify_acceptance_bundle(bundle)
    assert caught.value.code == "ACCEPTANCE_HASH_MISMATCH"
    manifest.write_bytes(original)
    (bundle / "artifacts/state.json").unlink()
    with pytest.raises(ArchiveError) as caught:
        verify_acceptance_bundle(bundle)
    assert caught.value.code == "ACCEPTANCE_HASH_MISMATCH"


def test_archive_refuses_worktree_storage_and_invalid_identity(tmp_path):
    with pytest.raises(ArchiveError) as caught:
        LocalAcceptanceArchive(root=ROOT, run_dir=tmp_path, run_id="fixture", edition_date=DATE, destination=ROOT / "tmp/archive")
    assert caught.value.code == "ACCEPTANCE_ARCHIVE_NOT_DURABLE"
    with pytest.raises(ArchiveError):
        LocalAcceptanceArchive(root=ROOT, run_dir=tmp_path, run_id="../escape", edition_date=DATE, destination=tmp_path / "archive")


def test_discovery_keeps_incomplete_bundles_visible_and_finalized_bundles_immutable(tmp_path):
    result = prove_acceptance_archive(ROOT, tmp_path / "archive")
    bundles = discover_acceptance_bundles(tmp_path / "archive")
    assert len(bundles) == 2
    partial = next(path for path in bundles if path.name.startswith("archive-incomplete"))
    assert verify_acceptance_bundle(partial, require_complete=False)["completion_state"] == "INCOMPLETE"
    with pytest.raises(ArchiveError):
        verify_acceptance_bundle(partial)


def _packet():
    return {
        "edition_date": DATE,
        "sources": [{"id": "fixture", "url": "https://authority.example/notice", "publisher": "authority.example",
            "publication_date": DATE, "accessed_at": f"{DATE}T07:00:00+00:00", "source_type": "official",
            "origin": "authority.example", "claim_supported": "Synthetic fixture operational notice.", "doi": None,
            "publication_status": "news", "full_text_status": "NOT_APPLICABLE", "methods_read": False,
            "limitations_read": False, "science_metadata": None}],
        "sections": [{"section_id": section, "status": "NO_NEWS", "candidates": [],
            "selected_candidate_id": None, "selection_reason": None,
            "no_news_reason": "Synthetic offline fixture has no qualifying candidate.", "fallback_action": "DOSSIER_FOLLOW_UP"}
            for section, _ in SECTION_HEADINGS],
        "hard_target_results": [{"target_id": f"HARD:{lane}", "status": "NO_QUALIFYING_CANDIDATE_FOUND",
            "search_intent": f"Synthetic current {lane} discovery.",
            "search_attempts": [{"query": f"current {lane} notice", "purpose": "Synthetic fixture search attempt"}],
            "candidate_matches": [], "no_qualifying_reason": "No qualifying candidate in this synthetic packet."}
            for lane in ("ACCOUNTABILITY", "SERVICE")],
    }


def _run_archived_fixture(tmp_path, monkeypatch, *, omit_service=False):
    destination = tmp_path / "archive"
    prove_acceptance_archive(ROOT, destination)
    packet = _packet()
    if omit_service:
        packet["hard_target_results"] = packet["hard_target_results"][:1]
    calls = []

    def invoke(provider, operation, payload):
        calls.append(operation)
        assert operation == "research"
        provider._capture("research.request.json", payload)
        provider._capture("research.raw.json", packet)
        return deepcopy(packet)

    monkeypatch.setattr(LocalCommandEditorialProvider, "_invoke", invoke)
    monkeypatch.setattr("dragon.research_acceptance._acceptance_workspace_changes", lambda *_: [])
    monkeypatch.setattr("dragon.provider_research_acceptance.audit_live_provider_gates", lambda *_: {"status": "PASS", "fixture": True, "provider_calls": 0})
    run_id = f"provider-research-acceptance-test-{uuid4()}"
    try:
        orchestrator, state, _ = run_provider_research_acceptance(root=ROOT, edition_date=DATE,
            run_id=run_id, provider=LocalCommandEditorialProvider(command=("fixture-provider",)), provider_authorized=True,
            research_adapter=OfflineReplayResearchAdapter(), service_probe=lambda _: {"status": "PASS"},
            require_durable_archive=True, durable_archive_root=destination)
        bundle = orchestrator.acceptance_archive
    finally:
        path = ROOT / "daily-runs" / DATE / "runs" / run_id
        if path.exists():
            shutil.rmtree(path)
    assert calls == ["research"]
    assert not path.exists()
    return bundle, state, calls


def test_full_native_bundle_replays_after_run_tree_deletion_without_provider_or_network(tmp_path, monkeypatch):
    bundle, state, calls = _run_archived_fixture(tmp_path, monkeypatch)
    assert state["stages"]["deep_research_execution"]["status"] == "COMPLETE"
    assert verify_acceptance_bundle(bundle)["provider_calls"] == 1
    monkeypatch.setattr(LocalCommandEditorialProvider, "_invoke", lambda *_: pytest.fail("replay invoked provider"))
    replay = replay_acceptance_bundle(bundle, code_root=ROOT)
    assert replay["FRESH_LIVE_REPLAY"] == "PASS", replay
    assert replay["provider_calls"] == replay["network_calls"] == 0
    assert replay["checks"]["normalization"] == "PASS"
    assert replay["checks"]["hard_target_dispositions"] == "PASS"
    assert replay["checks"]["action_materialization"] == "PASS"
    assert replay["checks"]["scheduling"] == "PASS"
    assert all(epoch["budget_allocation"]["round_cap"] == 8 for epoch in replay["epochs"])
    assert calls == ["research"]


def test_service_provider_omission_is_preserved_and_replay_reproduces_same_failure(tmp_path, monkeypatch):
    bundle, state, _ = _run_archived_fixture(tmp_path, monkeypatch, omit_service=True)
    assert state["stages"]["research"]["error_code"] == "HARD_TARGET_DISPOSITION_MISSING"
    assert not (bundle / "artifacts/provider-research/normalized-research-packet.json").exists()
    invocation = json.loads((bundle / "artifacts/provider-research/invocation.json").read_text(encoding="utf-8"))
    assert invocation["diagnostics"]["hard_target_results"][0]["target_id"] == "HARD:SERVICE"
    replay = replay_acceptance_bundle(bundle, code_root=ROOT)
    assert replay["FRESH_LIVE_REPLAY"] == "PASS"
    assert replay["checks"]["reproduced_failure"] == "HARD_TARGET_DISPOSITION_MISSING"
    assert replay["checks"]["scheduling"] == "NOT_REACHED"


def test_missing_durability_proof_blocks_before_provider(tmp_path):
    with pytest.raises(ResearchAcceptanceError) as caught:
        run_provider_research_acceptance(root=ROOT, edition_date=DATE,
            provider=LocalCommandEditorialProvider(command=("should-never-run",)), provider_authorized=True,
            require_durable_archive=True, durable_archive_root=tmp_path / "archive")
    assert caught.value.code == "BLOCKED_PRE_PROVIDER"


def test_replay_rejects_tampered_bundle_before_normalizing(tmp_path, monkeypatch):
    bundle, _, _ = _run_archived_fixture(tmp_path, monkeypatch)
    (bundle / "artifacts/provider-research/research.raw.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(LocalCommandEditorialProvider, "normalize_research_packet", lambda *_args, **_kwargs: pytest.fail("unverified bytes reached normalization"))
    with pytest.raises(ArchiveError) as caught:
        replay_acceptance_bundle(bundle, code_root=ROOT)
    assert caught.value.code == "ACCEPTANCE_HASH_MISMATCH"


def test_archive_failure_before_invocation_spends_zero_provider_calls(tmp_path):
    class ForbiddenProvider:
        mode = "production"
        def research(self, *_args):
            pytest.fail("archive failure did not block provider")
    def failed_checkpoint():
        raise ArchiveError("ACCEPTANCE_ARCHIVE_WRITE_FAILED", "injected failure")
    guard = OneShotProviderResearch(ForbiddenProvider(), tmp_path / "raw", "checkpoint-failure", "Africa/Casablanca",
        artifact_checkpoint=failed_checkpoint)
    with pytest.raises(ArchiveError):
        guard.research(DATE, {})
    assert guard.calls == 0


def test_failed_live_gate_archives_block_and_never_invokes_provider(tmp_path, monkeypatch):
    destination = tmp_path / "archive"
    prove_acceptance_archive(ROOT, destination)
    monkeypatch.setattr("dragon.research_acceptance._acceptance_workspace_changes", lambda *_: [])
    monkeypatch.setattr(LocalCommandEditorialProvider, "_invoke", lambda *_args: pytest.fail("preflight block invoked provider"))
    def blocked(*_args):
        raise ResearchAcceptanceError("BLOCKED_PRE_PROVIDER", "injected unhealthy runtime")
    monkeypatch.setattr("dragon.provider_research_acceptance.audit_live_provider_gates", blocked)
    run_id = f"provider-research-acceptance-blocked-{uuid4()}"
    try:
        with pytest.raises(ResearchAcceptanceError) as caught:
            run_provider_research_acceptance(root=ROOT, edition_date=DATE, run_id=run_id,
                provider=LocalCommandEditorialProvider(command=("forbidden",)), provider_authorized=True,
                service_probe=lambda _: {"status": "PASS"}, require_durable_archive=True, durable_archive_root=destination)
        assert caught.value.code == "BLOCKED_PRE_PROVIDER"
        manifest = verify_acceptance_bundle(destination / run_id)
        assert manifest["provider_calls"] == 0
        assert manifest["run_result"] == "BLOCKED_PRE_PROVIDER"
    finally:
        path = ROOT / "daily-runs" / DATE / "runs" / run_id
        if path.exists():
            shutil.rmtree(path)
