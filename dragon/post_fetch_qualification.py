"""Deterministic post-fetch qualification diagnostics.

This module describes what an exact fetched artifact established before the
evidence-role gate.  It is deliberately descriptive: it never upgrades a
source role, treats retrieval time as publication time, or turns navigation
pages into evidence.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any


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
    )
    issuer = raw.get("stated_issuing_authority") or raw.get("issuing_institution") or origin_detail.get("issuing_institution")
    dates = _date_resolution(raw)
    event_skeleton = event_skeleton if isinstance(event_skeleton, dict) else (raw.get("event_skeleton") if isinstance(raw.get("event_skeleton"), dict) else {})
    temporal_ok = temporal.get("active_on_edition_date") is True
    locator = raw.get("support_locator") or raw.get("claim_locator") or raw.get("exact_support_locator")
    claim_state = "CLAIM_SUPPORT_FOUND" if locator or validation.get("state") == "VALIDATED_EVIDENCE" else "CLAIM_SUPPORT_NOT_FOUND"
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
    elif claim_state != "CLAIM_SUPPORT_FOUND":
        blocker = "CLAIM_SUPPORT_NOT_FOUND"
    elif origin_detail.get("article_origin_state") in {"OFFICIAL_PORTAL_REPUBLICATION", "SYNDICATION_UNRESOLVED"} and not origin:
        blocker = "ORIGIN_UNRESOLVED"
    elif not role_resolution or role_resolution.get("evidence_role") in {None, "UNRESOLVED"}:
        blocker = "ROLE_UNRESOLVED"
    else:
        blocker = "ELIGIBLE_OBSERVATION"
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
        "claim_support": {"state": claim_state, "locator": locator},
        "evidence_role": role_resolution.get("evidence_role") or "UNRESOLVED",
        "validation_state": validation.get("state") or "DISCOVERED",
    }


__all__ = ["qualify_fetched_artifact"]
