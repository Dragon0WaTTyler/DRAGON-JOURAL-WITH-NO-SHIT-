from __future__ import annotations

import pytest

from dragon.provider_targeting import build_research_targeting
from dragon.providers import LocalCommandEditorialProvider, ProviderError


READINESS = {
    "coverage_rules": [
        {"id": "morocco_breadth", "sections": ["siyasa_dawla"], "minimum_active": 3},
        {"id": "world_breadth", "sections": ["world"], "minimum_active": 2},
        {"id": "reader_life", "sections": ["service"], "minimum_active": 2},
        {
            "id": "accountability_and_service",
            "sections": ["investigations", "opinion", "service"],
            "minimum_active": 2,
        },
    ],
}


def test_targeting_orders_hard_semantic_deficits_before_breadth() -> None:
    targeting = build_research_targeting("2099-01-02", READINESS)

    assert targeting["as_of_date"] == "2099-01-02"
    assert targeting["ordering"] == "HARD_UNRESOLVED_THEN_REMAINING_BREADTH"
    assert [(item["target_id"], item["semantic_lane"], item["hard"]) for item in targeting["unresolved_targets"]] == [
        ("HARD:ACCOUNTABILITY", "ACCOUNTABILITY", True),
        ("HARD:SERVICE", "SERVICE", True),
        ("BREADTH:morocco_breadth", "BREADTH", False),
        ("BREADTH:world_breadth", "BREADTH", False),
        ("BREADTH:reader_life", "BREADTH", False),
    ]
    assert all(item["current_status"] == "UNRESOLVED_PRE_DISCOVERY" for item in targeting["unresolved_targets"])
    assert all(item["minimum_closure_requirement"]["provider_cannot_close_need"] is True for item in targeting["unresolved_targets"])


def test_targeting_projects_existing_semantics_without_execution_authority() -> None:
    targeting = build_research_targeting("2099-01-02", READINESS)

    accountability = targeting["accountability_contract"]
    assert "formal audit or inspection action or finding" in accountability["qualifying_mechanisms"]
    assert "institutional participation without a concrete accountability action" in accountability["exclusions"]
    assert "generic call for transparency" in accountability["exclusions"]

    service = targeting["service_contract"]
    assert "service launch, activation, interruption, or restoration" in service["qualifying_mechanisms"]
    assert "future-only announcement when current operation is required" in service["exclusions"]

    assert targeting["source_expectations"]["provider_role_status"] == "UNVERIFIED_SUGGESTION"
    assert "current dated publication" in targeting["source_expectations"]["current_dated_publication"]
    assert targeting["claim_source_mapping"]["field"] == "claim_supported"
    assert targeting["provider_output"] == {
        "status": "DISCOVERY_INTELLIGENCE_ONLY",
        "provider_reported_roles_are_unverified": True,
        "can_close_research_need": False,
        "can_emit_executor_actions": False,
        "hard_target_dispositions_required": True,
        "hard_target_disposition_statuses": ["CANDIDATES_PRODUCED", "NO_QUALIFYING_CANDIDATE_FOUND"],
    }


def _hard_results() -> list[dict]:
    return [{
        "target_id": target_id,
        "status": "NO_QUALIFYING_CANDIDATE_FOUND",
        "search_intent": f"Find a current {target_id} event.",
        "search_attempts": [{"query": f"current {target_id}", "purpose": "fixture search"}],
        "candidate_matches": [],
        "no_qualifying_reason": "No qualifying candidate in the fixture.",
    } for target_id in ("HARD:ACCOUNTABILITY", "HARD:SERVICE")]


def test_hard_target_validator_requires_explicit_results_for_each_lane() -> None:
    targeting = build_research_targeting("2099-01-02", READINESS)
    with pytest.raises(ProviderError) as caught:
        LocalCommandEditorialProvider._validate_hard_target_results(
            [_hard_results()[0]], targeting, {}, {}, {},
        )
    assert caught.value.code == "HARD_TARGET_DISPOSITION_MISSING"
    assert caught.value.diagnostics["hard_target_results"][0]["target_id"] == "HARD:SERVICE"


def test_generic_candidate_cannot_be_reported_as_a_hard_lane_match() -> None:
    targeting = build_research_targeting("2099-01-02", READINESS)
    results = _hard_results()
    results[0] = {
        "target_id": "HARD:ACCOUNTABILITY",
        "status": "CANDIDATES_PRODUCED",
        "search_intent": "Find current oversight action.",
        "search_attempts": [{"query": "audit action", "purpose": "fixture search"}],
        "candidate_matches": [{
            "candidate_id": "world-generic",
            "semantic_match_rationale": "Generic country context.",
            "current_event_rationale": "Current date.",
            "expected_source_roles": ["PRIMARY"],
            "exact_artifact_source_ids": ["source-1"],
        }],
        "no_qualifying_reason": None,
    }
    with pytest.raises(ProviderError) as caught:
        LocalCommandEditorialProvider._validate_hard_target_results(
            results, targeting, {"world-generic": {"world"}},
            {"world-generic": {"id": "world-generic"}}, {"source-1": {"id": "source-1"}},
        )
    assert caught.value.code == "HARD_TARGET_CANDIDATE_MISMATCH"
    serialized = str(targeting).casefold()
    assert "budget" not in serialized
    assert "scheduler" not in serialized
