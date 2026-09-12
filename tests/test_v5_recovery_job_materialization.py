"""Regression coverage for lossless recovery-need job materialization."""

from __future__ import annotations

from pathlib import Path

import pytest

from dragon.config import load_local_config
from dragon.deep_research import (
    DeepResearchError,
    build_deep_research_state,
    create_lead,
    load_deep_research_config,
    start_research_job,
    validate_deep_research_state,
)
from dragon.deep_research_executor import (
    FixtureResearchAdapter,
    execute_research_round,
    plan_research_actions,
    replay_recovery_after_execution,
    schedule_research_actions,
)
from dragon.source_coverage import load_source_coverage
from dragon.source_intelligence import build_source_intelligence


ROOT = Path(__file__).resolve().parents[1]
CONFIG = load_deep_research_config(ROOT / "config" / "deep-research.yaml")
SECTIONS = {
    "front", "siyasa_dawla", "iqtisad_flous", "mojtama3", "ta3lim", "se77a",
    "3adl_7o9o9", "bi2a_manakh", "bniya_transport", "meknes_local",
    "filastin_middle_east", "africa_sahel", "world", "business_companies",
    "technology", "science", "sport", "culture", "adab", "history",
    "investigations", "opinion", "service",
}


def _source(identifier: str, source_type: str, origin: str) -> dict:
    return {
        "id": identifier, "url": f"https://{origin}/{identifier}",
        "publisher": origin, "publication_date": "2026-09-12",
        "accessed_at": "2026-09-12T08:00:00+01:00", "source_type": source_type,
        "claim_supported": f"Evidence for {identifier}",
    }


def _candidate(identifier: str, title: str, source_id: str, *, primary: bool) -> dict:
    return {
        "id": identifier, "rank": 1, "title": title,
        "facts": [title], "claims": [], "unknowns": [], "disputed_points": [],
        "entities": ["Meknes"], "geography": ["Morocco"],
        "discovery_source_ids": [source_id], "verification_source_ids": [source_id],
        "primary_evidence_source_ids": [source_id] if primary else [],
        "independent_evidence_source_ids": [] if primary else [source_id],
        "evidence_eligibility": {
            "status": "INELIGIBLE",
            "issues": ["INDEPENDENT_EVIDENCE_MISSING" if primary else "PRIMARY_EVIDENCE_MISSING"],
        },
    }


def _need(identifier: str, candidate_id: str | None, kind: str, *, desk: str = "sport", role: str | None = None) -> dict:
    return {
        "need_id": identifier, "kind": kind, "section_id": desk if candidate_id else None,
        "event_id": f"EVT-{identifier}", "candidate_id": candidate_id,
        "missing_evidence_role": role,
        "already_known_source_ids": ["sport-primary"] if candidate_id == "sport" else ["audit-independent"] if candidate_id else [],
        "already_known_origins": ["official.example"] if candidate_id == "sport" else ["independent.example"] if candidate_id else [],
        "topic_identifiers": ["Meknes", "Tennis Cup"] if candidate_id else ["world"],
        "query_context": {
            "entities": ["Meknes"], "geography": ["Morocco"],
            "event_terms": ["Meknes Tennis Cup"], "research_date": "2026-09-12",
        },
        "search_constraints": {
            "configured_source_routes": [
                {"role": "INDEPENDENT", "origin": "independent.example", "url": "https://independent.example/news"},
                {"role": "PRIMARY", "origin": "official.example", "url": "https://official.example/notices"},
            ],
            "eligible_section_ids": ["world"],
        },
        "attempt_count": 0, "max_attempts": 1,
        "stop_condition": "ROLE_EVIDENCE_ADDED_OR_ATTEMPTS_EXHAUSTED",
    }


def _packet() -> dict:
    sport = _candidate("sport", "Meknes Tennis Cup", "sport-primary", primary=True)
    investigation = _candidate("investigation", "Meknes audit", "audit-independent", primary=False)
    return {
        "edition_date": "2026-09-12",
        "sources": [
            _source("sport-primary", "official", "official.example"),
            _source("audit-independent", "independent", "independent.example"),
        ],
        "sections": [
            {"section_id": "sport", "status": "NO_NEWS", "candidates": [sport], "recovery_candidates": []},
            {"section_id": "investigations", "status": "NO_NEWS", "candidates": [investigation], "recovery_candidates": []},
        ],
    }


def _state(needs: list[dict]) -> dict:
    return build_deep_research_state(
        _packet(), {"event_clusters": []}, {"plans": []}, {"needs": needs}, CONFIG,
        run_scope_id="offline-preserved-run",
    )


def _job_for(state: dict, need_id: str) -> dict:
    return next(job for job in state["jobs"] if job["recovery_needs"] and job["recovery_needs"][0]["need_id"] == need_id)


def _coverage() -> dict:
    return load_source_coverage(ROOT / "config" / "source-coverage.yaml", SECTIONS)


def _has_sport_independent_gap(replay: dict) -> bool:
    return any(
        item.get("candidate_id") == "sport"
        and item.get("kind") == "FIND_INDEPENDENT_CORROBORATION"
        for item in replay["recovery"]["needs"]
    )


def test_all_executable_need_kinds_materialize_to_one_visible_job() -> None:
    needs = [
        _need("p0-independent", "sport", "FIND_INDEPENDENT_CORROBORATION", role="INDEPENDENT"),
        _need("p0-primary", "investigation", "FIND_PRIMARY_ORIGINAL_EVIDENCE", desk="investigations", role="PRIMARY"),
        _need("world", None, "NEED_WORLD_BREADTH"),
        _need("accountability", None, "NEED_ACCOUNTABILITY_AND_SERVICE"),
        _need("reader", None, "NEED_READER_LIFE"),
        _need("distinct", None, "NEED_DISTINCT_EVENT"),
    ]
    state = _state(needs)
    mappings = state["recovery_job_mappings"]
    assert {item["recovery_need_id"] for item in mappings} == {item["need_id"] for item in needs}
    assert len({item["job_id"] for item in mappings}) == len(needs)
    assert {item["run_scope_id"] for item in mappings} == {"offline-preserved-run"}
    assert validate_deep_research_state(state) == []


def test_no_news_candidate_p0_context_and_priority_reach_query_generation() -> None:
    need = _need("p0-independent", "sport", "FIND_INDEPENDENT_CORROBORATION", role="INDEPENDENT")
    job = _job_for(_state([need]), need["need_id"])
    actions = plan_research_actions(job, CONFIG)
    assert job["recovery_job"]["candidate_ids"] == ["sport"]
    assert job["budget_class"] == "STANDARD"
    assert job["recovery_job"]["event_ids"] == [need["event_id"]]
    assert actions[0]["priority_class"] == "P0_BLOCKING_EVIDENCE"
    assert actions[0]["recovery_candidate_id"] == "sport"
    assert actions[0]["event_context"]["entities"] == ["Meknes"]
    assert actions[0]["event_context"]["research_date"] == "2026-09-12"
    assert actions[0]["provenance_requirements"]["required_role"] == "INDEPENDENT"


def test_two_p0_jobs_do_not_collide_and_p1_still_receives_a_bounded_slot() -> None:
    p0a = _need("p0-sport", "sport", "FIND_INDEPENDENT_CORROBORATION", role="INDEPENDENT")
    p0b = _need("p0-audit", "investigation", "FIND_PRIMARY_ORIGINAL_EVIDENCE", desk="investigations", role="PRIMARY")
    p1 = _need("world", None, "NEED_WORLD_BREADTH")
    state = _state([p0a, p0b, p1])
    p3 = start_research_job(create_lead(
        desk="culture", topic="Background only", discovery_source={"known_seed": False},
        observed_at="2026-09-12", reason_interesting="OPTIONAL_CONTEXT",
    ), CONFIG, run_scope_id="offline-preserved-run")
    schedule = schedule_research_actions([*state["jobs"], p3], CONFIG)
    selected = schedule["actions"]
    assert selected[0]["priority_class"] == "P0_BLOCKING_EVIDENCE"
    assert {item["recovery_need_id"] for item in selected} >= {"p0-sport", "p0-audit", "world"}
    assert len({item["job_id"] for item in selected if item.get("recovery_need_id") in {"p0-sport", "p0-audit"}}) == 2
    assert all(item["priority_class"] != "P3_CONTEXT" for item in selected)


def test_both_p0_actions_execute_and_dead_end_leaves_independent_need_open() -> None:
    need = _need("p0-independent", "sport", "FIND_INDEPENDENT_CORROBORATION", role="INDEPENDENT")
    primary_need = _need("p0-primary", "investigation", "FIND_PRIMARY_ORIGINAL_EVIDENCE", desk="investigations", role="PRIMARY")
    packet = _packet()
    state = _state([need, primary_need])
    executions = [
        execute_research_round(
            _job_for(state, current["need_id"]),
            FixtureResearchAdapter({"FETCH_CONFIGURED_SOURCE": [{"result_type": "DEAD_END", "reason": "OFFLINE"}], "RECOVER_INDEPENDENT_SOURCE": [], "RECOVER_PRIMARY_SOURCE": []}),
            CONFIG,
        )
        for current in (need, primary_need)
    ]
    assert all(execution["actions"] for execution in executions)
    assert {
        action["recovery_need_id"] for execution in executions for action in execution["actions"]
    } >= {need["need_id"], primary_need["need_id"]}
    execution = executions[0]
    replay = replay_recovery_after_execution(packet, execution, _coverage(), load_local_config(ROOT)["editorial_readiness"])
    assert _has_sport_independent_gap(replay)
    assert replay["article_generation_allowed"] is False


@pytest.mark.parametrize("raw", [
    {"url": "https://independent.example/wrong", "title": "Unrelated concert", "text": "Unrelated concert coverage with sufficient extracted text for verification.", "content_hash": "a" * 64, "fetch_status": "FETCHED", "source_class": "independent", "relevant": False},
    {"url": "https://official.example/relabelled", "title": "Meknes Tennis Cup", "text": "Meknes Tennis Cup official statement with sufficient extracted text for verification.", "content_hash": "b" * 64, "fetch_status": "FETCHED", "source_class": "independent"},
])
def test_wrong_event_or_same_origin_cannot_close_independent_p0(raw: dict) -> None:
    need = _need("p0-independent", "sport", "FIND_INDEPENDENT_CORROBORATION", role="INDEPENDENT")
    packet = _packet()
    job = _job_for(_state([need]), need["need_id"])
    action = plan_research_actions(job, CONFIG)[0]
    execution = execute_research_round(job, FixtureResearchAdapter({"FETCH_CONFIGURED_SOURCE": [raw]}), CONFIG, actions=[action])
    replay = replay_recovery_after_execution(packet, execution, _coverage(), load_local_config(ROOT)["editorial_readiness"])
    assert _has_sport_independent_gap(replay)


def test_validated_independent_exact_page_can_close_p0() -> None:
    need = _need("p0-independent", "sport", "FIND_INDEPENDENT_CORROBORATION", role="INDEPENDENT")
    packet = _packet()
    job = _job_for(_state([need]), need["need_id"])
    action = plan_research_actions(job, CONFIG)[0]
    raw = {
        "url": "https://independent.example/meknes-tennis", "title": "Meknes Tennis Cup",
        "text": "Meknes Tennis Cup independently reported with sufficient direct supporting detail.",
        "content_hash": "c" * 64, "fetch_status": "FETCHED", "source_class": "independent",
    }
    execution = execute_research_round(job, FixtureResearchAdapter({"FETCH_CONFIGURED_SOURCE": [raw]}), CONFIG, actions=[action])
    replay = replay_recovery_after_execution(packet, execution, _coverage(), load_local_config(ROOT)["editorial_readiness"])
    assert not _has_sport_independent_gap(replay)


def test_unmapped_executable_need_fails_explicitly() -> None:
    missing = _need("missing", "does-not-exist", "FIND_INDEPENDENT_CORROBORATION", role="INDEPENDENT")
    with pytest.raises(DeepResearchError, match="RECOVERY_JOB_MATERIALIZATION_FAILED"):
        _state([missing])


def test_epoch_one_materializes_only_new_candidate_p0_without_p1_duplication() -> None:
    """A candidate created by Epoch 0 can enter the one permitted delta epoch."""
    p0 = _need("epoch1-independent", "sport", "FIND_INDEPENDENT_CORROBORATION", role="INDEPENDENT")
    p1 = _need("world", None, "NEED_WORLD_BREADTH")
    state = build_deep_research_state(
        _packet(), {"event_clusters": []}, {"plans": []}, {"needs": [p0]}, CONFIG,
        run_scope_id="epoch-replay", recovery_epoch=1, recovery_only=True,
    )
    assert state["recovery_epoch"] == 1
    assert [item["recovery_need_id"] for item in state["recovery_job_mappings"]] == [p0["need_id"]]
    assert state["recovery_job_mappings"][0]["priority"] == "P0_BLOCKING_EVIDENCE"
    assert state["jobs"][0]["budget_class"] == "STANDARD"
    assert all(p1["need_id"] not in job["context"]["SOURCE_GAPS"] for job in state["jobs"])
    assert plan_research_actions(state["jobs"][0], CONFIG)[0]["priority_class"] == "P0_BLOCKING_EVIDENCE"


def test_epoch_one_is_idempotent_for_the_same_delta_need() -> None:
    need = _need("epoch1-independent", "sport", "FIND_INDEPENDENT_CORROBORATION", role="INDEPENDENT")
    first = build_deep_research_state(_packet(), {"event_clusters": []}, {"plans": []}, {"needs": [need]}, CONFIG, run_scope_id="epoch-replay", recovery_epoch=1, recovery_only=True)
    second = build_deep_research_state(_packet(), {"event_clusters": []}, {"plans": []}, {"needs": [need]}, CONFIG, run_scope_id="epoch-replay", recovery_epoch=1, recovery_only=True)
    assert first["recovery_job_mappings"] == second["recovery_job_mappings"]
