"""Conservative, evidence-bound editorial-function classification.

These functions describe the journalistic work an exact, validated event can
perform.  They are deliberately not desk labels and never turn a discovery
lead into publication evidence by themselves.
"""

from __future__ import annotations

from typing import Iterable


CLASSIFIER_VERSION = "editorial-functions-v1"
VALIDATED = "VALIDATED"


def _text(parts: Iterable[object]) -> str:
    return " ".join(str(part or "") for part in parts).casefold()


def _contains(text: str, markers: tuple[str, ...]) -> list[str]:
    return [marker for marker in markers if marker in text]


_ACCOUNTABILITY_MECHANISMS = (
    "audit", "inspection", "oversight", "regulator", "regulatory", "enforcement",
    "sanction", "procurement", "ombudsman", "prosecution", "prosecutor",
    "monitoring", "directive", "circular", "complaint", "investigation",
    "parliamentary inquiry", "public accounts", "anti-corruption", "court ruling",
    "cour des comptes", "inspection générale", "contrôle", "régulateur",
    "sanction", "marché public", "médiateur", "poursuite", "parquet",
    "افتحاص", "تدقيق", "رقابة", "هيئة تنظيم", "عقوبة", "صفقة عمومية",
    "وسيط", "متابعة قضائية", "النيابة", "مكافحة الفساد", "لجنة برلمانية",
    "مراقبة", "توجيه", "دورية", "شكاية", "تحقيق",
)
_PUBLIC_POWER = (
    "public", "government", "ministry", "municipal", "authority", "state",
    "administration", "official", "institution", "parliament",
    "حكومة", "وزارة", "جماعة", "سلطة", "إدارة", "مؤسسة", "برلمان",
)
_PARTICIPATION_MARKERS = (
    "participation", "participated", "participate", "took part", "attended",
    "participe", "participé", "participer", "مشاركة", "يشارك", "شاركت",
)
_ACCOUNTABILITY_ACTION_MARKERS = (
    "audit report", "audit finding", "audit findings", "inspection report", "inspection finding",
    "enforcement", "sanction", "procurement", "ombudsman", "prosecution", "prosecutor",
    "monitoring", "directive", "circular", "complaint", "investigation", "court ruling",
    "rapport d'audit", "rapport d'inspection", "constat d'audit", "sanction", "marché public",
    "poursuite", "parquet", "dورية", "شكاية", "تحقيق", "صفقة عمومية", "افتحاص",
)
_ROUTINE_CONCENTRATION = (
    "projet de concentration", "notification de concentration", "merger notification",
    "concentration notification", "routine merger", "routine concentration",
    "مشروع تركيز اقتصادي", "إشعار بعملية تركيز", "تبليغ عملية تركيز",
)
_SUBSTANTIVE_ACCOUNTABILITY = (
    "sanction", "enforcement", "investigation", "audit finding", "inspection finding",
    "prosecution", "court ruling", "inquiry", "anti-corruption", "enquête",
    "abus de position", "pratique anticoncurrentielle", "injonction", "amende",
    "عقوبة", "غرامة", "تحقيق", "افتحاص", "فساد", "حكم قضائي", "ممارسات منافية للمنافسة",
)
_SERVICE_ACTIONS = (
    "registration", "register", "deadline", "eligibility", "eligible", "apply",
    "application", "schedule", "timetable", "opening hours", "opens", "closes",
    "procedure", "appointment", "service interruption", "service restoration",
    "water supply", "electricity supply", "outage", "disruption", "resumed",
    "restoration", "warning", "admission",
    "inscription", "date limite", "éligibilité", "horaire", "procédure",
    "candidature", "alerte", "ouverture", "fermeture", "rendez-vous",
    "rétablissement", "interruption", "reprise de service",
    "تسجيل", "آخر أجل", "اجل", "أهلية", "طلب", "جدول", "موعد", "إجراء",
    "فتح", "إغلاق", "انقطاع", "استئناف", "استعادة", "تحذير", "ولوج", "مباراة",
)


def classify_event_functions(
    *,
    title: object,
    facts: Iterable[object],
    evidence_source_ids: Iterable[object],
    exact_page_validated: bool,
) -> list[dict]:
    """Return auditable semantic functions for one already-validated event.

    The caller supplies only exact-page, claim-policy-safe evidence.  The
    classifier still requires a concrete mechanism/action, so a government
    policy announcement, airport statistic, generic opinion, or broad topic
    label cannot pass merely because it contains a fashionable word.
    """
    title_text = str(title or "").strip()
    fact_values = [str(item).strip() for item in facts if str(item or "").strip()]
    sources = sorted({str(item) for item in evidence_source_ids if str(item or "").strip()})
    # A headline can start a lead, but never close a semantic function.  The
    # exact page must contribute a separate concrete fact.
    supporting_facts = [fact for fact in fact_values if fact.casefold() != title_text.casefold()]
    if not exact_page_validated or not title_text or not supporting_facts or not sources:
        return []
    text = _text([title_text, *supporting_facts])
    records: list[dict] = []
    accountability = _contains(text, _ACCOUNTABILITY_MECHANISMS)
    power = _contains(text, _PUBLIC_POWER)
    participation_only = _contains(text, _PARTICIPATION_MARKERS) and not _contains(text, _ACCOUNTABILITY_ACTION_MARKERS)
    routine_concentration_only = _contains(text, _ROUTINE_CONCENTRATION) and not _contains(text, _SUBSTANTIVE_ACCOUNTABILITY)
    if accountability and power and not participation_only and not routine_concentration_only:
        records.append({
            "function": "ACCOUNTABILITY", "status": VALIDATED,
            "reason": "Concrete oversight/enforcement mechanism tied to public or institutional power.",
            "supporting_event_facts": supporting_facts[:3], "evidence_source_ids": sources,
            "classifier_version": CLASSIFIER_VERSION,
            "signals": {"mechanism": accountability[:3], "public_power": power[:3]},
        })
    service = _contains(text, _SERVICE_ACTIONS)
    if service:
        records.append({
            "function": "SERVICE", "status": VALIDATED,
            "reason": "Concrete, reader-actionable deadline, access rule, schedule, warning, or procedure.",
            "supporting_event_facts": supporting_facts[:3], "evidence_source_ids": sources,
            "classifier_version": CLASSIFIER_VERSION,
            "signals": {"practical_action": service[:3]},
        })
        records.append({
            "function": "READER_VALUE", "status": VALIDATED,
            "reason": "The validated service function provides practical reader value.",
            "supporting_event_facts": supporting_facts[:3], "evidence_source_ids": sources,
            "classifier_version": CLASSIFIER_VERSION,
            "signals": {"overlap": ["SERVICE"]},
        })
    return records


def validated_function_names(candidate: dict) -> set[str]:
    """Return only complete, versioned function assignments from a candidate."""
    values = candidate.get("editorial_functions", []) if isinstance(candidate, dict) else []
    result = set()
    for item in values:
        if not isinstance(item, dict):
            continue
        name = str(item.get("function") or "")
        if (
            name in {"ACCOUNTABILITY", "SERVICE", "READER_VALUE"}
            and item.get("status") == VALIDATED
            and item.get("classifier_version") == CLASSIFIER_VERSION
            and item.get("reason")
            and item.get("supporting_event_facts")
            and item.get("evidence_source_ids")
        ):
            result.add(name)
    return result
