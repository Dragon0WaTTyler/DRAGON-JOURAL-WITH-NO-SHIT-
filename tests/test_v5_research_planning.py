from pathlib import Path

import pytest

from dragon.research_planning import (
    ResearchPlanningError,
    build_hard_coverage_plan,
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
    assert len(plans["front"]["questions"]) <= plans["front"]["research_budget"]["maximum_followup_questions"]
    assert plans["front"]["critical_thinking_checks"]["alternative_cause_and_falsification"] == "PLANNED"
    assert plans["investigations"]["critical_thinking_checks"]["steelmanning"] == "PLANNED"
    assert set(plans["front"]["critical_thinking_checks"].values()) == {"PLANNED"}


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


def test_no_news_section_has_bounded_followup_without_candidate() -> None:
    candidate = _candidate("local-lead")
    packet = {"edition_date": "2099-01-02", "sections": [{
        "section_id": "meknes_local",
        "status": "NO_NEWS",
        "candidates": [],
        "selected_candidate_id": None,
        "selection_reason": None,
        "no_news_reason": "لم يظهر تطور محلي موثق وجدير بالنشر في نافذة البحث المحددة",
        "fallback_action": "RADAR",
    }]}
    intelligence = {"event_clusters": [{
        "event_id": "EVT-OLD",
        "candidate_keys": [f"meknes_local:{candidate['id']}"],
        "independent_origin_count": 2,
    }]}
    value = build_research_plan(packet, intelligence)
    plan = value["plans"][0]
    assert plan["status"] == "NO_NEWS"
    assert plan["candidate_id"] is None
    assert plan["research_branches"] == []
    assert plan["fallback_action"] == "RADAR"
    assert validate_research_plan(value, {"meknes_local"}) == []


def test_initial_plan_exposes_semantic_acquisition_before_recovery() -> None:
    candidate = _candidate("lead")
    packet = {"edition_date": "2099-01-02", "sections": [{
        "section_id": "front", "selected_candidate_id": "lead", "candidates": [candidate],
    }]}
    intelligence = {"event_clusters": [{
        "event_id": "EVT-1", "candidate_keys": ["front:lead"], "independent_origin_count": 2,
    }]}
    readiness = {"coverage_rules": [{
        "id": "accountability_and_service", "sections": ["investigations", "opinion", "service"], "minimum_active": 2,
    }]}
    value = build_research_plan(packet, intelligence, readiness=readiness)
    objective = value["semantic_acquisition_objectives"][0]
    assert objective["status"] == "ACQUISITION_REQUIRED"
    assert objective["missing_distinct_events"] == 2
    assert objective["proposed_editorial_functions"] == ["ACCOUNTABILITY", "SERVICE"]
    assert objective["classification_requirement"] == "VALIDATED_EXACT_PAGE_EVIDENCE"
    assert validate_research_plan(value, {"front"}) == []


def test_hard_coverage_plan_is_known_at_start_and_targets_missing_functions() -> None:
    packet = {"edition_date": "2026-09-13", "sections": []}
    intelligence = {"event_clusters": []}
    readiness = {"coverage_rules": [{
        "id": "accountability_and_service",
        "sections": ["investigations", "service"],
        "minimum_active": 2,
    }]}
    plan = build_hard_coverage_plan(packet, intelligence, readiness)
    requirement = plan["requirements"][0]
    assert plan["known_at_research_start"] is True
    assert requirement["deficit"] == 2
    assert [lane["target_editorial_function"] for lane in requirement["research_lanes"]] == [
        "ACCOUNTABILITY", "SERVICE",
    ]
    assert all(lane["planned_attempts"] == 1 for lane in requirement["research_lanes"])
    assert plan["budget_policy"]["total_limits_changed"] is False


def test_combined_semantic_minimum_does_not_force_one_of_each_function() -> None:
    packet = {"edition_date": "2026-09-13", "sections": [{
        "section_id": "investigations", "status": "ACTIVE",
        "selected_candidate_id": "a", "candidates": [{
            "id": "a", "editorial_functions": [{
                "function": "ACCOUNTABILITY", "status": "VALIDATED",
                "classifier_version": "editorial-functions-v1", "reason": "supported",
                "supporting_event_facts": ["fact"], "evidence_source_ids": ["s1"],
            }],
        }],
    }, {
        "section_id": "service", "status": "ACTIVE",
        "selected_candidate_id": "b", "candidates": [{
            "id": "b", "editorial_functions": [{
                "function": "ACCOUNTABILITY", "status": "VALIDATED",
                "classifier_version": "editorial-functions-v1", "reason": "supported",
                "supporting_event_facts": ["fact"], "evidence_source_ids": ["s2"],
            }],
        }],
    }]}
    intelligence = {"event_clusters": [{
        "event_id": "E1", "candidate_keys": ["investigations:a"],
    }, {"event_id": "E2", "candidate_keys": ["service:b"]}]}
    readiness = {"coverage_rules": [{
        "id": "accountability_and_service", "sections": ["investigations", "service"],
        "minimum_active": 2,
    }]}
    plan = build_hard_coverage_plan(packet, intelligence, readiness)
    assert plan["requirements"][0]["current_count"] == 2
    assert plan["requirements"][0]["deficit"] == 0
    assert plan["requirements"][0]["research_lanes"] == []
