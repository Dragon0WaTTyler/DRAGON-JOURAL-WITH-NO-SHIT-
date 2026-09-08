"""Deterministic chief-editor and claim-level fact-check gates."""

from __future__ import annotations

from collections import Counter, defaultdict
import re


def _normalized(value: str) -> str:
    return re.sub(r"[^\w\u0600-\u06ff]+", " ", value.casefold()).strip()


def chief_editor_report(decisions: list[dict]) -> dict:
    active = [item for item in decisions if item.get("status") == "ACTIVE"]
    issues: list[str] = []
    story_keys = Counter(str(item.get("story_key", "")) for item in active)
    headlines = Counter(_normalized(str(item.get("headline", ""))) for item in active)
    for key, count in story_keys.items():
        if key and count > 1:
            issues.append(f"DUPLICATE_STORY_KEY:{key}")
    for headline, count in headlines.items():
        if headline and count > 1:
            issues.append(f"DUPLICATE_HEADLINE:{headline}")
    facts: dict[str, set[str]] = defaultdict(set)
    for item in active:
        for claim in item.get("claims", []):
            if claim.get("classification") == "FACT" and claim.get("fact_key"):
                facts[str(claim["fact_key"])].add(str(claim.get("value")))
    for fact_key, values in facts.items():
        if len(values) > 1:
            issues.append(f"EDITORIAL_CONTRADICTION:{fact_key}")
    ranking = []
    for item in active:
        words = len(re.findall(r"\S+", " ".join(item.get("body", []))))
        material_claims = sum(bool(claim.get("material")) for claim in item.get("claims", []))
        score = min(words, 1500) / 30 + len(set(item.get("source_ids", []))) * 10 + material_claims * 3
        if item.get("section_id") == "front":
            score += 25
        ranking.append(
            {
                "article_id": item["id"],
                "section_id": item["section_id"],
                "word_count": words,
                "score": round(score, 3),
            }
        )
    ranking.sort(key=lambda item: (-item["score"], item["article_id"]))
    return {
        "status": "PASS" if not issues else "FAIL",
        "issues": issues,
        "ranking": ranking,
        "ranked_article_ids": [item["article_id"] for item in ranking],
        "front_page_article_ids": [item["article_id"] for item in ranking[:3]],
        "active_articles": len(active),
        "edition_words": sum(item["word_count"] for item in ranking),
    }


def factcheck_report(decisions: list[dict], sources: list[dict], *, synthetic: bool) -> dict:
    source_types = {item["id"]: str(item.get("source_type", "unknown")) for item in sources}
    articles = []
    edition_issues = []
    for item in decisions:
        if item.get("status") != "ACTIVE":
            continue
        claim_results = []
        for index, claim in enumerate(item.get("claims", []), start=1):
            classification = claim.get("classification")
            cited = claim.get("source_ids", [])
            cited_types = {source_types.get(source_id, "missing") for source_id in cited}
            issues = []
            outcome = "PASS"
            if any(source_id not in source_types for source_id in cited):
                issues.append("UNKNOWN_SOURCE")
            if classification in {"FACT", "ESTIMATE"} and not cited:
                issues.append("UNSUPPORTED_ASSERTION")
            if classification in {"CLAIM", "DISPUTED"} and not claim.get("attribution"):
                issues.append("ATTRIBUTION_MISSING")
            if (
                not synthetic
                and claim.get("material")
                and classification == "FACT"
                and not ({"primary", "official"} & cited_types)
            ):
                issues.append("PRIMARY_EVIDENCE_MISSING")
            if (
                not synthetic
                and claim.get("material")
                and classification == "FACT"
                and "independent" not in cited_types
                and not claim.get("independent_evidence_unavailable_reason")
            ):
                issues.append("INDEPENDENT_EVIDENCE_MISSING")
            if issues:
                outcome = "NEEDS_VERIFICATION"
                edition_issues.extend(
                    f"{item['id']}:claim-{index}:{issue}" for issue in issues
                )
            claim_results.append(
                {
                    "claim_index": index,
                    "claim_type": claim.get("claim_type", "general"),
                    "classification": classification,
                    "outcome": outcome,
                    "source_ids": cited,
                    "issues": issues,
                }
            )
        article_outcome = (
            "PASS"
            if claim_results and all(value["outcome"] == "PASS" for value in claim_results)
            else "NEEDS_VERIFICATION"
        )
        if not claim_results:
            edition_issues.append(f"{item['id']}:NO_STRUCTURED_CLAIMS")
        articles.append(
            {
                "article_id": item["id"],
                "outcome": article_outcome,
                "claims": claim_results,
            }
        )
    return {
        "status": "PASS" if not edition_issues and articles else "FAIL",
        "allowed_outcomes": ["PASS", "FIX", "REMOVE", "NEEDS_VERIFICATION"],
        "articles": articles,
        "issues": edition_issues,
    }


def adversarial_review(
    decisions: list[dict], claim_graph: dict, research_plan: dict, media_report: dict | None = None
) -> dict:
    """Independently challenge provenance and framing before editorial approval."""
    claims_by_article: dict[str, list[dict]] = defaultdict(list)
    for claim in claim_graph.get("claims", []):
        claims_by_article[str(claim.get("article_id"))].append(claim)
    plans = {item["section_id"]: item for item in research_plan.get("plans", [])}
    media = {
        item["article_id"]: item for item in (media_report or {}).get("articles", [])
    }
    results = []
    edition_issues = []
    for item in decisions:
        if item.get("status") != "ACTIVE":
            continue
        issues = []
        outcome = "PASS"
        for claim in claims_by_article.get(item["id"], []):
            assessment = claim.get("assessment")
            if assessment == "CONTRADICTED":
                issues.append(f"CONTRADICTED:{claim.get('claim_id')}")
                outcome = "HOLD"
            elif assessment == "PROVENANCE_UNAVAILABLE":
                issues.append(f"PROVENANCE_UNAVAILABLE:{claim.get('claim_id')}")
                if outcome != "HOLD":
                    outcome = "REMOVE_CLAIM"
            elif assessment == "PARTIALLY_SUPPORTED" and claim.get("material"):
                issues.append(f"MATERIAL_SUPPORT_INCOMPLETE:{claim.get('claim_id')}")
                if outcome not in {"HOLD", "REMOVE_CLAIM"}:
                    outcome = "FIX"
        plan = plans.get(item.get("section_id"))
        if not plan or len(plan.get("perspectives", [])) < 3:
            issues.append("PERSPECTIVE_MAP_INSUFFICIENT")
            if outcome == "PASS":
                outcome = "FIX"
        if not plan or not any("تفسير بديل" in question for question in plan.get("questions", [])):
            issues.append("ALTERNATIVE_EXPLANATION_NOT_TESTED")
            if outcome == "PASS":
                outcome = "FIX"
        elements = item.get("editorial_elements") or {}
        if not elements.get("uncertainty"):
            issues.append("UNCERTAINTY_NOT_PRESERVED")
            if outcome == "PASS":
                outcome = "FIX"
        material_claims = [
            claim for claim in claims_by_article.get(item["id"], []) if claim.get("material")
        ]
        media_item = media.get(item["id"])
        if (
            media_item
            and material_claims
            and media_item.get("independent_origin_count", 0) < 2
            and not all(
                claim.get("independent_evidence_unavailable_reason")
                for claim in material_claims
            )
        ):
            issues.append("WIRE_ORIGIN_INDEPENDENCE_INSUFFICIENT")
            if outcome == "PASS":
                outcome = "FIX"
        edition_issues.extend(f"{item['id']}:{issue}" for issue in issues)
        results.append({"article_id": item["id"], "outcome": outcome, "issues": issues})
    return {
        "status": "PASS" if results and not edition_issues else "FAIL",
        "allowed_outcomes": ["PASS", "FIX", "HOLD", "REMOVE_CLAIM"],
        "articles": results,
        "issues": edition_issues,
    }
