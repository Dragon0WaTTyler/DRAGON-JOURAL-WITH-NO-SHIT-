"""Offline acceptance coverage for bounded source/research recovery."""

from __future__ import annotations

from pathlib import Path

from dragon.config import load_local_config
from dragon.research_recovery import build_recovery_plan, validate_recovery_plan
from dragon.source_coverage import load_source_coverage
from dragon.source_intelligence import build_source_intelligence


ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {
    "front", "siyasa_dawla", "iqtisad_flous", "mojtama3", "ta3lim", "se77a",
    "3adl_7o9o9", "bi2a_manakh", "bniya_transport", "meknes_local",
    "filastin_middle_east", "africa_sahel", "world", "business_companies",
    "technology", "science", "sport", "culture", "adab", "history",
    "investigations", "opinion", "service",
}


def _source(identifier: str, source_type: str, origin: str) -> dict:
    return {
        "id": identifier, "url": f"https://{origin}/{identifier}", "publisher": origin,
        "publication_date": "2099-01-02", "accessed_at": "2099-01-02T07:00:00+00:00",
        "source_type": source_type, "claim_supported": f"Bounded support from {identifier}.",
    }


def _candidate(identifier: str, title: str, primary: list[str], independent: list[str], issues: list[str] | None = None) -> dict:
    return {
        "id": identifier, "rank": 1, "title": title,
        "discovery_source_ids": [*primary, *independent],
        "verification_source_ids": [*primary, *independent],
        "primary_evidence_source_ids": primary,
        "independent_evidence_source_ids": independent,
        "facts": ["Fact"], "claims": [], "unknowns": [], "disputed_points": [],
        "evidence_eligibility": {"status": "ELIGIBLE" if not issues else "INELIGIBLE", "issues": issues or []},
    }


def _plan(packet: dict, *, attempts: dict[str, int] | None = None) -> dict:
    coverage = load_source_coverage(ROOT / "config" / "source-coverage.yaml", EXPECTED)
    readiness = load_local_config(ROOT)["editorial_readiness"]
    return build_recovery_plan(packet, build_source_intelligence(packet), coverage, readiness, attempts_by_need=attempts)


def test_primary_only_and_independent_only_create_targeted_role_needs() -> None:
    packet = {
        "edition_date": "2099-01-02",
        "sources": [_source("p", "primary", "official.example"), _source("i", "independent", "news.example")],
        "sections": [
            {"section_id": "front", "status": "ACTIVE", "selected_candidate_id": "primary-only", "candidates": [_candidate("primary-only", "Primary only", ["p"], [], ["INDEPENDENT_EVIDENCE_MISSING"]) ]},
            {"section_id": "world", "status": "ACTIVE", "selected_candidate_id": "independent-only", "candidates": [_candidate("independent-only", "Independent only", [], ["i"], ["PRIMARY_EVIDENCE_MISSING"]) ]},
        ],
    }
    plan = _plan(packet)
    role_needs = {item["candidate_id"]: item for item in plan["needs"] if item["candidate_id"]}
    assert role_needs["primary-only"]["kind"] == "FIND_INDEPENDENT_CORROBORATION"
    assert role_needs["independent-only"]["kind"] == "FIND_PRIMARY_ORIGINAL_EVIDENCE"
    assert role_needs["primary-only"]["already_known_origins"] == ["https://official.example/p"]
    assert role_needs["primary-only"]["search_constraints"]["must_not_reuse_known_origin_for_both_roles"] is True


def test_coverage_inventory_has_every_v5_desk_and_closes_prior_seed_gaps() -> None:
    coverage = load_source_coverage(ROOT / "config" / "source-coverage.yaml", EXPECTED)
    desks = {item["section_id"]: item for item in coverage["desks"]}
    assert set(desks) == EXPECTED
    for section_id in (
        "meknes_local", "africa_sahel", "adab", "history", "investigations", "service"
    ):
        assert desks[section_id]["coverage_status"] == "COVERED"
        routes = {item["source_id"] for item in coverage["sources"]}
        assert set(desks[section_id]["source_ids"]).issubset(routes)


def test_complete_candidate_has_no_corroboration_need_and_no_news_is_not_promoted() -> None:
    packet = {
        "edition_date": "2099-01-02",
        "sources": [_source("p", "primary", "official.example"), _source("i", "independent", "news.example")],
        "sections": [
            {"section_id": "front", "status": "ACTIVE", "selected_candidate_id": "complete", "candidates": [_candidate("complete", "Complete", ["p"], ["i"]) ]},
            {"section_id": "service", "status": "NO_NEWS", "selected_candidate_id": None, "candidates": [], "no_news_reason": "No supported service item.", "fallback_action": "RADAR"},
        ],
    }
    plan = _plan(packet)
    assert not [item for item in plan["needs"] if item["candidate_id"] == "complete"]
    assert all(item.get("section_id") != "service" for item in plan["needs"] if item["candidate_id"])
    assert plan["selected_active_sections"] == 1


def test_unselected_weak_alternative_cannot_create_a_p0_loop_for_an_eligible_active_story() -> None:
    packet = {
        "edition_date": "2099-01-02",
        "sources": [_source("p", "primary", "official.example"), _source("i", "independent", "news.example")],
        "sections": [{
            "section_id": "front", "status": "ACTIVE", "selected_candidate_id": "selected",
            "candidates": [
                _candidate("selected", "Selected", ["p"], ["i"]),
                _candidate("weak", "Unselected alternative", ["p"], [], ["INDEPENDENT_EVIDENCE_MISSING"]),
            ],
        }],
    }
    plan = _plan(packet)
    assert not [item for item in plan["needs"] if item.get("candidate_id") == "weak"]


def test_no_news_recovery_candidate_does_not_create_a_publication_blocking_loop() -> None:
    packet = {
        "edition_date": "2099-01-02",
        "sources": [_source("p", "primary", "official.example")],
        "sections": [{
            "section_id": "service", "status": "NO_NEWS", "selected_candidate_id": None,
            "candidates": [], "no_news_reason": "No publishable service item.", "fallback_action": "RADAR",
            "recovery_candidates": [_candidate("lead", "Untitled research result", ["p"], [], ["INDEPENDENT_EVIDENCE_MISSING"])],
        }],
    }
    plan = _plan(packet)
    assert not [item for item in plan["needs"] if item.get("candidate_id") == "lead"]
    assert plan["selected_active_sections"] == 0
    assert plan["article_generation_allowed"] is False


def test_direct_official_action_needs_primary_but_not_automatic_independent_corroboration() -> None:
    candidate = _candidate("official", "ضوابط الحملة وفق البوابة الرسمية", ["p"], [], ["INDEPENDENT_EVIDENCE_MISSING"])
    candidate["facts"] = ["نشرت البوابة الرسمية ضوابط الحملة."]
    packet = {
        "edition_date": "2099-01-02", "sources": [_source("p", "official", "official.example")],
        "sections": [{"section_id": "siyasa_dawla", "status": "ACTIVE", "selected_candidate_id": "official", "candidates": [candidate]}],
    }
    plan = _plan(packet)
    assert not [item for item in plan["needs"] if item.get("candidate_id") == "official"]


def test_risky_claim_keeps_independent_requirement_even_when_an_official_source_exists() -> None:
    candidate = _candidate("risk", "اتهام بالفساد", ["p"], [], ["INDEPENDENT_EVIDENCE_MISSING"])
    candidate["facts"] = ["تقول البوابة الرسمية إن الملف قيد المراجعة."]
    packet = {
        "edition_date": "2099-01-02", "sources": [_source("p", "official", "official.example")],
        "sections": [{"section_id": "investigations", "status": "ACTIVE", "selected_candidate_id": "risk", "candidates": [candidate]}],
    }
    plan = _plan(packet)
    need = next(item for item in plan["needs"] if item.get("candidate_id") == "risk")
    assert need["missing_evidence_role"] == "INDEPENDENT"
    assert need["publication_critical_claim"] == "تقول البوابة الرسمية إن الملف قيد المراجعة."


def test_same_origin_roles_are_rejected_and_request_an_independent_replacement() -> None:
    packet = {
        "edition_date": "2099-01-02",
        "sources": [_source("p", "primary", "same.example"), _source("i", "independent", "same.example")],
        "sections": [{"section_id": "front", "status": "ACTIVE", "selected_candidate_id": "same", "candidates": [_candidate("same", "Same origin", ["p"], ["i"], ["EVIDENCE_ROLE_ORIGIN_OVERLAP"]) ]}],
    }
    plan = _plan(packet)
    need = next(item for item in plan["needs"] if item["candidate_id"] == "same")
    assert need["kind"] == "FIND_INDEPENDENT_CORROBORATION"
    assert need["search_constraints"]["must_not_reuse_known_origin_for_both_roles"] is True


def test_duplicate_front_placement_counts_as_one_distinct_event() -> None:
    sources = [_source("p", "primary", "official.example"), _source("i", "independent", "news.example")]
    candidate = _candidate("lead", "One event", ["p"], ["i"])
    packet = {
        "edition_date": "2099-01-02", "sources": sources,
        "sections": [
            {"section_id": "front", "status": "ACTIVE", "selected_candidate_id": "lead", "candidates": [candidate]},
            {"section_id": "ta3lim", "status": "ACTIVE", "selected_candidate_id": "lead", "candidates": [candidate]},
        ],
    }
    plan = _plan(packet)
    assert plan["selected_active_sections"] == 2
    assert plan["distinct_event_count"] == 1
    assert plan["duplicate_placements"] == [{"event_id": plan["duplicate_placements"][0]["event_id"], "candidate_keys": ["front:lead", "ta3lim:lead"]}]


def test_world_and_accountability_gaps_become_explicit_bounded_needs() -> None:
    packet = {
        "edition_date": "2099-01-02",
        "sources": [_source("p", "primary", "official.example"), _source("i", "independent", "news.example")],
        "sections": [{"section_id": "front", "status": "ACTIVE", "selected_candidate_id": "lead", "candidates": [_candidate("lead", "Lead", ["p"], ["i"]) ]}],
    }
    plan = _plan(packet)
    kinds = [item["kind"] for item in plan["needs"]]
    assert kinds.count("NEED_WORLD_BREADTH") == 2
    assert kinds.count("NEED_ACCOUNTABILITY_AND_SERVICE") == 2
    assert all(item["max_attempts"] == 1 for item in plan["needs"])


def _sufficient_packet() -> dict:
    sources, sections = [], []
    for index, section_id in enumerate(sorted(EXPECTED)):
        primary, independent = f"p{index}", f"i{index}"
        sources.extend([_source(primary, "primary", f"official-{index}.example"), _source(independent, "independent", f"news-{index}.example")])
        candidate = _candidate(f"c{index}", f"event{index}", [primary], [independent])
        sections.append({"section_id": section_id, "status": "ACTIVE", "selected_candidate_id": candidate["id"], "candidates": [candidate]})
    return {"edition_date": "2099-01-02", "sources": sources, "sections": sections}


def test_exhaustion_fails_closed_and_legitimate_recovered_fixture_passes() -> None:
    insufficient = _plan({
        "edition_date": "2099-01-02", "sources": [_source("p", "primary", "official.example")],
        "sections": [{"section_id": "front", "status": "ACTIVE", "selected_candidate_id": "only", "candidates": [_candidate("only", "Only", ["p"], [], ["INDEPENDENT_EVIDENCE_MISSING"]) ]}],
    })
    exhausted = _plan({
        "edition_date": "2099-01-02", "sources": [_source("p", "primary", "official.example")],
        "sections": [{"section_id": "front", "status": "ACTIVE", "selected_candidate_id": "only", "candidates": [_candidate("only", "Only", ["p"], [], ["INDEPENDENT_EVIDENCE_MISSING"]) ]}],
    }, attempts={item["need_id"]: item["max_attempts"] for item in insufficient["needs"]})
    assert exhausted["status"] == "RESEARCH_INSUFFICIENT"
    assert exhausted["article_generation_allowed"] is False
    passed = _plan(_sufficient_packet())
    assert passed["status"] == "PASS"
    assert passed["article_generation_allowed"] is True
    assert validate_recovery_plan(passed) == []
