"""Bounded, offline planning for evidence and editorial-breadth recovery."""

from __future__ import annotations

from collections import defaultdict
from copy import deepcopy

from dragon.source_coverage import desk_recovery_context
from dragon.evidence_policy import candidate_evidence_policy
from dragon.editorial_functions import validated_function_names


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
    target_function = str(need.get("target_editorial_function") or "")
    function_markers = {
        "ACCOUNTABILITY": ("audit", "oversight", "regulator", "court", "procurement", "corruption", "رقابة", "افتحاص"),
        "SERVICE": ("registration", "deadline", "schedule", "service", "eligibility", "transport", "تسجيل", "أجل", "خدمة"),
    }.get(target_function, ())
    canonical_source_routes = [
        {
            "source_id": record.get("source_id"), "name": record.get("publisher") or record.get("title"),
            "url": record.get("canonical_url"), "origin": record.get("canonical_url"),
            "role": "PRIMARY", "source_class": "KNOWN_INSTITUTIONAL_PUBLISHER",
            "authority_class": "KNOWN_FROM_SOURCE_INTELLIGENCE",
        }
        for record in intelligence.get("source_records", [])
        if target_function and record.get("canonical_url") and record.get("source_type") in {"PRIMARY", "OFFICIAL", "primary", "official"}
        and any(marker in " ".join(str(record.get(key) or "") for key in ("publisher", "title", "claims_supported")).casefold() for marker in function_markers)
    ]
    if target_function == "ACCOUNTABILITY":
        return {
            "editorial_gap": "ACCOUNTABILITY_SERVICE_FUNCTION",
            "objective": "Discover one distinct, evidence-backed event that documents oversight, enforcement, audit, or another concrete accountability mechanism.",
            "target_editorial_function": target_function,
            "current_function_coverage": need.get("current_function_coverage", {}),
            "candidate_event_themes": ["audit or inspection finding", "regulatory or court enforcement", "procurement or public-spending scrutiny"],
            "query_families": ["institutional", "oversight", "public-record"],
            "languages": ["ar", "fr", "en"],
            "geography_scope": "GLOBAL_WITH_MOROCCO_PRIORITY",
            "discovery_backends": ["searxng-general-search", "gdelt-doc", "public-rss-search"],
            "excluded_event_fingerprints": exclusions,
            "promotion_criteria": ["NEW_EVENT", "EXACT_PAGE", "SOURCE_IDENTIFIED", "DATE_RELEVANT", "CLAIM_POLICY_SATISFIED", "EDITORIAL_VALUE", "FUNCTION_VALIDATED"],
            "acceptable_story_roles": ["brief", "normal", "analysis"],
            "canonical_source_routes": canonical_source_routes,
        }
    if target_function == "SERVICE":
        return {
            "editorial_gap": "ACCOUNTABILITY_SERVICE_FUNCTION",
            "objective": "Discover one distinct, evidence-backed operational change, deadline, access rule, warning, or procedure that gives readers practical action-oriented information.",
            "target_editorial_function": target_function,
            "current_function_coverage": need.get("current_function_coverage", {}),
            "candidate_event_themes": ["registration or application deadline", "public-service schedule or access change", "verified public warning or procedure"],
            "query_families": ["operational", "deadline", "access"],
            "languages": ["ar", "fr", "en"],
            "geography_scope": "GLOBAL_WITH_MOROCCO_PRIORITY",
            "discovery_backends": ["searxng-general-search", "gdelt-doc", "public-rss-search"],
            "excluded_event_fingerprints": exclusions,
            "promotion_criteria": ["NEW_EVENT", "EXACT_PAGE", "SOURCE_IDENTIFIED", "DATE_RELEVANT", "CLAIM_POLICY_SATISFIED", "EDITORIAL_VALUE", "FUNCTION_VALIDATED"],
            "acceptable_story_roles": ["brief", "normal", "analysis"],
            "canonical_source_routes": canonical_source_routes,
        }
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


def _function_coverage(selected_events: dict[str, list[tuple[str, dict]]]) -> dict[str, set[str]]:
    """Count validated editorial functions per distinct event, never by desk."""
    values = {"ACCOUNTABILITY": set(), "SERVICE": set(), "READER_VALUE": set()}
    for event_id, placements in selected_events.items():
        functions = set().union(*(validated_function_names(candidate) for _placement, candidate in placements))
        for name in values:
            if name in functions:
                values[name].add(event_id)
    return values


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
    # Mode-B event bundles are run-scoped research state.  A concrete event
    # whose evidence contract is terminally blocked remains visible, but the
    # corresponding semantic need may use a later bounded slot for a distinct
    # event.  This is not a candidate/evidence shortcut and never creates P0.
    blocked_by_function: dict[str, list[dict]] = {}
    pivot_attempts = {
        str(item.get("need_id")): int(item.get("count", 0))
        for item in packet.get("semantic_pivot_attempts", [])
        if isinstance(item, dict) and item.get("need_id")
    }
    for bundle in packet.get("event_evidence_bundles", []):
        if not isinstance(bundle, dict) or bundle.get("state") != "EVENT_EVIDENCE_BLOCKED":
            continue
        memory = bundle.get("blocked_event_memory") if isinstance(bundle.get("blocked_event_memory"), dict) else {
            "event_lead_id": bundle.get("event_lead_id"),
            "event_fingerprint": bundle.get("event_fingerprint"),
            "recovery_need_id": bundle.get("recovery_need_id"),
            "target_editorial_function": bundle.get("target_editorial_function"),
            "blocker": bundle.get("failure_reason"),
            "pivot_eligible": True,
            "normal_recovery_attempted": True,
        }
        function = str(memory.get("target_editorial_function") or bundle.get("target_editorial_function") or "").upper()
        if function and memory.get("pivot_eligible") and memory.get("normal_recovery_attempted"):
            blocked_by_function.setdefault(function, []).append(deepcopy(memory))
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
    selected_events: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    for section, candidate in selected:
        key = f"{section['section_id']}:{candidate['id']}"
        selected_events[events.get(key, f"UNCLUSTERED:{key}")].append((key, candidate))
    active_sections = {section["section_id"] for section, _candidate in selected}
    distinct_events = set(selected_events)
    function_coverage = _function_coverage(selected_events)
    for rule in readiness.get("coverage_rules", []):
        if rule.get("id") == "accountability_and_service":
            rule_events = function_coverage["ACCOUNTABILITY"] | function_coverage["SERVICE"]
        else:
            rule_events = {
                event_id for event_id, placements in selected_events.items()
                if any(placement.split(":", 1)[0] in set(rule["sections"]) for placement, _candidate in placements)
            }
        missing = max(0, int(rule["minimum_active"]) - len(rule_events))
        for index in range(missing):
            need_id = f"BREADTH:{rule['id']}:{index + 1}"
            attempts = int(attempts_by_need.get(need_id, 0))
            eligible_sections = list(rule["sections"])
            function_counts = {name: len(event_ids) for name, event_ids in function_coverage.items()}
            target_function = None
            route_section = eligible_sections[index % len(eligible_sections)]
            if rule.get("id") == "accountability_and_service":
                # The combined minimum stays intact.  Diversifying the first
                # two bounded attempts gives the acquisition path a fair
                # chance to find either missing journalistic function.
                ordered = sorted(("ACCOUNTABILITY", "SERVICE"), key=lambda name: (function_counts[name], name))
                target_function = ordered[index % len(ordered)]
                route_section = "investigations" if target_function == "ACCOUNTABILITY" else "service"
            route_context = desk_recovery_context(coverage, route_section, capability=target_function)
            needs.append({
                "need_id": need_id,
                "kind": f"NEED_{rule['id'].upper()}",
                "section_id": None,
                "event_id": None,
                "candidate_id": None,
                "recovery_mode": "DISCOVER_NEW_EVENT_FOR_SEMANTIC_NEED",
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
                    "configured_discovery_routes": route_context.get("configured_discovery_routes", []),
                },
                # Normal breadth owns its own geography policy.  This is
                # intentionally separate from the Super Investigation scope
                # guard and prevents that subsystem's metadata from leaking
                # into ordinary semantic acquisition.
                "geography_policy": "GLOBAL_WITH_MOROCCO_PRIORITY",
                "allowed_geographies": [],
                "scope_origin": "NORMAL_EDITORIAL_BREADTH",
                "scope_reason": "Edition-wide accountability/service coverage; Morocco is a priority, not an exclusivity gate.",
                "attempt_count": attempts,
                "max_attempts": maximum,
                "stop_condition": "DISTINCT_ELIGIBLE_EVENT_ADDED_OR_ATTEMPTS_EXHAUSTED",
            })
            if target_function:
                needs[-1].update({
                    "target_editorial_function": target_function,
                    "current_function_coverage": function_counts,
                    "acquisition_diversity_key": target_function,
                    "search_constraints": {
                        **needs[-1]["search_constraints"],
                        "expected_evidence_topology": "CLAIM_SENSITIVE_POLICY",
                    },
                })
                blocked = blocked_by_function.get(target_function, [])
                if blocked:
                    pivot_count = pivot_attempts.get(need_id, 0)
                    needs[-1].update({
                        "pivot_mode": "FIND_ALTERNATIVE_EVENT_FOR_SEMANTIC_NEED",
                        "blocked_event_memory": blocked,
                        "blocked_event_fingerprints": [
                            item for item in blocked
                            if item.get("event_fingerprint")
                        ],
                        "pivot_reason": "CURRENT_EVENT_EVIDENCE_BLOCKED_AFTER_BOUNDED_RECOVERY",
                        "pivot_attempt_count": pivot_count,
                    })
            needs[-1]["event_acquisition_plan"] = _breadth_acquisition_plan(needs[-1], packet, intelligence)
            if target_function and blocked_by_function.get(target_function):
                # Keep exclusions in the acquisition plan so all subsequent
                # strategies avoid reselecting the blocked event.  This is a
                # retrieval exclusion, never an evidence or source blacklist.
                needs[-1]["event_acquisition_plan"]["blocked_event_memory"] = deepcopy(blocked_by_function[target_function])
                existing = list(needs[-1]["event_acquisition_plan"].get("excluded_event_fingerprints", []))
                seen = {str(item.get("event_fingerprint") or "") for item in existing if isinstance(item, dict)}
                for item in blocked_by_function[target_function]:
                    fingerprint = item.get("event_fingerprint")
                    if fingerprint and str(fingerprint) not in seen:
                        existing.append({"event_id": item.get("event_lead_id"), "fingerprint": fingerprint, "blocker": item.get("blocker")})
                needs[-1]["event_acquisition_plan"]["excluded_event_fingerprints"] = existing
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
            {"event_id": event_id, "candidate_keys": sorted(placement for placement, _candidate in placements)}
            for event_id, placements in sorted(selected_events.items()) if len(placements) > 1
        ],
        "editorial_function_coverage": {
            name: {"event_ids": sorted(event_ids), "count": len(event_ids)}
            for name, event_ids in function_coverage.items()
        },
        "blocked_event_memory": [
            deepcopy(item)
            for values in blocked_by_function.values()
            for item in values
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
