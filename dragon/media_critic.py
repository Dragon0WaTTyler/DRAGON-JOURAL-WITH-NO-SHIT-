"""Structured, evidence-limited comparison of media sourcing and framing."""

from __future__ import annotations

import re


CERTAINTY_MARKERS = ("حتما", "بالتأكيد", "لا شك", "يثبت", "حسم")
CAUSAL_MARKERS = ("سبب", "أدى إلى", "نتيجة", "بسبب")


def build_media_critic(articles: list[dict], research_plan: dict, intelligence: dict) -> dict:
    plans = {item["section_id"]: item for item in research_plan.get("plans", [])}
    events = {item["event_id"]: item for item in intelligence.get("event_clusters", [])}
    source_records = {item["source_id"]: item for item in intelligence.get("source_records", [])}
    records = []
    for article in articles:
        if article.get("status") != "ACTIVE":
            continue
        plan = plans.get(article["section_id"], {})
        event = events.get(plan.get("event_id"), {})
        sources = [source_records[item] for item in article.get("source_ids", []) if item in source_records]
        text = " ".join([str(article.get("headline", "")), *article.get("body", [])])
        observations = []
        if any(marker in text for marker in CERTAINTY_MARKERS):
            observations.append("CERTAINTY_LANGUAGE_PRESENT")
        if any(marker in text for marker in CAUSAL_MARKERS):
            observations.append("CAUSAL_LANGUAGE_PRESENT")
        if event.get("wire_origins"):
            observations.append("WIRE_DEPENDENCE_PRESENT")
        if event.get("independent_origin_count", 0) < 2:
            observations.append("INDEPENDENT_ORIGIN_COUNT_BELOW_TWO")
        records.append({
            "article_id": article["id"],
            "section_id": article["section_id"],
            "event_id": plan.get("event_id"),
            "publisher_count": len({item.get("publisher") for item in sources}),
            "independent_origin_count": event.get("independent_origin_count", 0),
            "wire_origins": event.get("wire_origins", []),
            "shared_event_candidate_keys": event.get("candidate_keys", []),
            "headline_terms": sorted(set(re.findall(r"[\w\u0600-\u06ff]+", str(article.get("headline", "")).casefold()))),
            "observations": observations,
            "inferences": [],
            "motive_claims": [],
        })
    return {
        "schema_version": 1,
        "status": "PASS",
        "articles": records,
        "summary": {
            "article_count": len(records),
            "wire_dependent_article_count": sum(bool(item["wire_origins"]) for item in records),
            "low_independence_article_count": sum(item["independent_origin_count"] < 2 for item in records),
        },
    }


def validate_media_critic(value: dict, articles: list[dict]) -> list[str]:
    expected = {item["id"] for item in articles if item.get("status") == "ACTIVE"}
    records = value.get("articles")
    if value.get("schema_version") != 1 or value.get("status") != "PASS" or not isinstance(records, list):
        return ["MEDIA_CRITIC_ROOT_INVALID"]
    observed = {item.get("article_id") for item in records if isinstance(item, dict)}
    if observed != expected or len(records) != len(expected):
        return ["MEDIA_CRITIC_INVENTORY_INVALID"]
    issues = []
    for item in records:
        if (
            not isinstance(item.get("observations"), list)
            or item.get("inferences") != []
            or item.get("motive_claims") != []
            or not isinstance(item.get("independent_origin_count"), int)
        ):
            issues.append(f"MEDIA_CRITIC_RECORD_INVALID:{item.get('article_id')}")
    return issues
