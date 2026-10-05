"""Event/claim-centric alternative-recovery tests; no network/provider calls."""

from __future__ import annotations

import json
from pathlib import Path
import sys
from urllib.parse import parse_qs, urlsplit

from dragon.deep_research import create_lead, load_deep_research_config, start_research_job
from dragon.deep_research_executor import (
    DiscoveryAdapterChain,
    FixtureResearchAdapter,
    GdeltDocSearchAdapter,
    _observation,
    event_fingerprint,
    gdelt_doc_adapter_from_config,
    publisher_discovery_states_from_config,
    execute_research_round,
    plan_research_actions,
    query_ladder,
    select_leads_for_followup,
    _lead_priority,
)
from dragon.discovery import FetchResponse


ROOT = Path(__file__).resolve().parents[1]
CONFIG = load_deep_research_config(ROOT / "config" / "deep-research.yaml")


def _need() -> dict:
    return {
        "need_id": "independent", "candidate_id": "weak-sport", "kind": "FIND_INDEPENDENT_CORROBORATION",
        "max_attempts": 2, "missing_evidence_role": "INDEPENDENT", "topic_identifiers": ["Meknes stadium audit"],
        "query_context": {"entities": ["Meknes"], "geography": ["Morocco"], "event_terms": ["stadium audit"], "research_date": "2026-09-11"},
        "search_constraints": {"configured_source_routes": [{"role": "INDEPENDENT", "origin": "blocked.example", "url": "https://blocked.example/latest"}]},
    }


def _job() -> dict:
    return start_research_job(
        create_lead(desk="sport", topic="Meknes stadium audit", event_entities=["Meknes"],
                    discovery_source={"url": "https://seed.example/a"}, observed_at="2026-09-11", reason_interesting="fixture"),
        CONFIG, budget_class="STANDARD", recovery_needs=[_need()], run_scope_id="fixture-run",
    )


def test_failed_route_is_scoped_to_event_and_next_ladder_seeks_alternative_origin() -> None:
    job = _job()
    configured = next(action for action in plan_research_actions(job, CONFIG) if action["action_type"] == "FETCH_CONFIGURED_SOURCE")
    execution = execute_research_round(job, FixtureResearchAdapter({configured["action_id"]: [{"result_type": "DEAD_END", "reason": "HTTP_403"}]}), CONFIG, actions=[configured])
    remembered = execution["job"]["executor_state"]["route_memory"]
    assert remembered[0]["state"] == "CURRENTLY_UNUSABLE"
    assert remembered[0]["event_fingerprint"] == event_fingerprint(job, _need())
    # A later bounded strategy is a fresh job for the same unmet role; route
    # memory is deliberately carried into that job rather than reusing a
    # completed branch from the first bounded round.
    followup_job = _job()
    followup_job["executor_state"] = execution["job"]["executor_state"]
    next_actions = plan_research_actions(followup_job, CONFIG)
    assert all(action.get("target") != "https://blocked.example/latest" for action in next_actions)
    alternative = next(action for action in next_actions if action["query_intent"] == "FIND_ALTERNATIVE_COVERAGE")
    assert "blocked.example" in alternative["excluded_origins"]
    assert alternative["event_fingerprint"] == remembered[0]["event_fingerprint"]


def test_gdelt_is_date_bounded_discovery_only_and_requires_exact_page_validation() -> None:
    seen: list[str] = []
    adapter = GdeltDocSearchAdapter(
        adapter_id="gdelt-doc", base_url="https://api.gdeltproject.org/api/v2/doc/doc",
        timeout_seconds=3, maximum_bytes=100_000, maximum_results=2,
        transport=lambda url, *_: (seen.append(url) or FetchResponse(url, 200, "application/json", json.dumps({"articles": [{"url": "https://alternate.example/report", "title": "Meknes audit"}]}).encode())),
    )
    action = next(item for item in plan_research_actions(_job(), CONFIG) if item["discovery_channel"] == "GDELT_DOC")
    raw = adapter.execute(action)[0]
    params = parse_qs(urlsplit(seen[0]).query)
    assert params["startdatetime"] == ["20260911000000"]
    assert params["enddatetime"] == ["20260911235959"]
    observation = _observation(action, raw, set())
    assert observation["observation_class"] == "LEAD"
    assert observation["publication_evidence"] is False
    assert observation["validation_state"] == "DISCOVERED"


def test_gdelt_config_is_optional_and_does_not_replace_other_channels(tmp_path: Path) -> None:
    path = tmp_path / "gdelt.yaml"
    path.write_text((ROOT / "config" / "gdelt-discovery.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    gdelt = gdelt_doc_adapter_from_config(path)
    assert gdelt is not None
    chain = DiscoveryAdapterChain([gdelt])
    assert chain.execute({"action_type": "SEARCH_DISCOVERY", "discovery_backends": ["other"], "discovery_channel": "OTHER"})[0]["reason"] == "SEARCH_BACKEND_UNAVAILABLE"


def test_publisher_feed_sitemap_and_media_cloud_states_are_explicit_and_non_evidence() -> None:
    states = publisher_discovery_states_from_config(ROOT / "config" / "publisher-discovery.yaml")
    assert states["publisher_owned_rss_atom"]["status"] == "ADAPTER_READY_NO_CONFIGURED_FEEDS"
    assert states["publisher_owned_sitemaps"]["status"] == "ADAPTER_READY_NO_CONFIGURED_SITEMAPS"
    assert states["media_cloud"]["status"] == "ADAPTER_READY_AUTH_NOT_CONFIGURED"
    assert all(item.get("discovery_only", True) for name, item in states.items() if name != "media_cloud")


def test_failed_family_leads_are_rejected_before_exact_page_followup() -> None:
    job = _job()
    job["executor_state"] = {"seen_urls": [], "seen_origins": [], "route_memory": [{
        "event_fingerprint": event_fingerprint(job, _need()), "origin": "blocked.example",
        "origin_family": "blocked.example", "state": "CURRENTLY_UNUSABLE",
    }]}
    action = next(item for item in plan_research_actions(job, CONFIG) if item["query_intent"] == "FIND_ALTERNATIVE_COVERAGE")
    observation = _observation(action, {"result_type": "LEAD", "url": "https://news.blocked.example/a", "title": "Meknes audit"}, set())
    assert observation["observation_class"] == "DUPLICATE"
    assert observation["publication_evidence"] is False


def test_known_event_fingerprint_is_rejected_before_breadth_promotion() -> None:
    job = _job()
    action = plan_research_actions(job, CONFIG)[0]
    action["provenance_requirements"]["must_be_distinct_event"] = True
    action["known_event_fingerprints"] = [{"event_id": "known", "fingerprint": "Meknes stadium audit public procurement"}]
    observation = _observation(action, {"result_type": "LEAD", "url": "https://new.example/repeat", "title": "Meknes stadium audit public procurement update"}, set())
    assert observation["observation_class"] == "DUPLICATE"
    assert observation["publication_evidence"] is False


def test_breadth_event_plan_uses_theme_date_and_rotating_eligible_desk() -> None:
    need = {
        "need_id": "BREADTH:NEED_DISTINCT_EVENT:2", "kind": "NEED_DISTINCT_EVENT", "max_attempts": 1,
        # This deliberately resembles a provider headline.  It must not be
        # copied into the acquisition query.
        "topic_identifiers": ["Provider phrasing that must not drive search"],
        "query_context": {"research_date": "2026-09-11"},
        "search_constraints": {"must_be_distinct_event": True, "eligible_section_ids": ["africa_sahel", "culture", "service"]},
        "event_acquisition_plan": {
            "editorial_gap": "DISTINCT_EVENT_BREADTH",
            "candidate_event_themes": ["institutional action", "geographically distinct development"],
            "query_families": ["institutional", "topical", "geographical"],
            "excluded_event_fingerprints": [{"event_id": "known", "fingerprint": "old event"}],
        },
    }
    ladder = query_ladder(_job(), need)
    assert ladder[0]["variant"] == "EVENT_THEME_DATE"
    assert ladder[0]["target_desk"] == "culture"
    assert ladder[0]["candidate_event_theme"] == "geographically distinct development"
    assert "2026-09" in ladder[0]["query"]
    assert "Provider phrasing" not in ladder[0]["query"]
    job = _job()
    job["recovery_needs"] = [need]
    action = plan_research_actions(job, CONFIG)[0]
    assert action["desk"] == "culture"
    assert action["known_event_fingerprints"][0]["event_id"] == "known"


def test_function_breadth_queries_are_diversified_and_do_not_search_desk_names() -> None:
    base = {
        "kind": "NEED_ACCOUNTABILITY_AND_SERVICE", "max_attempts": 1,
        "query_context": {"research_date": "2026-09-11"},
        "search_constraints": {"must_be_distinct_event": True, "eligible_section_ids": ["investigations", "service"]},
    }
    accountability = {
        **base, "need_id": "BREADTH:accountability_and_service:1",
        "target_editorial_function": "ACCOUNTABILITY",
        "event_acquisition_plan": {"target_editorial_function": "ACCOUNTABILITY"},
    }
    service = {
        **base, "need_id": "BREADTH:accountability_and_service:2",
        "target_editorial_function": "SERVICE",
        "event_acquisition_plan": {"target_editorial_function": "SERVICE"},
    }
    accountability_ladder = query_ladder(_job(), accountability)
    service_ladder = query_ladder(_job(), service)
    assert accountability_ladder[0]["target_desk"] == "investigations"
    assert service_ladder[0]["target_desk"] == "service"
    assert accountability_ladder[0]["query"] != service_ladder[0]["query"]
    assert any(term in accountability_ladder[0]["query"] for term in ("audit", "افتحاص", "رقابة"))
    assert any(term in service_ladder[0]["query"] for term in ("registration", "تسجيل", "أجل"))
    assert all("investigations" not in item["query"].casefold() for item in accountability_ladder)
    assert all("service" not in item["query"].casefold() for item in service_ladder)


def test_morocco_function_ladder_carries_arabic_and_french_routes() -> None:
    need = {
        "need_id": "BREADTH:accountability_and_service:2", "kind": "NEED_ACCOUNTABILITY_AND_SERVICE",
        "max_attempts": 1, "target_editorial_function": "SERVICE",
        "query_context": {"research_date": "2026-09-11"},
        "search_constraints": {"eligible_section_ids": ["service"]},
        "event_acquisition_plan": {"target_editorial_function": "SERVICE"},
    }
    ladder = query_ladder(_job(), need)
    assert any(item.get("language") == "ar" and "تسجيل" in item["query"] for item in ladder)
    assert any(item.get("language") == "fr" and "inscription" in item["query"] for item in ladder)


def test_function_route_uses_canonical_institution_navigation_as_discovery_only() -> None:
    need = {
        "need_id": "BREADTH:accountability_and_service:1", "kind": "NEED_ACCOUNTABILITY_AND_SERVICE", "max_attempts": 1,
        "target_editorial_function": "ACCOUNTABILITY", "query_context": {"research_date": "2026-09-11"},
        "search_constraints": {"eligible_section_ids": ["investigations"], "configured_source_routes": [
            {"name": "Audit Institution", "origin": "audit.gov.ma", "url": "https://audit.gov.ma/notices", "role": "PRIMARY", "authority_class": "AUDIT_INSTITUTION"},
            {"name": "Generic Ministry", "origin": "ministry.gov.ma", "url": "https://ministry.gov.ma/", "role": "PRIMARY", "authority_class": "PRIMARY_ORIGINAL"},
        ]},
        "event_acquisition_plan": {"target_editorial_function": "ACCOUNTABILITY"},
    }
    ladder = query_ladder(_job(), need)
    canonical = next(item for item in ladder if item["variant"] == "CANONICAL_NAVIGATION")
    assert canonical["action_type"] == "FETCH_CONFIGURED_SOURCE"
    assert canonical["target"] == "https://audit.gov.ma/notices"
    assert canonical["discovery_only"] is True


def test_canonical_listing_page_never_becomes_evidence_by_itself() -> None:
    action = plan_research_actions(_job(), CONFIG)[0]
    action.update({"action_type": "FETCH_URL", "discovery_only": True, "target": "https://official.example/page"})
    observation = _observation(action, {
        "verification_provenance": "FIXTURE_VERIFIED_EXACT_PAGE", "url": action["target"],
        "title": "Current notices", "source_class": "official", "text": "A listing of current notices.",
    }, set())
    assert observation["observation_class"] == "LEAD"
    assert observation["verification_status"] == "EXTRACTED_NOT_VERIFIED"
    assert observation["validation_state"] == "DISCOVERY_ONLY_INDEX"


def test_institutional_source_class_match_raises_fetch_priority_without_upgrading_evidence() -> None:
    action = {"target_editorial_function": "SERVICE", "query": "تسجيل آخر أجل", "event_context": {}}
    priority, reasons, _ = _lead_priority({
        "url": "https://www.elections.gov.ma/notices", "title": "وزارة الداخلية تحدد آخر أجل للتسجيل",
        "search_result": {"rank": 7, "snippet": "إعلان رسمي"},
    }, action)
    assert priority == "HIGH"
    assert "SEMANTIC_SOURCE_CLASS_MATCH" in reasons


def test_bounded_followup_inspects_both_missing_semantic_functions() -> None:
    actions = {
        "a": {"action_id": "a", "question_id": "qa", "action_type": "SEARCH_DISCOVERY", "priority_class": "P1_BREADTH", "recovery_need_id": "need-a", "target_editorial_function": "ACCOUNTABILITY", "excluded_origins": [], "excluded_origin_families": []},
        "s": {"action_id": "s", "question_id": "qs", "action_type": "SEARCH_DISCOVERY", "priority_class": "P1_BREADTH", "recovery_need_id": "need-s", "target_editorial_function": "SERVICE", "excluded_origins": [], "excluded_origin_families": []},
    }
    observations = [
        {"observation_class": "LEAD", "url": "https://audit.example/finding", "title": "Audit authority finding", "search_result": {"rank": 1, "snippet": "public audit"}, "provenance": {"action_id": "a"}},
        {"observation_class": "LEAD", "url": "https://agency.example/deadline", "title": "Registration deadline", "search_result": {"rank": 1, "snippet": "official registration deadline"}, "provenance": {"action_id": "s"}},
    ]
    selected = select_leads_for_followup(observations, actions, {"total": 2, "P1_BREADTH": 1})
    assert {item["_followup_need"] for item in selected} == {"need-a", "need-s"}


def test_validated_page_without_discernible_event_cannot_propose_breadth_candidate() -> None:
    need = {
        "need_id": "BREADTH:NEED_DISTINCT_EVENT:1", "kind": "NEED_DISTINCT_EVENT", "max_attempts": 1,
        "query_context": {"research_date": "2026-09-11"},
        "search_constraints": {"must_be_distinct_event": True, "eligible_section_ids": ["front"]},
        "event_acquisition_plan": {"editorial_gap": "DISTINCT_EVENT_BREADTH", "candidate_event_themes": ["institutional action"]},
    }
    job = _job()
    job["recovery_needs"] = [need]
    action = plan_research_actions(job, CONFIG)[0]
    action.update({"action_type": "FETCH_URL", "target": "https://official.example/page", "expected_result_type": "EXTRACTED_SOURCE"})
    raw = {
        "url": action["target"], "canonical_url": action["target"], "title": "", "claim": "",
        "text": "The official institution published a detailed public service notice with enough extracted text for validation.",
        "fetch_status": "FETCHED", "content_hash": "a" * 64, "source_class": "official",
        "published_at": "2026-09-11", "retrieved_at": "2026-09-11T08:00:00Z",
    }
    execution = execute_research_round(job, FixtureResearchAdapter({action["action_id"]: [raw]}), CONFIG, actions=[action])
    observation = execution["observations"][0]
    assert observation["verification_status"] == "VALIDATED_EVIDENCE"
    assert observation["event_proposal_rejection"] == "NO_DISCERNIBLE_EVENT"
    assert execution["source_packet_patch"]["candidate_discoveries"] == []


def test_replay_cli_accepts_relative_output_path_after_completed_rehearsal(monkeypatch, capsys) -> None:
    import dragon_recovery_replay

    monkeypatch.setattr(dragon_recovery_replay, "rehearse_preserved_run_with_discovery", lambda **_: {
        "status": "PRESERVED_REAL_DISCOVERY_REHEARSAL_COMPLETE", "remaining_recovery_needs": [],
    })
    monkeypatch.setattr(sys, "argv", ["dragon_recovery_replay.py", "--date", "2026-09-12", "--run-id", "fixture", "--real-discovery", "--output", "acceptance/fixture-relative-output"])
    assert dragon_recovery_replay.main() == 0
    assert "acceptance/fixture-relative-output" in capsys.readouterr().out


def test_replay_resolves_preserved_rehearsal_attempt_to_immutable_packet_id() -> None:
    from dragon_recovery_replay import provider_attempt_storage_id

    assert provider_attempt_storage_id("preserved-rehearsal:attempt-cc590") == "attempt-cc590"
    assert provider_attempt_storage_id("attempt-cc590") == "attempt-cc590"
