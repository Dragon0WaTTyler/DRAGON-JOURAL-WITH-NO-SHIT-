from pathlib import Path

from dragon.deep_research import create_lead, load_deep_research_config, start_research_job
from dragon.deep_research_executor import execute_research_round
from dragon.discovery import assess_source_url
from dragon.institutional_navigation import (
    classify_outbound_link, detect_official_portal_republication,
    extract_actor_attributions, extract_document_references, extract_outbound_link_candidates,
    resolve_institution_identity,
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


def test_third_party_page_cannot_claim_portal_identity_from_text_alone() -> None:
    detail = detect_official_portal_republication({
        "url": "https://news.example/story",
        "publisher": "News Example",
        "title": "Official portal announcement",
        "text": "The official portal published a notice according to the ministry.",
        "stated_issuing_institution": "Ministry of Interior",
    })
    assert detail["portal_identity_state"] == "PORTAL_IDENTITY_UNRESOLVED"
    assert detail["article_origin_state"] == "ORIGIN_UNRESOLVED"
    assert detail["provenance_edges"] == []


def test_maroc_portal_preserves_map_origin_and_observed_issuer() -> None:
    raw = {
        "url": "https://www.maroc.ma/ar/الأخبار/prosecution-directive",
        "publisher": "Maroc.ma",
        "article_metadata": {"publisher": {"name": "Maroc.ma", "canonical_domain": "www.maroc.ma"}},
        "title": "رئاسة النيابة العامة تدعو النيابات إلى التعبئة",
        "text": "أكد رئيس النيابة العامة في دورية جديدة موجهة إلى الوكلاء ضرورة تتبع الانتخابات. (ومع: 01 شتنبر 2026)",
        "source_route": {"verification_provenance": "official-national-portal-navigation"},
    }
    detail = detect_official_portal_republication(raw)
    assert detail["portal_identity_state"] == "OFFICIAL_NATIONAL_PORTAL"
    assert detail["portal_publisher"] == "Maroc.ma"
    assert detail["content_origin"] == "MAP"
    assert detail["issuing_institution"] == "Public Prosecution"
    assert detail["article_origin_state"] == "OFFICIAL_PORTAL_REPUBLICATION"
    assert detail["original_artifact_state"] == "ORIGINAL_ARTIFACT_NOT_FOUND"
    assert any(edge["type"] == "CONTENT_ORIGINATED_BY" for edge in detail["provenance_edges"])


def test_document_reference_extraction_is_page_derived() -> None:
    refs = extract_document_references({
        "title": "بلاغ لوزير الداخلية بشأن إشعارات الناخبين",
        "text": "بلاغ لوزير الداخلية يحدد الإجراء وآخر أجل 22 شتنبر 2026.",
    })
    assert refs
    assert refs[0]["document_type"] in {"COMMUNIQUE", "SERVICE_NOTICE"}
    assert refs[0]["issuer"] == "Ministry of Interior"
    assert refs[0]["provenance"] == "PAGE_TEXT_EXPLICIT"


def test_maroc_portal_profile_is_not_reclassified_by_article_topic() -> None:
    identity = resolve_institution_identity({
        "url": "https://www.maroc.ma/ar/الأخبار/prosecution-directive",
        "article_metadata": {"publisher": {"name": "Maroc.ma", "canonical_domain": "www.maroc.ma"}},
        "text": "رئاسة النيابة العامة أصدرت دورية للمحاكم.",
    })
    assert identity["profile_type"] == "OFFICIAL_NATIONAL_PORTAL"
    assert identity["state"] == "INSTITUTION_IDENTITY_RESOLVED"


def test_url_safety_is_separate_from_source_trust() -> None:
    safe = assess_source_url("https://service.public-institution.example/path?x=1#notice")
    assert safe["state"] == "URL_SAFE_SOURCE_UNKNOWN"
    assert safe["hostname"] == "service.public-institution.example"
    assert safe["path"] == "/path"
    assert safe["query"] == "x=1"
    assert safe["fragment"] == "notice"
    assert assess_source_url("http://guamcourts.gov/")["reason"] == "UNSUPPORTED_SCHEME_OR_MALFORMED_HOST"
    assert assess_source_url("https://user:pass@example.org/")["reason"] == "EMBEDDED_CREDENTIALS"
    assert assess_source_url("https://127.0.0.1/")["reason"] == "PRIVATE_OR_RESERVED_ADDRESS"
    assert assess_source_url("https://example.org:8443/")["reason"] == "UNSAFE_PORT"


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


def test_navigation_link_failure_opens_bounded_actor_first_discovery() -> None:
    lead = create_lead(
        desk="investigations", topic="election oversight", discovery_source={"url": "https://signal.example/lead"},
        observed_at="2026-09-13T07:00:00Z", reason_interesting="fixture", geography=["Morocco"],
    )
    job = start_research_job(lead, CONFIG, budget_class="STANDARD")
    branch = job["branches"][0]
    action = {
        "job_id": job["job_id"], "branch_id": branch["branch_id"], "question_id": branch["question_ids"][0],
        "action_id": "PORTAL-ACTION", "desk": "investigations", "research_regime": "GENERAL",
        "action_type": "FETCH_URL", "target": "https://maroc.ma/story", "query": "election oversight",
        "query_intent": "FUNCTION_ACCOUNTABILITY_PRIMARY_WINDOW", "query_variant": "EXACT", "query_fingerprint": "PORTAL",
        "priority_class": "P1_BREADTH", "discovery_channel": "fixture", "known_entities": ["Public Prosecution", "election"],
        "known_event_ids": [], "already_seen_urls": [], "already_seen_origins": [], "budget": {"class": "STANDARD"},
        "timeout_seconds": 5, "expected_result_type": "EXTRACTED_SOURCE", "recovery_need_id": "accountability",
        "recovery_candidate_id": None, "provenance_requirements": {"required_role": None, "must_be_distinct_event": False, "science_strict": False},
        "event_context": {"entities": ["Public Prosecution", "election"], "event_terms": ["directive"], "topic_terms": [], "aliases": [], "geography": ["Morocco"], "research_date": "2026-09-13"},
        "channel_fallback": None, "target_editorial_function": "ACCOUNTABILITY", "discovery_only": False, "navigation_depth": 0,
    }

    class Adapter:
        follow_discovery_leads = False
        def __init__(self): self.actions = []
        def execute(self, value):
            self.actions.append(value)
            target = value.get("target")
            if target == "https://maroc.ma/story":
                return [{
                    "url": target, "canonical_url": target, "title": "Public Prosecution announced election directive",
                    "text": "Public Prosecution announced a directive ordering monitoring and complaint handling during the election period. " * 8,
                    "published_at": "2026-09-10", "fetch_status": "FETCHED", "content_hash": "p" * 64,
                    "source_class": "unknown", "publisher": "Maroc.ma", "article_metadata": {"publisher": {"name": "Maroc.ma", "canonical_domain": "maroc.ma"}},
                    "links": [{"url": "https://prosecution.gov.ma/notices", "text": "official notices"}],
                }]
            if value.get("action_type") == "FETCH_URL" and target == "https://prosecution.gov.ma/notices":
                return [{"url": target, "canonical_url": target, "title": "Official notices", "text": "Institutional notices index." * 30, "published_at": "2026-09-10", "fetch_status": "FETCHED", "content_hash": "n" * 64, "source_class": "unknown", "publisher": "Public Prosecution"}]
            if value.get("action_type") == "SEARCH_OFFICIAL_SOURCE":
                return [{"url": "https://prosecution.gov.ma/directive-2026", "title": "Public Prosecution announced directive", "snippet": "directive monitoring election complaints", "source_class": "unknown"}]
            if target == "https://prosecution.gov.ma/directive-2026":
                return [{
                    "url": target, "canonical_url": target, "title": "Public Prosecution announced directive",
                    "text": "Public Prosecution announced a directive ordering monitoring and complaint handling during the election period. " * 8,
                    "published_at": "2026-09-10", "fetch_status": "FETCHED", "content_hash": "d" * 64,
                    "source_class": "unknown", "publisher": "Public Prosecution", "article_metadata": {"publisher": {"name": "Public Prosecution", "canonical_domain": "prosecution.gov.ma"}},
                }]
            return [{"result_type": "DEAD_END", "reason": "UNEXPECTED_FIXTURE_ACTION"}]

    adapter = Adapter()
    result = execute_research_round(job, adapter, CONFIG, actions=[action])
    actor_searches = [item for item in result["actor_first_telemetry"] if item.get("status") == "SEARCH_DISPATCHED"]
    assert actor_searches and actor_searches[0].get("after_official_link") == "https://prosecution.gov.ma/notices"
    assert any(item.get("target") == "https://prosecution.gov.ma/directive-2026" for item in adapter.actions)
    exact = [item for item in result["observations"] if item.get("url") == "https://prosecution.gov.ma/directive-2026" and item.get("extraction_status") == "FETCHED"]
    assert exact and exact[0]["source_class"] == "primary", exact
    assert exact[0]["verification_status"] == "VALIDATED_EVIDENCE"
