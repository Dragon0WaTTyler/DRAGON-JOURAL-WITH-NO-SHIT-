"""Deterministic cover direction and functional Arabic page planning."""

from __future__ import annotations

import hashlib


COVER_VARIANTS = {
    "PORTRAIT_DOSSIER": ("portrait-left", "portrait-center", "monochrome-red-block"),
    "SYMBOLIC_EDITORIAL": ("single-symbol", "split-symbol", "minimal-metaphor"),
    "SATIRICAL_CARICATURE": ("center-caricature", "ensemble-caricature", "captioned-symbol"),
    "DRAMATIC_CURRENT_EVENT": ("full-bleed-event", "split-event", "center-cutout"),
}


def _choice(key: str, values: tuple[str, ...]) -> str:
    number = int(hashlib.sha256(key.encode("utf-8")).hexdigest()[:8], 16)
    return values[number % len(values)]


def build_cover_brief(
    edition_date: str, lead: dict, secondary: list[dict], *, synthetic: bool
) -> dict:
    section = lead.get("section_id")
    if section == "investigations":
        mode = "PORTRAIT_DOSSIER"
    elif section in {"opinion", "culture"}:
        mode = "SATIRICAL_CARICATURE"
    elif section in {"science", "technology", "history"}:
        mode = "SYMBOLIC_EDITORIAL"
    else:
        mode = "DRAMATIC_CURRENT_EVENT"
    variant = _choice(f"{edition_date}:{lead.get('story_key')}:{mode}", COVER_VARIANTS[mode])
    return {
        "schema_version": 1,
        "edition_date": edition_date,
        "masthead": "DRAGON",
        "issue_label": "نسخة اختبار اصطناعية" if synthetic else "النسخة اليومية",
        "source_article_id": lead["id"],
        "source_story_key": lead.get("story_key"),
        "mode": mode,
        "composition_variant": variant,
        "headline": lead["headline"],
        "standfirst": lead["standfirst"],
        "secondary_teasers": [
            {"article_id": item["id"], "headline": item["headline"]}
            for item in secondary[:3]
        ],
        "hero_art": {
            "classification": "DETERMINISTIC_GRAPHIC",
            "contains_reader_text": False,
            "documentary_evidence": False,
            "generation_status": "FALLBACK_REQUIRED" if not synthetic else "SYNTHETIC_FIXTURE",
        },
        "typography": {
            "language": "ar", "direction": "rtl", "deterministic": True,
            "palette": ["#111111", "#f5efe3", "#9e1523"],
        },
    }


def validate_cover_brief(
    value: dict, article_ids: set[str], *, expected_date: str | None = None
) -> list[str]:
    issues = []
    mode = value.get("mode")
    if value.get("schema_version") != 1 or value.get("source_article_id") not in article_ids:
        issues.append("COVER_BRIEF_IDENTITY_INVALID")
    if value.get("masthead") != "DRAGON":
        issues.append("COVER_MASTHEAD_INVALID")
    if expected_date is not None and value.get("edition_date") != expected_date:
        issues.append("COVER_DATE_INVALID")
    if mode not in COVER_VARIANTS or value.get("composition_variant") not in COVER_VARIANTS.get(mode, ()):
        issues.append("COVER_BRIEF_MODE_INVALID")
    hero = value.get("hero_art", {})
    if hero.get("contains_reader_text") is not False or hero.get("documentary_evidence") is not False:
        issues.append("COVER_ART_TEXT_OR_EVIDENCE_CONFUSION")
    if value.get("typography", {}).get("direction") != "rtl":
        issues.append("COVER_TYPOGRAPHY_NOT_RTL")
    teasers = value.get("secondary_teasers")
    if (
        not isinstance(teasers, list)
        or len(teasers) > 4
        or any(
            not isinstance(item, dict)
            or item.get("article_id") not in article_ids
            or not isinstance(item.get("headline"), str)
            or not item["headline"].strip()
            for item in teasers
        )
    ):
        issues.append("COVER_TEASER_RAIL_INVALID")
    return issues


GRAMMARS = {
    "front": "LEAD",
    "investigations": "INVESTIGATION_DOSSIER",
    "science": "SCIENCE",
    "history": "HISTORY",
    "culture": "CULTURE",
    "adab": "CULTURE",
    "opinion": "ANALYSIS",
    "service": "DATA",
}


def build_layout_plan(articles: list[dict], cover_brief: dict) -> dict:
    pages = []
    for index, article in enumerate(
        (item for item in articles if item.get("status") == "ACTIVE"), start=2
    ):
        grammar = GRAMMARS.get(article["section_id"], "NORMAL_NEWS")
        components = ["section-bar", "headline", "standfirst", "byline", "body", "sources", "folio"]
        if grammar == "INVESTIGATION_DOSSIER":
            components.extend(["evidence-box", "timeline", "counter-position"])
        elif grammar == "SCIENCE":
            components.extend(["study-passport", "method", "limitations"])
        elif grammar == "DATA":
            components.extend(["data-source", "chart-slot"])
        elif grammar in {"ANALYSIS", "HISTORY"}:
            components.extend(["context-rail", "pull-quote"])
        pages.append({
            "page_role": grammar,
            "article_id": article["id"],
            "section_id": article["section_id"],
            "ordinal": index,
            "columns": 2 if grammar in {"LEAD", "NORMAL_NEWS", "INVESTIGATION_DOSSIER"} else 1,
            "visual_priority": "HERO" if article["id"] == cover_brief["source_article_id"] else "STANDARD",
            "components": components,
            "may_rewrite_facts": False,
        })
    return {
        "schema_version": 1,
        "status": "PASS",
        "direction": "rtl",
        "cover": {"page_role": "COVER", "ordinal": 1, "brief_article_id": cover_brief["source_article_id"]},
        "pages": pages,
    }


def validate_layout_plan(value: dict, articles: list[dict]) -> list[str]:
    expected = {item["id"] for item in articles if item.get("status") == "ACTIVE"}
    pages = value.get("pages")
    if value.get("schema_version") != 1 or value.get("status") != "PASS" or value.get("direction") != "rtl":
        return ["LAYOUT_PLAN_ROOT_INVALID"]
    if not isinstance(pages, list) or {item.get("article_id") for item in pages} != expected or len(pages) != len(expected):
        return ["LAYOUT_PLAN_INVENTORY_INVALID"]
    issues = []
    for page in pages:
        if page.get("may_rewrite_facts") is not False or not page.get("components") or page.get("columns") not in {1, 2, 3}:
            issues.append(f"LAYOUT_PLAN_PAGE_INVALID:{page.get('article_id')}")
    return issues
