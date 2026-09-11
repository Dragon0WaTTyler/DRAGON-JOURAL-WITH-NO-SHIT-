from copy import deepcopy
from pathlib import Path

from dragon.design import (
    ARCHETYPES, COVER_SKILL_SHA256, HERO_MODES, build_cover_brief,
    build_hero_art_prompt, build_layout_plan, load_cover_skill,
    validate_cover_brief, validate_layout_plan,
)


DATE = "2099-01-02"


def _article(identifier: str, section: str = "front") -> dict:
    return {
        "id": identifier, "section_id": section, "status": "ACTIVE",
        "story_key": f"story-{identifier}", "headline": f"عنوان عربي {identifier}",
        "standfirst": "أطروحة موثقة من القصة الرئيسية لا تضيف ادعاء جديدا.",
    }


def _graph(article_id: str = "lead") -> dict:
    return {"claims": [{"claim_id": "CLM-ONE", "article_id": article_id, "assessment": "SUPPORTED", "text": "وثيقة تثبت الرقم"}]}


def _political_lead() -> dict:
    lead = _article("lead", "investigations")
    lead.update({
        "cover_actors": [{"id": "actor-1", "name": "شخصية عامة", "evidence_ids": ["CLM-ONE"]}],
        "cover_concept": {
            "metaphor": "الوثيقة بين الخطاب والنتيجة",
            "documented_contradiction": {"text": "وعد معلن يقابله رقم موثق", "evidence_ids": ["CLM-ONE"]},
            "evidence_prop": {"label": "إيصال موثق", "evidence_ids": ["CLM-ONE"]},
            "verified_quote": {"text": "وثيقة تثبت الرقم", "verified": True, "evidence_ids": ["CLM-ONE"]},
        },
    })
    return lead


def test_skill_is_vendored_active_and_hash_validates() -> None:
    skill = load_cover_skill()
    assert skill["active"] is True
    assert skill["version"] == "1.1.0"
    assert skill["sha256"] == COVER_SKILL_SHA256
    assert Path("design/skills/alousbou.cover.v2.md").is_file()


def test_political_lead_produces_claim_aware_structured_brief() -> None:
    others = [_article("top-1"), _article("top-2"), _article("bottom-1"), _article("bottom-2")]
    brief = build_cover_brief(DATE, _political_lead(), others, synthetic=False, claim_graph=_graph())
    assert validate_cover_brief(brief, {"lead", "top-1", "top-2", "bottom-1", "bottom-2"}, expected_date=DATE) == []
    assert brief["visual"]["archetype"] == "I"
    assert brief["visual"]["hero_mode"] == "real_face_satirical_photomontage"
    assert brief["visual"]["documented_contradiction_evidence_ids"] == ["CLM-ONE"]
    assert brief["visual"]["evidence_prop"] == "إيصال موثق"
    assert brief["supporting"]["quote_stamp"]["verified"] is True
    assert len(brief["supporting"]["top_teasers"]) == 3
    assert len(brief["supporting"]["bottom_teasers"]) == 1
    assert brief["metadata"]["qr_quiet_zone_modules"] == 4


def test_exactly_one_archetype_and_one_hero_mode_are_represented() -> None:
    brief = build_cover_brief(DATE, _political_lead(), [], synthetic=False, claim_graph=_graph())
    assert brief["visual"]["archetype"] in ARCHETYPES
    assert brief["visual"]["hero_mode"] in HERO_MODES
    assert not isinstance(brief["visual"]["archetype"], list)
    assert not isinstance(brief["visual"]["hero_mode"], list)


def test_headline_red_semantics_and_manual_rtl_lines_are_checked() -> None:
    brief = build_cover_brief(DATE, _article("lead"), [], synthetic=False, claim_graph=_graph())
    assert brief["typography"]["headline_red_phrase"] in brief["lead_story"]["title"]
    bad = deepcopy(brief)
    bad["typography"]["headline_red_phrase"] = "غير موجود"
    bad["typography"]["headline_lines"] = ["كسر", "غير مطابق"]
    issues = validate_cover_brief(bad, {"lead"}, expected_date=DATE)
    assert "COVER_HEADLINE_RED_SEMANTICS_INVALID" in issues
    assert "COVER_HEADLINE_LINES_INVALID" in issues


def test_unverified_quote_and_unlinked_public_figure_cannot_enter_cover() -> None:
    brief = build_cover_brief(DATE, _political_lead(), [], synthetic=False, claim_graph=_graph())
    brief["supporting"]["quote_stamp"] = {"text": "مخترع", "verified": False, "evidence_ids": []}
    brief["lead_story"]["actors"][0]["evidence_ids"] = ["unknown"]
    issues = validate_cover_brief(brief, {"lead"}, expected_date=DATE)
    assert "COVER_QUOTE_UNVERIFIED" in issues
    assert "COVER_PUBLIC_FIGURE_LINKAGE_INVALID" in issues


def test_unsupported_factual_contradiction_falls_back_to_non_factual_symbolic_cover() -> None:
    lead = _political_lead()
    lead["cover_concept"]["documented_contradiction"]["evidence_ids"] = ["missing"]
    brief = build_cover_brief(DATE, lead, [], synthetic=False, claim_graph=_graph())
    assert brief["visual"]["factual_satire"] is False
    assert brief["visual"]["documented_contradiction"] is None
    assert brief["lead_story"]["actors"] == []
    assert brief["visual"]["hero_mode"] != "real_face_satirical_photomontage"


def test_hero_prompt_explicitly_excludes_text_and_arabic_typography() -> None:
    brief = build_cover_brief(DATE, _political_lead(), [], synthetic=False, claim_graph=_graph())
    prompt = build_hero_art_prompt(brief).lower()
    assert all(phrase in prompt for phrase in ("no words", "no arabic text", "no letters", "no qr code", "no typography"))
    assert brief["hero_art"]["contains_reader_text"] is False


def test_serious_institutional_lead_uses_restrained_non_photomontage_archetype() -> None:
    brief = build_cover_brief(DATE, _article("lead", "science"), [], synthetic=False, claim_graph=_graph())
    assert brief["visual"]["archetype"] == "C"
    assert brief["visual"]["hero_mode"] == "symbolic_illustration"
    assert brief["visual"]["factual_satire"] is False


def test_dark_crisis_and_arabic_headline_fixture_uses_white_red_rtl_system() -> None:
    lead = _article("lead")
    lead["cover_archetype"] = "A"
    lead["headline"] = "أزمة\nواضحة"
    brief = build_cover_brief(DATE, lead, [], synthetic=False, claim_graph=_graph())
    assert brief["visual"]["background"] == "dark_photo"
    assert brief["typography"]["masthead_color"] == "white"
    assert brief["typography"]["headline_base_color"] == "white"
    assert brief["typography"]["headline_lines"] == ["أزمة", "واضحة"]
    assert brief["typography"]["direction"] == "rtl"


def test_final_manifest_provenance_is_required_for_complete_cover() -> None:
    brief = build_cover_brief(DATE, _article("lead"), [], synthetic=True, claim_graph=_graph())
    assert "COVER_PROVENANCE_INVALID" in validate_cover_brief(brief, {"lead"}, expected_date=DATE, final=True)
    brief["cover_provenance"] = {
        "cover_skill_id": "arabic-editorial-cover-director", "cover_skill_version": "1.1.0",
        "brief_hash": brief["brief_hash"], "archetype": brief["visual"]["archetype"],
        "hero_mode": brief["visual"]["hero_mode"], "lead_story_id": "lead",
        "evidence_references": ["CLM-ONE"], "hero_art_provider_mode": "NONE",
        "artwork_sha256": "a", "final_cover_sha256": "b", "qa_result": "PASS",
    }
    assert validate_cover_brief(brief, {"lead"}, expected_date=DATE, final=True) == []


def test_layout_remains_compatible_with_v2_cover_brief() -> None:
    articles = [_article("lead"), _article("paper", "science"), _article("data", "service")]
    brief = build_cover_brief(DATE, articles[0], articles[1:], synthetic=True, claim_graph=_graph())
    plan = build_layout_plan(articles, brief)
    assert validate_layout_plan(plan, articles) == []
    assert {item["article_id"]: item["page_role"] for item in plan["pages"]}["lead"] == "LEAD"
