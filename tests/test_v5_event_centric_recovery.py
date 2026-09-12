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


def test_replay_cli_accepts_relative_output_path_after_completed_rehearsal(monkeypatch, capsys) -> None:
    import dragon_recovery_replay

    monkeypatch.setattr(dragon_recovery_replay, "rehearse_preserved_run_with_discovery", lambda **_: {
        "status": "PRESERVED_REAL_DISCOVERY_REHEARSAL_COMPLETE", "remaining_recovery_needs": [],
    })
    monkeypatch.setattr(sys, "argv", ["dragon_recovery_replay.py", "--date", "2026-09-12", "--run-id", "fixture", "--real-discovery", "--output", "acceptance/fixture-relative-output"])
    assert dragon_recovery_replay.main() == 0
    assert "acceptance/fixture-relative-output" in capsys.readouterr().out
