from dragon.institutional_navigation import classify_page_type
from dragon.post_fetch_qualification import qualify_fetched_artifact


def _base(**overrides):
    value = {
        "url": "https://authority.gov.ma/notices/7",
        "fetch_status": "FETCHED",
        "title": "Operational registration notice",
        "text": "The authority announces the registration procedure and deadline for eligible applicants.",
        "published_at": "2026-08-24",
        "publisher": "Authority",
        "content_hash": "hash-7",
        "retrieved_at": "2026-09-13T08:00:00Z",
    }
    value.update(overrides)
    return value


def test_configured_publisher_is_descriptive_but_role_remains_explicit():
    result = qualify_fetched_artifact(
        _base(),
        page_type="SERVICE_NOTICE",
        temporal={"active_on_edition_date": True, "reason": "ACTIVE_WINDOW"},
        role_resolution={"evidence_role": "PRIMARY"},
    )
    assert result["publisher"] == "Authority"
    assert result["evidence_role"] == "PRIMARY"
    assert result["first_blocking_reason"] == "CLAIM_SUPPORT_NOT_FOUND"


def test_jsonld_publication_date_is_resolved_with_provenance():
    result = qualify_fetched_artifact(
        _base(published_at=None, article_metadata={"publication_date": {"normalized": "2026-08-24", "source": "JSON_LD"}}),
        page_type="ARTICLE_DETAIL",
        temporal={"active_on_edition_date": True},
    )
    assert result["publication_date"] == {"value": "2026-08-24", "provenance": "JSON_LD", "state": "RESOLVED"}


def test_visible_date_is_resolved_and_retrieval_time_is_not_used():
    result = qualify_fetched_artifact(
        _base(published_at="2026-08-24"),
        page_type="ARTICLE_DETAIL",
        temporal={"active_on_edition_date": True},
    )
    assert result["publication_date"]["value"] == "2026-08-24"
    assert result["retrieved_at"] == "2026-09-13T08:00:00Z"

    no_date = qualify_fetched_artifact(_base(published_at=None), page_type="ARTICLE_DETAIL")
    assert no_date["first_blocking_reason"] == "PUBLICATION_DATE_UNRESOLVED"


def test_modified_only_date_is_weak_not_publication_evidence():
    result = qualify_fetched_artifact(
        _base(published_at=None, article_metadata={"modified_date": "2026-09-13"}),
        page_type="ARTICLE_DETAIL",
    )
    assert result["publication_date"]["state"] == "UNRESOLVED"
    assert result["modified_date"] == "2026-09-13"
    assert result["first_blocking_reason"] == "PUBLICATION_DATE_WEAK"


def test_navigation_page_is_navigation_only_even_with_text_and_date():
    raw = _base(url="https://authority.gov.ma/about", title="About the authority")
    assert classify_page_type(raw) == "NAVIGATION_PAGE"
    result = qualify_fetched_artifact(raw, page_type="NAVIGATION_PAGE")
    assert result["navigation_only"] is True
    assert result["first_blocking_reason"] == "NAVIGATION_ONLY"


def test_publisher_and_issuer_are_distinct_for_republication():
    result = qualify_fetched_artifact(
        _base(publisher="Maroc.ma", stated_issuing_authority="Ministry of Interior", content_origin="MAP"),
        page_type="ARTICLE_DETAIL",
        temporal={"active_on_edition_date": True},
        origin_detail={
            "portal_publisher": "Maroc.ma",
            "issuing_institution": "Ministry of Interior",
            "content_origin": "MAP",
            "article_origin_state": "OFFICIAL_PORTAL_REPUBLICATION",
        },
    )
    assert result["publisher"] == "Maroc.ma"
    assert result["issuer"] == "Ministry of Interior"
    assert result["origin"] == "MAP"
    assert result["first_blocking_reason"] == "CLAIM_SUPPORT_NOT_FOUND"


def test_exact_artifact_requires_claim_support_before_eligibility():
    result = qualify_fetched_artifact(
        _base(support_locator="#article-body"),
        page_type="OFFICIAL_NOTICE",
        validation={"state": "VALIDATED_EVIDENCE"},
        role_resolution={"evidence_role": "PRIMARY"},
        temporal={"active_on_edition_date": True},
    )
    assert result["claim_support"]["state"] == "CLAIM_SUPPORT_FOUND"
    assert result["first_blocking_reason"] == "ELIGIBLE_OBSERVATION"


def test_stale_artifact_is_temporally_blocked():
    result = qualify_fetched_artifact(
        _base(published_at="2026-08-01"),
        page_type="ARTICLE_DETAIL",
        temporal={"active_on_edition_date": False, "reason": "EXPIRED_DEADLINE"},
    )
    assert result["first_blocking_reason"] == "TEMPORAL_OUT_OF_WINDOW"

