"""Bounded, offline planning for evidence and editorial-breadth recovery."""

from __future__ import annotations

from collections import defaultdict

from dragon.source_coverage import desk_recovery_context
from dragon.evidence_policy import candidate_evidence_policy


DEFAULT_RECOVERY_POLICY = {"max_attempts_per_need": 1}


def _breadth_acquisition_plan(need: dict, packet: dict, intelligence: dict) -> dict:
    """Make a breadth gap an event-first, bounded discovery objective."""
    candidates = {
        f"{section.get('section_id')}:{candidate.get('id')}": candidate
        for section in packet.get("sections", [])
        for candidate in [*section.get("candidates", []), *section.get("recovery_candidates", [])]
    }
    exclusions = []
    for cluster in intelligence.get("event_clusters", []):
        labels = [str(candidates[key].get("title") or "") for key in cluster.get("candidate_keys", []) if key in candidates]
        exclusions.append({"event_id": cluster["event_id"], "candidate_keys": cluster.get("candidate_keys", []), "fingerprint": " | ".join(sorted(label for label in labels if label))})
    kind = str(need.get("kind") or "")
    is_morocco = "MOROCCO" in kind
    themes = (
        ["institutional action", "public service", "economy or infrastructure", "regional or local development"]
        if is_morocco else ["international institutional action", "geographically distinct development", "service or cultural significance"]
    )
    languages = ["ar", "fr"] if is_morocco else ["en", "ar"]
    return {
        "editorial_gap": "MOROCCO_BREADTH" if is_morocco else "DISTINCT_EVENT_BREADTH",
        "objective": "Discover a verified event in the edition window that is materially distinct from every excluded cluster.",
        "candidate_event_themes": themes,
        "query_families": ["institutional", "topical", "geographical", "consequence_oriented"],
        "languages": languages,
        "discovery_backends": ["searxng-general-search", "gdelt-doc", "public-rss-search"],
        "excluded_event_fingerprints": exclusions,
        "promotion_criteria": ["NEW_EVENT", "EXACT_PAGE", "SOURCE_IDENTIFIED", "DATE_RELEVANT", "CLAIM_POLICY_SATISFIED", "EDITORIAL_VALUE"],
        "acceptable_story_roles": ["brief", "normal", "analysis"],
    }


def _origins(candidate: dict, sources: dict[str, dict]) -> list[str]:
    source_ids = set().union(*(
        set(candidate.get(field, []))
        for field in (
            "discovery_source_ids", "verification_source_ids",
            "primary_evidence_source_ids", "independent_evidence_source_ids",
        )
    ))
    return sorted({str(sources[item].get("origin") or sources[item].get("url")) for item in source_ids if item in sources})


def _event_map(intelligence: dict) -> dict[str, str]:
    return {
        candidate_key: event["event_id"]
        for event in intelligence.get("event_clusters", [])
        for candidate_key in event.get("candidate_keys", [])
    }


def _selected(packet: dict) -> list[tuple[dict, dict]]:
    selected = []
    for section in packet.get("sections", []):
        if section.get("status") != "ACTIVE":
            continue
        candidate = next((item for item in section.get("candidates", []) if item.get("id") == section.get("selected_candidate_id")), None)
        if candidate is not None:
            selected.append((section, candidate))
    return selected


def build_recovery_plan(
    packet: dict,
    intelligence: dict,
    coverage: dict,
    readiness: dict,
    *,
    attempts_by_need: dict[str, int] | None = None,
    policy: dict | None = None,
) -> dict:
    """Describe the smallest honest follow-ups needed before article generation.

    It never performs discovery or changes a candidate. A later explicitly
    enabled executor may satisfy a need only by adding exact, independently
    verified sources to a new research packet.
    """
    attempts_by_need = attempts_by_need or {}
    policy = {**DEFAULT_RECOVERY_POLICY, **(policy or {})}
    maximum = int(policy["max_attempts_per_need"])
    source_by_id = {item["id"]: item for item in packet.get("sources", [])}
    events = _event_map(intelligence)
    needs: list[dict] = []
    for section in packet.get("sections", []):
        # A captured or demoted candidate is a research lead, not an active
        # publication commitment.  Creating P0 work for every NO_NEWS lead
        # made one malformed recovery observation regenerate endless needs.
        # Only the selected candidate of an ACTIVE section can block its
        # current edition; alternatives remain available for replacement.
        if section.get("status") == "ACTIVE":
            candidates = [item for item in section.get("candidates", []) if item.get("id") == section.get("selected_candidate_id")]
        elif section.get("status") == "NO_NEWS":
            # A material recovery lead may still earn a bounded attempt and
            # later reopen the desk.  A placeholder created from an empty
            # extraction cannot: it has neither an editorial claim nor a
            # stable event identity, and repeatedly generated P0 loops in all
            # three preserved failures.
            candidates = [
                item for item in section.get("recovery_candidates", [])
                if str(item.get("title") or "").strip().casefold() != "untitled research result"
            ]
        else:
            candidates = []
        for candidate in candidates:
            eligibility = candidate.get("evidence_eligibility", {})
            issues = set(eligibility.get("issues", []))
            evidence_policy = candidate.get("evidence_policy") or candidate_evidence_policy(
                candidate, source_by_id, section_id=section.get("section_id"),
            )
            roles = set(evidence_policy.get("required_roles", []))
            missing_role = "INDEPENDENT" if "INDEPENDENT" in roles and issues & {
                "INDEPENDENT_EVIDENCE_MISSING", "INDEPENDENT_EVIDENCE_UNKNOWN",
                "INDEPENDENT_EVIDENCE_TYPE_INVALID", "EVIDENCE_ROLE_SOURCE_OVERLAP",
                "EVIDENCE_ROLE_ORIGIN_OVERLAP",
            } else "PRIMARY" if "PRIMARY" in roles and issues & {
                "PRIMARY_EVIDENCE_MISSING", "PRIMARY_EVIDENCE_UNKNOWN", "PRIMARY_EVIDENCE_TYPE_INVALID",
            } else None
            if missing_role is None:
                continue
            key = f"CORROBORATE:{section['section_id']}:{candidate['id']}:{missing_role}"
            attempts = int(attempts_by_need.get(key, 0))
            desk = desk_recovery_context(coverage, section["section_id"])
            needs.append({
                "need_id": key,
                "kind": "FIND_INDEPENDENT_CORROBORATION" if missing_role == "INDEPENDENT" else "FIND_PRIMARY_ORIGINAL_EVIDENCE",
                "section_id": section["section_id"],
                "event_id": events.get(f"{section['section_id']}:{candidate['id']}"),
                "candidate_id": candidate["id"],
                "missing_evidence_role": missing_role,
                "priority": "P0_BLOCKING_EVIDENCE",
                "claim_type": evidence_policy.get("claim_type"),
                "publication_critical_claim": evidence_policy.get("blocking_claim"),
                "already_known_source_ids": sorted(set().union(*(
                    set(candidate.get(field, [])) for field in (
                        "discovery_source_ids", "verification_source_ids", "primary_evidence_source_ids", "independent_evidence_source_ids"
                    )
                ))),
                "already_known_origins": _origins(candidate, source_by_id),
                "topic_identifiers": [candidate.get("title", "")],
                "query_context": {
                    "entities": list(candidate.get("entities", [])),
                    "geography": list(candidate.get("geography", [])),
                    "event_terms": [
                        candidate.get("title", ""), *candidate.get("facts", []),
                        *candidate.get("claims", []),
                    ],
                    "research_date": packet.get("edition_date"),
                },
                "search_constraints": {
                    "must_use_exact_source_page": True,
                    "must_not_reuse_known_origin_for_both_roles": True,
                    **desk,
                },
                "attempt_count": attempts,
                "max_attempts": maximum,
                "stop_condition": "ROLE_EVIDENCE_ADDED_OR_ATTEMPTS_EXHAUSTED",
            })
    selected = _selected(packet)
    selected_events: dict[str, list[str]] = defaultdict(list)
    for section, candidate in selected:
        key = f"{section['section_id']}:{candidate['id']}"
        selected_events[events.get(key, f"UNCLUSTERED:{key}")].append(key)
    active_sections = {section["section_id"] for section, _candidate in selected}
    distinct_events = set(selected_events)
    for rule in readiness.get("coverage_rules", []):
        rule_events = {
            event_id for event_id, placements in selected_events.items()
            if any(placement.split(":", 1)[0] in set(rule["sections"]) for placement in placements)
        }
        missing = max(0, int(rule["minimum_active"]) - len(rule_events))
        for index in range(missing):
            need_id = f"BREADTH:{rule['id']}:{index + 1}"
            attempts = int(attempts_by_need.get(need_id, 0))
            eligible_sections = list(rule["sections"])
            route_context = desk_recovery_context(coverage, eligible_sections[index % len(eligible_sections)])
            needs.append({
                "need_id": need_id,
                "kind": f"NEED_{rule['id'].upper()}",
                "section_id": None,
                "event_id": None,
                "candidate_id": None,
                "missing_evidence_role": None,
                "already_known_source_ids": [],
                "already_known_origins": [],
                "topic_identifiers": list(rule["sections"]),
                "query_context": {"research_date": packet.get("edition_date"), "desk": eligible_sections},
                "search_constraints": {
                    "must_be_distinct_event": True,
                    "eligible_section_ids": eligible_sections,
                    "must_satisfy_primary_and_independent_evidence": True,
                    "configured_source_routes": route_context["configured_source_routes"],
                },
                "attempt_count": attempts,
                "max_attempts": maximum,
                "stop_condition": "DISTINCT_ELIGIBLE_EVENT_ADDED_OR_ATTEMPTS_EXHAUSTED",
            })
            needs[-1]["event_acquisition_plan"] = _breadth_acquisition_plan(needs[-1], packet, intelligence)
    # ``minimum_active_sections`` is the inherited V4 publication-item floor
    # (four leads plus six secondary treatments), not a count of underlying
    # events.  A front lead, a service item and an analysis may legitimately
    # treat the same event, so turning that item floor into a global distinct
    # event floor wrongly demands filler.  The article provider independently
    # enforces the placement floor.  Research recovery instead enforces the
    # semantic coverage rules above, each of which counts distinct events in
    # its own editorial family.
    exhausted = bool(needs) and all(item["attempt_count"] >= item["max_attempts"] for item in needs)
    return {
        "schema_version": 1,
        "status": "PASS" if not needs else "RESEARCH_INSUFFICIENT" if exhausted else "RECOVERY_REQUIRED",
        "edition_date": packet.get("edition_date"),
        "selected_active_sections": len(active_sections),
        "distinct_event_count": len(distinct_events),
        "duplicate_placements": [
            {"event_id": event_id, "candidate_keys": sorted(placements)}
            for event_id, placements in sorted(selected_events.items()) if len(placements) > 1
        ],
        "needs": needs,
        "article_generation_allowed": not needs,
    }


def validate_recovery_plan(value: dict) -> list[str]:
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        return ["RESEARCH_RECOVERY_ROOT_INVALID"]
    if value.get("status") not in {"PASS", "RECOVERY_REQUIRED", "RESEARCH_INSUFFICIENT"}:
        return ["RESEARCH_RECOVERY_STATUS_INVALID"]
    needs = value.get("needs")
    if not isinstance(needs, list) or value.get("article_generation_allowed") != (not needs):
        return ["RESEARCH_RECOVERY_NEEDS_INVALID"]
    issues = []
    for need in needs:
        required = {"need_id", "kind", "missing_evidence_role", "already_known_source_ids", "already_known_origins", "attempt_count", "max_attempts", "stop_condition"}
        if not isinstance(need, dict) or not required.issubset(need) or need["attempt_count"] < 0 or need["max_attempts"] < 1:
            issues.append("RESEARCH_RECOVERY_NEED_INVALID")
            continue
        if need["missing_evidence_role"] not in {None, "PRIMARY", "INDEPENDENT"}:
            issues.append("RESEARCH_RECOVERY_ROLE_INVALID")
        if set(need["already_known_source_ids"]) & set(need["already_known_origins"]):
            issues.append("RESEARCH_RECOVERY_IDENTITY_MIXED")
    if value["status"] == "PASS" and needs:
        issues.append("RESEARCH_RECOVERY_PASS_WITH_NEEDS")
    if value["status"] == "RESEARCH_INSUFFICIENT" and not all(item["attempt_count"] >= item["max_attempts"] for item in needs):
        issues.append("RESEARCH_RECOVERY_EXHAUSTION_INVALID")
    return sorted(set(issues))
