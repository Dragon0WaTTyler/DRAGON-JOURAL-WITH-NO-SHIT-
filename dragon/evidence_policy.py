"""Claim-sensitive evidence topology for research candidates.

Unrecognised candidates retain the historic primary-plus-independent rule.
Only a narrowly detected direct official action or routine verified fact may
use one exact primary source; risky and scientific claims never enter that
exception.
"""

from __future__ import annotations


PRIMARY_TYPES = {"primary", "official", "paper"}
_RISK_MARKERS = (
    "corruption", "criminal", "guilt", "misconduct", "alleg", "accus",
    "impact", "major economic", "will have", "فساد", "جريمة", "إدانة", "اتهام", "اختلاس", "قتل", "إصابة", "أثر",
)
_OFFICIAL_MARKERS = (
    "official", "ministry", "government", "operator", "schedule", "timetable",
    "announc", "portal", "بلاغ", "وزارة", "الوزارة", "البوابة", "أعلنت",
    "اعلنت", "موعد", "نشرة", "ضوابط", "نتائج",
    "audit report", "تقرير تدقيق", "تقرير الافتحاص",
    "directive", "circular", "monitoring", "enforcement", "complaint",
    "توجيه", "دورية", "مراقبة", "شكاية", "إنفاذ",
)
_ROUTINE_MARKERS = ("schedule", "timetable", "warning", "forecast", "service", "registration", "procedure", "deadline", "application", "موعد", "نشرة", "توقع", "خدمة", "تسجيل", "إجراء", "أجل")


def candidate_evidence_policy(candidate: dict, sources_by_id: dict[str, dict], *, section_id: str | None = None) -> dict:
    """Return safe role requirements plus the claim that makes them material."""
    primary_ids = [item for item in candidate.get("primary_evidence_source_ids", []) if item in sources_by_id]
    text = " ".join(str(item) for item in [candidate.get("title", ""), *candidate.get("facts", []), *candidate.get("claims", [])]).casefold()
    explicit = str(candidate.get("claim_type") or candidate.get("story_type") or "").upper()
    risky = section_id == "science" or any(marker in text for marker in _RISK_MARKERS)
    direct_primary = any(str(sources_by_id[item].get("source_type") or "").casefold() in PRIMARY_TYPES for item in primary_ids)
    official_signal = any(marker in text for marker in _OFFICIAL_MARKERS)
    routine_signal = any(marker in text for marker in _ROUTINE_MARKERS)
    if section_id == "science" or "SCIENCE" in explicit or "STUDY" in explicit:
        claim_type, roles = "SCIENCE", ("PRIMARY", "INDEPENDENT")
    elif risky or any(token in explicit for token in ("ALLEGATION", "INVESTIGATION", "CONTESTED")):
        claim_type, roles = "SERIOUS_OR_CONTESTED", ("PRIMARY", "INDEPENDENT")
    elif direct_primary and official_signal:
        claim_type, roles = "DIRECT_OFFICIAL_ACTION", ("PRIMARY",)
    elif direct_primary and routine_signal:
        claim_type, roles = "ROUTINE_VERIFIED_FACT", ("PRIMARY",)
    else:
        claim_type, roles = "REPORTED_OR_INTERPRETIVE", ("PRIMARY", "INDEPENDENT")
    claims = candidate.get("claims", [])
    facts = candidate.get("facts", [])
    return {
        "claim_type": claim_type,
        "required_roles": list(roles),
        "blocking_claim": str((claims[0] if claims else None) or (facts[0] if facts else None) or candidate.get("title") or ""),
        "risky_claim_protection": claim_type in {"SCIENCE", "SERIOUS_OR_CONTESTED"},
    }
