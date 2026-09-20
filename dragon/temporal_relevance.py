"""Evidence-bound temporal relevance for exact research pages."""

from __future__ import annotations

from datetime import date
import re
from typing import Iterable


TEMPORAL_TYPES = {
    "PUBLICATION_TIME", "EVENT_TIME", "EFFECTIVE_START", "EFFECTIVE_END",
    "DEADLINE", "ACTIVE_ON_EDITION_DATE", "TEMPORAL_RELEVANCE_UNRESOLVED",
    "PUBLICATION_WINDOW", "ACTIVE_OPERATIONAL_WINDOW", "ACTIVE_DEADLINE_WINDOW",
    "CONTINUING_EVENT_NEW_DEVELOPMENT", "EVENT_EXPIRED",
}

_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5,
    "juin": 6, "juillet": 7, "août": 8, "aout": 8, "septembre": 9, "octobre": 10,
    "novembre": 11, "décembre": 12, "decembre": 12,
    # Arabic publication dates in the source corpus use both Maghrebi and
    # pan-Arabic month spellings. These are unambiguous calendar tokens.
    "يناير": 1, "فبراير": 2, "مارس": 3, "أبريل": 4, "ابريل": 4,
    "ماي": 5, "يونيو": 6, "يوليو": 7, "يوليوز": 7, "غشت": 8,
    "أغسطس": 8, "اغسطس": 8, "شتنبر": 9, "سبتمبر": 9,
    "أكتوبر": 10, "اكتوبر": 10, "نونبر": 11, "نوفمبر": 11,
    "دجنبر": 12, "ديسمبر": 12,
}

_TEXT_DATE = r"(\d{4}-\d{2}-\d{2}|\d{1,2}\s+[A-Za-zÀ-ÿ\u0600-\u06ff]+\s+\d{4})"
_ARABIC_MONTH_PATTERN = "|".join(sorted((re.escape(name) for name in _MONTHS if re.search(r"[\u0600-\u06ff]", name)), key=len, reverse=True))
_ARABIC_DEADLINE_PATTERN = re.compile(
    rf"(?:آخر\s+أجل|إلى\s+غاية|تنتهي[\s\S]{{0,120}}?)\s*(?P<day>\d{{1,2}})\s+(?P<month>{_ARABIC_MONTH_PATTERN})\s+(?P<year>\d{{4}}|الجاري)",
    re.IGNORECASE,
)


def _date_value(value: object) -> str | None:
    text = str(value or "").strip()
    match = re.search(r"(\d{4}-\d{2}-\d{2})", text)
    if match:
        try:
            date.fromisoformat(match.group(1))
            return match.group(1)
        except ValueError:
            return None
    match = re.search(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b", text)
    if match:
        try:
            return date(int(match.group(3)), int(match.group(2)), int(match.group(1))).isoformat()
        except ValueError:
            return None
    match = re.search(r"\b(\d{1,2})\s+([A-Za-zÀ-ÿ\u0600-\u06ff]+)\s+(\d{4})\b", text)
    if match and match.group(2).casefold() in _MONTHS:
        try:
            return date(int(match.group(3)), _MONTHS[match.group(2).casefold()], int(match.group(1))).isoformat()
        except ValueError:
            return None
    return None


def _first_date(parts: Iterable[object]) -> str | None:
    return next((parsed for item in parts if (parsed := _date_value(item))), None)


def _arabic_deadline_from_text(text: str, publication: str | None) -> str | None:
    """Resolve only labelled Arabic deadline forms with trusted year context.

    ``الجاري`` is document-relative, never execution-relative: its year is
    available only when the exact page has a publication date in the same
    named month.  This prevents a retrieval date from silently manufacturing
    a deadline for an otherwise undated historical page.
    """
    for match in _ARABIC_DEADLINE_PATTERN.finditer(text):
        month = _MONTHS.get(match.group("month").casefold())
        if month is None:
            continue
        year_token = match.group("year")
        if year_token == "الجاري":
            reference = _date_value(publication)
            if not reference:
                continue
            reference_date = date.fromisoformat(reference)
            if reference_date.month != month:
                continue
            year = reference_date.year
        else:
            year = int(year_token)
        try:
            return date(year, month, int(match.group("day"))).isoformat()
        except ValueError:
            continue
    return None


def evaluate_temporal_relevance(raw: dict, edition_date: str, *, exact_text: str | None = None) -> dict:
    """Classify currentness without inventing dates or treating guidance as news."""
    edition = _date_value(edition_date)
    metadata = raw.get("article_metadata") if isinstance(raw.get("article_metadata"), dict) else {}
    structured = raw.get("structured_fields") if isinstance(raw.get("structured_fields"), dict) else {}
    publication = _first_date((raw.get("published_at"), raw.get("publication_date"), metadata.get("publication_date"), structured.get("publication_date")))
    text = " ".join(str(item or "") for item in (exact_text, raw.get("text"), raw.get("extracted_text"), raw.get("claim")))
    values = {
        "PUBLICATION_TIME": publication,
        "EVENT_TIME": _first_date((raw.get("event_time"), raw.get("event_date"), metadata.get("event_time"), structured.get("event_time"))),
        "EFFECTIVE_START": _first_date((raw.get("effective_start"), metadata.get("effective_start"), structured.get("effective_start"))),
        "EFFECTIVE_END": _first_date((raw.get("effective_end"), metadata.get("effective_end"), structured.get("effective_end"))),
        "DEADLINE": _first_date((raw.get("deadline"), metadata.get("deadline"), structured.get("deadline"))),
        # A continuing story is current only when the exact page supplies a
        # dated material development.  This is deliberately separate from
        # publication time so an old, still-valid framework cannot qualify.
        "NEW_DEVELOPMENT_TIME": _first_date((
            raw.get("new_development_date"), raw.get("material_development_date"),
            metadata.get("new_development_date"), metadata.get("material_development_date"),
            structured.get("new_development_date"), structured.get("material_development_date"),
        )),
    }
    arabic_deadline = _arabic_deadline_from_text(text, publication)
    if not values["DEADLINE"] and arabic_deadline:
        values["DEADLINE"] = arabic_deadline
    # Explicit labelled dates in exact text are admissible source evidence.
    labelled = {
        "EFFECTIVE_START": rf"(?:effective|from|starts?|open(?:s)?|ابتداء|من)\D{{0,30}}{_TEXT_DATE}",
        "EFFECTIVE_END": rf"(?:effective until|through|until|ends?|to|إلى|حتى)\D{{0,30}}{_TEXT_DATE}",
        "DEADLINE": rf"(?:deadline|last date|date limite|آخر أجل|أجل)\D{{0,30}}{_TEXT_DATE}",
    }
    for key, pattern in labelled.items():
        # ``إلى غاية`` and ``تنتهي`` are the demonstrated Arabic deadline
        # forms.  Do not also record their date as a generic effective end.
        if key == "EFFECTIVE_END" and arabic_deadline:
            continue
        if not values[key]:
            match = re.search(pattern, text, re.I)
            values[key] = _date_value(match.group(1)) if match else None
    def result(**extra: object) -> dict:
        return {
            **extra,
            "publication_time": values["PUBLICATION_TIME"],
            "event_time": values["EVENT_TIME"],
            "effective_start": values["EFFECTIVE_START"],
            "effective_end": values["EFFECTIVE_END"],
            "deadline": values["DEADLINE"],
            "new_development_time": values["NEW_DEVELOPMENT_TIME"],
            "dates": values,
            "edition_date": edition_date,
        }
    if not edition:
        return result(active_on_edition_date=False, temporal_eligibility_type="TEMPORAL_RELEVANCE_UNRESOLVED", rejection_reason="TEMPORAL_RELEVANCE_UNRESOLVED", evidence=[])
    evidence = [key for key, value in values.items() if value]
    start, end, deadline = values["EFFECTIVE_START"], values["EFFECTIVE_END"], values["DEADLINE"]
    development = values["NEW_DEVELOPMENT_TIME"]
    continuing_markers = (
        "new development", "new decision", "updated", "update", "renewed",
        "announced", "enforcement", "finding", "decision", "complaint",
        "مستجد", "تحديث", "قرار", "إجراء", "شكوى", "نتيجة",
        "nouveau", "mise à jour", "décision", "plainte", "résultat",
    )
    # A page published after the edition cutoff was unavailable to that
    # edition. Its inferred operational dates cannot make it retroactively
    # eligible.
    if publication and publication > edition:
        kind, active, reason = "TEMPORAL_RELEVANCE_UNRESOLVED", False, "PUBLICATION_AFTER_EDITION_DATE"
    elif start and end and start <= edition <= end:
        kind, active, reason = "ACTIVE_OPERATIONAL_WINDOW", True, "EXPLICIT_EFFECTIVE_INTERVAL_INCLUDES_EDITION_DATE"
    elif deadline:
        kind, active, reason = ("ACTIVE_DEADLINE_WINDOW", True, "EXPLICIT_DEADLINE_REMAINS_OPEN_ON_EDITION_DATE") if deadline >= edition else ("EVENT_EXPIRED", False, "EXPLICIT_DEADLINE_PRECEDES_EDITION_DATE")
    elif end and end >= edition and any(marker in text.casefold() for marker in ("ongoing", "open", "current", "active", "جار", "مفتوح")):
        kind, active, reason = "ACTIVE_OPERATIONAL_WINDOW", True, "EXPLICIT_ACTIVE_PERIOD_REMAINS_OPEN_ON_EDITION_DATE"
    elif development and development <= edition and any(marker in text.casefold() for marker in continuing_markers):
        kind, active, reason = "CONTINUING_EVENT_NEW_DEVELOPMENT", True, "DATED_MATERIAL_DEVELOPMENT_ON_CONTINUING_EVENT"
    elif publication and publication[:7] == edition[:7]:
        kind, active, reason = "PUBLICATION_WINDOW", True, "PUBLICATION_TIME_IN_EDITION_MONTH"
    elif publication:
        kind, active, reason = "TEMPORAL_RELEVANCE_UNRESOLVED", False, "NO_EXPLICIT_ACTIVE_WINDOW"
    else:
        kind, active, reason = "TEMPORAL_RELEVANCE_UNRESOLVED", False, "NO_EXPLICIT_TEMPORAL_SIGNAL"
    return result(
        active_on_edition_date=active,
        temporal_eligibility_type=kind,
        rejection_reason=None if active else reason,
        evidence=evidence,
        reason=reason,
        source_text_provenance=text[:500] if evidence and active else None,
        temporal_evidence_fields=evidence,
    )
