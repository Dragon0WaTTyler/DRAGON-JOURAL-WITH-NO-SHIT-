from dragon.design import build_cover_brief, build_layout_plan, validate_cover_brief, validate_layout_plan


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
    assert validate_cover_brief(brief, {"lead"}) == []
    assert brief["mode"] == "PORTRAIT_DOSSIER"
    assert brief["hero_art"]["contains_reader_text"] is False
    assert brief["hero_art"]["documentary_evidence"] is False
    assert brief["typography"]["direction"] == "rtl"


def test_layout_uses_functional_page_grammars_without_editorial_authority() -> None:
    articles = [_article("lead", "front"), _article("paper", "science"), _article("data", "service")]
    brief = build_cover_brief("2099-01-02", articles[0], articles[1:], synthetic=True)
    plan = build_layout_plan(articles, brief)
    assert validate_layout_plan(plan, articles) == []
    roles = {item["article_id"]: item["page_role"] for item in plan["pages"]}
    assert roles == {"lead": "LEAD", "paper": "SCIENCE", "data": "DATA"}
    assert all(item["may_rewrite_facts"] is False for item in plan["pages"])
