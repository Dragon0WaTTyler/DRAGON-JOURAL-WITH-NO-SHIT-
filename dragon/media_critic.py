"""Structured, evidence-limited comparison of media sourcing and framing."""

from __future__ import annotations

import re


CERTAINTY_MARKERS = ("حتما", "بالتأكيد", "لا شك", "يثبت", "حسم")
CAUSAL_MARKERS = ("سبب", "أدى إلى", "نتيجة", "بسبب")
LOADED_MARKERS = ("فضيحة", "كارثة", "خيانة", "انهيار حتمي", "صادم")


def _normalize(value: object) -> str:
    return re.sub(r"[^\w\u0600-\u06ff]+", " ", str(value or "").casefold()).strip()


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
        if any(marker in text for marker in LOADED_MARKERS):
            observations.append("LOADED_VOCABULARY_PRESENT")
        source_views = []
        claim_sources: dict[str, set[str]] = {}
        claim_labels: dict[str, str] = {}
        for source in sources:
            claims = [
                str(value) for value in source.get("claims_supported", []) if value
            ]
            for claim in claims:
                normalized = _normalize(claim)
                if normalized:
                    claim_sources.setdefault(normalized, set()).add(source["source_id"])
                    claim_labels.setdefault(normalized, claim)
            source_views.append({
                "source_id": source["source_id"],
                "publisher": source.get("publisher"),
                "authority_level": source.get("authority_level"),
                "primary_evidence": bool(source.get("primary_evidence")),
                "independent_origin_group": source.get("independent_origin_group"),
                "wire_origin": source.get("wire_origin"),
                "published_at": source.get("published_at"),
                "claims_supported": claims,
            })
        shared_claims = [
            {"claim": claim_labels[key], "source_ids": sorted(source_ids)}
            for key, source_ids in sorted(claim_sources.items()) if len(source_ids) >= 2
        ]
        source_specific_claims = [
            {"claim": claim_labels[key], "source_ids": sorted(source_ids)}
            for key, source_ids in sorted(claim_sources.items()) if len(source_ids) == 1
        ]
        inference = (
            ["WIRE_DEPENDENCE_LIMITS_APPARENT_SOURCE_DIVERSITY"]
            if event.get("wire_origins") else []
        )
        unresolved = list(plan.get("unknowns", []))
        questions = list(plan.get("questions", []))
        records.append({
            "article_id": article["id"],
            "section_id": article["section_id"],
            "event_id": plan.get("event_id"),
            "publisher_count": len({item.get("publisher") for item in sources}),
            "independent_origin_count": event.get("independent_origin_count", 0),
            "wire_origins": event.get("wire_origins", []),
            "shared_event_candidate_keys": event.get("candidate_keys", []),
            "headline_terms": sorted(set(re.findall(r"[\w\u0600-\u06ff]+", str(article.get("headline", "")).casefold()))),
            "source_views": source_views,
            "shared_factual_claims": shared_claims,
            "source_specific_claims": source_specific_claims,
            "included_context": {
                "known_facts": list(plan.get("known_facts", [])),
                "reported_claims": list(plan.get("reported_claims", [])),
                "disputed_points": list(plan.get("disputed_points", [])),
            },
            "explicitly_unresolved_context": unresolved,
            "quoted_actors": {"status": "NOT_CAPTURED_IN_STRUCTURED_INPUT", "actors": []},
            "missing_actors": {"status": "NOT_INFERRED", "actors": []},
            "primary_evidence_source_ids": sorted(
                source["source_id"] for source in sources if source.get("primary_evidence")
            ),
            "headline_framing": {
                "certainty_language": any(marker in text for marker in CERTAINTY_MARKERS),
                "causal_language": any(marker in text for marker in CAUSAL_MARKERS),
                "loaded_vocabulary": sorted(marker for marker in LOADED_MARKERS if marker in text),
            },
            "chronology": sorted(
                [
                    {"source_id": source["source_id"], "published_at": source.get("published_at")}
                    for source in sources if source.get("published_at")
                ],
                key=lambda item: (item["published_at"], item["source_id"]),
            ),
            "unanswered_questions": questions,
            "observations": observations,
            "inferences": inference,
            "unproven_possibilities": [],
            "analysis_layers": {
                "OBSERVATION": observations,
                "EDITORIAL_INFERENCE": inference,
                "UNPROVEN_POSSIBILITY": [],
            },
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
            or item.get("motive_claims") != []
            or not isinstance(item.get("independent_origin_count"), int)
            or not isinstance(item.get("source_views"), list)
            or not isinstance(item.get("shared_factual_claims"), list)
            or not isinstance(item.get("source_specific_claims"), list)
            or not isinstance(item.get("explicitly_unresolved_context"), list)
            or set(item.get("analysis_layers", {})) != {
                "OBSERVATION", "EDITORIAL_INFERENCE", "UNPROVEN_POSSIBILITY"
            }
            or item.get("analysis_layers", {}).get("OBSERVATION") != item.get("observations")
            or item.get("analysis_layers", {}).get("EDITORIAL_INFERENCE") != item.get("inferences")
            or item.get("analysis_layers", {}).get("UNPROVEN_POSSIBILITY") != item.get("unproven_possibilities")
            or item.get("quoted_actors", {}).get("status") != "NOT_CAPTURED_IN_STRUCTURED_INPUT"
            or item.get("missing_actors", {}).get("status") != "NOT_INFERRED"
        ):
            issues.append(f"MEDIA_CRITIC_RECORD_INVALID:{item.get('article_id')}")
    return issues
