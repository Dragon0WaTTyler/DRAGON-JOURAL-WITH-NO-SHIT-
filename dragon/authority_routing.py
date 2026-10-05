"""Deterministic need-to-authority and artifact-family routing metadata.

This module is deliberately retrieval-only.  Authority and artifact hints are
never evidence, source roles, or claim support; exact pages still pass the
existing provenance and evidence gates.
"""

from __future__ import annotations

import re


AUTHORITY_CAPABILITIES = {
    "EXECUTIVE_MINISTRY", "PUBLIC_SERVICE_OPERATOR", "LOCAL_AUTHORITY",
    "PARLIAMENT", "JUDICIAL_COURT", "PUBLIC_PROSECUTION",
    "AUDIT_INSTITUTION", "REGULATOR", "STATISTICS_AUTHORITY",
    "CENTRAL_BANK", "FINANCE_AUTHORITY", "PROCUREMENT_AUTHORITY",
    "PUBLIC_AGENCY", "INTERNATIONAL_ORGANIZATION", "UNION",
    "CIVIL_SOCIETY_ORGANIZATION", "ACADEMIC_OR_RESEARCH_INSTITUTION",
    "INDEPENDENT_NEWSROOM", "OFFICIAL_NATIONAL_PORTAL",
}

ARTIFACT_FAMILIES = {
    "COMMUNIQUE", "PRESS_RELEASE", "CIRCULAR", "DIRECTIVE", "DECISION",
    "JUDGMENT", "ORDER", "REPORT", "AUDIT_REPORT", "STATISTICAL_RELEASE",
    "DATASET", "BULLETIN", "SERVICE_NOTICE", "REGULATION",
    "PARLIAMENTARY_RECORD", "QUESTION", "COMMITTEE_RECORD",
    "PROCUREMENT_NOTICE", "TENDER", "CONTRACT_AWARD", "CONTRACT_AMENDMENT",
    "BUDGET", "PUBLICATION", "OFFICIAL_PDF", "NEWS_ARTICLE",
}

_ROUTE_TYPE_ARTIFACT_FAMILIES = {
    "AUDIT_PUBLICATIONS": "AUDIT_REPORT", "REPORTS": "REPORT",
    "PRESS_RELEASES": "PRESS_RELEASE", "DECISIONS": "DECISION",
    "COURT_DECISIONS": "JUDGMENT", "REGULATORY_ACTIONS": "DECISION",
    "NOTICES": "SERVICE_NOTICE", "SERVICE_PORTAL": "SERVICE_NOTICE",
    "PROCUREMENT_RESULTS": "CONTRACT_AWARD", "CONSULTATIONS": "PROCUREMENT_NOTICE",
    "PUBLICATIONS": "PUBLICATION",
}

AUTHORITY_ALIASES = {
    "public prosecution": "PUBLIC_PROSECUTION",
    "presidency of the public prosecution": "PUBLIC_PROSECUTION",
    "parquet": "PUBLIC_PROSECUTION",
    "cour des comptes": "AUDIT_INSTITUTION",
    "supreme audit council": "AUDIT_INSTITUTION",
    "audit court": "AUDIT_INSTITUTION",
    "bank al-maghrib": "CENTRAL_BANK",
    "bkam": "CENTRAL_BANK",
    "hcp": "STATISTICS_AUTHORITY",
    "haut commissariat au plan": "STATISTICS_AUTHORITY",
    "house of representatives": "PARLIAMENT",
    "parliament": "PARLIAMENT",
    "public procurement portal": "PROCUREMENT_AUTHORITY",
    "marches publics": "PROCUREMENT_AUTHORITY",
}

_AUTHORITY_MARKERS = {
    "PUBLIC_PROSECUTION": ("prosecution", "parquet", "prosecutor", "public prosecution", "النيابة العامة", "الوكيل العام"),
    "AUDIT_INSTITUTION": ("cour des comptes", "audit", "supreme audit", "افتحاص", "المجلس الأعلى للحسابات"),
    "CENTRAL_BANK": ("bank al-maghrib", "bkam", "central bank", "بنك المغرب"),
    "STATISTICS_AUTHORITY": ("hcp", "haut commissariat", "statistics", "statistical", "المندوبية السامية للتخطيط"),
    "PARLIAMENT": ("parliament", "house of representatives", "chambre des représentants", "البرلمان"),
    "PROCUREMENT_AUTHORITY": ("procurement", "marches publics", "public contracts", "الصفقات العمومية"),
}


def normalize_authority_terms(value: object) -> str:
    """Normalize names for exact alias matching, never fuzzy entity merging."""
    return " ".join(re.findall(r"[\w\u0600-\u06ff]+", str(value or "").casefold()))


def authority_capability_from_text(*values: object) -> str | None:
    text = normalize_authority_terms(" ".join(str(value or "") for value in values))
    if not text:
        return None
    for alias, capability in sorted(AUTHORITY_ALIASES.items(), key=lambda item: len(item[0]), reverse=True):
        if normalize_authority_terms(alias) in text:
            return capability
    for capability, markers in _AUTHORITY_MARKERS.items():
        if any(normalize_authority_terms(marker) in text for marker in markers):
            return capability
    return None


def configured_artifact_family_for_route(route: dict | None, authority_capability: str | None = None) -> str | None:
    """Return an artifact family only when the configured route declares one.

    Generic listings deliberately return ``None``. A route's institutional
    ownership must not make it look like a matching document surface.
    """
    route = route if isinstance(route, dict) else {}
    explicit = str(route.get("artifact_family") or "").upper().strip()
    if explicit in ARTIFACT_FAMILIES:
        return explicit
    route_type = str(route.get("route_type") or "").upper()
    capability = authority_capability or str(route.get("authority_type") or "").upper()
    if route_type == "PUBLICATIONS" and capability == "STATISTICS_AUTHORITY":
        return "STATISTICAL_RELEASE"
    return _ROUTE_TYPE_ARTIFACT_FAMILIES.get(route_type)


def artifact_family_for_route(route: dict | None, function: str | None = None, authority_capability: str | None = None) -> str:
    """Map route type/authority metadata to an expected artifact family."""
    route = route if isinstance(route, dict) else {}
    capability = authority_capability or str(route.get("authority_type") or "").upper()
    configured = configured_artifact_family_for_route(route, capability)
    if configured:
        return configured
    authority_defaults = {
        "PUBLIC_PROSECUTION": "DIRECTIVE", "AUDIT_INSTITUTION": "AUDIT_REPORT",
        "STATISTICS_AUTHORITY": "STATISTICAL_RELEASE", "CENTRAL_BANK": "DECISION",
        "PARLIAMENT": "PARLIAMENTARY_RECORD", "PROCUREMENT_AUTHORITY": "CONTRACT_AWARD",
    }
    if capability in authority_defaults:
        return authority_defaults[capability]
    if capability == "STATISTICS_AUTHORITY":
        return "STATISTICAL_RELEASE"
    if capability == "CENTRAL_BANK":
        return "DECISION"
    if capability == "PUBLIC_PROSECUTION":
        return "DIRECTIVE"
    if capability == "AUDIT_INSTITUTION":
        return "AUDIT_REPORT"
    if capability == "PARLIAMENT":
        return "PARLIAMENTARY_RECORD"
    if capability == "PROCUREMENT_AUTHORITY":
        return "CONTRACT_AWARD"
    if str(function or "").upper() == "SERVICE":
        return "SERVICE_NOTICE"
    return "NEWS_ARTICLE"


def authority_route_metadata(route: dict | None, function: str | None = None, *, actor: object = None, subject: object = None) -> dict:
    """Return explainable authority/artifact hints for one route."""
    route = route if isinstance(route, dict) else {}
    observed_text = " ".join(str(route.get(key) or "") for key in ("name", "publisher", "authority_id", "authority_type", "authority_class"))
    explicit = authority_capability_from_text(actor, subject)
    capability = str(route.get("authority_type") or "").upper().strip() or authority_capability_from_text(observed_text)
    if capability not in AUTHORITY_CAPABILITIES:
        capability = explicit or {
            "JUDICIAL_PROSECUTORIAL": "AUDIT_INSTITUTION",
            "PUBLIC_FINANCE": "FINANCE_AUTHORITY",
            "PUBLIC_STATISTICS": "STATISTICS_AUTHORITY",
            "PARLIAMENTARY": "PARLIAMENT",
            "PUBLIC_PROCUREMENT": "PROCUREMENT_AUTHORITY",
            "INDEPENDENT_MEDIA": "INDEPENDENT_NEWSROOM",
            "MOROCCAN_UNION": "UNION",
            "MOROCCAN_CIVIL_SOCIETY": "CIVIL_SOCIETY_ORGANIZATION",
            "INTERNATIONAL_ORGANIZATION": "INTERNATIONAL_ORGANIZATION",
            "OFFICIAL_GOVERNMENT": "OFFICIAL_NATIONAL_PORTAL",
        }.get(str(route.get("source_family") or "").upper(), "")
    artifact = artifact_family_for_route(route, function, capability)
    reason = "EXPLICIT_ATTRIBUTED_ACTOR" if explicit and explicit == capability else {
        "PUBLIC_PROSECUTION": "LEGAL_JURISDICTION",
        "AUDIT_INSTITUTION": "AUDIT_JURISDICTION",
        "CENTRAL_BANK": "MONETARY_AUTHORITY",
        "STATISTICS_AUTHORITY": "STATISTICAL_AUTHORITY",
        "PARLIAMENT": "PARLIAMENTARY_JURISDICTION",
        "PROCUREMENT_AUTHORITY": "AWARDING_AUTHORITY",
        "PUBLIC_SERVICE_OPERATOR": "RESPONSIBLE_SERVICE_OPERATOR",
    }.get(capability, "FALLBACK_FAMILY_MATCH")
    return {
        "authority_capability": capability or "AUTHORITY_UNRESOLVED",
        "authority_id": route.get("authority_id") or route.get("source_id") or route.get("route_id"),
        "artifact_family": artifact,
        "authority_selection_reason": reason,
        "artifact_selection_reason": "ROUTE_ARTIFACT_TYPE" if route.get("route_type") else "AUTHORITY_DEFAULT_ARTIFACT",
    }


def authority_artifact_preferences(function: str | None, *, actor: object = None, event_terms: object = None) -> list[dict]:
    """Return bounded authority/artifact branches for a semantic need."""
    explicit = authority_capability_from_text(actor, event_terms)
    if explicit == "PUBLIC_PROSECUTION":
        return [{"authority_capability": explicit, "artifact_families": ["CIRCULAR", "DIRECTIVE", "COMMUNIQUE"]}, {"authority_capability": "JUDICIAL_COURT", "artifact_families": ["JUDGMENT", "ORDER"]}, {"authority_capability": "OFFICIAL_NATIONAL_PORTAL", "artifact_families": ["PRESS_RELEASE", "COMMUNIQUE"]}, {"authority_capability": "INDEPENDENT_NEWSROOM", "artifact_families": ["NEWS_ARTICLE"]}]
    if explicit == "AUDIT_INSTITUTION":
        return [{"authority_capability": explicit, "artifact_families": ["AUDIT_REPORT", "REPORT", "OFFICIAL_PDF"]}, {"authority_capability": "PUBLIC_FINANCE", "artifact_families": ["REPORT", "BULLETIN"]}, {"authority_capability": "INDEPENDENT_NEWSROOM", "artifact_families": ["NEWS_ARTICLE"]}]
    if str(function or "").upper() == "SERVICE":
        return [{"authority_capability": "PUBLIC_SERVICE_OPERATOR", "artifact_families": ["SERVICE_NOTICE", "COMMUNIQUE"]}, {"authority_capability": "EXECUTIVE_MINISTRY", "artifact_families": ["SERVICE_NOTICE", "DIRECTIVE"]}, {"authority_capability": "LOCAL_AUTHORITY", "artifact_families": ["SERVICE_NOTICE", "DECISION"]}, {"authority_capability": "STATISTICS_AUTHORITY", "artifact_families": ["STATISTICAL_RELEASE", "DATASET"]}]
    return [{"authority_capability": "PUBLIC_PROSECUTION", "artifact_families": ["CIRCULAR", "DIRECTIVE", "COMMUNIQUE"]}, {"authority_capability": "AUDIT_INSTITUTION", "artifact_families": ["AUDIT_REPORT", "REPORT"]}, {"authority_capability": "REGULATOR", "artifact_families": ["DECISION", "REGULATION"]}, {"authority_capability": "PARLIAMENT", "artifact_families": ["QUESTION", "PARLIAMENTARY_RECORD"]}, {"authority_capability": "INDEPENDENT_NEWSROOM", "artifact_families": ["NEWS_ARTICLE"]}]
