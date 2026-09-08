from dragon.design import COVER_VARIANTS, build_cover_brief, build_layout_plan, validate_cover_brief, validate_layout_plan


def _article(identifier: str, section: str) -> dict:
    return {
        "id": identifier, "section_id": section, "status": "ACTIVE",
        "story_key": f"story-{identifier}", "headline": f"عنوان {identifier}",
        "standfirst": "مقدمة عربية",
    }


def test_cover_direction_separates_art_from_arabic_typography_and_is_stable() -> None:
    lead = _article("lead", "investigations")
    brief = build_cover_brief("2099-01-02", lead, [_article("other", "science")], synthetic=False)
    repeated = build_cover_brief("2099-01-02", lead, [], synthetic=False)
    assert brief["mode"] == repeated["mode"]
    assert brief["composition_variant"] == repeated["composition_variant"]
    assert validate_cover_brief(brief, {"lead", "other"}, expected_date="2099-01-02") == []
    assert brief["mode"] == "PORTRAIT_DOSSIER"
    assert brief["hero_art"]["contains_reader_text"] is False
    assert brief["hero_art"]["documentary_evidence"] is False
    assert brief["masthead"] == "DRAGON"
    assert brief["secondary_teasers"] == [{"article_id": "other", "headline": "عنوان other"}]
    assert brief["typography"]["direction"] == "rtl"


def test_cover_brief_rejects_wrong_date_masthead_and_unknown_teaser() -> None:
    lead = _article("lead", "front")
    brief = build_cover_brief("2099-01-02", lead, [], synthetic=False)
    brief["masthead"] = ""
    brief["secondary_teasers"] = [{"article_id": "missing", "headline": "عنوان عربي"}]
    issues = validate_cover_brief(brief, {"lead"}, expected_date="2099-01-03")
    assert issues == [
        "COVER_MASTHEAD_INVALID", "COVER_DATE_INVALID", "COVER_TEASER_RAIL_INVALID"
    ]


def test_all_cover_modes_expose_several_deterministic_variants() -> None:
    sections = {
        "PORTRAIT_DOSSIER": "investigations",
        "SYMBOLIC_EDITORIAL": "science",
        "SATIRICAL_CARICATURE": "opinion",
        "DRAMATIC_CURRENT_EVENT": "front",
    }
    for mode, section_id in sections.items():
        observed = {
            build_cover_brief(
                f"2099-01-{day:02d}", _article(f"lead-{day}", section_id), [], synthetic=True
            )["composition_variant"]
            for day in range(1, 21)
        }
        assert observed == set(COVER_VARIANTS[mode])


def test_layout_uses_functional_page_grammars_without_editorial_authority() -> None:
    articles = [_article("lead", "front"), _article("paper", "science"), _article("data", "service")]
    brief = build_cover_brief("2099-01-02", articles[0], articles[1:], synthetic=True)
    plan = build_layout_plan(articles, brief)
    assert validate_layout_plan(plan, articles) == []
    roles = {item["article_id"]: item["page_role"] for item in plan["pages"]}
    assert roles == {"lead": "LEAD", "paper": "SCIENCE", "data": "DATA"}
    assert all(item["may_rewrite_facts"] is False for item in plan["pages"])


def test_lead_and_special_story_types_route_to_executable_page_grammars() -> None:
    lead = _article("lead", "science")
    factcheck = {**_article("check", "front"), "story_type": "FACT_CHECK"}
    document = {**_article("record", "siyasa_dawla"), "story_type": "DOCUMENT_PUBLIC_RECORD"}
    opener = {**_article("opener", "mojtama3"), "story_type": "SECTION_OPENER"}
    brief = build_cover_brief("2099-01-02", lead, [factcheck, document], synthetic=True)
    plan = build_layout_plan([lead, factcheck, document, opener], brief)
    pages = {item["article_id"]: item for item in plan["pages"]}
    assert pages["lead"]["page_role"] == "LEAD"
    assert pages["check"]["page_role"] == "FACT_CHECK"
    assert "fact-check-verdict" in pages["check"]["components"]
    assert pages["record"]["page_role"] == "DOCUMENT_PUBLIC_RECORD"
    assert "document-excerpt" in pages["record"]["components"]
    assert pages["opener"]["page_role"] == "SECTION_OPENER"
