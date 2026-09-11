"""Offline regressions for the 2026-09-11 article-length failure."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from dragon.config import load_local_config
from dragon.providers import LocalCommandEditorialProvider, ProviderError, SECTION_HEADINGS, SyntheticEditorialProvider


ROOT = Path(__file__).resolve().parents[1]


def _research(active_count: int = 12) -> dict:
    value = SyntheticEditorialProvider().research("2099-01-02")
    for index, section in enumerate(value["sections"]):
        if index < active_count:
            continue
        section.update({
            "status": "NO_NEWS", "candidates": [], "selected_candidate_id": None,
            "selection_reason": None,
            "no_news_reason": "لا توجد مادة موثقة كافية للنشر في هذا القسم التجريبي",
            "fallback_action": "SKIP",
        })
    return value


def _articles(research: dict, words: int) -> list[dict]:
    value = SyntheticEditorialProvider().articles(research)
    active_sections = {item["section_id"] for item in research["sections"] if item["status"] == "ACTIVE"}
    for item in value:
        if item["section_id"] not in active_sections:
            section_id = item["section_id"]
            item.clear()
            item.update({
                "section_id": section_id, "status": "SKIPPED",
                "skip_reason": "لا توجد مادة موثقة كافية للنشر في هذا القسم التجريبي",
            })
        else:
            item["body"] = ["كلمة " * words]
    return value


class _RecordingProvider(LocalCommandEditorialProvider):
    def __init__(self, initial: list[dict], repaired: list[dict] | None = None, **kwargs):
        super().__init__(("offline",), **kwargs)
        self.initial = initial
        self.repaired = repaired
        self.calls: list[dict] = []

    def _invoke(self, operation: str, payload: dict):
        assert operation == "articles"
        self.calls.append(payload)
        return copy.deepcopy(self.initial if len(self.calls) == 1 else self.repaired)


def test_minimized_historical_fixture_has_the_recorded_deficits() -> None:
    fixture = json.loads((ROOT / "tests/fixtures/live_provider_length_under_budget.json").read_text(encoding="utf-8"))
    assert fixture["active_articles"] == 12
    assert sum(fixture["initial_active_words"]) == fixture["initial_total_words"] == 3190
    assert sum(fixture["repaired_active_words"]) == fixture["repaired_total_words"] == 3314
    assert sum(word < fixture["minimum_article_words"] for word in fixture["repaired_active_words"]) == 11


def test_prompt_receives_authoritative_per_article_budgets() -> None:
    research = _research()
    initial = _articles(research, 500)
    provider = _RecordingProvider(initial)
    assert provider.articles(research)
    contract = provider.calls[0]["article_budget_contract"]
    assert len(contract["articles"]) == 12
    assert contract["generation_target_words"] == 8700
    assert {item["minimum_words"] for item in contract["articles"]} == {350}
    assert next(item for item in contract["articles"] if item["role"] == "LEAD")["target_words"] == 1000
    assert {item["target_words"] for item in contract["articles"] if item["role"] == "STANDARD"} == {700}
    assert all(item["evidence_ids"] for item in contract["articles"])


def test_generation_target_is_coherent_with_edition_budget() -> None:
    contract = _RecordingProvider(_articles(_research(), 500))._article_budget_contract(_research())
    assert contract["generation_target_words"] >= 6000 > contract["acceptance_floor_words"] == 4000
    assert sum(item["target_words"] for item in contract["articles"]) == contract["generation_target_words"]


def test_role_quality_targets_constrain_broad_coverage_without_lowering_hard_floors() -> None:
    research = SyntheticEditorialProvider().research("2099-01-02")
    contract = _RecordingProvider(_articles(research, 500))._article_budget_contract(research)

    assert contract["generation_target_words"] == 9000
    assert contract["quality_target_constrained"] is True
    assert all(item["target_words"] >= item["minimum_words"] == 350 for item in contract["articles"])
    assert any(item["role"] == "LEAD" and item["quality_target_constrained"] for item in contract["articles"])


def test_validator_reports_every_underlength_article_and_aggregate_deficit() -> None:
    research = _research()
    short = _articles(research, 250)
    provider = _RecordingProvider(short, short)
    with pytest.raises(ProviderError) as caught:
        provider.articles(research)
    diagnostics = caught.value.diagnostics
    assert len(diagnostics["article_length_failures"]) == 12
    assert {item["deficit_to_minimum"] for item in diagnostics["article_length_failures"]} == {100}
    assert diagnostics["aggregate"] == {
        "active_articles": 12, "raw_active_words": 3000, "valid_active_words": 0,
        "minimum_words": 4000, "target_words": 8700,
        "deficit_to_minimum": 1000, "deficit_to_target": 5700,
    }


def test_repair_receives_all_article_and_aggregate_deficits() -> None:
    research = _research()
    initial, repaired = _articles(research, 250), _articles(research, 500)
    provider = _RecordingProvider(initial, repaired)
    assert provider.articles(research)
    repair = provider.calls[1]["repair_context"]
    assert len(repair["failing_articles"]) == 12
    assert {item["article_id"] for item in repair["failing_articles"]} == {
        item["id"] for item in initial if item["status"] == "ACTIVE"
    }
    assert all(item["actual_words"] == 250 and item["deficit_to_minimum"] == 100 for item in repair["failing_articles"])
    assert repair["aggregate"]["deficit_to_minimum"] == 1000
    assert repair["aggregate"]["deficit_to_target"] == 5700


def test_repair_must_preserve_active_ids_and_evidence_linkage() -> None:
    research = _research()
    initial, repaired = _articles(research, 250), _articles(research, 500)
    provider = _RecordingProvider(initial, repaired)
    accepted = provider.articles(research)
    assert [item["id"] for item in accepted if item["status"] == "ACTIVE"] == [item["id"] for item in initial if item["status"] == "ACTIVE"]
    assert [item["source_ids"] for item in accepted if item["status"] == "ACTIVE"] == [item["source_ids"] for item in initial if item["status"] == "ACTIVE"]


def test_repair_cannot_silently_skip_or_shorten_a_selected_active_article() -> None:
    research = _research()
    initial, repaired = _articles(research, 250), _articles(research, 500)
    repaired[0] = {"section_id": repaired[0]["section_id"], "status": "SKIPPED", "skip_reason": "سبب تحريري محدد لكنه لا يثبت زوال الدليل"}
    provider = _RecordingProvider(initial, repaired)
    with pytest.raises(ProviderError, match="approved repair_skip_reason_code"):
        provider.articles(research)


def test_repair_cannot_shorten_a_valid_article() -> None:
    research = _research()
    initial = _articles(research, 500)
    initial[0]["body"] = ["قصير " * 250]
    repaired = _articles(research, 500)
    repaired[1]["body"] = ["مختصر " * 400]
    provider = _RecordingProvider(initial, repaired)
    with pytest.raises(ProviderError) as caught:
        provider.articles(research)
    assert caught.value.diagnostics["repair_shortened_articles"] == [{
        "article_id": repaired[1]["id"], "section_id": repaired[1]["section_id"],
        "previous_words": 500, "actual_words": 400,
    }]


def test_selected_research_coverage_cannot_be_silently_dropped() -> None:
    research = _research()
    initial = _articles(research, 500)
    initial[0] = {"section_id": initial[0]["section_id"], "status": "SKIPPED", "skip_reason": "سبب تحريري محدد لكنه ليس إبطالاً للدليل"}
    provider = _RecordingProvider(initial, initial)
    with pytest.raises(ProviderError) as caught:
        provider.articles(research)
    assert caught.value.diagnostics["selected_active_skipped"]


def test_impossible_word_floor_or_unsupported_budget_blocks_before_provider_invocation() -> None:
    research = _research(11)
    provider = _RecordingProvider([], [])
    with pytest.raises(ProviderError, match="at least 12"):
        provider.articles(research)
    assert provider.calls == []


def test_failed_live_research_packet_now_blocks_before_article_invocation() -> None:
    historical = json.loads((ROOT / "acceptance/provider-trials/2026-09-11/attempts/attempt-6d24f562361843da939d2116cb92680e/research.raw.json").read_text(encoding="utf-8"))
    calls: list[str] = []

    class ResearchOnlyProvider(LocalCommandEditorialProvider):
        def _invoke(self, operation: str, payload: dict):
            calls.append(operation)
            if operation == "research":
                return historical
            raise AssertionError("under-covered research must not invoke articles")

    replay = ResearchOnlyProvider(("offline",)).research("2026-09-11")
    assert not [section for section in replay["sections"] if section["status"] == "ACTIVE"]
    with pytest.raises(ProviderError) as replay_blocked:
        ResearchOnlyProvider(("offline",)).articles(replay)
    assert replay_blocked.value.code == "RESEARCH_INSUFFICIENT"
    assert calls == ["research"]

    feasible = _research()
    provider = _RecordingProvider([], [])
    selected = next(item for item in feasible["sections"] if item["status"] == "ACTIVE")["candidates"][0]
    for key in ("discovery_source_ids", "verification_source_ids", "primary_evidence_source_ids", "independent_evidence_source_ids"):
        selected[key] = []
    with pytest.raises(ProviderError, match="cannot safely support"):
        provider.articles(feasible)
    assert provider.calls == []


def test_no_live_provider_path_or_scheduler_is_used_by_budget_tests() -> None:
    config = load_local_config(ROOT)
    assert config["scheduler"]["enabled"] is False
    assert config["cutover"]["local_scheduler_enabled"] is False
    assert all("offline" == provider.command[0] for provider in [_RecordingProvider([], [])])
