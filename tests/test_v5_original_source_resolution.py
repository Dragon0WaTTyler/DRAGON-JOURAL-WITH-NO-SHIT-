from dragon.original_source_resolution import (
    build_original_source_resolution,
    preferred_resolution_query,
    resolution_failure_for_observation,
)


def _page(text, *, title="Portal report", url="https://portal.gov.ma/news/item"):
    return {
        "url": url,
        "canonical_url": url,
        "title": title,
        "text": text,
        "publisher": "National Portal",
        "published_at": "2026-09-01",
        "fetch_status": "FETCHED",
        "content_hash": "a" * 64,
        "stated_issuing_authority": "Public Prosecution",
        "document_references": [{
            "document_type": "CIRCULAR",
            "issuer": "Public Prosecution",
            "issuer_provenance": "PAGE_TEXT_EXPLICIT",
        }],
    }


def test_resolution_uses_observed_actor_and_keeps_target_context_namespaced():
    page = _page("Public Prosecution issued a circular ordering monitoring and complaint processing during elections.")
    action = {
        "target_editorial_function": "ACCOUNTABILITY",
        "recovery_need_id": "N-1",
        "query": "Supreme Audit Council audit 2026",
        "source_route": {
            "route_id": "prosecution-route",
            "url": "https://prosecution.gov.ma/notices",
            "origin": "prosecution.gov.ma",
            "name": "Public Prosecution",
            "route_type": "NOTICES",
        },
    }
    plan = build_original_source_resolution(page, action)
    assert plan["observed"]["actor"] == "Public Prosecution"
    assert plan["observed"]["actor_provenance"].startswith("PAGE_")
    assert plan["search_context"]["target_function"] == "ACCOUNTABILITY"
    assert "Supreme Audit Council" not in str(plan["observed"])
    assert plan["candidate_targets"][0]["ownership"] == "ACTOR_ROUTE_MATCH"
    assert "site:prosecution.gov.ma" in preferred_resolution_query(plan)


def test_missing_route_is_diagnostic_not_a_guessed_url():
    page = _page("Public Prosecution issued a circular ordering monitoring and complaint processing during elections.")
    plan = build_original_source_resolution(page, {"target_editorial_function": "ACCOUNTABILITY"})
    assert plan["failure_category"] == "INSTITUTION_KNOWN_NO_ARTIFACT_ROUTE"
    assert plan["candidate_targets"] == []
    assert preferred_resolution_query(plan) == "Public Prosecution OFFICIAL_CIRCULAR DIRECTIVES 2026-09-01"


def test_portal_surface_does_not_take_precedence_over_observed_issuer_discovery():
    page = _page("The filing procedure remains open through 9 September 2026.")
    page["stated_issuing_authority"] = "Ministry of Interior"
    page["document_references"] = [{
        "document_type": "COMMUNIQUE", "issuer": "Ministry of Interior",
        "issuer_provenance": "PAGE_TEXT_EXPLICIT",
    }]
    plan = build_original_source_resolution(page, {
        "target_editorial_function": "SERVICE",
        "source_route": {
            "route_id": "maroc-news", "url": "https://maroc.ma/en/news",
            "origin": "maroc.ma", "name": "Maroc.ma", "route_type": "NEWS_LISTING",
        },
    })

    assert plan["candidate_targets"][0]["ownership"] == "PORTAL_SURFACE_ONLY"
    assert preferred_resolution_query(plan).startswith("Ministry of Interior")
    assert not preferred_resolution_query(plan).startswith("site:maroc.ma")


def test_unattributed_or_circular_portal_text_cannot_create_an_issuer():
    for text in (
        "The filing procedure remains open through 9 September 2026.",
        "The ministry says the filing procedure remains open.",
        "According to this portal, the portal notice remains active.",
    ):
        page = _page(text, url="https://maroc.ma/news/unattributed")
        page.pop("stated_issuing_authority", None)
        page["document_references"] = []
        plan = build_original_source_resolution(page, {"target_editorial_function": "SERVICE"})
        assert plan["observed"]["actor"] is None
        assert plan["failure_category"] == "ORIGINAL_ACTOR_UNKNOWN"
        assert plan["original_artifact_state"] == "ORIGINAL_ARTIFACT_NOT_FOUND"


def test_service_artifact_family_and_chain_are_observed_only():
    page = _page(
        "The Ministry issued a service notice with a registration procedure and deadline through 22 September.",
        title="Operational registration notice",
    )
    page.pop("stated_issuing_authority")
    page["document_references"] = [{
        "document_type": "SERVICE_NOTICE", "issuer": "Ministry of Interior",
        "issuer_provenance": "PAGE_TEXT_EXPLICIT",
    }]
    plan = build_original_source_resolution(page, {
        "target_editorial_function": "SERVICE",
        "source_route": {"route_id": "service", "url": "https://service.gov.ma/", "origin": "service.gov.ma", "name": "Ministry of Interior", "route_type": "SERVICE_PORTAL"},
    })
    assert plan["observed"]["actor"] == "Ministry of Interior"
    assert "SERVICE_NOTICES" in plan["observed"]["artifact_families"]
    assert any(edge["type"] == "ATTRIBUTED_ORIGINAL_ACTOR" for edge in plan["provenance_edges"])
    assert plan["role_effect"] == "NONE_UNTIL_EXACT_TARGET_VALIDATED"


def test_resolution_failure_preserves_public_portal_blocker():
    assert resolution_failure_for_observation({
        "content_origin": "MAP",
        "original_artifact_state": "ORIGINAL_ARTIFACT_NOT_FOUND",
        "original_source_resolution": {"failure_category": None},
    }) == "PORTAL_REPUBLICATION_ONLY"
