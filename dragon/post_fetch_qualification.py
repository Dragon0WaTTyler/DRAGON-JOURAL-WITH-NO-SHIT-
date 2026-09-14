"""Deterministic post-fetch qualification diagnostics.

This module describes what an exact fetched artifact established before the
evidence-role gate.  It is deliberately descriptive: it never upgrades a
source role, treats retrieval time as publication time, or turns navigation
pages into evidence.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from dragon.claim_support import resolve_claim_support


_NAVIGATION_TYPES = {
    "LISTING_PAGE", "SEARCH_RESULTS_PAGE", "CATEGORY_PAGE", "PORTAL_HOME",
    "NAVIGATION_PAGE", "AGGREGATOR",
}


def _date_value(value: Any) -> str | None:
    if isinstance(value, dict):
        value = value.get("normalized") or value.get("value") or value.get("raw")
    value = str(value or "").strip()
    if not value or value.lower() in {"none", "null", "unknown"}:
        return None
    return value


def _date_resolution(raw: dict) -> dict:
    metadata = raw.get("article_metadata") if isinstance(raw.get("article_metadata"), dict) else {}
    publication = metadata.get("publication_date")
    # Some extractors serialize a modified timestamp in the publication-date
    # slot while preserving its provenance.  Never promote that timestamp to
    # publication time; retain it as weak/modified-only metadata.
    if isinstance(publication, dict) and str(publication.get("source") or "").upper() in {"MODIFIED_DATE_ONLY", "MODIFIED", "LAST_MODIFIED"}:
        modified = _date_value(publication)
        return {
            "value": None,
            "provenance": "UNRESOLVED",
            "modified_date": modified,
            "state": "UNRESOLVED",
        }
    value = _date_value(publication) or _date_value(raw.get("published_at")) or _date_value(raw.get("publication_date"))
    if value:
        source = (
            publication.get("source") if isinstance(publication, dict) and publication.get("normalized") else
            "RAW_FETCH_FIELD"
        )
        return {"value": value, "provenance": source or "EXPLICIT_FETCH_METADATA", "state": "RESOLVED"}
    modified = _date_value(metadata.get("modified_date")) or _date_value(raw.get("modified_at"))
    return {
        "value": None,
        "provenance": "UNRESOLVED",
        "modified_date": modified,
        "state": "UNRESOLVED",
    }


def qualify_fetched_artifact(
    raw: dict,
    *,
    page_type: str | None = None,
    validation: dict | None = None,
    role_resolution: dict | None = None,
    temporal: dict | None = None,
    origin_detail: dict | None = None,
    event_skeleton: dict | None = None,
) -> dict:
    """Return an explicit post-fetch qualification/attrition record."""
    validation = validation if isinstance(validation, dict) else {}
    role_resolution = role_resolution if isinstance(role_resolution, dict) else {}
    temporal = temporal if isinstance(temporal, dict) else {}
    origin_detail = origin_detail if isinstance(origin_detail, dict) else {}
    page_type = str(page_type or raw.get("page_type") or "UNKNOWN_PAGE_TYPE")
    metadata = raw.get("article_metadata") if isinstance(raw.get("article_metadata"), dict) else {}
    publisher = (
        ((metadata.get("publisher") or {}).get("name") if isinstance(metadata.get("publisher"), dict) else None)
        or raw.get("publisher") or raw.get("page_publisher") or origin_detail.get("portal_publisher")
        or ((raw.get("publisher_profile") or {}).get("canonical_publisher_name") if isinstance(raw.get("publisher_profile"), dict) else None)
        or ((raw.get("publisher_profile") or {}).get("publisher_name") if isinstance(raw.get("publisher_profile"), dict) else None)
    )
    issuer = raw.get("stated_issuing_authority") or raw.get("issuing_institution") or origin_detail.get("issuing_institution")
    dates = _date_resolution(raw)
    event_skeleton = event_skeleton if isinstance(event_skeleton, dict) else (raw.get("event_skeleton") if isinstance(raw.get("event_skeleton"), dict) else {})
    temporal_ok = temporal.get("active_on_edition_date") is True
    claim_support = resolve_claim_support(
        raw,
        claim=raw.get("claim") or event_skeleton.get("title") or raw.get("title"),
    )
    locator = claim_support.get("locator")
    claim_state = str(claim_support.get("state") or "CLAIM_SUPPORT_NOT_FOUND")
    origin = raw.get("content_origin") or origin_detail.get("content_origin")
    if page_type in _NAVIGATION_TYPES:
        blocker = "NAVIGATION_ONLY"
    elif not publisher:
        blocker = "PUBLISHER_UNRESOLVED"
    elif not dates.get("value"):
        blocker = "PUBLICATION_DATE_WEAK" if dates.get("modified_date") else "PUBLICATION_DATE_UNRESOLVED"
    elif temporal.get("active_on_edition_date") is False and temporal.get("reason") not in {"NO_EXPLICIT_ACTIVE_WINDOW", None}:
        blocker = "TEMPORAL_OUT_OF_WINDOW"
    elif validation.get("state") in {"WRONG_EVENT", "CONTEXT_ONLY"}:
        blocker = "EVENT_MISMATCH"
    elif claim_support.get("support_type") == "CONTRADICTS":
        blocker = "CLAIM_SUPPORT_CONTRADICTS"
    elif claim_support.get("support_type") in {"PARTIAL_SUPPORT", "CONTEXT_ONLY", "AMBIGUOUS"}:
        blocker = "CLAIM_SUPPORT_AMBIGUOUS"
    elif claim_support.get("support_type") != "DIRECT_SUPPORT":
        blocker = "CLAIM_SUPPORT_NOT_FOUND"
    elif origin_detail.get("article_origin_state") in {"OFFICIAL_PORTAL_REPUBLICATION", "SYNDICATION_UNRESOLVED"} and not origin:
        blocker = "ORIGIN_UNRESOLVED"
    elif not role_resolution or role_resolution.get("evidence_role") in {None, "UNRESOLVED"}:
        blocker = "ROLE_UNRESOLVED"
    else:
        blocker = "ELIGIBLE_OBSERVATION"
    progression = ["FETCHED", "PARSED"]
    if page_type not in {"UNKNOWN_PAGE_TYPE", "UNKNOWN"}:
        progression.append("ARTIFACT_TYPE_RESOLVED")
    if publisher:
        progression.append("PUBLISHER_RESOLVED")
    if dates.get("value"):
        progression.append("DATE_RESOLVED")
    if temporal.get("active_on_edition_date") is True:
        progression.append("TEMPORAL_MATCH")
    if origin:
        progression.append("ORIGIN_RESOLVED")
    if validation.get("state") not in {"WRONG_EVENT", "CONTEXT_ONLY"} and event_skeleton.get("state") == "CONCRETE_EVENT":
        progression.append("EVENT_MATCH")
    if claim_state == "CLAIM_SUPPORT_FOUND":
        progression.append("CLAIM_SUPPORT_FOUND")
    if role_resolution.get("evidence_role") not in {None, "UNRESOLVED"}:
        progression.append("ROLE_CLASSIFIED")
    if blocker == "ELIGIBLE_OBSERVATION":
        progression.append("OBSERVATION_CREATED")
    return {
        "schema_version": 1,
        "state": "ELIGIBLE_OBSERVATION" if blocker == "ELIGIBLE_OBSERVATION" else "QUALIFICATION_BLOCKED",
        "first_blocking_reason": blocker,
        "page_type": page_type,
        "navigation_only": page_type in _NAVIGATION_TYPES,
        "publisher": publisher,
        "issuer": issuer,
        "origin": origin,
        "publication_date": dates,
        "modified_date": dates.get("modified_date"),
        "event_date": event_skeleton.get("event_date") or event_skeleton.get("published_at"),
        "retrieved_at": raw.get("retrieved_at") or raw.get("observed_at"),
        "temporal": {
            "active_on_edition_date": temporal.get("active_on_edition_date"),
            "reason": temporal.get("reason"),
        },
        "claim_support": claim_support,
        "evidence_role": role_resolution.get("evidence_role") or "UNRESOLVED",
        "validation_state": validation.get("state") or "DISCOVERED",
        "progression": progression,
    }


__all__ = ["qualify_fetched_artifact"]
