"""Publisher identity is useful provenance, never automatic article evidence."""

from dragon.publisher_profiles import PublisherProfileCache, article_origin_evaluation, publisher_profile_from_pages


def _page(url: str, text: str, *, publisher: str = "Example News") -> dict:
    return {"canonical_url": url, "text": text, "publisher": publisher, "title": "About Example News", "language": "en"}


def test_unknown_domain_can_resolve_first_party_profile_without_article_promotion() -> None:
    profile = publisher_profile_from_pages("https://africanews.example", [_page("https://africanews.example/about", "Example News is part of Example Media Group.")])
    assert profile["identity_state"] == "PUBLISHER_PROFILE_RESOLVED"
    assert profile["article_evidence_role"] == "UNRESOLVED"
    assert profile["parent_company"] == "Example Media Group"


def test_profile_cache_reuses_provenance_bound_profile() -> None:
    cache = PublisherProfileCache()
    profile = cache.put(publisher_profile_from_pages("https://news.example", [_page("https://news.example/about", "About")]))
    cached = cache.get("https://news.example/article")
    assert cached == profile and cached is not profile


def test_same_newsroom_family_is_not_independent_of_existing_evidence() -> None:
    profile = publisher_profile_from_pages("https://news.example", [_page("https://news.example/about", "About")])
    result = article_origin_evaluation({"article_origin_state": "ORIGINAL_UNKNOWN"}, publisher_profile=profile, existing_origin_ids={profile["newsroom_family_id"]})
    assert result["evidence_role"] == "UNRESOLVED"
    assert result["reason"] == "PUBLISHER_FAMILY_OVERLAPS_EXISTING_EVIDENCE"


def test_wire_and_partner_credit_never_close_independent_role() -> None:
    profile = publisher_profile_from_pages("https://news.example", [_page("https://news.example/about", "About")])
    for state in ("WIRE_REPUBLICATION", "PARTNER_REPUBLICATION", "SYNDICATION_UNRESOLVED"):
        assert article_origin_evaluation({"article_origin_state": state}, publisher_profile=profile, existing_origin_ids=set())["evidence_role"] == "UNRESOLVED"
