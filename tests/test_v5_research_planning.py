from pathlib import Path

import pytest

from dragon.research_planning import (
    ResearchPlanningError,
    build_research_plan,
    load_research_budget_config,
    validate_research_plan,
)


ROOT = Path(__file__).resolve().parents[1]


def _candidate(identifier: str, *, disputed: bool = False) -> dict:
    return {
        "id": identifier,
        "facts": ["واقعة موثقة"],
        "claims": ["ادعاء يحتاج إلى نسبة واضحة"],
        "unknowns": ["معلومة غير متاحة"],
        "disputed_points": ["نقطة خلاف"] if disputed else [],
        "discovery_source_ids": ["s1"],
        "verification_source_ids": ["s2"],
        "primary_evidence_source_ids": ["s2"],
        "independent_evidence_source_ids": ["s1"],
    }


def test_research_plan_is_stable_relevant_and_evidence_budgeted() -> None:
    sections = []
    intelligence_events = []
    for section_id in ("front", "science", "investigations"):
        candidate = _candidate(f"{section_id}-lead", disputed=section_id == "investigations")
        sections.append({
            "section_id": section_id,
            "selected_candidate_id": candidate["id"],
            "candidates": [candidate],
        })
        intelligence_events.append({
            "event_id": f"EVT-{section_id.upper()}",
            "candidate_keys": [f"{section_id}:{candidate['id']}"],
            "independent_origin_count": 2,
        })
    packet = {"edition_date": "2099-01-02", "sections": sections}
    intelligence = {"event_clusters": intelligence_events}

    value = build_research_plan(packet, intelligence)
    assert value == build_research_plan(packet, intelligence)
    assert validate_research_plan(value, {"front", "science", "investigations"}) == []
    plans = {item["section_id"]: item for item in value["plans"]}
    assert "خبير المنهجية" in plans["science"]["perspectives"]
    assert "الموقف المقابل" in plans["investigations"]["perspectives"]
    assert plans["investigations"]["research_budget"]["level"] == "investigation"
    assert plans["front"]["event_id"] == "EVT-FRONT"
    assert any("أصل خبري واحد" in item for item in plans["front"]["questions"])
    assert plans["front"]["context_management"]["policy"] == "BOUNDED_PERIODIC_COMPRESSION"
    assert set(plans["front"]["research_snapshot"]) == {
        "what_we_know", "what_is_strongly_supported", "what_is_disputed",
        "what_remains_unknown", "what_to_search_next",
    }
    assert plans["front"]["research_budget"]["signal_contributions"]


def test_research_plan_validator_rejects_missing_inventory() -> None:
    value = {"schema_version": 1, "status": "PASS", "plans": []}
    assert "RESEARCH_PLAN_SECTION_INVENTORY_INVALID" in validate_research_plan(
        value, {"front"}
    )


def test_budget_policy_is_strict_config_and_context_is_bounded(tmp_path: Path) -> None:
    config = load_research_budget_config(ROOT / "config" / "research-budget.yaml")
    candidate = _candidate("lead")
    candidate["facts"] = [f"fact-{index}" for index in range(20)]
    packet = {"edition_date": "2099-01-02", "sections": [{
        "section_id": "front", "selected_candidate_id": "lead", "candidates": [candidate]
    }]}
    intelligence = {"event_clusters": [{
        "event_id": "EVT-1", "candidate_keys": ["front:lead"], "independent_origin_count": 2
    }]}
    plan = build_research_plan(packet, intelligence, config)["plans"][0]
    assert len(plan["known_facts"]) == config["context"]["maximum_items_per_bucket"]
    assert plan["context_management"]["input_items"] > plan["context_management"]["retained_items"]
    assert len(plan["research_branches"]) <= plan["research_budget"]["maximum_parallel_branches"]

    bad = tmp_path / "research-budget.yaml"
    value = dict(config)
    value["thresholds"] = {"normal": 9, "major": 7, "investigation": 4}
    import yaml
    bad.write_text(yaml.safe_dump(value), encoding="utf-8")
    with pytest.raises(ResearchPlanningError):
        load_research_budget_config(bad, ROOT / "config" / "research-budget-schema.json")
