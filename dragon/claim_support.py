"""Deterministic exact-claim support matching.

The resolver only locates candidate passages and classifies their linguistic
relationship to a requested proposition.  It never assigns a source role or
promotes evidence; callers must still apply the normal publisher, temporal,
event, and claim policies.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import re
from typing import Any


_STOP = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with", "that", "this", "is", "was", "were", "are", "be", "by", "as", "at", "from", "into", "de", "des", "du", "la", "le", "les", "et", "en", "dans", "pour", "par", "que", "من", "في", "على", "إلى", "عن", "و", "ال", "هو", "هي", "تم", "قد", "أن", "إن",
}
_NEGATION = re.compile(r"\b(?:not|no|never|didn't|did not|denied|deny|denies|رفض|تنفي|نفى|لم|لن|لا)\b", re.I)
_MODAL = re.compile(r"\b(?:may|might|could|will|would|plans? to|planned to|expects? to|expected to|proposes? to|proposed to|قد|ربما|سوف|سي|ينوي|يعتزم|متوقع|مقترح)\b", re.I)
_ATTRIBUTION = re.compile(r"\b(?:according to|reported by|reports that|alleged(?:ly)?|alleges?|claims? that|said|cited|بحسب|وفقا ل|أفاد|قال|زعمت|حسب)\b", re.I)


def _tokens(value: Any) -> list[str]:
    result = []
    for token in re.findall(r"[\w\u0600-\u06ff]+(?:[-'][\w\u0600-\u06ff]+)?", str(value or "").casefold()):
        if len(token) > 2 and token not in _STOP:
            result.append(token)
    return result


def _numbers(value: Any) -> list[str]:
    return re.findall(r"\d+(?:[.,]\d+)?(?:\s*(?:billion|million|bn|mn|مليار|مليون))?", str(value or "").casefold())


def _number_value(value: str) -> Decimal | None:
    match = re.match(r"([\d.,]+)\s*(billion|million|bn|mn|مليار|مليون)?", value.casefold().replace(" ", ""))
    if not match:
        return None
    try:
        number = Decimal(match.group(1).replace(",", ""))
    except InvalidOperation:
        return None
    unit = match.group(2) or ""
    if unit in {"billion", "bn", "مليار"}:
        number *= Decimal("1000000000")
    elif unit in {"million", "mn", "مليون"}:
        number *= Decimal("1000000")
    return number


def normalize_claim(claim: Any) -> dict:
    """Expose deterministic claim components without inventing facts."""
    text = str(claim or "").strip()
    return {
        "text": text,
        "subject": text,
        "predicate": None,
        "object": None,
        "event_type": None,
        "actors": [],
        "numbers": _numbers(text),
        "dates": re.findall(r"\b(?:19|20)\d{2}(?:[-/]\d{1,2}(?:[-/]\d{1,2})?)?\b", text),
        "locations": [],
        "document_ids": re.findall(r"\b[A-Z]{1,5}[-/]\d{1,}[A-Z\d/-]*\b", text),
        "quoted_phrases": re.findall(r"[\"“](.*?)[\"”]", text),
        "tokens": _tokens(text),
    }


def _passages(raw: dict) -> list[dict]:
    text = str(raw.get("text") or raw.get("extracted_text") or raw.get("content") or "").strip()
    passages = [part.strip() for part in re.split(r"\n\s*\n|(?<=[.!؟。])\s+(?=[A-ZÀ-ÖØ-ÞА-Я\u0600-\u06ff])", text) if part.strip()]
    result = [{"locator": {"paragraph": index}, "text": part, "source": "BODY"} for index, part in enumerate(passages, 1)]
    structured = raw.get("structured_fields") if isinstance(raw.get("structured_fields"), dict) else {}
    for key in ("paragraphs", "list", "items", "rows", "table_rows"):
        values = structured.get(key)
        if not isinstance(values, list):
            continue
        for index, value in enumerate(values, 1):
            content = " ".join(str(item or "") for item in value.values()) if isinstance(value, dict) else str(value or "")
            if content.strip():
                result.append({"locator": {"structure": key, "index": index}, "text": content.strip(), "source": "STRUCTURED"})
    return result


def _numeric_match(claim: str, passage: str) -> bool:
    claim_numbers = [_number_value(item) for item in _numbers(claim)]
    page_numbers = [_number_value(item) for item in _numbers(passage)]
    claim_numbers = [item for item in claim_numbers if item is not None]
    page_numbers = [item for item in page_numbers if item is not None]
    return not claim_numbers or any(item in page_numbers for item in claim_numbers)


def resolve_claim_support(raw: dict, *, claim: Any = None, claim_family: Any = None) -> dict:
    """Return bounded passage candidates and an evidence-neutral support state."""
    explicit = raw.get("support_locator") or raw.get("claim_locator") or raw.get("exact_support_locator")
    target = str(claim or raw.get("claim") or claim_family or raw.get("title") or "").strip()
    components = normalize_claim(target)
    target_tokens = set(components["tokens"])
    if explicit:
        return {
            "state": "CLAIM_SUPPORT_FOUND", "support_type": "DIRECT_SUPPORT", "locator": explicit,
            "passage": None, "matched_terms": sorted(target_tokens), "candidate_passages": [],
            "claim": components, "diagnosis": "SUPPORT_PRESENT_LOCATOR_SUPPLIED",
        }
    if not target_tokens:
        return {"state": "CLAIM_SUPPORT_NOT_FOUND", "support_type": "NO_SUPPORT", "locator": None, "passage": None, "matched_terms": [], "candidate_passages": [], "claim": components, "diagnosis": "TARGET_CLAIM_TOO_VAGUE"}
    candidates = []
    for passage in _passages(raw):
        text = passage["text"]
        words = set(_tokens(text))
        matched = target_tokens & words
        if not matched:
            continue
        ratio = len(matched) / max(1, len(target_tokens))
        if ratio < 0.34 and len(matched) < 3:
            continue
        candidates.append({**passage, "matched_terms": sorted(matched), "match_ratio": round(ratio, 3)})
    candidates.sort(key=lambda item: (-len(item["matched_terms"]), -item["match_ratio"], str(item["locator"])))
    if not candidates:
        return {"state": "CLAIM_SUPPORT_NOT_FOUND", "support_type": "NO_SUPPORT", "locator": None, "passage": None, "matched_terms": [], "candidate_passages": [], "claim": components, "diagnosis": "SUPPORT_GENUINELY_ABSENT"}
    best = candidates[0]
    text = best["text"]
    matched_terms = best["matched_terms"]
    if not _numeric_match(target, text):
        return {"state": "CLAIM_SUPPORT_AMBIGUOUS", "support_type": "AMBIGUOUS", "locator": best["locator"], "passage": text, "matched_terms": matched_terms, "candidate_passages": candidates[:5], "claim": components, "reason": "NUMERIC_MISMATCH", "diagnosis": "TARGET_CLAIM_TOO_SPECIFIC"}
    if _NEGATION.search(text):
        return {"state": "CLAIM_SUPPORT_FOUND", "support_type": "CONTRADICTS", "locator": best["locator"], "passage": text, "matched_terms": matched_terms, "candidate_passages": candidates[:5], "claim": components, "reason": "NEGATED_ASSERTION", "diagnosis": "CONTRADICTORY_SOURCE"}
    if _MODAL.search(text):
        return {"state": "CLAIM_SUPPORT_AMBIGUOUS", "support_type": "AMBIGUOUS", "locator": best["locator"], "passage": text, "matched_terms": matched_terms, "candidate_passages": candidates[:5], "claim": components, "reason": "MODAL_OR_FUTURE_ASSERTION", "diagnosis": "TARGET_CLAIM_TOO_SPECIFIC"}
    if _ATTRIBUTION.search(text):
        return {"state": "CLAIM_SUPPORT_AMBIGUOUS", "support_type": "PARTIAL_SUPPORT", "locator": best["locator"], "passage": text, "matched_terms": matched_terms, "candidate_passages": candidates[:5], "claim": components, "reason": "ATTRIBUTED_ASSERTION", "diagnosis": "SUPPORT_PRESENT_LOCATOR_FOUND"}
    if best["match_ratio"] >= 0.6 or len(matched_terms) >= 4:
        return {"state": "CLAIM_SUPPORT_FOUND", "support_type": "DIRECT_SUPPORT", "locator": best["locator"], "passage": text, "matched_terms": matched_terms, "candidate_passages": candidates[:5], "claim": components, "diagnosis": "SUPPORT_PRESENT_EXTRACTION_LOSS" if best["source"] == "STRUCTURED" else "SUPPORT_PRESENT_LOCATOR_FOUND"}
    return {"state": "CLAIM_SUPPORT_AMBIGUOUS", "support_type": "CONTEXT_ONLY", "locator": best["locator"], "passage": text, "matched_terms": matched_terms, "candidate_passages": candidates[:5], "claim": components, "reason": "INSUFFICIENT_PROPOSITION_MATCH", "diagnosis": "CONTEXT_ONLY"}


__all__ = ["normalize_claim", "resolve_claim_support"]
