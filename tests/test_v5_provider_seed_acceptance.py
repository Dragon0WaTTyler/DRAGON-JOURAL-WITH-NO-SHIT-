"""Regression coverage for provider seed research entering the V5 pipeline."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

import dragon_provider_check
from dragon.provider_acceptance import (
    OfflineReplayResearchAdapter,
    build_provider_seed_orchestrator,
)
from dragon.providers import LocalCommandEditorialProvider, ProviderError, SECTION_HEADINGS
from dragon.state import sha256_file


ROOT = Path(__file__).resolve().parents[1]
DATE = "2099-12-29"


class NoArticleProvider:
    mode = "production"
    available = True

    def __init__(self) -> None:
        self.article_calls = 0

    def articles(self, research: dict) -> list[dict]:
        self.article_calls += 1
        raise AssertionError("article provider must not run before post-recovery readiness")


def _source(identifier: str, source_type: str, origin: str) -> dict:
    return {
        "id": identifier,
        "url": f"https://{origin}/{identifier}",
        "publisher": origin,
        "publication_date": DATE,
        "accessed_at": f"{DATE}T07:00:00+00:00",
        "source_type": source_type,
        "claim_supported": f"Support from {identifier}",
        "doi": None,
        "publication_status": "news",
        "full_text_status": "NOT_APPLICABLE",
        "methods_read": False,
        "limitations_read": False,
        "science_metadata": None,
    }


def _candidate(identifier: str, primary: str, independent: str, rank: int) -> dict:
    return {
        "id": identifier,
        "rank": rank,
        "title": f"Distinct event {identifier}",
        "discovery_source_ids": [primary, independent],
        "verification_source_ids": [primary, independent],
        "primary_evidence_source_ids": [primary],
        "independent_evidence_source_ids": [independent],
        "facts": [f"Fact for {identifier}"],
        "claims": [],
        "unknowns": [],
        "disputed_points": [],
        "evidence_eligibility": {"status": "ELIGIBLE", "issues": []},
    }


def _nine_section_seed() -> dict:
    active = {
        "front", "siyasa_dawla", "iqtisad_flous", "mojtama3", "ta3lim",
        "sport", "culture", "opinion", "service",
    }
    sources: list[dict] = []
    sections: list[dict] = []
    for index, (section_id, _heading) in enumerate(SECTION_HEADINGS):
        if section_id not in active:
            sections.append({
                "section_id": section_id,
                "status": "NO_NEWS",
                "candidates": [],
                "selected_candidate_id": None,
                "selection_reason": None,
                "no_news_reason": "لا توجد مادة مكتملة الأدلة لهذا القسم في حزمة البذور.",
                "fallback_action": "DOSSIER_FOLLOW_UP",
            })
            continue
        primary, independent = f"p{index}", f"i{index}"
        sources.extend([
            _source(primary, "official", f"official-{index}.example"),
            _source(independent, "independent", f"news-{index}.example"),
        ])
        first = _candidate(f"{section_id}-1", primary, independent, 1)
        second = _candidate(f"{section_id}-2", primary, independent, 2)
        sections.append({
            "section_id": section_id,
            "status": "ACTIVE",
            "candidates": [first, second],
            "selected_candidate_id": first["id"],
            "selection_reason": "اختيار بذرة موثق لاختبار الاسترداد قبل التحرير.",
            "no_news_reason": None,
            "fallback_action": None,
        })
    return {"edition_date": DATE, "sources": sources, "sections": sections}


def test_malformed_provider_seed_fails_structural_gate_without_articles() -> None:
    provider = LocalCommandEditorialProvider(command=("unused",))
    with pytest.raises(ProviderError) as caught:
        provider.normalize_research_packet(DATE, {"edition_date": DATE, "sources": []})
    assert caught.value.code == "RESEARCH_PACKET_INVALID"


def test_provider_selected_and_local_eligibility_are_reported_separately() -> None:
    seed = _nine_section_seed()
    for section in seed["sections"]:
        for candidate in section["candidates"]:
            candidate.pop("evidence_eligibility")
    counts = dragon_provider_check._research_counts(seed)
    assert counts["provider_selected_sections"] == 9
    assert counts["pre_recovery_candidate_count"] == 18
    assert counts["pre_recovery_evidence_eligible_candidates"] == 0


def test_incomplete_seed_executes_deep_research_before_final_insufficiency() -> None:
    raw_dir = ROOT / "tmp" / "provider-seed-acceptance-test"
    run_dir = ROOT / "daily-runs" / DATE
    shutil.rmtree(run_dir, ignore_errors=True)
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / "research.raw.json"
    seed = _nine_section_seed()
    raw_path.write_text(json.dumps(seed, ensure_ascii=False), encoding="utf-8")
    delegate = NoArticleProvider()
    try:
        orchestrator = build_provider_seed_orchestrator(
            root=ROOT,
            edition_date=DATE,
            provider=delegate,
            normalized_packet=seed,
            raw_packet_path=raw_path,
            raw_packet_sha256=sha256_file(raw_path),
            mode="OFFLINE_REPLAY",
            research_adapter=OfflineReplayResearchAdapter(),
            offline_replay=True,
        )
        state = orchestrator.run()
        deep = json.loads((run_dir / "deep-research" / "state.json").read_text(encoding="utf-8"))
        execution = json.loads((run_dir / "deep-research" / "execution-report.json").read_text(encoding="utf-8"))
        recovery = json.loads((run_dir / "research-recovery" / "plan.json").read_text(encoding="utf-8"))
        assert state["stages"]["research"]["status"] == "COMPLETE"
        assert state["stages"]["deep_research"]["status"] == "COMPLETE"
        assert state["stages"]["deep_research_execution"]["status"] == "COMPLETE"
        assert state["stages"]["research_recovery"]["error_code"] == "RESEARCH_INSUFFICIENT"
        assert sum(len(job["question_tree"]) for job in deep["jobs"]) > 0
        assert sum(len(job["branches"]) for job in deep["jobs"]) > 0
        assert sum(len(job["actions"]) for job in execution["jobs"]) > 0
        assert sum(len(job["observations"]) for job in execution["jobs"]) > 0
        assert recovery["distinct_event_count"] == 9
        assert recovery["status"] == "RESEARCH_INSUFFICIENT"
        assert delegate.article_calls == 0
    finally:
        shutil.rmtree(raw_dir, ignore_errors=True)
        shutil.rmtree(run_dir, ignore_errors=True)
