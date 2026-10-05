"""Deterministic discovery targets for the untrusted provider research call.

This module projects existing V5 readiness and semantic contracts into a
provider-readable *discovery* brief.  It does not classify an event, alter a
coverage threshold, or create executable research work.
"""

from __future__ import annotations

from copy import deepcopy


ACCOUNTABILITY_CONTRACT = {
    "semantic_lane": "ACCOUNTABILITY",
    "qualifying_mechanisms": [
        "formal audit or inspection action or finding",
        "regulatory enforcement or sanction",
        "prosecution, court, or formal legal action",
        "formal investigation, complaint, directive, or circular",
        "procurement or public-accountability action",
        "equivalent concrete oversight mechanism tied to public or institutional power",
    ],
    "exclusions": [
        "institutional participation without a concrete accountability action",
        "conference or meeting attendance",
        "generic report without a current action or consequence",
        "historical finding without a current consequence",
        "commentary or opinion",
        "generic call for transparency",
        "index, listing, navigation, or home page",
    ],
    "discovery_objective": (
        "Find a current concrete accountability or oversight action and its exact "
        "original institutional artifact."
    ),
}

SERVICE_CONTRACT = {
    "semantic_lane": "SERVICE",
    "qualifying_mechanisms": [
        "service launch, activation, interruption, or restoration",
        "changed public access, registration, deadline, eligibility, or procedure",
        "official public warning or current schedule",
        "current operational implementation by a public service authority or operator",
    ],
    "exclusions": [
        "generic service description",
        "policy discussion without a current operational change",
        "index, listing, navigation, or home page",
        "future-only announcement when current operation is required",
        "secondary reporting that lacks required original support",
    ],
    "discovery_objective": (
        "Find a current actionable public-service event and its exact original "
        "institutional artifact."
    ),
}

# These are the existing DRAGON desks for the two semantic hard lanes.  A
# provider cannot satisfy a hard-lane disposition by relabeling a generic
# country or world candidate.
HARD_TARGET_SECTIONS = {
    "ACCOUNTABILITY": {"investigations", "opinion"},
    "SERVICE": {"service"},
}

SOURCE_EXPECTATIONS = {
    "original_primary": (
        "Prefer an exact issuer document or event-specific original institutional artifact; "
        "a homepage is discovery context, not a substitute."
    ),
    "current_dated_publication": (
        "Prefer a current dated publication whose stated event or effective date can be assessed."
    ),
    "independent_corroboration": (
        "When the existing claim-sensitive evidence contract requires corroboration, provide "
        "a distinct independent newsroom origin in addition to the original artifact."
    ),
    "context": (
        "Background, aggregation, navigation, and secondary context may guide discovery but "
        "cannot substitute for required evidence."
    ),
    "provider_role_status": "UNVERIFIED_SUGGESTION",
    "exact_url_preference": "EXACT_EVENT_DOCUMENT_OVER_HOMEPAGE",
}

TEMPORAL_GUIDANCE = {
    "publication_date": "Record the source publication date exactly.",
    "event_effective_date": (
        "When material, state the event or effective date in claim_supported; publication date "
        "is not by itself proof that the event is current."
    ),
    "current_eligibility": (
        "For a current target, do not present a future-only announcement as current operation."
    ),
}


def _coverage_rules(readiness: dict) -> list[dict]:
    rules = readiness.get("coverage_rules", []) if isinstance(readiness, dict) else []
    return [item for item in rules if isinstance(item, dict) and isinstance(item.get("id"), str)]


def _target(rule: dict, *, target_id: str, semantic_lane: str, hard: bool, objective: str) -> dict:
    return {
        "target_id": target_id,
        "coverage_rule_id": rule["id"],
        "semantic_lane": semantic_lane,
        "mandatory": True,
        "hard": hard,
        "current_status": "UNRESOLVED_PRE_DISCOVERY",
        "minimum_closure_requirement": {
            "minimum_distinct_events": int(rule.get("minimum_active", 0)),
            "eligible_sections": list(rule.get("sections", [])),
            "provider_cannot_close_need": True,
        },
        "discovery_objective": objective,
        **({
            "source_role_guidance": (
                "Prefer a current first-party operational artifact as PRIMARY where the existing evidence contract requires it; "
                "independent reporting can corroborate but cannot replace required PRIMARY evidence."
            )
        } if semantic_lane == "SERVICE" else {}),
    }


def build_research_targeting(edition_date: str, readiness: dict) -> dict:
    """Build ordered, provider-visible discovery targets from V5 contracts.

    The provider runs before source intelligence and recovery planning, so every
    readiness gap is truthfully ``UNRESOLVED_PRE_DISCOVERY``.  The ordering is
    discovery guidance only: it neither changes the combined coverage rule nor
    gives provider-originated work scheduler authority.
    """
    if not isinstance(edition_date, str) or len(edition_date) != 10:
        raise ValueError("PROVIDER_TARGETING_DATE_INVALID")
    rules = _coverage_rules(readiness)
    by_id = {item["id"]: item for item in rules}
    targets: list[dict] = []
    combined = by_id.get("accountability_and_service")
    if combined:
        targets.extend([
            _target(
                combined,
                target_id="HARD:ACCOUNTABILITY",
                semantic_lane="ACCOUNTABILITY",
                hard=True,
                objective=ACCOUNTABILITY_CONTRACT["discovery_objective"],
            ),
            _target(
                combined,
                target_id="HARD:SERVICE",
                semantic_lane="SERVICE",
                hard=True,
                objective=SERVICE_CONTRACT["discovery_objective"],
            ),
        ])
    for rule in rules:
        if rule["id"] == "accountability_and_service":
            continue
        targets.append(_target(
            rule,
            target_id=f"BREADTH:{rule['id']}",
            semantic_lane="BREADTH",
            hard=False,
            objective=(
                "Find an additional distinct qualifying event for the "
                f"{rule['id']} coverage requirement."
            ),
        ))
    return {
        "schema_version": 1,
        "as_of_date": edition_date,
        "ordering": "HARD_UNRESOLVED_THEN_REMAINING_BREADTH",
        "unresolved_targets": targets,
        "accountability_contract": deepcopy(ACCOUNTABILITY_CONTRACT),
        "service_contract": deepcopy(SERVICE_CONTRACT),
        "source_expectations": deepcopy(SOURCE_EXPECTATIONS),
        "claim_source_mapping": {
            "field": "claim_supported",
            "requirement": (
                "For every source, state the precise candidate claim that exact source is intended to support."
            ),
        },
        "temporal_guidance": deepcopy(TEMPORAL_GUIDANCE),
        "provider_output": {
            "status": "DISCOVERY_INTELLIGENCE_ONLY",
            "provider_reported_roles_are_unverified": True,
            "can_close_research_need": False,
            "can_emit_executor_actions": False,
            "hard_target_dispositions_required": True,
            "hard_target_disposition_statuses": [
                "CANDIDATES_PRODUCED", "NO_QUALIFYING_CANDIDATE_FOUND",
            ],
        },
    }
