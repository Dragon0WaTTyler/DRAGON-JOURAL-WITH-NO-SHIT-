"""Offline regression coverage for evidence qualification root causes.

Each fixture is deliberately hash-bound and local: no adapter, provider, or
network call is involved.  The cases mirror the failure modes investigated in
the 2026-09-20 bounded acquisition run.
"""

from dragon.deep_research_executor import _observation as make_observation
from dragon.post_fetch_qualification import qualify_fetched_artifact
from dragon.temporal_relevance import evaluate_temporal_relevance


EDITION = "2026-09-20"


def _action(**overrides):
    value = {
        "action_id": "ACT-OFFLINE-1",
        "question_id": "Q-OFFLINE-1",
        "branch_id": "BR-OFFLINE-1",
        "action_type": "FETCH_URL",
        "expected_result_type": "EXTRACTED_SOURCE",
        "target_editorial_function": "ACCOUNTABILITY",
        "recovery_need_id": "BREADTH:accountability_and_service:1",
        "originating_recovery_need_id": "BREADTH:accountability_and_service:1",
        "recovery_mode": "DISCOVER_NEW_EVENT_FOR_SEMANTIC_NEED",
        "event_context": {"research_date": EDITION, "topic_terms": ["accountability"]},
        "provenance_requirements": {"required_role": None, "must_be_distinct_event": True},
    }
    value.update(overrides)
    return value


def _raw(**overrides):
    value = {
        "url": "https://authority.gov.ma/notices/monitoring",
        "canonical_url": "https://authority.gov.ma/notices/monitoring",
        "title": "Authority announces monitoring directive",
        "publisher": "Authority",
        "text": (
            "Authority announces a monitoring directive for the active public process. "
            "The directive remains effective from 2026-09-10 through 2026-09-25. "
        ) * 4,
        "published_at": "2026-09-10",
        "fetch_status": "FETCHED",
        "content_hash": "a" * 64,
        "source_class": "unknown",
    }
    value.update(overrides)
    return value


def _court_route():
    return {
        "route_id": "cdc-publications",
        "url": "https://www.courdescomptes.ma/publications/",
        "origin": "www.courdescomptes.ma",
        "role": "PRIMARY",
        "authority_class": "PRIMARY_ORIGINAL",
        "discovery_only": False,
        "publisher": "Cour des comptes",
        "name": "Cour des comptes Morocco",
    }


def _court_report(**overrides):
    value = _raw(
        url="https://www.courdescomptes.ma/publication/rapport-annuel-2024-2025/",
        canonical_url="https://www.courdescomptes.ma/publication/rapport-annuel-2024-2025/",
        title="Rapport annuel de la Cour des comptes au titre de 2024-2025",
        publisher="Cour des comptes",
        text=(
            "Rapport annuel de la Cour des comptes au titre de 2024-2025. "
            "La Cour des comptes rend public ledit rapport."
        ) * 4,
        published_at=None,
        article_metadata={
            "publisher": {"name": "Cour des comptes", "canonical_domain": "www.courdescomptes.ma"},
            "publication_date": {"normalized": "2026-02-25T14:48:54+00:00", "source": "MODIFIED_DATE_ONLY"},
        },
    )
    value.update(overrides)
    return value


def test_01_original_institutional_current_event_is_primary_and_eligible():
    observation = make_observation(_action(), _raw(), set())
    assert observation["source_role_resolution"]["evidence_role"] == "PRIMARY"
    assert observation["temporal_relevance"]["active_on_edition_date"] is True
    assert observation["post_fetch_qualification"]["state"] == "ELIGIBLE_OBSERVATION"


def test_02_historical_first_party_report_is_primary_only_for_its_narrow_publication_claim():
    observation = make_observation(_action(source_route=_court_route()), _court_report(), set())
    role = observation["source_role_resolution"]
    assert role["evidence_role"] == "PRIMARY"
    assert role["claim_scope"] == "NARROW_DOCUMENT_PUBLICATION"
    assert observation["event_skeleton"] is None
    assert observation["post_fetch_qualification"]["first_blocking_reason"] == "PUBLICATION_DATE_WEAK"


def test_03_official_portal_republication_does_not_become_primary():
    action = _action(source_route={
        "route_id": "maroc-news", "url": "https://www.maroc.ma/en/news", "origin": "www.maroc.ma",
        "role": "PRIMARY", "authority_class": "PRIMARY_ORIGINAL", "discovery_only": False,
        "publisher": "Maroc.ma", "name": "Maroc.ma",
        "verification_provenance": "official-national-portal-navigation",
    })
    raw = _raw(
        url="https://www.maroc.ma/ar/news/prosecution-directive",
        canonical_url="https://www.maroc.ma/ar/news/prosecution-directive",
        title="تقرير رئاسة النيابة العامة",
        publisher="Maroc.ma",
        article_metadata={"publisher": {"name": "Maroc.ma", "canonical_domain": "www.maroc.ma"}},
        text=("نشرت رئاسة النيابة العامة التقرير الجديد حول تتبع الشكايات. (ومع: 01 شتنبر 2026) " * 5),
        published_at="2026-09-01",
    )
    observation = make_observation(action, raw, set())
    assert observation["origin_detail"]["article_origin_state"] == "OFFICIAL_PORTAL_REPUBLICATION"
    assert observation["source_role_resolution"]["evidence_role"] == "UNRESOLVED"


def test_04_modified_http_metadata_is_not_publication_evidence():
    result = qualify_fetched_artifact(
        _court_report(), page_type="REPORT_DETAIL", role_resolution={"evidence_role": "PRIMARY"},
    )
    assert result["publication_date"]["value"] is None
    assert result["modified_date"] == "2026-02-25T14:48:54+00:00"
    assert result["first_blocking_reason"] == "PUBLICATION_DATE_WEAK"


def test_05_publication_date_is_kept_distinct_from_event_date():
    raw = _raw(event_date="2026-09-08", published_at="2026-09-10")
    observation = make_observation(_action(), raw, set())
    assert observation["post_fetch_qualification"]["publication_date"]["value"] == "2026-09-10"
    assert observation["post_fetch_qualification"]["event_date"] == "2026-09-08"


def test_06_arabic_deadline_forms_are_parsed_without_using_retrieval_time():
    value = evaluate_temporal_relevance(
        {"published_at": "2026-09-04", "text": "يستمر إيداع الطلبات إلى غاية 22 شتنبر 2026."},
        "2026-09-13",
    )
    assert value["deadline"] == "2026-09-22"
    assert value["active_on_edition_date"] is True


def test_07_expired_deadline_remains_blocked():
    value = evaluate_temporal_relevance(
        {"published_at": "2026-09-04", "text": "آخر أجل 9 شتنبر 2026 لإيداع الطلبات."},
        EDITION,
    )
    assert value["temporal_eligibility_type"] == "EVENT_EXPIRED"
    assert value["active_on_edition_date"] is False


def test_08_support_for_one_claim_does_not_support_an_unrelated_claim():
    supported = qualify_fetched_artifact(
        _raw(claim="Authority announces monitoring directive"), page_type="OFFICIAL_NOTICE",
        role_resolution={"evidence_role": "PRIMARY"}, temporal={"active_on_edition_date": True},
    )
    unrelated = qualify_fetched_artifact(
        _raw(claim="Authority awards a construction contract"), page_type="OFFICIAL_NOTICE",
        role_resolution={"evidence_role": "PRIMARY"}, temporal={"active_on_edition_date": True},
    )
    assert supported["claim_support"]["support_type"] == "DIRECT_SUPPORT"
    assert unrelated["claim_support"]["support_type"] != "DIRECT_SUPPORT"
    assert unrelated["first_blocking_reason"] == "CLAIM_SUPPORT_NOT_FOUND"


def test_09_retrieved_artifact_can_remain_blocked_after_successful_fetch():
    raw = _court_report(text="Rapport annuel de la Cour des comptes au titre de 2024-2025. " * 4)
    observation = make_observation(_action(source_route=_court_route()), raw, set())
    assert observation["extraction_status"] == "FETCHED"
    assert observation["post_fetch_qualification"]["state"] == "QUALIFICATION_BLOCKED"
    assert observation["source_role_resolution"]["evidence_role"] == "UNRESOLVED"


def test_10_fully_supported_primary_semantic_and_temporal_artifact_is_eligible():
    observation = make_observation(_action(), _raw(), set())
    qualification = observation["post_fetch_qualification"]
    assert observation["validation_state"] == "VALIDATED_EVIDENCE"
    assert qualification["claim_support"]["support_type"] == "DIRECT_SUPPORT"
    assert qualification["evidence_role"] == "PRIMARY"
    assert qualification["temporal"]["active_on_edition_date"] is True
    assert qualification["state"] == "ELIGIBLE_OBSERVATION"
