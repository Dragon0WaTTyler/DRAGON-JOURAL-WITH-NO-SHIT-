"""Offline regressions for publication-candidate evidence eligibility."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from dragon.providers import LocalCommandEditorialProvider, ProviderError, SECTION_HEADINGS


ROOT = Path(__file__).resolve().parents[1]


def _source(identifier: str, source_type: str, url: str) -> dict:
    return {
        "id": identifier,
        "url": url,
        "publisher": f"Publisher {identifier}",
        "publication_date": "2026-09-11",
        "accessed_at": "2026-09-11",
        "source_type": source_type,
        "claim_supported": f"Evidence supplied by {identifier}.",
        "doi": None,
        "publication_status": "news",
        "full_text_status": "FULL_TEXT_VERIFIED",
        "methods_read": False,
        "limitations_read": False,
        "science_metadata": None,
    }


def _candidate(identifier: str, rank: int, *, primary: list[str], independent: list[str], verification: list[str] | None = None) -> dict:
    source_ids = verification or [*primary, *independent]
    return {
        "id": identifier,
        "rank": rank,
        "title": f"Candidate {identifier}",
        "discovery_source_ids": source_ids,
        "verification_source_ids": source_ids,
        "primary_evidence_source_ids": primary,
        "independent_evidence_source_ids": independent,
        "facts": ["A bounded verified fact."],
        "claims": [],
        "unknowns": ["A bounded uncertainty."],
        "disputed_points": [],
    }


def _packet(*, front_candidates: list[dict] | None = None, selected: str | None = None, only_front: bool = False) -> dict:
    sources = [
        _source("p", "primary", "https://primary.example/document"),
        _source("i", "independent", "https://independent.example/report"),
    ]
    sections = []
    for section_id, _heading in SECTION_HEADINGS:
        if only_front and section_id != "front":
            sections.append({
                "section_id": section_id,
                "status": "NO_NEWS",
                "candidates": [],
                "selected_candidate_id": None,
                "selection_reason": None,
                "no_news_reason": "No publishable evidence was found for this test section.",
                "fallback_action": "SKIP",
            })
            continue
        candidates = (
            front_candidates if section_id == "front" and front_candidates is not None else [
                _candidate(f"{section_id}-one", 1, primary=["p"], independent=["i"]),
                _candidate(f"{section_id}-two", 2, primary=["p"], independent=["i"]),
            ]
        )
        sections.append({
            "section_id": section_id,
            "status": "ACTIVE",
            "candidates": candidates,
            "selected_candidate_id": selected if section_id == "front" and selected else candidates[0]["id"],
            "selection_reason": "The selected candidate is initially ranked first for this test.",
            "no_news_reason": None,
            "fallback_action": None,
        })
    return {"edition_date": "2026-09-11", "sources": sources, "sections": sections}


class _OfflinePacketProvider(LocalCommandEditorialProvider):
    packet: dict
    calls: list[str]

    def _invoke(self, operation: str, payload: dict):
        self.calls.append(operation)
        if operation == "research":
            return copy.deepcopy(self.packet)
        raise AssertionError("article generation must not be invoked by an ineligible packet test")


def _provider(packet: dict, **kwargs) -> _OfflinePacketProvider:
    provider = _OfflinePacketProvider(("offline",), minimum_active_sections=1, minimum_edition_words=350, **kwargs)
    object.__setattr__(provider, "packet", packet)
    object.__setattr__(provider, "calls", [])
    return provider


def test_primary_and_independent_evidence_remain_publishable() -> None:
    provider = _provider(_packet(only_front=True))
    research = provider.research("2026-09-11")
    front = next(section for section in research["sections"] if section["section_id"] == "front")
    assert front["status"] == "ACTIVE"
    assert front["selected_candidate_id"] == "front-one"


@pytest.mark.parametrize(
    "primary,independent",
    [(["p"], []), ([], ["i"])],
    ids=["primary-only", "independent-only"],
)
def test_one_role_only_is_held_before_article_generation(primary: list[str], independent: list[str]) -> None:
    candidates = [
        _candidate("front-one", 1, primary=primary, independent=independent),
        _candidate("front-two", 2, primary=primary, independent=independent),
    ]
    provider = _provider(_packet(front_candidates=candidates, only_front=True))
    research = provider.research("2026-09-11")
    front = next(section for section in research["sections"] if section["section_id"] == "front")
    assert front["status"] == "NO_NEWS"
    assert front["candidates"] == []
    assert len(front["recovery_candidates"]) == 2
    assert {item["evidence_eligibility"]["status"] for item in front["recovery_candidates"]} == {"RESEARCH_INCOMPLETE"}
    with pytest.raises(ProviderError) as blocked:
        provider.articles(research)
    assert blocked.value.code == "RESEARCH_INSUFFICIENT"
    assert provider.calls == ["research"]


def test_unambiguous_primary_in_verification_is_linked_deterministically() -> None:
    candidates = [
        _candidate("front-one", 1, primary=[], independent=["i"], verification=["p", "i"]),
        _candidate("front-two", 2, primary=["p"], independent=["i"]),
    ]
    provider = _provider(_packet(front_candidates=candidates, only_front=True))
    research = provider.research("2026-09-11")
    front = next(section for section in research["sections"] if section["section_id"] == "front")
    selected = next(item for item in front["candidates"] if item["id"] == "front-one")
    assert selected["primary_evidence_source_ids"] == ["p"]
    assert selected["evidence_eligibility"]["status"] == "ELIGIBLE"
    assert research["evidence_normalization"]["link_repairs"][0]["linked_primary_evidence_source_ids"] == ["p"]


def test_same_origin_cannot_fill_both_evidence_roles() -> None:
    candidates = [
        _candidate("front-one", 1, primary=["p"], independent=["i"]),
        _candidate("front-two", 2, primary=["p"], independent=["i"]),
    ]
    packet = _packet(front_candidates=candidates, only_front=True)
    packet["sources"] = [
        _source("p", "official", "https://same-origin.example/statement"),
        _source("i", "independent", "https://same-origin.example/report"),
    ]
    research = _provider(packet).research("2026-09-11")
    front = next(section for section in research["sections"] if section["section_id"] == "front")
    assert front["status"] == "NO_NEWS"
    assert research["evidence_normalization"]["demotions"][0]["outcome"] == "RESEARCH_INCOMPLETE"


def test_evidence_ineligible_front_rank_cannot_outrank_eligible_candidate() -> None:
    candidates = [
        _candidate("front-one", 1, primary=[], independent=["i"]),
        _candidate("front-two", 2, primary=["p"], independent=["i"]),
    ]
    research = _provider(_packet(front_candidates=candidates, only_front=True)).research("2026-09-11")
    front = next(section for section in research["sections"] if section["section_id"] == "front")
    assert front["status"] == "ACTIVE"
    assert front["selected_candidate_id"] == "front-two"
    assert research["evidence_normalization"]["demotions"][0]["outcome"] == "DEMOTED_TO_ELIGIBLE_CANDIDATE"


def test_recovery_gate_blocks_article_provider_before_invocation() -> None:
    provider = _provider(_packet(only_front=True))
    research = provider.research("2026-09-11")
    research["research_recovery"] = {"status": "RECOVERY_REQUIRED"}
    with pytest.raises(ProviderError) as blocked:
        provider.articles(research)
    assert blocked.value.code == "RESEARCH_RECOVERY_REQUIRED"
    assert provider.calls == ["research"]


def test_preserved_2026_09_11_front_omission_reproduces_old_failure_then_repairs() -> None:
    fragment = json.loads(
        (ROOT / "tests" / "fixtures" / "research-2026-09-11-front-omission.json").read_text(encoding="utf-8")
    )
    packet = _packet()
    packet["sources"].extend(fragment["sources"])
    packet["sections"][0] = fragment["front"]

    with pytest.raises(ProviderError) as old_path:
        _provider(packet, normalize_evidence_links=False).research("2026-09-11")
    assert old_path.value.code == "RESEARCH_PACKET_INVALID"
    assert old_path.value.detail == "active candidate front_1 needs primary and independent evidence ids"

    repaired = _provider(packet).research("2026-09-11")
    front = next(section for section in repaired["sections"] if section["section_id"] == "front")
    selected = next(item for item in front["candidates"] if item["id"] == "front_1")
    assert front["selected_candidate_id"] == "front_1"
    assert selected["primary_evidence_source_ids"] == ["s01"]
    assert selected["independent_evidence_source_ids"] == ["s02"]
