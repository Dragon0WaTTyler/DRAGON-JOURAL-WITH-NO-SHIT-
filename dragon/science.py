"""Scientific material passports and integrity gates."""

from __future__ import annotations

import re


DOI_PATTERN = re.compile(r"^10\.\d{4,9}/\S+$", re.IGNORECASE)


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
                metadata = source.get("science_metadata") or {}
                passports.append({
                    "source_id": source_id,
                    "paper_id": metadata.get("paper_id"),
                    "doi": source.get("doi"),
                    "title": metadata.get("title"),
                    "authors": metadata.get("authors", []),
                    "journal": metadata.get("journal"),
                    "publication_status": source.get("publication_status") or "unknown",
                    "version_type": metadata.get("version_type"),
                    "full_text_status": source.get("full_text_status") or "UNKNOWN",
                    "methods_read": bool(source.get("methods_read")),
                    "limitations_read": bool(source.get("limitations_read")),
                    "sample": metadata.get("sample"),
                    "sample_size": metadata.get("sample_size"),
                    "design": metadata.get("design"),
                    "effect_result": metadata.get("effect_result"),
                    "statistics": metadata.get("statistics"),
                    "corrections_retractions": metadata.get("corrections_retractions", []),
                    "conflicting_study_source_ids": metadata.get("conflicting_study_source_ids", []),
                    "locators": metadata.get("locators", []),
                    "confidence": metadata.get("confidence", "UNKNOWN"),
                    "doi_verified": bool(metadata.get("doi_verified")),
                    "metadata_matches": bool(metadata.get("metadata_matches")),
                    "claim_alignment": metadata.get("claim_alignment", "NOT_ASSESSED"),
                    "correlation_only": bool(metadata.get("correlation_only")),
                    "metadata_verified": bool(
                        metadata.get("doi_verified") and metadata.get("metadata_matches")
                    ),
                })
            metadata = source.get("science_metadata") or {}
            full_text = source.get("full_text_status") or "UNKNOWN"
            if study_claims and not metadata:
                article_issues.append(f"SCIENCE_METADATA_MISSING:{source_id}")
            if study_claims and metadata:
                missing_metadata = [
                    field for field in ("paper_id", "title", "authors", "journal", "design", "locators")
                    if not metadata.get(field)
                ]
                if missing_metadata:
                    article_issues.append(
                        f"SCIENCE_PASSPORT_INCOMPLETE:{source_id}:{','.join(missing_metadata)}"
                    )
            doi = source.get("doi")
            if doi and (not DOI_PATTERN.match(str(doi)) or not metadata.get("doi_verified")):
                article_issues.append(f"SCIENCE_DOI_UNVERIFIED:{source_id}")
            if metadata and not metadata.get("metadata_matches"):
                article_issues.append(f"SCIENCE_METADATA_MISMATCH:{source_id}")
            if metadata.get("claim_alignment") == "MISALIGNED":
                article_issues.append(f"SCIENCE_CLAIM_MISALIGNED:{source_id}")
            if metadata.get("claim_alignment") == "PARTIAL" and not any(
                marker in text for marker in ("تطابق جزئي", "لا يطابق بالكامل", "دعم جزئي")
            ):
                article_issues.append(f"SCIENCE_PARTIAL_ALIGNMENT_UNDISCLOSED:{source_id}")
            if (
                source.get("publication_status") == "preprint"
                and metadata.get("version_type") not in {None, "UNKNOWN", "PREPRINT"}
            ):
                article_issues.append(f"SCIENCE_VERSION_STATUS_MISMATCH:{source_id}")
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
            if metadata.get("sample_size") is not None and metadata["sample_size"] < 30 and not any(
                marker in text for marker in ("عينة صغيرة", "عينة محدودة", "صغر العينة")
            ):
                article_issues.append(f"SMALL_SAMPLE_CAUTION_MISSING:{source_id}")
            if metadata.get("correlation_only") and any(
                marker in text for marker in ("يسبب", "تسبب", "يؤدي إلى", "نتيجة ل")
            ) and not any(
                marker in text for marker in ("ارتباط", "لا يثبت السببية", "لا يثبت سببا")
            ):
                article_issues.append(f"CORRELATION_CAUSATION_OVERSTATEMENT:{source_id}")
            if source.get("limitations_read") and not any(
                marker in text for marker in ("حدود", "قيود", "محدودية")
            ):
                article_issues.append(f"SCIENCE_LIMITATIONS_OMITTED:{source_id}")
            if metadata.get("conflicting_study_source_ids") and not any(
                marker in text for marker in ("تعارض", "متضاربة", "خلاف علمي")
            ):
                article_issues.append(f"CONFLICTING_STUDIES_OMITTED:{source_id}")
            if metadata.get("corrections_retractions") and not any(
                marker in text for marker in ("تصحيح", "سحب", "تراجع")
            ):
                article_issues.append(f"CORRECTION_RETRACTION_OMITTED:{source_id}")
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
    passport_fields = {
        "source_id", "paper_id", "doi", "title", "authors", "journal",
        "publication_status", "version_type", "full_text_status", "methods_read",
        "limitations_read", "sample", "sample_size", "design", "effect_result",
        "statistics", "corrections_retractions", "conflicting_study_source_ids",
        "locators", "confidence", "doi_verified", "metadata_matches",
        "claim_alignment", "correlation_only", "metadata_verified",
    }
    if any(
        not isinstance(item, dict)
        or set(item) != passport_fields
        or not isinstance(item.get("authors"), list)
        or not isinstance(item.get("locators"), list)
        or not isinstance(item.get("metadata_verified"), bool)
        for item in passports
    ):
        return ["SCIENCE_PASSPORT_SCHEMA_INVALID"]
    if any(
        record.get("status") not in {"PASS", "HOLD"}
        or (record.get("status") == "PASS") != (not record.get("issues"))
        for record in records
    ):
        return ["SCIENCE_ARTICLE_STATUS_MISMATCH"]
    if (value["status"] == "PASS") != (not value.get("issues")):
        return ["SCIENCE_REPORT_STATUS_MISMATCH"]
    return []
