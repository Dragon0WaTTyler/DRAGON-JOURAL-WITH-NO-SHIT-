"""Deterministic scope guard for future persistent super investigations."""

from __future__ import annotations


MOROCCO_SCOPE_MARKERS = {
    "morocco", "maroc", "المغرب", "meknes", "meknès", "مكناس", "fes-meknes",
    "fès-meknès", "فاس مكناس",
}
ALLOWED_CONCLUSIONS = (
    "SUPPORTED", "NOT_SUPPORTED", "NO_EVIDENCE_OF_MISCONDUCT",
    "EXPLANATION_FOUND", "UNRESOLVED", "PUBLICATION_READY",
)


def _matches_scope(value: object) -> bool:
    text = str(value or "").casefold()
    return any(marker in text for marker in MOROCCO_SCOPE_MARKERS)


def evaluate_super_investigation_scope(lead: dict) -> dict:
    """Classify eligibility without inferring scandal or wrongdoing."""
    geography = lead.get("geography", [])
    entities = lead.get("entities", [])
    connections = lead.get("scope_connections", [])
    direct = any(_matches_scope(item) for item in geography)
    supporting = [
        item for item in connections
        if isinstance(item, dict)
        and _matches_scope(item.get("connected_scope"))
        and bool(str(item.get("relationship") or "").strip())
        and bool(item.get("direct_evidence_source_ids"))
    ]
    foreign_entities = [
        item for item in entities
        if isinstance(item, dict) and not _matches_scope(item.get("geography"))
    ]
    supported_names = {
        str(item.get("entity") or "").strip().casefold() for item in supporting
    }
    allowed_foreign = [
        item for item in foreign_entities
        if str(item.get("name") or "").strip().casefold() in supported_names
    ]
    excluded_foreign = [item for item in foreign_entities if item not in allowed_foreign]
    eligible = (direct or bool(supporting)) and not excluded_foreign
    return {
        "schema_version": 1,
        "status": "ELIGIBLE" if eligible else "NOT_ELIGIBLE",
        "mode": "SUPER_INVESTIGATION" if eligible else "NORMAL_DEEP_RESEARCH",
        "scope_rule": "MOROCCO + MEKNES ONLY",
        "direct_scope_match": direct,
        "supporting_scope_connections": supporting,
        "foreign_entities": allowed_foreign,
        "excluded_foreign_entities": excluded_foreign,
        "allowed_conclusions": list(ALLOWED_CONCLUSIONS),
        "reason": (
            "Direct Morocco/Meknes scope or evidence-linked supporting connection."
            if eligible else "No direct evidence-linked Morocco/Meknes scope."
        ),
    }
