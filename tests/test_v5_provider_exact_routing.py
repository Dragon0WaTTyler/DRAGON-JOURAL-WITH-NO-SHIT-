"""Offline regression coverage for provider exact-artifact routing.

These fixtures exercise the production normalizer, planner, scheduler, and
executor without invoking a provider or performing network retrieval.
"""

from __future__ import annotations

from pathlib import Path

from dragon.deep_research import build_deep_research_state, load_deep_research_config
from dragon.deep_research_executor import (
    FixtureResearchAdapter,
    execute_research_round,
    plan_research_actions,
    schedule_research_actions,
)
from dragon.providers import LocalCommandEditorialProvider
from dragon.source_intelligence import build_source_intelligence


ROOT = Path(__file__).resolve().parents[1]
DATE = "2099-12-30"
CONFIG = load_deep_research_config(ROOT / "config" / "deep-research.yaml")


def _source(identifier: str, url: str) -> dict:
    return {
        "id": identifier,
        "url": url,
        "publisher": "fixture.example",
        "publication_date": DATE,
        "accessed_at": f"{DATE}T07:00:00+00:00",
        "source_type": "official",
        "claim_supported": f"Provider-reported claim for {identifier}.",
        "doi": None,
        "publication_status": "news",
        "full_text_status": "NOT_APPLICABLE",
        "methods_read": False,
        "limitations_read": False,
        "science_metadata": None,
        "provider_lead_id": f"PROVIDER-LEAD-{identifier}",
        "provider_supplied_url": url,
        "lead_origin": "PROVIDER_EXACT",
    }


def _candidate(identifier: str, source_ids: list[str]) -> dict:
    return {
        "id": identifier,
        "rank": 1,
        "title": "Provider exact-document routing fixture",
        "discovery_source_ids": source_ids,
        "verification_source_ids": source_ids,
        "primary_evidence_source_ids": source_ids[:1],
        "independent_evidence_source_ids": [],
        "facts": ["Provider-reported discovery context only."],
        "claims": [],
        "unknowns": [],
        "disputed_points": [],
    }


def _packet(urls: list[str], *, selected: bool = True) -> dict:
    sources = [_source(f"s{index}", url) for index, url in enumerate(urls, 1)]
    selected_candidate = _candidate("selected", [source["id"] for source in sources])
    alternate = _candidate("alternate", [source["id"] for source in sources])
    return {
        "edition_date": DATE,
        "sources": sources,
        "sections": [{
            "section_id": "front", "status": "ACTIVE",
            "candidates": [selected_candidate, alternate],
            "selected_candidate_id": "selected" if selected else "alternate",
        }],
    }


def _job(urls: list[str], *, selected: bool = True) -> dict:
    state = build_deep_research_state(
        _packet(urls, selected=selected), {"event_clusters": []},
        {"plans": [{"section_id": "front", "research_budget": {"level": "normal"}}]},
        {"needs": []}, CONFIG, run_scope_id="provider-exact-routing-fixture",
    )
    return state["jobs"][0]


def _hard_candidate_state() -> dict:
    source = _source("s1", "https://fixture.example/accountability-report")
    candidate = _candidate("selected", [source["id"]])
    packet = {
        "edition_date": DATE,
        "sources": [source],
        "sections": [{
            "section_id": "investigations", "status": "ACTIVE",
            "candidates": [candidate, dict(candidate, id="alternate", rank=2)],
            "selected_candidate_id": "selected",
        }],
    }
    need = {
        "need_id": "BREADTH:accountability_and_service:1",
        "kind": "NEED_ACCOUNTABILITY_AND_SERVICE",
        "target_editorial_function": "ACCOUNTABILITY",
        "attempt_count": 0,
        "max_attempts": 1,
        "search_constraints": {"eligible_section_ids": ["investigations"]},
        "topic_identifiers": ["investigations"],
        "query_context": {},
        "event_acquisition_plan": {"target_editorial_function": "ACCOUNTABILITY"},
    }
    return build_deep_research_state(
        packet, {"event_clusters": []},
        {"plans": [{"section_id": "investigations", "research_budget": {"level": "investigation"}}]},
        {"needs": [need]}, CONFIG, run_scope_id="provider-exact-hard-fixture",
    )


def _exact_actions(job: dict) -> list[dict]:
    return [item for item in plan_research_actions(job, CONFIG) if item.get("lead_origin") == "PROVIDER_EXACT"]


def test_normalizer_assigns_immutable_provider_lead_identity_and_source_intelligence_preserves_it() -> None:
    raw = {
        "edition_date": DATE,
        "sources": [_source("normalizer", "https://fixture.example/exact?utm_source=test")],
        "sections": [],
    }
    # The normalizer rejects an incomplete editorial packet after source
    # normalization, so use its source-level result through a complete
    # no-news packet rather than trust a synthetic action fixture.
    from dragon.providers import SECTION_HEADINGS
    raw["sections"] = [{
        "section_id": section_id, "status": "NO_NEWS", "candidates": [],
        "selected_candidate_id": None, "selection_reason": None,
        "no_news_reason": "لا توجد مادة مكتملة الأدلة في حزمة الاختبار هذه.",
        "fallback_action": "DOSSIER_FOLLOW_UP",
    } for section_id, _heading in SECTION_HEADINGS]
    normalized = LocalCommandEditorialProvider(command=("fixture",)).normalize_research_packet(DATE, raw)
    source = normalized["sources"][0]
    assert source["provider_lead_id"].startswith("PROVIDER-LEAD-")
    assert source["provider_supplied_url"] == "https://fixture.example/exact?utm_source=test"
    assert source["lead_origin"] == "PROVIDER_EXACT"
    record = build_source_intelligence(normalized)["source_records"][0]
    assert record["provider_lead_id"] == source["provider_lead_id"]
    assert record["provider_supplied_url"] == source["provider_supplied_url"]


def test_selected_candidate_routes_safe_provider_url_to_fetch_before_generic_context() -> None:
    job = _job(["https://fixture.example/exact-document"])
    actions = plan_research_actions(job, CONFIG)
    assert actions[0]["action_type"] == "FETCH_URL"
    assert actions[0]["target"] == "https://fixture.example/exact-document"
    assert actions[0]["query_intent"] == "PROVIDER_EXACT_ARTIFACT"
    assert actions[0]["provider_candidate_id"] == "front:selected"
    assert actions[0]["provider_lead_id"] == "PROVIDER-LEAD-s1"
    assert next(item for item in actions if item["query_intent"] == "CONTEXT")["strategy_index"] > actions[0]["strategy_index"]


def test_unsafe_provider_url_is_retained_as_lead_but_not_materialized_as_fetch() -> None:
    job = _job(["http://127.0.0.1/private"])
    assert job["lead"]["discovery_source"]["exact_provider_sources"][0]["url"] == "http://127.0.0.1/private"
    assert not _exact_actions(job)


def test_unselected_provider_alternative_does_not_create_an_extra_job_or_fetch_budget() -> None:
    job = _job(["https://fixture.example/selected"], selected=True)
    state = build_deep_research_state(
        _packet(["https://fixture.example/selected"], selected=True), {"event_clusters": []},
        {"plans": [{"section_id": "front", "research_budget": {"level": "normal"}}]},
        {"needs": []}, CONFIG, run_scope_id="provider-exact-routing-fixture",
    )
    assert len(state["jobs"]) == 1
    assert _exact_actions(job)[0]["provider_candidate_id"] == "front:selected"


def test_multiple_equivalent_provider_urls_create_one_physical_exact_fetch() -> None:
    job = _job([
        "https://fixture.example/document?utm_source=one",
        "https://fixture.example/document",
    ])
    exact = _exact_actions(job)
    assert len(exact) == 1
    assert exact[0]["target"] == "https://fixture.example/document?utm_source=one"


def test_seen_equivalent_url_is_not_planned_again() -> None:
    job = _job(["https://fixture.example/document?utm_source=one"])
    job["executor_state"] = {"seen_urls": ["https://fixture.example/document"], "seen_origins": []}
    assert not _exact_actions(job)


def test_exact_provider_actions_remain_subject_to_fixed_round_cap_and_global_fairness() -> None:
    job = _job([f"https://fixture.example/document-{index}" for index in range(12)])
    schedule = schedule_research_actions([job], CONFIG)
    assert len(schedule["actions"]) == CONFIG["executor"]["maximum_actions_per_round"]
    assert len(schedule["deferred_actions"]) > 0
    deferred = next(item for item in schedule["deferred_actions"] if item.get("lead_origin") == "PROVIDER_EXACT")
    assert deferred["deferred_reason"] == "ROUND_BUDGET_PRIORITY_AND_FAIRNESS"
    assert deferred["provider_lead_id"] and deferred["target"].startswith("https://fixture.example/")
    assert schedule["budget_allocation"]["budget_increased"] is False


def test_selected_provider_exact_route_for_unresolved_hard_lane_gets_hard_opportunity() -> None:
    state = _hard_candidate_state()
    candidate_job = next(job for job in state["jobs"] if not job.get("recovery_needs"))
    exact = next(item for item in plan_research_actions(candidate_job, CONFIG) if item.get("lead_origin") == "PROVIDER_EXACT")

    assert exact["target_editorial_function"] == "ACCOUNTABILITY"
    assert exact["research_lane"] == "HARD:ACCOUNTABILITY"
    assert exact["priority_class"] == "P1_BREADTH"
    assert exact["hard_deficit"] == {
        "need_id": "BREADTH:accountability_and_service:1",
        "target_editorial_function": "ACCOUNTABILITY",
    }

    schedule = schedule_research_actions(state["jobs"], CONFIG)
    assert exact["action_id"] in {item["action_id"] for item in schedule["actions"]}
    assert schedule["budget_allocation"]["budget_increased"] is False


def test_exact_fetch_directness_does_not_grant_primary_evidence_or_bypass_qualification() -> None:
    job = _job(["https://fixture.example/exact-document"])
    action = _exact_actions(job)[0]
    result = execute_research_round(job, FixtureResearchAdapter({action["action_id"]: [{
        "url": "https://fixture.example/exact-document", "title": "Unresolved fixture page",
        "source_class": "unknown", "claim": "A direct fetch is still unverified.",
        "published_at": DATE, "retrieved_at": f"{DATE}T08:00:00Z", "content_hash": "a" * 64,
    }]}), CONFIG, actions=[action])
    observation = result["observations"][0]
    assert observation["provenance"]["provider_lead_id"] == action["provider_lead_id"]
    assert observation["verification_status"] != "VALIDATED_EVIDENCE"
    assert not result["source_packet_patch"]["sources"]


def test_redirect_or_canonical_outcome_retains_original_provider_lineage() -> None:
    job = _job(["https://fixture.example/original"])
    action = _exact_actions(job)[0]
    result = execute_research_round(job, FixtureResearchAdapter({action["action_id"]: [{
        "url": "https://fixture.example/final", "final_url": "https://fixture.example/final",
        "title": "Redirect fixture", "source_class": "unknown", "claim": "Redirected fixture.",
        "published_at": DATE, "retrieved_at": f"{DATE}T08:00:00Z", "content_hash": "b" * 64,
    }]}), CONFIG, actions=[action])
    provenance = result["observations"][0]["provenance"]
    assert provenance["provider_supplied_url"] == "https://fixture.example/original"
    assert provenance["final_url"] == "https://fixture.example/final"
    assert provenance["lead_origin"] == "PROVIDER_EXACT"


def test_qualified_source_patch_preserves_provider_ancestry_without_changing_its_role() -> None:
    job = _job(["https://fixture.example/exact-document"])
    action = _exact_actions(job)[0]
    result = execute_research_round(job, FixtureResearchAdapter({action["action_id"]: [{
        "url": "https://fixture.example/exact-document", "title": "Fixture official notice",
        "source_class": "official", "claim": "The authority issued a fixture notice.",
        "published_at": DATE, "retrieved_at": f"{DATE}T08:00:00Z", "content_hash": "c" * 64,
        "verification_provenance": "FIXTURE_VERIFIED_EXACT_PAGE",
    }]}), CONFIG, actions=[action])
    patches = result["source_packet_patch"]["sources"]
    assert patches and patches[0]["provenance"]["provider_lead_id"] == action["provider_lead_id"]
    assert patches[0]["source_type"] == "official"


def test_provider_lineage_is_not_added_to_deterministic_generic_discovery() -> None:
    job = _job([])
    action = plan_research_actions(job, CONFIG)[0]
    assert action["lead_origin"] == "DETERMINISTIC_DISCOVERY"
    assert action["provider_lead_id"] is None
