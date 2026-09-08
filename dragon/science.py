"""Scientific material passports and integrity gates."""

from __future__ import annotations


def science_integrity_report(articles: list[dict], intelligence: dict) -> dict:
    sources = {item["source_id"]: item for item in intelligence.get("source_records", [])}
    passports = []
    article_results = []
    issues = []
    seen_sources = set()
    for article in articles:
        if article.get("status") != "ACTIVE":
            continue
        study_claims = [claim for claim in article.get("claims", []) if claim.get("claim_type") == "study"]
        if article.get("section_id") != "science" and not study_claims:
            continue
        source_ids = sorted({source for claim in study_claims for source in claim.get("source_ids", [])})
        if not source_ids:
            source_ids = sorted(article.get("source_ids", []))
        article_issues = []
        text = " ".join([str(article.get("headline", "")), *article.get("body", [])])
        for source_id in source_ids:
            source = sources.get(source_id)
            if source is None:
                article_issues.append(f"SCIENCE_SOURCE_MISSING:{source_id}")
                continue
            if source_id not in seen_sources:
                seen_sources.add(source_id)
                passports.append({
                    "source_id": source_id,
                    "doi": source.get("doi"),
                    "publication_status": source.get("publication_status") or "unknown",
                    "full_text_status": source.get("full_text_status") or "UNKNOWN",
                    "methods_read": bool(source.get("methods_read")),
                    "limitations_read": bool(source.get("limitations_read")),
                    "metadata_verified": bool(source.get("doi")) or source.get("publication_status") not in {None, "unknown"},
                })
            full_text = source.get("full_text_status") or "UNKNOWN"
            if full_text != "FULL_TEXT_VERIFIED" and (
                source.get("methods_read") or source.get("limitations_read")
            ):
                article_issues.append(f"FULL_TEXT_READING_MISREPRESENTED:{source_id}")
            if source.get("publication_status") == "preprint" and not any(
                marker in text for marker in ("ما قبل التحكيم", "مسودة بحث", "لم تخضع للتحكيم")
            ):
                article_issues.append(f"PREPRINT_LABEL_MISSING:{source_id}")
            if full_text == "ABSTRACT_ONLY" and "الملخص" not in text:
                article_issues.append(f"ABSTRACT_ONLY_LABEL_MISSING:{source_id}")
        issues.extend(f"{article['id']}:{issue}" for issue in article_issues)
        article_results.append({
            "article_id": article["id"],
            "study_claim_count": len(study_claims),
            "source_ids": source_ids,
            "status": "PASS" if not article_issues else "HOLD",
            "issues": article_issues,
        })
    return {
        "schema_version": 1,
        "status": "PASS" if not issues else "FAIL",
        "passports": passports,
        "articles": article_results,
        "issues": issues,
        "no_active_science_material": not article_results,
    }


def validate_science_report(value: dict, articles: list[dict]) -> list[str]:
    if value.get("schema_version") != 1 or value.get("status") not in {"PASS", "FAIL"}:
        return ["SCIENCE_REPORT_ROOT_INVALID"]
    expected = {
        item["id"] for item in articles if item.get("status") == "ACTIVE" and (
            item.get("section_id") == "science"
            or any(claim.get("claim_type") == "study" for claim in item.get("claims", []))
        )
    }
    records = value.get("articles")
    if not isinstance(records, list) or {item.get("article_id") for item in records} != expected:
        return ["SCIENCE_REPORT_INVENTORY_INVALID"]
    passports = value.get("passports")
    if not isinstance(passports, list) or len({item.get("source_id") for item in passports}) != len(passports):
        return ["SCIENCE_PASSPORT_INVENTORY_INVALID"]
    if (value["status"] == "PASS") != (not value.get("issues")):
        return ["SCIENCE_REPORT_STATUS_MISMATCH"]
    return []
