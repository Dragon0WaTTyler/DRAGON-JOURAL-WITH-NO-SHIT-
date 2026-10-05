"""Alousbou V2 cover direction, provenance gates, and Arabic page planning.

The cover director deliberately selects direction; it never creates a factual
claim. Generated hero art is decorative and all Arabic type is composed by the
local renderer.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re


COVER_SKILL_ID = "arabic-editorial-cover-director"
COVER_SKILL_VERSION = "1.1.0"
COVER_SKILL_SHA256 = "5b376e4c5bc7484d6881b3a0de8f264d5088b8c4271bc6fc9b2bb51ff1e9cbf3"
COVER_SKILL_SOURCE_PATH = r"C:\Users\walid\Downloads\alousbou.cover.v2.md"
COVER_SKILL_REPOSITORY_PATH = "design/skills/alousbou.cover.v2.md"

ARCHETYPES = tuple("ABCDEFGHIJ")
HERO_MODES = (
    "ink_caricature", "symbolic_illustration", "object_metaphor", "split_photo",
    "dual_portrait", "cinematic_ensemble", "real_face_satirical_photomontage",
)
# Compatibility surface for callers from the pre-V2 direction API.  New briefs
# use ``visual.archetype`` and ``visual.hero_mode`` exclusively.
COVER_VARIANTS = {
    "PORTRAIT_DOSSIER": ("D",),
    "SYMBOLIC_EDITORIAL": ("C",),
    "SATIRICAL_CARICATURE": ("B",),
    "DRAMATIC_CURRENT_EVENT": ("A",),
}
BACKGROUND_TOKENS = {"off_white", "gray_paper", "sepia", "dark_photo"}
HEADLINE_POSITIONS = {"left", "right", "lower_center"}
HERO_POSITIONS = {"left", "right", "center", "full_bleed"}


def _choice(key: str, values: tuple[str, ...]) -> str:
    number = int(hashlib.sha256(key.encode("utf-8")).hexdigest()[:8], 16)
    return values[number % len(values)]


def _canonical_hash(value: dict) -> str:
    return hashlib.sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest()


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_cover_skill(root: Path | None = None) -> dict:
    """Load the vendored design authority and prove its identity."""
    root = root or _repo_root()
    # Synthetic orchestrator tests intentionally use a disposable data root;
    # the installed art-direction contract remains code-owned beside V5.
    if not (root / "config" / "cover-system.json").is_file():
        root = _repo_root()
    config_path = root / "config" / "cover-system.json"
    skill_path = root / COVER_SKILL_REPOSITORY_PATH
    if not config_path.is_file() or not skill_path.is_file():
        raise ValueError("COVER_SKILL_MISSING")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    digest = hashlib.sha256(skill_path.read_bytes()).hexdigest()
    if (
        config.get("skill_id") != COVER_SKILL_ID
        or config.get("version") != COVER_SKILL_VERSION
        or config.get("sha256") != COVER_SKILL_SHA256
        or config.get("source_path") != COVER_SKILL_SOURCE_PATH
        or config.get("active") is not True
        or config.get("repository_path") != COVER_SKILL_REPOSITORY_PATH
        or digest != COVER_SKILL_SHA256
    ):
        raise ValueError("COVER_SKILL_IDENTITY_INVALID")
    text = skill_path.read_text(encoding="utf-8")
    if f"name: {COVER_SKILL_ID}" not in text or f"version: {COVER_SKILL_VERSION}" not in text:
        raise ValueError("COVER_SKILL_FRONTMATTER_INVALID")
    return {**config, "sha256": digest}


def _supported_claims(article_id: str, claim_graph: dict | None) -> list[dict]:
    if not isinstance(claim_graph, dict):
        return []
    return [item for item in claim_graph.get("claims", []) if item.get("article_id") == article_id and item.get("assessment") == "SUPPORTED"]


def _refs(value: object, allowed: set[str]) -> list[str]:
    if not isinstance(value, list):
        return []
    return list(dict.fromkeys(str(item) for item in value if str(item) in allowed))


def _headline_lines(headline: str) -> list[str]:
    """The brief owns line breaks; renderer must never invent them."""
    supplied = [part.strip() for part in headline.split("\n") if part.strip()]
    return supplied if supplied else [headline.strip()]


def _red_phrase(headline: str) -> str:
    words = re.findall(r"[\w\u0600-\u06ff]+", headline)
    return words[-1] if words else headline.strip()


def _safe_concept(lead: dict, supported_ids: set[str]) -> tuple[dict | None, dict | None, dict | None]:
    """Admit factual satire only through explicit, supported editorial input."""
    concept = lead.get("cover_concept") if isinstance(lead.get("cover_concept"), dict) else {}
    contradiction, prop, quote = (concept.get("documented_contradiction"), concept.get("evidence_prop"), concept.get("verified_quote"))
    valid_contradiction = contradiction if isinstance(contradiction, dict) and isinstance(contradiction.get("text"), str) and contradiction["text"].strip() and _refs(contradiction.get("evidence_ids"), supported_ids) else None
    valid_prop = prop if isinstance(prop, dict) and isinstance(prop.get("label"), str) and prop["label"].strip() and _refs(prop.get("evidence_ids"), supported_ids) else None
    valid_quote = quote if isinstance(quote, dict) and quote.get("verified") is True and isinstance(quote.get("text"), str) and quote["text"].strip() and _refs(quote.get("evidence_ids"), supported_ids) else None
    return valid_contradiction, valid_prop, valid_quote


def _safe_actors(lead: dict, supported_ids: set[str]) -> list[dict]:
    actors = lead.get("cover_actors") if isinstance(lead.get("cover_actors"), list) else []
    result = []
    for actor in actors:
        if not isinstance(actor, dict) or not isinstance(actor.get("id"), str) or not actor["id"]:
            continue
        evidence_ids = _refs(actor.get("evidence_ids"), supported_ids)
        if evidence_ids:
            result.append({"id": actor["id"], "name": str(actor.get("name") or actor["id"]), "evidence_ids": evidence_ids})
    return result


def _select_visual(lead: dict, actors: list[dict], contradiction: dict | None, prop: dict | None) -> dict:
    """Deterministic, editorially reasoned selection: no random visual modes."""
    forced = lead.get("cover_archetype") if lead.get("cover_archetype") in ARCHETYPES else None
    section = str(lead.get("section_id") or "")
    factual_satire = bool(actors and contradiction and prop)
    if factual_satire:
        archetype = forced or ("J" if len(actors) >= 3 else "H" if len(actors) == 2 else "I")
        mode = "real_face_satirical_photomontage"
    elif forced:
        archetype = forced
        mode = {"A": "split_photo", "B": "ink_caricature", "C": "symbolic_illustration", "D": "object_metaphor", "E": "ink_caricature", "F": "dual_portrait", "G": "cinematic_ensemble", "H": "dual_portrait", "I": "symbolic_illustration", "J": "cinematic_ensemble"}[archetype]
    elif section in {"science", "technology", "history", "culture", "adab"}:
        archetype, mode = "C", "symbolic_illustration"
    elif section in {"investigations", "service", "siyasa_dawla", "iqtisad_flous"}:
        archetype, mode = "D", "object_metaphor"
    else:
        archetype, mode = "B", "ink_caricature"
    dark = archetype == "A"
    return {"archetype": archetype, "hero_mode": mode, "hero_position": "full_bleed" if dark else ("right" if archetype in {"C", "F"} else "left"), "headline_position": "lower_center" if dark or archetype in {"G", "H", "J"} else ("left" if archetype == "C" else "right"), "background": "dark_photo" if dark else ("sepia" if archetype == "G" else "off_white"), "factual_satire": factual_satire}


def build_cover_brief(edition_date: str, lead: dict, secondary: list[dict], *, synthetic: bool, claim_graph: dict | None = None, metadata: dict | None = None, root: Path | None = None) -> dict:
    """Create the V2 canonical direction object from already-approved edition data."""
    skill = load_cover_skill(root)
    supported = _supported_claims(str(lead["id"]), claim_graph)
    supported_ids = {str(item["claim_id"]) for item in supported if item.get("claim_id")}
    actors = _safe_actors(lead, supported_ids)
    contradiction, prop, quote = _safe_concept(lead, supported_ids)
    # A recognizable person is a factual assertion in the cover concept.  Do
    # not carry them into a symbolic fallback when the full contradiction and
    # prop chain is not supported.
    if not (contradiction and prop):
        actors = []
    visual = _select_visual(lead, actors, contradiction, prop)
    headline = str(lead["headline"])
    top = [{"article_id": item["id"], "headline": item["headline"], "section_id": item.get("section_id")} for item in secondary[:3]]
    bottom = [{"article_id": item["id"], "headline": item["headline"], "section_id": item.get("section_id")} for item in secondary[3:5]]
    info = metadata or {}
    lead_evidence = [str(item["claim_id"]) for item in supported if item.get("claim_id")]
    visual.update({"metaphor": str((lead.get("cover_concept") or {}).get("metaphor") or "معالجة رمزية واحدة مستندة إلى قصة الغلاف"), "documented_contradiction": None if contradiction is None else contradiction["text"], "documented_contradiction_evidence_ids": [] if contradiction is None else _refs(contradiction.get("evidence_ids"), supported_ids), "evidence_prop": None if prop is None else prop["label"], "evidence_prop_evidence_ids": [] if prop is None else _refs(prop.get("evidence_ids"), supported_ids), "accent_red": "#ED1846", "red_target_area_percent": 2.5})
    brief = {
        "schema_version": 2, "skill": skill, "edition_date": edition_date, "masthead": "DRAGON", "issue_label": "نسخة اختبار اصطناعية" if synthetic else "النسخة اليومية",
        "source_article_id": lead["id"], "source_story_key": lead.get("story_key"), "mode": visual["hero_mode"], "composition_variant": visual["archetype"],
        "lead_story": {"article_id": lead["id"], "title": headline, "thesis": str(lead.get("standfirst") or ""), "actors": actors, "evidence_ids": lead_evidence},
        "visual": visual,
        "typography": {"language": "ar", "direction": "rtl", "rtl": True, "masthead_color": "white" if visual["background"] == "dark_photo" else "black", "headline_base_color": "white" if visual["background"] == "dark_photo" else "black", "headline_red_phrase": _red_phrase(headline), "headline_lines": _headline_lines(headline), "palette": ["#0B0B0B", "#F2F1EC", "#ED1846"], "deterministic": True},
        "supporting": {"top_teasers": top, "bottom_teasers": bottom, "upper_left_callout": None, "quote_stamp": quote},
        "metadata": {"issue": str(info.get("issue") or edition_date), "date": edition_date, "price": info.get("price"), "website": info.get("website"), "qr_target": str(info.get("qr_target") or f"https://dragon.local/edition/{edition_date}"), "qr_quiet_zone_modules": 4},
        "hero_art": {"classification": "DETERMINISTIC_GRAPHIC", "contains_reader_text": False, "documentary_evidence": False, "generation_status": "FALLBACK_REQUIRED", "provider_mode": "NONE", "prompt": None},
        "qa": {"machine": {"status": "PENDING"}, "human_review": {"status": "REQUIRED", "checks": ["visual_metaphor_clarity", "satire_readability", "hierarchy", "facial_coherence", "thumbnail_impact", "periodical_authenticity"]}},
    }
    brief["brief_hash"] = _canonical_hash({key: value for key, value in brief.items() if key != "brief_hash"})
    return brief


def build_hero_art_prompt(brief: dict) -> str:
    visual = brief["visual"]
    return ("Portrait editorial hero artwork for an Arabic weekly periodical; " f"{visual['hero_mode'].replace('_', ' ')}, {visual['background']} palette, one metaphor: {visual['metaphor']}; " f"reserve {visual['headline_position']} negative space for later Arabic headline and a clean top masthead zone; " "no words, no Arabic text, no letters, no masthead, no logos, no QR code, no typography, no watermark.")


def validate_cover_brief(value: dict, article_ids: set[str], *, expected_date: str | None = None, final: bool = False) -> list[str]:
    issues: list[str] = []
    if value.get("schema_version") != 2 or value.get("source_article_id") not in article_ids: issues.append("COVER_BRIEF_IDENTITY_INVALID")
    if value.get("masthead") != "DRAGON": issues.append("COVER_MASTHEAD_INVALID")
    if expected_date is not None and value.get("edition_date") != expected_date: issues.append("COVER_DATE_INVALID")
    skill = value.get("skill", {})
    if not (isinstance(skill, dict) and skill.get("skill_id") == COVER_SKILL_ID and skill.get("version") == COVER_SKILL_VERSION and skill.get("sha256") == COVER_SKILL_SHA256 and skill.get("active") is True): issues.append("COVER_SKILL_INVALID")
    lead = value.get("lead_story", {})
    if not isinstance(lead, dict) or lead.get("article_id") != value.get("source_article_id") or not isinstance(lead.get("thesis"), str): issues.append("COVER_LEAD_INVALID")
    visual = value.get("visual", {})
    if visual.get("archetype") not in ARCHETYPES or visual.get("hero_mode") not in HERO_MODES: issues.append("COVER_VISUAL_SELECTION_INVALID")
    if visual.get("hero_position") not in HERO_POSITIONS or visual.get("headline_position") not in HEADLINE_POSITIONS or visual.get("background") not in BACKGROUND_TOKENS: issues.append("COVER_GEOMETRY_INVALID")
    if visual.get("accent_red") != "#ED1846" or visual.get("red_target_area_percent") not in {2.5, 3.0, 4.0, 5.0, 6.0}: issues.append("COVER_COLOR_TOKEN_INVALID")
    typography = value.get("typography", {})
    headline = lead.get("title", "") if isinstance(lead, dict) else ""
    if typography.get("direction") != "rtl" or typography.get("rtl") is not True: issues.append("COVER_TYPOGRAPHY_NOT_RTL")
    if not isinstance(typography.get("headline_lines"), list) or not typography["headline_lines"] or "\n".join(typography["headline_lines"]) != headline: issues.append("COVER_HEADLINE_LINES_INVALID")
    red_phrase = typography.get("headline_red_phrase")
    if not isinstance(red_phrase, str) or not red_phrase or red_phrase not in headline: issues.append("COVER_HEADLINE_RED_SEMANTICS_INVALID")
    if typography.get("masthead_color") not in {"black", "white"} or typography.get("headline_base_color") not in {"black", "white"}: issues.append("COVER_TYPOGRAPHY_COLOR_INVALID")
    supporting = value.get("supporting", {})
    for key, maximum in (("top_teasers", 3), ("bottom_teasers", 2)):
        teasers = supporting.get(key) if isinstance(supporting, dict) else None
        if not isinstance(teasers, list) or len(teasers) > maximum or any(not isinstance(item, dict) or item.get("article_id") not in article_ids or not str(item.get("headline") or "").strip() for item in teasers): issues.append(f"COVER_{key.upper()}_INVALID")
    quote = supporting.get("quote_stamp") if isinstance(supporting, dict) else None
    evidence = set(lead.get("evidence_ids", [])) if isinstance(lead, dict) else set()
    if quote is not None and (not isinstance(quote, dict) or quote.get("verified") is not True or not _refs(quote.get("evidence_ids"), evidence)): issues.append("COVER_QUOTE_UNVERIFIED")
    metadata = value.get("metadata", {})
    if not isinstance(metadata, dict) or metadata.get("date") != value.get("edition_date") or not str(metadata.get("issue") or "") or not str(metadata.get("qr_target") or "").startswith("https://") or metadata.get("qr_quiet_zone_modules") != 4: issues.append("COVER_METADATA_OR_QR_INVALID")
    hero = value.get("hero_art", {})
    if not isinstance(hero, dict) or hero.get("contains_reader_text") is not False or hero.get("documentary_evidence") is not False: issues.append("COVER_ART_TEXT_OR_EVIDENCE_CONFUSION")
    factual = visual.get("factual_satire") is True
    actors = lead.get("actors", []) if isinstance(lead, dict) else []
    if any(not isinstance(actor, dict) or not _refs(actor.get("evidence_ids"), evidence) for actor in actors): issues.append("COVER_PUBLIC_FIGURE_LINKAGE_INVALID")
    if factual and (not actors or not visual.get("documented_contradiction") or not _refs(visual.get("documented_contradiction_evidence_ids"), evidence) or not visual.get("evidence_prop") or not _refs(visual.get("evidence_prop_evidence_ids"), evidence) or visual.get("hero_mode") != "real_face_satirical_photomontage"): issues.append("COVER_FACTUAL_SATIRE_PROVENANCE_INVALID")
    if not factual and (actors or visual.get("documented_contradiction") or visual.get("evidence_prop")): issues.append("COVER_UNSUPPORTED_FACTUAL_CONCEPT")
    if final:
        provenance = value.get("cover_provenance", {})
        required = {"cover_skill_id", "cover_skill_version", "brief_hash", "archetype", "hero_mode", "lead_story_id", "evidence_references", "hero_art_provider_mode", "artwork_sha256", "final_cover_sha256", "qa_result"}
        if not isinstance(provenance, dict) or not required <= provenance.keys() or provenance.get("qa_result") != "PASS": issues.append("COVER_PROVENANCE_INVALID")
    return issues


GRAMMARS = {"front": "LEAD", "investigations": "INVESTIGATION_DOSSIER", "science": "SCIENCE", "history": "HISTORY", "culture": "CULTURE", "adab": "CULTURE", "opinion": "ANALYSIS", "service": "DATA"}
STORY_GRAMMARS = {"NEWS": "NORMAL_NEWS", "ANALYSIS": "ANALYSIS", "INVESTIGATION": "INVESTIGATION_DOSSIER", "SCIENCE": "SCIENCE", "HISTORY": "HISTORY", "CULTURE": "CULTURE", "FACT_CHECK": "FACT_CHECK", "DATA": "DATA", "DOCUMENT_PUBLIC_RECORD": "DOCUMENT_PUBLIC_RECORD", "SECTION_OPENER": "SECTION_OPENER"}


def build_layout_plan(articles: list[dict], cover_brief: dict) -> dict:
    pages = []
    for index, article in enumerate((item for item in articles if item.get("status") == "ACTIVE"), start=2):
        grammar = "LEAD" if article["id"] == cover_brief["source_article_id"] else STORY_GRAMMARS.get(article.get("story_type"), GRAMMARS.get(article["section_id"], "NORMAL_NEWS"))
        components = ["section-bar", "headline", "standfirst", "byline", "body", "sources", "folio"]
        if grammar == "INVESTIGATION_DOSSIER": components.extend(["evidence-box", "timeline", "counter-position"])
        elif grammar == "SCIENCE": components.extend(["study-passport", "method", "limitations"])
        elif grammar == "DATA": components.extend(["data-source", "chart-slot"])
        elif grammar == "FACT_CHECK": components.extend(["fact-check-verdict", "evidence-box", "known-unknown"])
        elif grammar == "DOCUMENT_PUBLIC_RECORD": components.extend(["document-excerpt", "evidence-box", "data-source"])
        elif grammar == "SECTION_OPENER": components.extend(["section-opener", "brief-rail"])
        elif grammar in {"ANALYSIS", "HISTORY"}: components.extend(["context-rail", "pull-quote"])
        pages.append({"page_role": grammar, "article_id": article["id"], "section_id": article["section_id"], "ordinal": index, "columns": 2 if grammar in {"LEAD", "NORMAL_NEWS", "INVESTIGATION_DOSSIER"} else 1, "visual_priority": "HERO" if article["id"] == cover_brief["source_article_id"] else "STANDARD", "components": components, "may_rewrite_facts": False})
    return {"schema_version": 1, "status": "PASS", "direction": "rtl", "cover": {"page_role": "COVER", "ordinal": 1, "brief_article_id": cover_brief["source_article_id"]}, "pages": pages}


def validate_layout_plan(value: dict, articles: list[dict]) -> list[str]:
    expected = {item["id"] for item in articles if item.get("status") == "ACTIVE"}
    pages = value.get("pages")
    if value.get("schema_version") != 1 or value.get("status") != "PASS" or value.get("direction") != "rtl": return ["LAYOUT_PLAN_ROOT_INVALID"]
    if not isinstance(pages, list) or {item.get("article_id") for item in pages} != expected or len(pages) != len(expected): return ["LAYOUT_PLAN_INVENTORY_INVALID"]
    return [f"LAYOUT_PLAN_PAGE_INVALID:{page.get('article_id')}" for page in pages if page.get("page_role") not in {"LEAD", "NORMAL_NEWS", *STORY_GRAMMARS.values()} or page.get("may_rewrite_facts") is not False or not page.get("components") or page.get("columns") not in {1, 2, 3}]
