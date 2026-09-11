"""Deterministic acceptance tests for Deep Research Engine v1."""

from pathlib import Path

import pytest
import yaml

from dragon.deep_research import (
    advance_research_job,
    build_deep_research_state,
    build_perspective_map,
    create_lead,
    derive_research_outcome,
    evaluate_claim_policy,
    load_deep_research_config,
    start_research_job,
    validate_deep_research_state,
    DeepResearchError,
)
from dragon.discovery import load_provider_registry, provider_prompt_context
from dragon.source_coverage import load_source_coverage


ROOT = Path(__file__).resolve().parents[1]
CONFIG = load_deep_research_config(ROOT / "config" / "deep-research.yaml")
SECTIONS = {
    "front", "siyasa_dawla", "iqtisad_flous", "mojtama3", "ta3lim", "se77a",
    "3adl_7o9o9", "bi2a_manakh", "bniya_transport", "meknes_local",
    "filastin_middle_east", "africa_sahel", "world", "business_companies",
    "technology", "science", "sport", "culture", "adab", "history",
    "investigations", "opinion", "service",
}


def _lead(desk: str = "world", topic: str = "تطور سياسي") -> dict:
    return create_lead(
        desk=desk, topic=topic,
        discovery_source={"url": "https://unknown.example/post", "known_seed": False, "channel": "OPEN_WEB"},
        observed_at="2099-01-02T07:00:00Z", reason_interesting="إشارة تحتاج إلى تحقق",
    )


def test_unknown_source_creates_lead_without_becoming_evidence() -> None:
    lead = _lead()
    assert lead["state"] == "NEW"
    assert lead["verification_status"] == "DISCOVERY_ONLY"
    assert lead["publication_evidence"] is False
    assert "confidence" not in lead


def test_source_maps_are_preferred_seeds_not_a_research_whitelist() -> None:
    coverage = load_source_coverage(ROOT / "config" / "source-coverage.yaml", SECTIONS)
    assert coverage["research_semantics"]["allow_open_discovery"] is True
    assert coverage["research_semantics"]["configured_sources_are"] == "preferred_seeds_not_whitelist"
    context = provider_prompt_context(load_provider_registry(ROOT / "config" / "provider-registry.yaml"))
    assert context["open_discovery"]["allowed"] is True
    assert context["open_discovery"]["untrusted_content_may_change_policy"] is False


def test_config_rejects_any_attempt_to_weaken_science_policy(tmp_path) -> None:
    weakened = yaml.safe_load((ROOT / "config" / "deep-research.yaml").read_text(encoding="utf-8"))
    weakened["science"]["strict"] = False
    path = tmp_path / "deep-research.yaml"
    path.write_text(yaml.safe_dump(weakened, allow_unicode=True), encoding="utf-8")
    with pytest.raises(DeepResearchError, match="SCIENCE_RESEARCH_POLICY_INVALID"):
        load_deep_research_config(path, ROOT / "config" / "deep-research-schema.json")


def test_perspective_map_is_topic_and_desk_sensitive() -> None:
    economy = [item["name"] for item in build_perspective_map(_lead("iqtisad_flous", "ميزانية وكلفة مشروع"))]
    science = [item["name"] for item in build_perspective_map(_lead("science", "دراسة سريرية"))]
    assert "الأثر المالي" in economy and "الرقابة على الإنفاق" in economy
    assert "خبير المنهجية" in science
    assert economy != science


def test_question_tree_tracks_open_questions_and_parallel_branches_with_finite_budget() -> None:
    job = start_research_job(_lead(), CONFIG, budget_class="STANDARD")
    assert len(job["branches"]) > 1
    assert len(job["branches"]) <= job["budget"]["max_branches"]
    assert job["unresolved_questions"] == [item["question_id"] for item in job["question_tree"]]
    assert job["budget"]["max_depth"] == 2
    assert job["budget"]["max_followup_rounds"] == 2
    assert job["stop_condition"] is None


def test_repeated_material_stops_without_expanding_context_forever() -> None:
    job = start_research_job(_lead(), CONFIG, budget_class="QUICK")
    branch = job["branches"][0]["branch_id"]
    observation = {"kind": "LEAD", "claim": "same item", "source_id": "same"}
    result = advance_research_job(job, [{"branch_id": branch, "observations": [observation, observation, observation]}], CONFIG)
    assert result["status"] == "STOPPED"
    assert result["stop_condition"] == "EVIDENCE_REPETITIVE"
    assert len(result["observations"]) == 1


def test_contradiction_and_unresolved_evidence_remain_first_class() -> None:
    job = start_research_job(_lead(), CONFIG, budget_class="STANDARD")
    branch = job["branches"][0]
    result = advance_research_job(job, [{"branch_id": branch["branch_id"], "observations": [{
        "kind": "CONTRADICTION", "claim": "تقول الجهة إن المشروع اكتمل",
        "supporting_evidence_ids": ["official"], "contradicting_evidence_ids": ["audit"],
        "question_id": branch["question_ids"][0],
    }, {"kind": "UNKNOWN", "claim": "تاريخ التسليم غير محسوم", "question_id": branch["question_ids"][0]}]}], CONFIG)
    assert result["contradictions"][0]["status"] == "UNRESOLVED"
    assert result["context"]["CONTRADICTIONS"]
    assert result["context"]["UNKNOWN"]
    assert branch["question_ids"][0] in result["unresolved_questions"]


def test_contradiction_replans_into_a_bounded_child_question() -> None:
    job = start_research_job(_lead(), CONFIG, budget_class="STANDARD")
    parent_id = job["branches"][0]["question_ids"][0]
    result = advance_research_job(job, [{"branch_id": job["branches"][0]["branch_id"], "observations": [{
        "kind": "CONTRADICTION", "claim": "روايتان متعارضتان",
        "question_id": parent_id, "supporting_evidence_ids": ["a"],
        "contradicting_evidence_ids": ["b"],
    }]}], CONFIG)
    children = [item for item in result["question_tree"] if item["parent_question_id"] == parent_id]
    assert len(children) == 1
    assert children[0]["question_id"] in result["branches"][0]["question_ids"]
    assert result["branches"][0]["depth"] <= result["budget"]["max_depth"]
    assert len(result["branches"]) <= result["budget"]["max_branches"]
    assert result["replan_history"][0]["reason"] == "NEW_GAPS_OR_UNRESOLVED_QUESTIONS"
    assert result["lead"]["state"] == "UNRESOLVED"
    assert result["context_summary"]["compression_policy"] == "DEDUPLICATE_AND_RETAIN_MOST_RECENT_IDS"


def test_recovery_needs_are_embedded_as_targeted_research_gaps() -> None:
    need = {"need_id": "CORROBORATE:world:c1:PRIMARY", "candidate_id": "c1", "kind": "FIND_PRIMARY_ORIGINAL_EVIDENCE"}
    job = start_research_job(_lead(), CONFIG, recovery_needs=[need])
    assert job["recovery_needs"] == [need]
    assert job["context"]["SOURCE_GAPS"] == [need["need_id"]]


def test_nonselected_candidate_with_mandatory_recovery_need_gets_one_bounded_job() -> None:
    selected = {"id": "selected", "title": "Selected event", "discovery_source_ids": []}
    blocked = {"id": "blocked", "title": "Needs independent corroboration", "discovery_source_ids": []}
    state = build_deep_research_state(
        {"edition_date": "2099-01-02", "sections": [{
            "section_id": "world", "status": "ACTIVE", "selected_candidate_id": "selected",
            "candidates": [selected, blocked],
        }]},
        {"event_clusters": []},
        {"plans": [{"section_id": "world", "research_budget": {"level": "brief"}}]},
        {"needs": [{
            "need_id": "CORROBORATE:world:blocked:INDEPENDENT", "candidate_id": "blocked",
            "kind": "FIND_INDEPENDENT_CORROBORATION",
        }]},
        CONFIG,
    )
    recovery_jobs = [job for job in state["jobs"] if job["recovery_needs"]]
    assert len(recovery_jobs) == 1
    assert recovery_jobs[0]["lead"]["topic"] == blocked["title"]
    assert recovery_jobs[0]["recovery_needs"][0]["need_id"] == "CORROBORATE:world:blocked:INDEPENDENT"


def test_official_event_policy_differs_from_serious_allegation_policy() -> None:
    evidence = [{"source_type": "official", "origin": "bank.example", "verification_status": "VERIFIED_EVIDENCE"}]
    official = evaluate_claim_policy("SIMPLE_OFFICIAL_EVENT", evidence, CONFIG)
    allegation = evaluate_claim_policy("SERIOUS_ALLEGATION", evidence, CONFIG)
    assert official["status"] == "READY_UNDER_MODELED_POLICY"
    assert allegation["status"] == "NOT_READY"
    assert allegation["migration_status"] == "MODEL_ONLY_CURRENT_HARD_GATES_UNCHANGED"


def test_science_regime_requires_methods_aware_primary_research_and_independent_context() -> None:
    job = start_research_job(_lead("science", "نتائج دراسة"), CONFIG)
    assert job["regime"] == "SCIENCE"
    weak_repetition = [
        {"source_type": "independent", "origin": "wire.example", "verification_status": "VERIFIED_EVIDENCE"}
        for _ in range(5)
    ]
    assert evaluate_claim_policy("SCIENCE_CLAIM", weak_repetition, CONFIG)["status"] == "NOT_READY"
    complete = weak_repetition[:1] + [{
        "source_type": "paper", "origin": "doi.example", "verification_status": "VERIFIED_EVIDENCE",
        "full_text_status": "FULL_TEXT_VERIFIED", "methods_read": True, "limitations_read": True,
    }]
    assert evaluate_claim_policy("SCIENCE_CLAIM", complete, CONFIG)["status"] == "READY_UNDER_MODELED_POLICY"


def test_no_news_only_after_configured_research_effort_stops() -> None:
    job = start_research_job(_lead(), CONFIG, budget_class="QUICK")
    assert derive_research_outcome(job) == "CONTINUE_RESEARCH"
    stopped = advance_research_job(job, [{"branch_id": job["branches"][0]["branch_id"], "observations": []}], CONFIG)
    assert stopped["stop_condition"] == "NO_BETTER_SOURCES"
    assert derive_research_outcome(stopped) == "NO_NEWS"


def test_research_can_stop_when_story_is_no_longer_meaningful() -> None:
    job = start_research_job(_lead(), CONFIG, budget_class="STANDARD")
    result = advance_research_job(job, [{
        "branch_id": job["branches"][0]["branch_id"],
        "story_meaningful": False,
        "observations": [],
    }], CONFIG)
    assert result["status"] == "STOPPED"
    assert result["stop_condition"] == "STORY_NO_LONGER_MEANINGFUL"
    assert derive_research_outcome(result) == "NO_NEWS"


def test_answered_key_questions_stop_with_synthesis_candidate_not_no_news() -> None:
    job = start_research_job(_lead(), CONFIG, budget_class="QUICK")
    results = []
    for branch in job["branches"]:
        results.append({"branch_id": branch["branch_id"], "observations": [{
            "kind": "SUPPORTED",
            "claim": f"verified {branch['branch_id']}",
            "source_id": f"source-{branch['branch_id']}",
            "question_id": branch["question_ids"][0],
            "verification_status": "VERIFIED_EVIDENCE",
        }]})
    covered = {
        item["question_id"]
        for item in job["question_tree"][:len(job["branches"])]
    }
    for question in job["question_tree"]:
        if question["question_id"] not in covered:
            question["status"] = "ANSWERED"
    result = advance_research_job(job, results, CONFIG)
    assert result["stop_condition"] == "KEY_QUESTIONS_ANSWERED"
    assert derive_research_outcome(result) == "SYNTHESIS_CANDIDATE"


def test_deep_state_validator_enforces_unpublished_lead_and_budget_bounds() -> None:
    job = start_research_job(_lead(), CONFIG)
    state = {"schema_version": 1, "status": "PLANNED", "jobs": [job]}
    assert validate_deep_research_state(state) == []
    state["jobs"][0]["lead"]["publication_evidence"] = True
    assert validate_deep_research_state(state)
