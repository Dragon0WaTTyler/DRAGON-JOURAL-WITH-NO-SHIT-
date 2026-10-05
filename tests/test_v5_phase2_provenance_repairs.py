"""Offline regressions for bounded Phase 2 provenance repairs."""

from pathlib import Path

from dragon.deep_research import create_lead, load_deep_research_config, start_research_job
from dragon.deep_research_executor import (
    _provenance_followup_candidates,
    execute_research_round,
    resolve_exact_source_role,
)
from dragon.editorial_functions import classify_event_functions


CONFIG = load_deep_research_config(Path("config/deep-research.yaml"))


def _action(*, target="https://secondary.fixture/story", function="SERVICE", followups=0):
    lead = create_lead(
        desk="service", topic="offline provenance repair",
        discovery_source={"url": "https://signal.fixture/lead"},
        observed_at="2099-01-02T07:00:00Z", reason_interesting="fixture", geography=["Fixture"],
    )
    job = start_research_job(lead, CONFIG, budget_class="STANDARD")
    if followups:
        job["executor_state"] = {"lead_followups": followups, "search_actions": 0, "fetches": 0, "seen_urls": [], "seen_origins": [], "route_memory": []}
    branch = job["branches"][0]
    return job, {
        "job_id": job["job_id"], "branch_id": branch["branch_id"], "question_id": branch["question_ids"][0],
        "action_id": "PARENT", "desk": "service", "research_regime": "GENERAL_JOURNALISM",
        "action_type": "FETCH_URL", "target": target, "query": "Mouakaba transport service",
        "query_intent": "FIXTURE", "query_variant": "EXACT", "query_fingerprint": "PHASE2",
        "priority_class": "P1_BREADTH", "discovery_channel": "fixture", "known_entities": [],
        "known_event_ids": [], "already_seen_urls": [], "already_seen_origins": [],
        "budget": {"class": "STANDARD", "round": 0, "max_rounds": 2}, "timeout_seconds": 5,
        "expected_result_type": "EXTRACTED_SOURCE", "recovery_need_id": "service",
        "recovery_candidate_id": None, "recovery_mode": "DISCOVER_NEW_EVENT_FOR_SEMANTIC_NEED",
        "target_editorial_function": function, "candidate_event_theme": function,
        "provenance_requirements": {"required_role": None, "must_be_distinct_event": False, "science_strict": False},
        "event_context": {"entities": [], "aliases": [], "event_terms": ["transport", "service"], "topic_terms": [], "geography": ["Fixture"], "research_date": "2099-01-02"},
        "channel_fallback": None, "discovery_only": False, "navigation_depth": 0,
    }


def _court_route():
    return {
        "route_id": "court-news", "url": "https://www.courdescomptes.fixture/news", "origin": "www.courdescomptes.fixture",
        "role": "PRIMARY", "authority_class": "PRIMARY_ORIGINAL", "discovery_only": False,
        "publisher": "Court of Accounts", "name": "Court of Accounts",
    }


def _court_article(**overrides):
    value = {
        "url": "https://www.courdescomptes.fixture/news/participation", "title": "Court of Accounts participated in audit meeting",
        "text": "The Court of Accounts participated in the audit meeting on 2 January 2099. " * 6,
        "published_at": "2099-01-02", "fetch_status": "FETCHED",
        "article_metadata": {"publisher": {"name": "Court of Accounts", "canonical_domain": "www.courdescomptes.fixture"}, "jsonld_article_types": ["NewsArticle"]},
        "article_attribution": {"author_byline": "Institutional newsroom", "article_origin_state": "ORIGINAL_UNKNOWN"},
    }
    value.update(overrides)
    return value


def test_verified_bylined_institutional_self_attestation_is_primary_only_for_participation_claim():
    _, action = _action(function="ACCOUNTABILITY")
    action["source_route"] = _court_route()
    resolved = resolve_exact_source_role(
        _court_article(), action,
        {"state": "CONCRETE_EVENT", "actor": "Court of Accounts", "action": "participated"},
    )
    assert resolved["source_class"] == "primary"
    assert resolved["claim_scope"] == "NARROW_SELF_ATTESTED_EVENT"
    assert resolved["reason"] == "FIRST_PARTY_SELF_ATTESTATION_VERIFIED_DOMAIN_DIRECT_SELF_ACTION"
    functions = classify_event_functions(
        title="Participation of the Court of Accounts in the meeting of Supreme Audit Institutions",
        facts=["The Court of Accounts took part in the constitutive meeting hosted by the Accountability State Authority."],
        evidence_source_ids=["SRC-C"], exact_page_validated=True,
    )
    assert "ACCOUNTABILITY" not in {item["function"] for item in functions}


def test_bylined_secondary_or_wire_article_cannot_use_self_attestation_path():
    _, action = _action(function="ACCOUNTABILITY")
    action["source_route"] = _court_route()
    secondary = _court_article(url="https://independent.fixture/court", article_metadata={"publisher": {"name": "Independent", "canonical_domain": "independent.fixture"}, "jsonld_article_types": ["NewsArticle"]})
    assert resolve_exact_source_role(secondary, action, {"state": "CONCRETE_EVENT", "actor": "Court of Accounts", "action": "participated"})["source_class"] == "independent"
    wire = _court_article(article_attribution={"author_byline": "Desk", "article_origin_state": "WIRE_REPUBLICATION", "wire_credit": "MAP"})
    assert resolve_exact_source_role(wire, action, {"state": "CONCRETE_EVENT", "actor": "Court of Accounts", "action": "participated"})["source_class"] == "unknown"


def test_page_metadata_publisher_profile_alone_cannot_self_upgrade_a_newsroom():
    _, action = _action(function="ACCOUNTABILITY")
    raw = _court_article(
        url="https://newsroom.fixture/court-meeting",
        article_metadata={"publisher": {"name": "Newsroom", "canonical_domain": "newsroom.fixture"}, "jsonld_article_types": ["NewsArticle"]},
        publisher_profile={
            "canonical_domain": "newsroom.fixture", "canonical_publisher_name": "Newsroom",
            "identity_state": "PUBLISHER_PROFILE_RESOLVED", "identity_provenance": "PAGE_METADATA_ONLY",
        },
    )
    resolved = resolve_exact_source_role(raw, action, {"state": "CONCRETE_EVENT", "actor": "Court of Accounts", "action": "participated"})
    assert resolved["source_class"] == "independent"


def test_navigation_page_is_not_first_party_claim_specific_evidence():
    _, action = _action(function="ACCOUNTABILITY")
    action["source_route"] = _court_route()
    resolved = resolve_exact_source_role(
        _court_article(url="https://www.courdescomptes.fixture/", title="Court of Accounts", text="Court of Accounts participated in a meeting." * 6),
        action, {"state": "CONCRETE_EVENT", "actor": "Court of Accounts", "action": "participated"},
    )
    assert resolved["source_class"] != "primary"


def _future_parent(url="https://secondary.fixture/story", homepage="https://mouakaba.transport.gov.ma/"):
    return {
        "url": url, "canonical_url": url,
        "title": "Ministry of Transport launches Mouakaba service",
        "claim": "Ministry of Transport launches Mouakaba service",
        "text": "The Ministry of Transport and Logistics announced Mouakaba transport service. Applications begin 2099-01-04. " * 5,
        "links": [{"url": homepage, "text": "Mouakaba official platform"}],
        "published_at": "2099-01-01", "fetch_status": "FETCHED", "content_hash": "a" * 64,
        "source_class": "unknown", "publisher": "Secondary Fixture",
        "article_metadata": {"publisher": {"name": "Secondary Fixture", "canonical_domain": "secondary.fixture"}, "jsonld_article_types": ["NewsArticle"]},
        "article_attribution": {"author_byline": "Reporter", "article_origin_state": "ORIGINAL_UNKNOWN"},
    }


def test_issuer_matched_official_homepage_gets_one_bounded_followup_but_future_service_stays_ineligible():
    job, action = _action()

    class Adapter:
        follow_discovery_leads = False
        def __init__(self): self.targets = []
        def execute(self, value):
            self.targets.append(value.get("target"))
            if value.get("target") == action["target"]:
                return [_future_parent()]
            if value.get("target") == "https://mouakaba.transport.gov.ma/":
                return [{
                    "url": value["target"], "canonical_url": value["target"], "title": "Mouakaba platform",
                    "text": "Applications begin 2099-01-04.", "published_at": "2099-01-01", "fetch_status": "FETCHED",
                    "content_hash": "b" * 64, "source_class": "unknown", "publisher": "Mouakaba",
                }]
            return [{"result_type": "DEAD_END", "reason": "UNEXPECTED"}]

    adapter = Adapter()
    result = execute_research_round(job, adapter, CONFIG, actions=[action])
    assert adapter.targets.count("https://mouakaba.transport.gov.ma/") == 1
    assert result["budget_consumed"]["lead_followups"] == 1
    parent = next(item for item in result["observations"] if item["url"] == action["target"])
    assert parent["provenance_recovery_reason"] == "TARGETED_OFFICIAL_HOMEPAGE"
    assert not result["source_packet_patch"]["candidate_discoveries"]


def test_official_homepage_requires_page_observed_issuer_host_match_and_preserves_direct_priority():
    _, action = _action()
    raw = _future_parent()
    observation = {
        "official_link_candidates": [
            {"url": "https://mouakaba.transport.gov.ma/", "type": "INSTITUTIONAL_DETAIL", "reason": "OFFICIAL_HOMEPAGE_NAVIGATION_ONLY"},
            {"url": "https://mouakaba.transport.gov.ma/notices/current", "type": "OFFICIAL_DOCUMENT", "reason": "OFFICIAL_ARTIFACT_SIGNAL", "document_signal": True},
        ],
        "event_skeleton": {"state": "CONCRETE_EVENT"},
        "claim_support": {"support_type": "DIRECT_SUPPORT"},
        "temporal_relevance": {"temporal_eligibility_type": "FUTURE_EVENT", "effective_start": "2099-01-04", "active_on_edition_date": False},
        "stated_issuing_authority": "Ministry of Transport and Logistics", "document_references": [], "original_source_resolution": {},
    }
    selected = _provenance_followup_candidates(observation, raw, action, set())
    assert selected[0]["url"].endswith("/notices/current")
    mismatch = _future_parent(homepage="https://finance.gov.ma/")
    observation["official_link_candidates"] = [{"url": "https://finance.gov.ma/", "type": "INSTITUTIONAL_DETAIL", "reason": "OFFICIAL_HOMEPAGE_NAVIGATION_ONLY"}]
    assert _provenance_followup_candidates(observation, mismatch, action, set()) == []


def test_homepage_followup_deduplicates_and_budget_exhaustion_blocks_it():
    _, action = _action()
    raw = _future_parent()
    observation = {
        "official_link_candidates": [{"url": "https://mouakaba.transport.gov.ma/", "type": "INSTITUTIONAL_DETAIL", "reason": "OFFICIAL_HOMEPAGE_NAVIGATION_ONLY"}],
        "event_skeleton": {"state": "CONCRETE_EVENT"}, "claim_support": {"support_type": "DIRECT_SUPPORT"},
        "temporal_relevance": {"temporal_eligibility_type": "FUTURE_EVENT", "effective_start": "2099-01-04", "active_on_edition_date": False},
        "stated_issuing_authority": "Ministry of Transport and Logistics", "document_references": [], "original_source_resolution": {},
    }
    assert _provenance_followup_candidates(observation, raw, action, {"https://mouakaba.transport.gov.ma/"}) == []
    job, exhausted = _action(followups=CONFIG["executor"]["lead_followup_limits"]["STANDARD"]["total"])

    class Adapter:
        follow_discovery_leads = False
        def __init__(self): self.targets = []
        def execute(self, value):
            self.targets.append(value.get("target"))
            return [_future_parent(url=value["target"])]

    adapter = Adapter()
    result = execute_research_round(job, adapter, CONFIG, actions=[exhausted])
    assert adapter.targets == [exhausted["target"]]
    assert result["budget_consumed"]["lead_followups"] == CONFIG["executor"]["lead_followup_limits"]["STANDARD"]["total"]
