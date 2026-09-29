"""Offline tests for the explicitly authorized provider research boundary."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from dragon.provider_research_acceptance import (
    OneShotProviderResearch,
    build_provider_research_acceptance_orchestrator,
    run_provider_research_acceptance,
)
from dragon.provider_acceptance import OfflineReplayResearchAdapter
from dragon.providers import LocalCommandEditorialProvider, ProviderError, SECTION_HEADINGS
from dragon.research_acceptance import (
    FORBIDDEN_STAGES,
    PROVIDER_RESEARCH_ACCEPTANCE_MODE,
    ResearchAcceptanceError,
)


ROOT = Path(__file__).resolve().parents[1]
DATE = "2099-12-28"


def _source(identifier: str, source_type: str, origin: str) -> dict:
    return {
        "id": identifier,
        "url": f"https://{origin}/{identifier}",
        "publisher": origin,
        "publication_date": DATE,
        "accessed_at": f"{DATE}T07:00:00+00:00",
        "source_type": source_type,
        "origin": origin,
        "claim_supported": f"Exact supporting claim from {identifier}.",
        "doi": None,
        "publication_status": "news",
        "full_text_status": "NOT_APPLICABLE",
        "methods_read": False,
        "limitations_read": False,
        "science_metadata": None,
    }


def _undercovered_packet() -> dict:
    return {
        "edition_date": DATE,
        "sources": [_source("provider-lead", "official", "authority.example")],
        "sections": [
            {
                "section_id": section_id,
                "status": "NO_NEWS",
                "candidates": [],
                "selected_candidate_id": None,
                "selection_reason": None,
                "no_news_reason": "لا توجد أدلة مكتملة كافية لهذا القسم في حزمة الاختبار الجديدة.",
                "fallback_action": "DOSSIER_FOLLOW_UP",
            }
            for section_id, _heading in SECTION_HEADINGS
        ],
    }


def _recovery_ready_packet() -> dict:
    """A synthetic raw provider packet whose missing breadth is recoverable.

    This is offline test data only.  The adapter below supplies independently
    retrieved fixtures through the normal executor rather than trusting the
    provider packet as evidence.
    """
    active = {
        "front", "siyasa_dawla", "iqtisad_flous", "mojtama3", "ta3lim",
        "sport", "culture", "opinion", "service",
    }
    sources: list[dict] = []
    sections: list[dict] = []
    for index, (section_id, _heading) in enumerate(SECTION_HEADINGS):
        if section_id not in active:
            sections.append({
                "section_id": section_id, "status": "NO_NEWS", "candidates": [],
                "selected_candidate_id": None, "selection_reason": None,
                "no_news_reason": "Synthetic fixture has no selected item.",
                "fallback_action": "DOSSIER_FOLLOW_UP",
            })
            continue
        primary, independent = f"p{index}", f"i{index}"
        sources.extend([_source(primary, "official", f"official-{index}.example"), _source(independent, "independent", f"news-{index}.example")])
        candidate = {
            "id": f"{section_id}-1", "rank": 1, "title": f"Distinct event {section_id}",
            "discovery_source_ids": [primary, independent], "verification_source_ids": [primary, independent],
            "primary_evidence_source_ids": [primary], "independent_evidence_source_ids": [independent],
            "facts": [f"Fixture fact for {section_id}"], "claims": [], "unknowns": [], "disputed_points": [],
        }
        if section_id == "siyasa_dawla":
            candidate["editorial_functions"] = [{
                "function": "ACCOUNTABILITY", "status": "VALIDATED",
                "reason": "Synthetic current audit mechanism.",
                "supporting_event_facts": ["Audit authority completed an inspection."],
                "evidence_source_ids": [primary, independent], "classifier_version": "fixture-v1",
            }]
        elif section_id == "service":
            candidate["editorial_functions"] = [{
                "function": name, "status": "VALIDATED", "reason": "Synthetic current procedure.",
                "supporting_event_facts": ["Applicants have a current procedure."],
                "evidence_source_ids": [primary, independent], "classifier_version": "fixture-v1",
            } for name in ("SERVICE", "READER_VALUE")]
        alternate = dict(candidate)
        alternate.update({"id": f"{section_id}-2", "rank": 2, "title": f"Alternate event {section_id}"})
        sections.append({
            "section_id": section_id, "status": "ACTIVE", "candidates": [candidate, alternate],
            "selected_candidate_id": candidate["id"], "selection_reason": "Synthetic fixture selection.",
            "no_news_reason": None, "fallback_action": None,
        })
    for section_id, primary in (
        ("world", "world-primary"), ("africa_sahel", "africa-primary"),
        ("filastin_middle_east", "middle-east-primary"),
    ):
        sources.append(_source(primary, "official", f"{section_id}.official.example"))
        section = next(item for item in sections if item["section_id"] == section_id)
        section["recovery_candidates"] = [{
            "id": f"{section_id}-recovery", "rank": 1, "title": f"Distinct recovery event {section_id}",
            "discovery_source_ids": [primary], "verification_source_ids": [primary],
            "primary_evidence_source_ids": [primary], "independent_evidence_source_ids": [],
            "facts": [f"Recovery fixture fact for {section_id}"], "claims": [], "unknowns": [], "disputed_points": [],
            "evidence_eligibility": {"status": "RESEARCH_INCOMPLETE", "issues": ["INDEPENDENT_EVIDENCE_MISSING"]},
        }]
    return {"edition_date": DATE, "sources": sources, "sections": sections}


class CompleteRecoveryAdapter:
    def execute(self, action: dict) -> list[dict]:
        candidate_id = action.get("recovery_candidate_id") or action["action_id"]
        role = action.get("target_evidence_role")
        source_class = "official" if role == "PRIMARY" else "independent"
        return [{
            "url": f"https://{source_class}.example/{candidate_id}",
            "title": f"{source_class.title()} recovery report {candidate_id}", "source_class": source_class,
            "claim": f"Exact fixture evidence for {candidate_id}.", "published_at": DATE,
            "retrieved_at": f"{DATE}T08:00:00+00:00",
            "content_hash": hashlib.sha256(f"{source_class}:{candidate_id}".encode()).hexdigest(),
            "verification_provenance": "FIXTURE_VERIFIED_EXACT_PAGE",
        }]


def _provider(packet: dict) -> LocalCommandEditorialProvider:
    return LocalCommandEditorialProvider(command=("fixture-provider",))


def _provider_invoke(packet: dict, calls: list[str], *, failure: ProviderError | None = None):
    """Exercise the real adapter's research()/normalizer without a subprocess."""
    def invoke(provider, operation, _payload):
        calls.append(operation)
        assert operation == "research"
        if failure is not None:
            raise failure
        provider._capture("research.raw.json", packet)
        return packet
    return invoke


def _passing_probe(_config: dict) -> dict:
    return {"status": "PASS", "endpoint": "fixture", "http_status": 200, "bytes_sampled": 1}


@pytest.fixture(autouse=True)
def _clean_date_dir():
    date_dir = ROOT / "daily-runs" / DATE
    shutil.rmtree(date_dir, ignore_errors=True)
    yield
    shutil.rmtree(date_dir, ignore_errors=True)


def test_provider_backed_boundary_requires_explicit_authorization():
    with pytest.raises(ResearchAcceptanceError) as caught:
        build_provider_research_acceptance_orchestrator(
            root=ROOT, edition_date=DATE, provider=_provider(_undercovered_packet()),
            provider_authorized=False, research_adapter=OfflineReplayResearchAdapter(),
        )
    assert caught.value.code == "PROVIDER_RESEARCH_AUTHORIZATION_REQUIRED"


def test_provider_accountability_without_service_candidate_preserves_no_news_truth() -> None:
    packet = _undercovered_packet()
    packet["sources"].append(_source("accountability-independent", "independent", "news.example"))
    packet["sections"] = [
        {
            "section_id": section_id,
            "status": "ACTIVE",
            "candidates": [
                {
                    "id": "accountability-1", "rank": 1,
                    "title": "A current accountability action",
                    "discovery_source_ids": ["provider-lead"],
                    "verification_source_ids": ["provider-lead", "accountability-independent"],
                    "primary_evidence_source_ids": ["provider-lead"],
                    "independent_evidence_source_ids": ["accountability-independent"],
                    "facts": ["A current oversight action was announced."],
                    "claims": [], "unknowns": [], "disputed_points": [],
                },
                {
                    "id": "accountability-2", "rank": 2,
                    "title": "An alternate accountability action",
                    "discovery_source_ids": ["provider-lead"],
                    "verification_source_ids": ["provider-lead", "accountability-independent"],
                    "primary_evidence_source_ids": ["provider-lead"],
                    "independent_evidence_source_ids": ["accountability-independent"],
                    "facts": ["An alternate current oversight action was announced."],
                    "claims": [], "unknowns": [], "disputed_points": [],
                },
            ],
            "selected_candidate_id": "accountability-1",
            "selection_reason": "The selected action has distinct source roles.",
            "no_news_reason": None,
            "fallback_action": None,
        }
        if section_id == "investigations"
        else section
        for section in packet["sections"]
        for section_id in [section["section_id"]]
    ]

    normalized = _provider(packet).normalize_research_packet(DATE, packet)
    accountability = next(item for item in normalized["sections"] if item["section_id"] == "investigations")
    service = next(item for item in normalized["sections"] if item["section_id"] == "service")
    assert len(accountability["candidates"]) == 2
    assert service["status"] == "NO_NEWS"
    assert service["candidates"] == []
    assert service["selected_candidate_id"] is None


def test_technical_provider_mode_records_actual_time_and_rejects_overrides():
    with pytest.raises(ResearchAcceptanceError) as caught:
        build_provider_research_acceptance_orchestrator(
            root=ROOT, edition_date=DATE, provider=_provider(_undercovered_packet()),
            provider_authorized=True, research_adapter=OfflineReplayResearchAdapter(),
            technical_validation=True, created_at=f"{DATE}T07:00:00+00:00",
        )
    assert caught.value.code == "TECHNICAL_ACCEPTANCE_TIME_OVERRIDE_FORBIDDEN"


def test_authorized_undercovered_provider_packet_is_raw_captured_and_stops_before_editorial(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(LocalCommandEditorialProvider, "_invoke", _provider_invoke(_undercovered_packet(), calls))
    monkeypatch.setattr("dragon.research_acceptance._acceptance_workspace_changes", lambda *_: [])

    orchestrator, state, report_path = run_provider_research_acceptance(
        root=ROOT,
        edition_date=DATE,
        run_id="provider-undercovered",
        provider=_provider(_undercovered_packet()),
        provider_authorized=True,
        research_adapter=OfflineReplayResearchAdapter(),
        service_probe=_passing_probe,
    )

    run_dir = orchestrator.store.run_dir
    invocation = json.loads((run_dir / "provider-research" / "invocation.json").read_text(encoding="utf-8"))
    source_intelligence = json.loads((run_dir / "source-intelligence" / "report.json").read_text(encoding="utf-8"))
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert len(calls) == 1
    assert state["run_result"] == "FAILED"
    assert state["stages"]["research_recovery"]["error_code"] == "RESEARCH_RECOVERY_REQUIRED"
    assert invocation["status"] == "NORMALIZED"
    assert invocation["provider_call_index"] == 1
    assert invocation["request"]["sha256"]
    assert invocation["raw_response"]["sha256"]
    assert invocation["normalized_packet"]["sha256"]
    provider_input = json.loads((run_dir / "provider-research" / "request.json").read_text(encoding="utf-8"))["provider_input"]
    assert {"source_change_monitoring", "source_discovery", "research_semantics", "research_targeting"} <= set(provider_input)
    targeting = provider_input["research_targeting"]
    assert targeting["as_of_date"] == DATE
    assert [item["target_id"] for item in targeting["unresolved_targets"][:2]] == [
        "HARD:ACCOUNTABILITY", "HARD:SERVICE",
    ]
    assert targeting["provider_output"]["can_close_research_need"] is False
    assert targeting["provider_output"]["can_emit_executor_actions"] is False
    persisted_packet = json.loads((run_dir / "research" / "research-packet.json").read_text(encoding="utf-8"))
    assert persisted_packet["provider_research_acceptance_provenance"]["raw_response_sha256"] == invocation["raw_response"]["sha256"]
    assert source_intelligence["source_records"][0]["fetch_status"] == "PROVIDER_REPORTED"
    assert "FETCH_NOT_INDEPENDENTLY_VERIFIED" in source_intelligence["source_records"][0]["uncertainty"]
    assert report["provider_research_calls"] == report["provider_call_limit"] == 1
    assert tuple(orchestrator.stage_names) == tuple(report["allowed_stages"])
    assert not (set(orchestrator.stage_names) & FORBIDDEN_STAGES)
    assert "article_generation" not in state["stages"]
    assert not (run_dir / "articles" / "articles.json").exists()
    assert report["verdict"] == "RESEARCH_RECOVERY_REQUIRED"


def test_structurally_complete_provider_fixture_remains_unverified_and_stops_before_editorial(monkeypatch):
    calls: list[str] = []
    packet = _recovery_ready_packet()
    monkeypatch.setattr(LocalCommandEditorialProvider, "_invoke", _provider_invoke(packet, calls))
    monkeypatch.setattr("dragon.research_acceptance._acceptance_workspace_changes", lambda *_: [])

    orchestrator, state, report_path = run_provider_research_acceptance(
        root=ROOT,
        edition_date=DATE,
        run_id="provider-complete",
        provider=_provider(packet),
        provider_authorized=True,
        research_adapter=CompleteRecoveryAdapter(),
        service_probe=_passing_probe,
    )

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert len(calls) == 1
    # The executor handles the synthetic retrievals, but the raw provider
    # sources remain discovery intelligence.  The evidence contract must not
    # turn a provider-shaped "complete" packet into completed coverage.
    assert state["run_result"] == "FAILED"
    assert state["stages"]["research_recovery"]["error_code"] == "RESEARCH_RECOVERY_REQUIRED"
    assert report["verdict"] == "RESEARCH_RECOVERY_REQUIRED"
    assert "article_generation" not in state["stages"]
    assert not (orchestrator.store.run_dir / "articles" / "articles.json").exists()
    assert report["forbidden_stages_absent"] == sorted(FORBIDDEN_STAGES)


def test_provider_claimed_verification_is_clamped_until_independent_retrieval(tmp_path: Path):
    packet = _undercovered_packet()
    packet["sources"][0]["verification_status"] = "VALIDATED_EVIDENCE"

    class CapturingProvider:
        mode = "production"

        def research(self, edition_date, _input):
            (tmp_path / "research.raw.json").write_text(json.dumps(packet), encoding="utf-8")
            return packet

    wrapper = OneShotProviderResearch(CapturingProvider(), tmp_path, "verification-clamp", "Africa/Casablanca")
    returned = wrapper.research(DATE, {})
    raw = json.loads((tmp_path / "research.raw.json").read_text(encoding="utf-8"))
    normalized = json.loads((tmp_path / "normalized-research-packet.json").read_text(encoding="utf-8"))
    assert raw["sources"][0]["verification_status"] == "VALIDATED_EVIDENCE"
    assert returned["sources"][0]["verification_status"] == "PROVIDER_REPORTED"
    assert normalized["sources"][0]["verification_status"] == "PROVIDER_REPORTED"


def test_provider_execution_failure_is_recorded_once_without_a_packet(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(
        LocalCommandEditorialProvider,
        "_invoke",
        _provider_invoke(_undercovered_packet(), calls, failure=ProviderError("AI_PROVIDER_EXECUTION_FAILED", "fixture failure")),
    )
    monkeypatch.setattr("dragon.research_acceptance._acceptance_workspace_changes", lambda *_: [])

    orchestrator, state, _report_path = run_provider_research_acceptance(
        root=ROOT, edition_date=DATE, run_id="provider-failure", provider=_provider(_undercovered_packet()),
        provider_authorized=True, research_adapter=OfflineReplayResearchAdapter(), service_probe=_passing_probe,
    )

    invocation = json.loads((orchestrator.store.run_dir / "provider-research" / "invocation.json").read_text(encoding="utf-8"))
    assert calls == ["research"]
    assert state["run_result"] == "FAILED"
    assert state["stages"]["research"]["error_code"] == "AI_PROVIDER_EXECUTION_FAILED"
    assert invocation["status"] == "FAILED"
    assert not (orchestrator.store.run_dir / "research" / "research-packet.json").exists()


def test_invalid_or_failed_provider_never_creates_successful_packet(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(LocalCommandEditorialProvider, "_invoke", _provider_invoke({"edition_date": DATE}, calls))
    monkeypatch.setattr("dragon.research_acceptance._acceptance_workspace_changes", lambda *_: [])

    orchestrator, state, report_path = run_provider_research_acceptance(
        root=ROOT,
        edition_date=DATE,
        run_id="provider-invalid",
        provider=_provider({"edition_date": DATE}),
        provider_authorized=True,
        research_adapter=OfflineReplayResearchAdapter(),
        service_probe=_passing_probe,
    )

    assert len(calls) == 1
    assert state["run_result"] == "FAILED"
    assert state["stages"]["research"]["error_code"] == "RESEARCH_PACKET_INVALID"
    assert not (orchestrator.store.run_dir / "research" / "research-packet.json").exists()
    assert json.loads(report_path.read_text(encoding="utf-8"))["provider_research_calls"] == 1


def test_one_shot_wrapper_rejects_any_second_research_call(tmp_path: Path):
    class CapturingProvider:
        mode = "production"

        def __init__(self):
            self.calls = 0

        def research(self, edition_date, _input):
            self.calls += 1
            (tmp_path / "research.raw.json").write_text(json.dumps(_undercovered_packet()), encoding="utf-8")
            return _undercovered_packet()

    delegate = CapturingProvider()
    wrapper = OneShotProviderResearch(delegate, tmp_path, "one-shot", "Africa/Casablanca")
    wrapper.research(DATE, {})
    with pytest.raises(ProviderError) as caught:
        wrapper.research(DATE, {})
    assert caught.value.code == "PROVIDER_RESEARCH_CALL_LIMIT_EXCEEDED"
    assert delegate.calls == 1
