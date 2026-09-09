"""Claim/evidence provenance graph construction and structural validation."""

from __future__ import annotations

from collections import defaultdict
import hashlib
import re


def _claim_id(article_id: str, index: int, text: str) -> str:
    digest = hashlib.sha256(f"{article_id}\0{index}\0{text}".encode("utf-8")).hexdigest()[:12]
    return f"CLM-{digest.upper()}"


def _tokens(value: object) -> set[str]:
    result = set()
    for token in re.findall(r"[\w\u0600-\u06ff]+", str(value or "").casefold()):
        normalized = token
        if re.search(r"[\u0600-\u06ff]", normalized):
            if len(normalized) > 4 and normalized[0] in "وفبكل":
                normalized = normalized[1:]
            if len(normalized) > 4 and normalized.startswith("ال"):
                normalized = normalized[2:]
        if len(normalized) >= 3:
            result.add(normalized)
    return result


def _source_supports_claim(source: dict, claim: dict) -> bool:
    if source.get("source_type") == "synthetic":
        return True
    claim_tokens = _tokens(claim.get("text"))
    support_tokens = set().union(*(
        _tokens(value) for value in source.get("claims_supported", []) if value
    ))
    return bool(claim_tokens and support_tokens and claim_tokens & support_tokens)


def build_claim_graph(articles: list[dict], intelligence: dict) -> dict:
    sources = {item["source_id"]: item for item in intelligence.get("source_records", [])}
    graph_claims = []
    fact_values: dict[str, set[str]] = defaultdict(set)
    for article in articles:
        if article.get("status") != "ACTIVE":
            continue
        for index, claim in enumerate(article.get("claims", []), start=1):
            source_ids = claim.get("source_ids", [])
            evidence = []
            origins = set()
            types = set()
            for source_id in source_ids:
                source = sources.get(source_id)
                if source is None:
                    evidence.append({
                        "source_id": source_id,
                        "url": None,
                        "source_type": "missing",
                        "independent_origin_group": None,
                        "wire_origin": None,
                        "supports": False,
                        "contradicts": False,
                        "alignment": "PROVENANCE_UNAVAILABLE",
                    })
                    continue
                origin = source["independent_origin_group"]
                supports = _source_supports_claim(source, claim)
                if supports:
                    origins.add(origin)
                    types.add(source.get("source_type"))
                evidence.append({
                    "source_id": source_id,
                    "url": source["canonical_url"],
                    "source_type": source.get("source_type"),
                    "independent_origin_group": origin,
                    "wire_origin": source.get("wire_origin"),
                    "supports": supports,
                    "contradicts": False,
                    "alignment": (
                        "SYNTHETIC_FIXTURE" if source.get("source_type") == "synthetic"
                        else "CLAIM_SUPPORT_TEXT_ALIGNED" if supports
                        else "CITATION_DOES_NOT_SUPPORT_CLAIM"
                    ),
                })
            material_fact = bool(claim.get("material")) and claim.get("classification") == "FACT"
            if not source_ids or any(item["alignment"] == "PROVENANCE_UNAVAILABLE" for item in evidence):
                assessment = "PROVENANCE_UNAVAILABLE"
            elif not any(item["supports"] for item in evidence):
                assessment = "NOT_SUPPORTED"
            elif any(not item["supports"] for item in evidence):
                assessment = "PARTIALLY_SUPPORTED"
            elif material_fact and not ({"primary", "official"} & types):
                assessment = "PARTIALLY_SUPPORTED"
            elif material_fact and "independent" not in types and not claim.get("independent_evidence_unavailable_reason"):
                assessment = "PARTIALLY_SUPPORTED"
            else:
                assessment = "SUPPORTED"
            confidence = "HIGH" if assessment == "SUPPORTED" and len(origins) >= 2 else (
                "MEDIUM" if assessment == "SUPPORTED" else "LOW"
            )
            fact_key = claim.get("fact_key")
            if fact_key and claim.get("classification") == "FACT":
                fact_values[str(fact_key)].add(str(claim.get("value")))
            graph_claims.append({
                "claim_id": _claim_id(article["id"], index, str(claim.get("text", ""))),
                "article_id": article["id"],
                "section_id": article["section_id"],
                "text": claim.get("text"),
                "claim_type": claim.get("claim_type"),
                "classification": claim.get("classification"),
                "material": bool(claim.get("material")),
                "fact_key": fact_key,
                "value": claim.get("value"),
                "independent_evidence_unavailable_reason": claim.get(
                    "independent_evidence_unavailable_reason"
                ),
                "evidence": evidence,
                "independent_origins": len(origins),
                "confidence": confidence,
                "assessment": assessment,
                "disputed": False,
            })
    disputed_keys = {key for key, values in fact_values.items() if len(values) > 1}
    for claim in graph_claims:
        if claim["fact_key"] in disputed_keys:
            claim["disputed"] = True
            claim["assessment"] = "CONTRADICTED"
            claim["confidence"] = "LOW"
    unsupported = sum(
        claim["assessment"] not in {"SUPPORTED"} for claim in graph_claims
    )
    return {
        "schema_version": 1,
        "status": "PASS",
        "claims": graph_claims,
        "summary": {
            "claim_count": len(graph_claims),
            "unsupported_or_disputed_claim_count": unsupported,
            "disputed_fact_keys": sorted(disputed_keys),
        },
    }


def validate_claim_graph(value: dict, articles: list[dict]) -> list[str]:
    if value.get("schema_version") != 1 or value.get("status") != "PASS":
        return ["CLAIM_GRAPH_ROOT_INVALID"]
    expected = sum(
        len(item.get("claims", [])) for item in articles if item.get("status") == "ACTIVE"
    )
    claims = value.get("claims")
    if not isinstance(claims, list) or len(claims) != expected:
        return ["CLAIM_GRAPH_INVENTORY_INVALID"]
    issues = []
    ids = set()
    for claim in claims:
        claim_id = claim.get("claim_id") if isinstance(claim, dict) else None
        if (
            not claim_id
            or claim_id in ids
            or claim.get("assessment") not in {
                "SUPPORTED", "PARTIALLY_SUPPORTED", "NOT_SUPPORTED", "CONTRADICTED",
                "PROVENANCE_UNAVAILABLE"
            }
            or not isinstance(claim.get("evidence"), list)
        ):
            issues.append(f"CLAIM_GRAPH_RECORD_INVALID:{claim_id}")
        ids.add(claim_id)
    return issues
