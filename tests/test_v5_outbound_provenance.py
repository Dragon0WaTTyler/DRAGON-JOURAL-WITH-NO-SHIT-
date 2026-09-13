from pathlib import Path

from dragon.deep_research import create_lead, load_deep_research_config, start_research_job
from dragon.deep_research_executor import execute_research_round
from dragon.institutional_navigation import (
    classify_outbound_link, detect_official_portal_republication,
    extract_actor_attributions, extract_outbound_link_candidates,
)


CONFIG = load_deep_research_config(Path("config/deep-research.yaml"))


def test_service_link_is_classified_without_becoming_evidence() -> None:
    item = classify_outbound_link(
        "https://recrutements.ma/story", "https://concours.dgsn.gov.ma/Pages/SuiviCandidature",
        label="official registration portal", context="official application registration",
        semantic_target="SERVICE",
    )
    assert item["type"] == "OFFICIAL_SERVICE_DESTINATION"
    assert item["official_looking"] is True
    assert item["cross_domain"] is True


def test_markdown_links_and_attribution_are_preserved_as_discovery_metadata() -> None:
    raw = {
        "url": "https://recrutements.ma/concours-dgsn-gov-ma",
        "title": "التسجيل في مباراة الأمن الوطني",
        "text": "وفق المديرية العامة للأمن الوطني، التسجيل عبر [المنصة الرسمية](https://concours.dgsn.gov.ma/Pages/SuiviCandidature)",
    }
    links = extract_outbound_link_candidates(raw, semantic_target="SERVICE")
    attrs = extract_actor_attributions(raw)
    assert links[0]["type"] == "OFFICIAL_SERVICE_DESTINATION"
    assert any(actor["name"] == "General Directorate of National Security" for actor in attrs["actors"])
    assert attrs["attribution_phrases"]


def test_homepage_link_is_navigation_only() -> None:
    item = classify_outbound_link(
        "https://news.example/story", "https://agency.gov.ma/", label="official portal",
        context="the authority website", semantic_target="ACCOUNTABILITY",
    )
    assert item["type"] == "INSTITUTIONAL_DETAIL"
    assert item["reason"] == "OFFICIAL_HOMEPAGE_NAVIGATION_ONLY"


def test_official_portal_republication_keeps_publisher_and_issuer_distinct() -> None:
    raw = {
        "url": "https://www.gov.ma/announcement",
        "publisher": "National Portal",
        "stated_issuing_institution": "Ministry of Interior",
        "title": "Official portal announcement",
        "text": "According to the Ministry of Interior, the procedure is open.",
    }
    detail = detect_official_portal_republication(raw)
    assert detail["article_origin_state"] == "OFFICIAL_PORTAL_REPUBLICATION"
    assert detail["portal_publisher"] == "National Portal"
    assert detail["issuing_institution"] == "Ministry of Interior"


def test_explicit_official_link_recovery_consumes_one_existing_followup_slot() -> None:
    lead = create_lead(
        desk="service", topic="registration deadline", discovery_source={"url": "https://signal.example/lead"},
        observed_at="2026-09-13T07:00:00Z", reason_interesting="fixture", geography=["Morocco"],
    )
    job = start_research_job(lead, CONFIG, budget_class="STANDARD")
    branch = job["branches"][0]
    action = {
        "job_id": job["job_id"], "branch_id": branch["branch_id"], "question_id": branch["question_ids"][0],
        "action_id": "SECONDARY-ACTION", "desk": "service", "research_regime": "GENERAL",
        "action_type": "FETCH_URL", "target": "https://recrutements.ma/story", "query": "registration",
        "query_intent": "FUNCTION_SERVICE_PRIMARY_WINDOW", "query_variant": "EXACT", "query_fingerprint": "SECONDARY",
        "priority_class": "P1_BREADTH", "discovery_channel": "fixture", "known_entities": ["DGSN", "registration"],
        "known_event_ids": [], "already_seen_urls": [], "already_seen_origins": [], "budget": {"class": "STANDARD"},
        "timeout_seconds": 5, "expected_result_type": "EXTRACTED_SOURCE", "recovery_need_id": "service",
        "recovery_candidate_id": None, "provenance_requirements": {"required_role": None, "must_be_distinct_event": False, "science_strict": False},
        "event_context": {"entities": ["DGSN"], "event_terms": ["registration"], "topic_terms": [], "aliases": [], "geography": ["Morocco"], "research_date": "2026-09-13"},
        "channel_fallback": None, "target_editorial_function": "SERVICE", "discovery_only": False, "navigation_depth": 0,
    }

    class Adapter:
        follow_discovery_leads = False
        def __init__(self): self.targets = []
        def execute(self, value):
            self.targets.append(value.get("target"))
            if value.get("target") == "https://recrutements.ma/story":
                return [{"url": value["target"], "canonical_url": value["target"], "title": "التسجيل في مباراة الأمن الوطني", "text": "وفق المديرية العامة للأمن الوطني، التسجيل مفتوح وآخر أجل 2026-09-22 عبر [المنصة الرسمية](https://concours.dgsn.gov.ma/Pages/SuiviCandidature). " * 3, "published_at": "2026-09-07", "fetch_status": "FETCHED", "content_hash": "a" * 64, "source_class": "unknown", "publisher": "Recruitments"}]
            return [{"url": value["target"], "canonical_url": value["target"], "title": "Official DGSN registration portal", "text": "The official service portal provides registration procedure and deadline 2026-09-22 for applicants in Morocco. " * 5, "published_at": "2026-09-07", "fetch_status": "FETCHED", "content_hash": "b" * 64, "source_class": "official", "publisher": "DGSN"}]

    adapter = Adapter()
    result = execute_research_round(job, adapter, CONFIG, actions=[action])
    assert "https://concours.dgsn.gov.ma/Pages/SuiviCandidature" in adapter.targets
    assert result["budget_consumed"]["lead_followups"] == 1
    parent = next(item for item in result["observations"] if item["url"] == "https://recrutements.ma/story")
    assert parent["source_class"] == "unknown"
    assert result["provenance_recovery"]["official_links_selected"] == 1
