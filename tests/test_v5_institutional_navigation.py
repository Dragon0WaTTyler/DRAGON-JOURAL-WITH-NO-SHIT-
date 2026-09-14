import json
from pathlib import Path

from dragon.deep_research_executor import FixtureResearchAdapter, execute_research_round
from dragon.deep_research import create_lead, load_deep_research_config, start_research_job
from dragon.institutional_navigation import (
    classify_page_type, classify_navigation_type, extract_listing_child_links, resolve_institution_identity,
)
from dragon.deep_research_executor import extract_event_skeleton
from dragon.structured_extraction import extract_structured_document


CONFIG = load_deep_research_config(Path("config/deep-research.yaml"))


def test_page_types_cover_institutional_shapes() -> None:
    assert classify_page_type({"url": "https://news.google.com/rss/x", "title": "x"}) == "AGGREGATOR"
    assert classify_page_type({"url": "https://agency.gov.ma/", "title": "Portal", "text": "Welcome"}) == "PORTAL_HOME"
    assert classify_page_type({"url": "https://maroc.ma/ar", "title": "Maroc.ma", "text": "Welcome", "published_at": "2026-09-14"}) == "PORTAL_HOME"
    assert classify_page_type({"url": "https://agency.gov.ma/notices", "title": "Current notices", "text": "Registration closes 2026-09-22", "links": ["https://agency.gov.ma/notices/1"]}) == "SERVICE_NOTICE"
    assert classify_page_type({"url": "https://audit.gov.ma/decisions/1", "title": "Official decision", "text": "Official decision enforcement against entity X."}) == "OFFICIAL_DECISION"
    assert classify_page_type({"url": "https://service.gov.ma/concours", "title": "التسجيل في مباراة الشرطة", "text": "منصة التسجيل وآخر أجل 2026-09-22."}) == "SERVICE_NOTICE"
    assert classify_page_type({"url": "https://hcp.ma/report", "title": "Situation du marché du travail", "text": "Le rapport présente les résultats de l'enquête."}) == "REPORT_DETAIL"


def test_institution_identity_resolves_canonical_and_subdomain_relationship() -> None:
    value = resolve_institution_identity({
        "url": "https://procurement.agency.gov.ma/notices",
        "title": "Public procurement notices", "text": "Ministry public procurement portal",
        "publisher": "Ministry of Administration",
    }, known_profile={"canonical_domain": "agency.gov.ma", "canonical_publisher_name": "Ministry of Administration", "identity_state": "PUBLISHER_PROFILE_RESOLVED"})
    assert value["state"] == "INSTITUTION_IDENTITY_RESOLVED"
    assert value["relationship"] == "SUBDOMAIN_OF_CANONICAL"
    assert value["profile_type"] == "PROCUREMENT_PORTAL"
    assert value["evidence_role"] == "UNRESOLVED"


def test_unresolved_identity_has_specific_diagnostic() -> None:
    value = resolve_institution_identity({"url": "https://example.org/page", "title": "Untitled", "text": "generic text"})
    assert value["state"] == "CANONICAL_DOMAIN_UNRESOLVED"


def test_article_body_institution_mention_does_not_establish_publisher_ownership() -> None:
    value = resolve_institution_identity({
        "url": "https://news.example/story",
        "title": "News report",
        "publisher": "News Example",
        "text": "The Ministry of Interior announced a public procedure.",
    })
    assert value["state"] == "CANONICAL_DOMAIN_UNRESOLVED"
    assert value["identity_confidence"] == "LOW"


def test_listing_child_links_rank_semantic_first_party_and_bound_depth() -> None:
    raw = {
        "url": "https://service.gov.ma/notices", "canonical_url": "https://service.gov.ma/notices",
        "title": "Current notices", "text": "Registration closes 2026-09-22.",
        "links": [
            {"url": "https://service.gov.ma/about", "text": "About"},
            {"url": "https://service.gov.ma/notices/registration-2026", "text": "Registration deadline 22 September 2026"},
            {"url": "https://other.example/item", "text": "General news"},
        ],
    }
    links = extract_listing_child_links(raw, semantic_target="SERVICE", edition_date="2026-09-13")
    assert links and links[0]["url"].endswith("registration-2026")
    assert all(item["navigation_depth"] == 2 for item in links)
    assert len(links) <= 8


def test_listing_child_ranking_does_not_leak_parent_body_signals_into_navigation_links() -> None:
    raw = {
        "url": "https://portal.gov.ma/news", "canonical_url": "https://portal.gov.ma/news",
        "title": "Current notices",
        # These words describe a neighboring item, not every child link.
        "text": "The ministry announced a registration deadline and active public-service procedure.",
        "links": [
            {"url": "https://portal.gov.ma/contact", "text": "Call us"},
            {"url": "https://portal.gov.ma/news/polling-notice-2026-09-22", "text": "Polling-station notice through 22 September 2026"},
        ],
    }
    selected = extract_listing_child_links(raw, semantic_target="SERVICE", edition_date="2026-09-13", maximum=1)
    assert selected and selected[0]["url"].endswith("polling-notice-2026-09-22")


def test_listing_without_detail_is_not_evidence() -> None:
    raw = {"url": "https://agency.gov.ma/", "title": "Current notices", "text": "No links are available."}
    assert extract_listing_child_links(raw, semantic_target="SERVICE", edition_date="2026-09-13") == []


def test_official_notice_structured_fields_can_form_event_without_newsroom_date() -> None:
    skeleton = extract_event_skeleton({
        "title": "Registration notice for eligible applicants", "title_state": "TITLE_RESOLVED",
        "text": "The public agency announces the registration procedure for eligible applicants. Follow the stated deadline and submit the required application through the official service portal.",
        "source_class": "official", "publisher": "Public Agency",
        "structured_fields": {"issuer": "Public Agency", "deadline": "2026-09-22", "status": "open", "category": "registration"},
    }, {"event_context": {"research_date": "2026-09-13", "entities": ["Public Agency"], "event_terms": ["registration"], "geography": ["Morocco"]}})
    assert skeleton["state"] == "CONCRETE_EVENT"
    assert skeleton["page_type"] == "SERVICE_NOTICE"
    assert skeleton["temporal_relevance"]["deadline"] == "2026-09-22"


def test_procurement_homepage_is_not_an_accountability_event() -> None:
    raw = {"url": "https://procurement.gov.ma/", "title": "Procurement portal", "text": "A public portal for publishing and consulting procurement notices."}
    assert classify_page_type(raw) == "PORTAL_HOME"
    assert extract_listing_child_links(raw, semantic_target="ACCOUNTABILITY", edition_date="2026-09-13") == []


def test_structured_notice_fields_are_preserved_without_inference() -> None:
    payload = json.dumps({"notice_number": "N-7", "issuer": "Public Agency", "deadline": "2026-09-22", "description": "Registration procedure"}).encode()
    value = extract_structured_document(payload, content_type="application/json", source_url="https://agency.gov.ma/notice.json")
    assert value["structured_fields"] == {"notice_number": "N-7", "issuer": "Public Agency", "deadline": "2026-09-22", "description": "Registration procedure"}


def test_listing_child_followup_uses_existing_bounded_slot() -> None:
    lead = create_lead(
        desk="service", topic="registration deadline", discovery_source={"url": "https://signal.example/lead"},
        observed_at="2026-09-13T07:00:00Z", reason_interesting="fixture", geography=["Morocco"],
    )
    job = start_research_job(lead, CONFIG, budget_class="STANDARD")
    branch = job["branches"][0]
    action = {
        "job_id": job["job_id"], "branch_id": branch["branch_id"], "question_id": branch["question_ids"][0],
        "action_id": "LISTING-ACTION", "desk": "service", "research_regime": "GENERAL",
        "action_type": "FETCH_CONFIGURED_SOURCE", "target": "https://agency.gov.ma/notices",
        "query": "registration", "query_intent": "LISTING", "query_variant": "EXACT", "query_fingerprint": "LISTING",
        "priority_class": "P1_BREADTH", "discovery_channel": "fixture", "known_entities": ["registration"],
        "known_event_ids": [], "already_seen_urls": [], "already_seen_origins": [],
        "budget": {"class": "STANDARD", "round": 0, "max_rounds": 2}, "timeout_seconds": 5,
        "expected_result_type": "EXTRACTED_SOURCE", "recovery_need_id": "service", "recovery_candidate_id": None,
        "provenance_requirements": {"required_role": None, "must_be_distinct_event": False, "science_strict": False},
        "event_context": {"entities": ["registration"], "event_terms": ["registration"], "topic_terms": [], "aliases": [], "geography": ["Morocco"], "research_date": "2026-09-13"},
        "channel_fallback": None, "target_editorial_function": "SERVICE", "discovery_only": True,
        "navigation_depth": 0, "source_route": {"canonical_domain": "agency.gov.ma", "canonical_publisher_name": "Public Agency", "identity_state": "PUBLISHER_PROFILE_RESOLVED"},
    }

    class Adapter:
        follow_discovery_leads = False
        def __init__(self): self.actions = []
        def execute(self, value):
            self.actions.append(value)
            if value["target"].endswith("/notices"):
                return [{"url": value["target"], "canonical_url": value["target"], "title": "Current notices", "text": "Registration closes 2026-09-22. See the detail notice for the procedure and authority.", "links": [{"url": "https://agency.gov.ma/notices/registration-2026", "text": "Registration deadline 22 September 2026"}], "source_class": "official", "publisher": "Public Agency", "fetch_status": "FETCHED", "content_hash": "a" * 64, "published_at": "2026-09-01"}]
            return [{"url": value["target"], "canonical_url": value["target"], "title": "Registration deadline 22 September 2026", "text": "Public Agency announces the registration procedure. Registration closes 2026-09-22 for eligible applicants in Morocco. " * 8, "source_class": "official", "publisher": "Public Agency", "fetch_status": "FETCHED", "content_hash": "b" * 64, "published_at": "2026-09-01"}]

    adapter = Adapter()
    result = execute_research_round(job, adapter, CONFIG, actions=[action])
    assert any(item["target"].endswith("registration-2026") for item in adapter.actions)
    listing = next(item for item in result["observations"] if item.get("page_type") == "LISTING_PAGE")
    assert listing["listing_resolution_state"] == "CHILD_DETAIL_SELECTED"
    assert result["budget_consumed"]["lead_followups"] == 1


def test_audit_index_prefers_report_artifact_over_recent_ceremony() -> None:
    raw = {
        "url": "https://audit.gov.ma/actualites/", "title": "Actualités", "links": [
            {"url": "https://audit.gov.ma/avis/ceremony-2026-09-08", "text": "08 Sep. 2026 - Participation à une cérémonie"},
            {"url": "https://audit.gov.ma/publications/rapport-controle-2026.pdf", "text": "Rapport d'audit et résultats du contrôle"},
        ],
    }
    selected = extract_listing_child_links(raw, semantic_target="ACCOUNTABILITY", edition_date="2026-09-13", expected_artifact_family="AUDIT_REPORT", maximum=1)
    assert selected[0]["candidate_class"] == "EXACT_ARTIFACT_MATCH"
    assert selected[0]["possible_document_type"] == "AUDIT_REPORT"
    assert selected[0]["url"].endswith("rapport-controle-2026.pdf")


def test_procurement_listing_preserves_row_context_and_award_family() -> None:
    raw = {
        "url": "https://marches.gov.ma/results", "links": [{
            "href": "https://marches.gov.ma/detail/award-77", "anchor_text": "Résultat définitif - marché 77",
            "surrounding_text": "REF 77/2026 — fournisseur retenu", "section": "Résultats",
        }],
    }
    selected = extract_listing_child_links(raw, semantic_target="ACCOUNTABILITY", edition_date="2026-09-13", expected_artifact_family="CONTRACT_AWARD", maximum=1)
    assert selected[0]["candidate_class"] == "EXACT_ARTIFACT_MATCH"
    assert selected[0]["possible_reference_number"] == "77/2026"
    assert selected[0]["section"] == "Résultats"


def test_service_target_without_index_date_remains_fetch_eligible() -> None:
    raw = {
        "url": "https://service.gov.ma/notices", "title": "Service notices", "links": [
            {"url": "https://service.gov.ma/notices/registration", "text": "Inscription et procédure de dépôt"},
        ],
    }
    candidate = extract_listing_child_links(raw, semantic_target="SERVICE", edition_date="2026-09-13", expected_artifact_family="SERVICE_NOTICE", maximum=1)[0]
    assert candidate["candidate_class"] in {"EXACT_ARTIFACT_MATCH", "STRONG_ARTIFACT_CANDIDATE"}
    assert candidate["current_window_signal"] == "UNKNOWN"


def test_service_category_prefers_operator_endpoint_over_language_and_pagination() -> None:
    raw = {
        "url": "https://maroc.ma/en/digital-services", "title": "Digital services",
        "links": [
            {"url": "https://maroc.ma/fr/services-numeriques", "text": "Français"},
            {"url": "https://maroc.ma/en/digital-services?page=1", "text": "2"},
            {"url": "https://maroc.ma/en/digital-services/general-public", "text": "General Public"},
            {"url": "https://passport.gov.ma/Home/Index", "text": "Biometric Passport Application Service"},
            {"url": "https://agency.gov.ma/procedure", "text": "Public service procedure"},
        ],
    }
    values = extract_listing_child_links(raw, semantic_target="SERVICE", edition_date="2026-09-13", expected_artifact_family="SERVICE_NOTICE", maximum=5)
    assert all(item["candidate_type"] not in {"LANGUAGE_VARIANT", "PAGINATION"} for item in values)
    assert values[0]["candidate_type"] in {"SERVICE_ENDPOINT", "APPLICATION_PORTAL"}


def test_navigation_subtypes_preserve_route_shape() -> None:
    assert classify_navigation_type({"url": "https://gov.ma/news", "links": ["https://gov.ma/news/1"]}, action={"source_route": {"route_type": "NEWS_LISTING"}}) == "NEWS_INDEX"
    assert classify_navigation_type({"url": "https://gov.ma/reports", "links": ["https://gov.ma/reports/1"]}, action={"source_route": {"route_type": "AUDIT_PUBLICATIONS"}}) == "REPORT_INDEX"
    assert classify_navigation_type({"url": "https://gov.ma/news/1", "title": "Directive", "text": "The authority issued a directive."}, action={"navigation_depth": 2, "source_route": {"route_type": "NEWS_LISTING"}}) is None


def test_procurement_advanced_search_is_navigation_not_exact_notice() -> None:
    value = classify_page_type({
        "url": "https://www.marchespublics.gov.ma/pmmp/EntrepriseAdvancedSearch/RechercheAvis",
        "title": "Recherche avancée des avis", "text": "Résultats de recherche des avis d'attribution",
    })
    assert value == "SEARCH_RESULTS_PAGE"
