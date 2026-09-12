"""Deterministic claim-aware exact-page promotion acceptance tests."""

from __future__ import annotations

import json
from pathlib import Path

from dragon.deep_research import create_lead, load_deep_research_config, start_research_job
from dragon.deep_research_executor import (
    DiscoveryAdapterChain,
    FixtureResearchAdapter,
    SearxngSearchAdapter,
    apply_executor_results_to_packet,
    create_research_action,
    execute_research_round,
)
from dragon.discovery import FetchResponse
from dragon.research_recovery import build_recovery_plan
from dragon.source_intelligence import build_source_intelligence


ROOT = Path(__file__).resolve().parents[1]
CONFIG = load_deep_research_config(ROOT / "config" / "deep-research.yaml")


def _job(need: dict | None = None):
    lead = create_lead(
        desk="front", topic="Meknes audit procurement",
        discovery_source={"url": "https://signal.example/meknes", "known_seed": False},
        observed_at="2099-01-02T07:00:00Z", reason_interesting="promotion fixture",
        geography=["Meknes"],
    )
    lead["event_entities"] = ["Meknes", "audit"]
    return start_research_job(lead, CONFIG, budget_class="STANDARD", recovery_needs=[need] if need else [])


def _page(source_class="official", **extra):
    return {
        "url": "https://audit.example/reports/meknes-audit",
        "canonical_url": "https://audit.example/reports/meknes-audit",
        "title": "Meknes audit procurement report",
        "text": "Meknes audit report describes public procurement findings and publication details in a direct official statement.",
        "fetch_status": "FETCHED", "content_hash": "a" * 64,
        "source_class": source_class, "published_at": "2099-01-02",
        "retrieved_at": "2099-01-02T08:00:00Z", "claim": "The audit institution published a Meknes procurement report.",
        **extra,
    }


def test_configured_official_exact_page_promotes_claim_aware_evidence() -> None:
    adapter = FixtureResearchAdapter({"FETCH_URL": [_page()]})
    action = {
        "job_id": _job()["job_id"], "branch_id": _job()["branches"][0]["branch_id"],
        "question_id": _job()["branches"][0]["question_ids"][0], "action_id": "ACT-PAGE",
        "desk": "front", "research_regime": "GENERAL", "action_type": "FETCH_URL",
        "target": "https://audit.example/reports/meknes-audit", "query": "Meknes audit",
        "query_intent": "TEST", "query_variant": "EXACT", "query_fingerprint": "TEST:meknes audit",
        "priority_class": "P0_BLOCKING_EVIDENCE", "discovery_channel": "fixture",
        "known_entities": ["Meknes", "audit"], "known_event_ids": [], "already_seen_urls": [], "already_seen_origins": [],
        "budget": {"class": "STANDARD", "round": 0, "max_rounds": 2}, "timeout_seconds": 10,
        "expected_result_type": "EXTRACTED_SOURCE", "recovery_need_id": "need", "recovery_candidate_id": "candidate",
        "provenance_requirements": {"required_role": "PRIMARY", "must_be_distinct_event": False, "science_strict": False},
        "event_context": {"entities": ["Meknes"], "event_terms": ["audit", "procurement"], "aliases": [], "topic_terms": [], "geography": ["Meknes"]},
        "channel_fallback": None,
    }
    job = _job()
    action.update(job_id=job["job_id"], branch_id=job["branches"][0]["branch_id"], question_id=job["branches"][0]["question_ids"][0])
    outcome = execute_research_round(job, adapter, CONFIG, actions=[action])
    observation = outcome["observations"][0]
    assert observation["verification_status"] == "VALIDATED_EVIDENCE"
    assert observation["validation_state"] == "VALIDATED_EVIDENCE"
    assert observation["evidence_relation"] == "SUPPORTS"
    assert outcome["source_packet_patch"]["sources"]


def test_unknown_wrong_event_context_and_contradiction_are_explicit() -> None:
    job = _job()
    base = {
        "job_id": job["job_id"], "branch_id": job["branches"][0]["branch_id"], "question_id": job["branches"][0]["question_ids"][0],
        "desk": "front", "research_regime": "GENERAL", "action_type": "FETCH_URL", "target": "https://example.test/page",
        "query": "Meknes audit", "query_intent": "TEST", "query_variant": "EXACT", "query_fingerprint": "T", "priority_class": "P0_BLOCKING_EVIDENCE",
        "discovery_channel": "fixture", "known_entities": ["Meknes"], "known_event_ids": [], "already_seen_urls": [], "already_seen_origins": [],
        "budget": {"class": "STANDARD", "round": 0, "max_rounds": 2}, "timeout_seconds": 10, "expected_result_type": "EXTRACTED_SOURCE",
        "recovery_need_id": None, "recovery_candidate_id": None, "provenance_requirements": {"required_role": None, "must_be_distinct_event": False, "science_strict": False},
        "event_context": {"entities": ["Meknes"], "aliases": [], "event_terms": ["audit"], "topic_terms": [], "geography": []}, "channel_fallback": None,
    }
    pages = [_page("unknown"), _page(text="A different Casablanca cultural event has no overlap.", title="Casablanca event", claim="A different cultural event."), _page(context_only=True), _page(contradicts=True)]
    states, classes = [], []
    for index, page in enumerate(pages):
        action = {**base, "action_id": f"ACT-{index}"}
        result = execute_research_round(job, FixtureResearchAdapter({"FETCH_URL": [page]}), CONFIG, actions=[action])
        states.append(result["observations"][0]["validation_state"])
        classes.append(result["observations"][0]["observation_class"])
    assert states == ["SOURCE_UNKNOWN", "WRONG_EVENT", "CONTEXT_ONLY", "VALIDATED_EVIDENCE"]
    assert classes == ["LEAD", "IRRELEVANT", "CONTEXT", "CONTRADICTION"]


def test_searxng_normalizes_json_and_unavailable_endpoint_is_bounded() -> None:
    adapter = SearxngSearchAdapter(
        adapter_id="searx-fixture", base_url="https://search.example", timeout_seconds=3,
        maximum_bytes=100_000, maximum_results=2, language="fr", categories="general",
        transport=lambda url, timeout, maximum: FetchResponse(url, 200, "application/json", json.dumps({"results": [{"url": "https://news.example/item", "title": "Result", "content": "Snippet", "engine": "bing"}]}).encode()),
    )
    result = adapter.execute({"action_type": "SEARCH_DISCOVERY", "query": "Meknes audit"})[0]
    assert result["verification_provenance"] == "DISCOVERY_ONLY_SEARXNG"
    assert result["search_result"]["backend"] == "searx-fixture"
    unavailable = SearxngSearchAdapter(
        adapter_id="searx-fixture", base_url="https://search.example", timeout_seconds=3,
        maximum_bytes=100_000, maximum_results=2,
        transport=lambda *_: (_ for _ in ()).throw(TimeoutError()),
    ).execute({"action_type": "SEARCH_DISCOVERY", "query": "x"})
    assert unavailable[0]["reason"] == "SEARCH_BACKEND_UNAVAILABLE"


def test_multiple_discovery_backends_deduplicate_before_exact_page_followup() -> None:
    class Backend:
        follow_discovery_leads = True
        def __init__(self, url: str) -> None:
            self.url = url
        def execute(self, action):
            return [{"result_type": "LEAD", "url": self.url, "canonical_url": self.url, "title": "same"}]
    results = DiscoveryAdapterChain([Backend("https://news.example/item?utm_source=x"), Backend("https://news.example/item")]).execute({"action_type": "SEARCH_DISCOVERY"})
    assert len(results) == 1


def test_exact_independent_page_closes_candidate_corroboration_without_fixture_override() -> None:
    need = {
        "need_id": "independent", "candidate_id": "candidate", "kind": "FIND_INDEPENDENT_CORROBORATION", "max_attempts": 1,
        "missing_evidence_role": "INDEPENDENT", "topic_identifiers": ["Meknes", "audit"],
        "query_context": {"entities": ["Meknes"], "event_terms": ["audit"], "aliases": [], "geography": ["Meknes"], "research_date": "2099-01-02"},
    }
    job = _job(need)
    action = create_research_action(job, job["branches"][0], recovery_need=need)
    adapter = FixtureResearchAdapter({
        "RECOVER_INDEPENDENT_SOURCE": [{"result_type": "LEAD", "url": "https://news.example/meknes-audit", "title": "Meknes audit", "source_class": "unknown"}],
        "FETCH_URL": [{**_page("independent"), "url": "https://news.example/meknes-audit", "canonical_url": "https://news.example/meknes-audit"}],
    })
    adapter.follow_discovery_leads = True
    execution = execute_research_round(job, adapter, CONFIG, actions=[action])
    assert execution["source_packet_patch"]["candidate_evidence_updates"]
    packet = {
        "edition_date": "2099-01-02",
        "sources": [{"id": "primary", "url": "https://official.example/meknes", "publisher": "official", "source_type": "official", "claim_supported": "Official Meknes audit."}],
        "sections": [{"section_id": "front", "status": "ACTIVE", "selected_candidate_id": "candidate", "candidates": [{
            "id": "candidate", "rank": 1, "title": "Meknes audit", "facts": [], "claims": [], "unknowns": [], "disputed_points": [],
            "discovery_source_ids": ["primary"], "verification_source_ids": ["primary"], "primary_evidence_source_ids": ["primary"], "independent_evidence_source_ids": [],
        }]}],
    }
    recovered = apply_executor_results_to_packet(packet, execution)
    candidate = recovered["sections"][0]["candidates"][0]
    assert candidate["evidence_eligibility"]["status"] == "ELIGIBLE"
    assert candidate["independent_evidence_source_ids"]


def test_distinct_event_requires_new_event_and_two_validated_roles() -> None:
    job = _job()
    branch = job["branches"][0]
    base = {
        "job_id": job["job_id"], "branch_id": branch["branch_id"], "question_id": branch["question_ids"][0], "desk": "front",
        "research_regime": "GENERAL", "action_type": "FETCH_URL", "query": "Meknes audit", "query_intent": "DISTINCT", "query_variant": "EXACT",
        "query_fingerprint": "DISTINCT", "priority_class": "P1_DISTINCT_EVENT", "discovery_channel": "fixture", "known_entities": ["Meknes"],
        "known_event_ids": ["EVT-OLD"], "already_seen_urls": [], "already_seen_origins": [], "budget": {"class": "STANDARD", "round": 0, "max_rounds": 2},
        "timeout_seconds": 10, "expected_result_type": "EXTRACTED_SOURCE", "recovery_need_id": "distinct", "recovery_candidate_id": None,
        "provenance_requirements": {"required_role": None, "must_be_distinct_event": True, "science_strict": False},
        "event_context": {"entities": ["Meknes"], "aliases": [], "event_terms": ["audit"], "topic_terms": [], "geography": []}, "channel_fallback": None,
    }
    actions = [{**base, "action_id": "ACT-OFFICIAL", "target": "https://official.example/new", "query_fingerprint": "DISTINCT:official"}, {**base, "action_id": "ACT-NEWS", "target": "https://news.example/new", "query_fingerprint": "DISTINCT:news"}]
    adapter = FixtureResearchAdapter({
        "ACT-OFFICIAL": [{**_page("official"), "url": "https://official.example/new", "canonical_url": "https://official.example/new", "event_id": "EVT-NEW"}],
        "ACT-NEWS": [{**_page("independent"), "url": "https://news.example/new", "canonical_url": "https://news.example/new", "event_id": "EVT-NEW"}],
    })
    execution = execute_research_round(job, adapter, CONFIG, actions=actions)
    packet = {"edition_date": "2099-01-02", "sources": [], "sections": [{"section_id": "front", "status": "NO_NEWS", "selected_candidate_id": None, "candidates": [], "recovery_candidates": []}]}
    recovered = apply_executor_results_to_packet(packet, execution)
    section = recovered["sections"][0]
    assert section["status"] == "ACTIVE"
    assert section["selected_candidate_id"]
    assert build_source_intelligence(recovered)["summary"]["event_count"] == 1
