"""Offline, hash-bound research closure. Absence never creates evidence or stories.

The finite obligation is the native acquisition ladder, plus selected exact
fetches and their follow-ups. A round cap is not a successful search outcome.
"""

from copy import deepcopy
from datetime import datetime
import hashlib
import json

from dragon.deep_research_executor import FETCH_ACTIONS, _publisher_family, plan_research_actions, reconcile_discovery_leads
from dragon.editorial_functions import classify_event_functions, validated_function_names
from dragon.evidence_policy import candidate_evidence_policy
from dragon.provider_targeting import HARD_TARGET_SECTIONS
from dragon.source_intelligence import build_source_intelligence


LANES = ("ACCOUNTABILITY", "SERVICE")
TERMINAL = {"VALIDATED_EVENT", "VERIFIED_NO_QUALIFYING_EVENT"}
STATES = TERMINAL | {
    "BLOCKED_TECHNICAL_FAILURE", "BLOCKED_CONTRACT_FAILURE",
    "BLOCKED_BUDGET_BEFORE_REQUIRED_SEARCH", "UNRESOLVED",
    "BLOCKED_MANDATORY_PROTOCOL_CAPACITY",
}
EMPTY_RESULTS = {"SEARXNG_NO_MATCHES", "RSS_NO_MATCHES"}
REQUEST_FIELDS = (
    "action_id", "job_id", "action_type", "target", "query", "discovery_channel",
    "search_language", "recovery_need_id", "strategy_index", "strategy_count",
    "target_editorial_function", "research_date",
)


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":")).encode("utf-8")).hexdigest()


def packet_digest(packet: dict) -> str:
    return digest({k: v for k, v in packet.items()
                   if k not in {"research_recovery", "research_finality", "source_intelligence", "research_plan", "deep_research"}})


def _lane(action: dict) -> str:
    return str(action.get("target_editorial_function") or "").upper()


def _request(action: dict) -> dict:
    request = {key: action.get(key) for key in REQUEST_FIELDS}
    request["research_date"] = action.get("research_date") or (action.get("event_context") or {}).get("research_date")
    return request


def _observations(epochs: list[dict]) -> list[dict]:
    return [o for epoch in epochs for job in epoch.get("execution", {}).get("jobs", [])
            for o in job.get("observations", [])]


def _time(value: object) -> float | None:
    try:
        parsed = datetime.fromisoformat(str(value))
        return parsed.timestamp() if parsed.tzinfo is not None else None
    except (ValueError, TypeError, OverflowError):
        return None


def _events(packet: dict, observations: list[dict], epochs: list[dict]) -> dict[str, list[str]]:
    """Consume the existing gates; provider role labels alone cannot validate."""
    result = {lane: set() for lane in LANES}
    exact_actions = {a["action_id"]: a for epoch in epochs for job in epoch.get("execution", {}).get("jobs", [])
                     for a in job.get("actions", []) if a.get("action_type") in FETCH_ACTIONS}
    observations = [o for o in observations if (o.get("provenance") or {}).get("action_id") in exact_actions]
    sources = {s["id"]: s for s in packet.get("sources", [])}
    event_map = {key: cluster["event_id"] for cluster in build_source_intelligence(packet).get("event_clusters", [])
                 for key in cluster.get("candidate_keys", [])}
    for section in packet.get("sections", []):
        if section.get("status") != "ACTIVE":
            continue
        for candidate in section.get("candidates", []):
            if candidate.get("id") != section.get("selected_candidate_id"):
                continue
            functions = validated_function_names(candidate)
            if not functions or candidate.get("evidence_eligibility", {}).get("status") != "ELIGIBLE":
                continue
            policy = candidate_evidence_policy(candidate, sources, section_id=section.get("section_id"))
            selected = []
            for role in policy["required_roles"]:
                ids = candidate.get("primary_evidence_source_ids" if role == "PRIMARY" else "independent_evidence_source_ids", [])
                exact = [o for o in observations if o.get("source_id") in ids
                         and o.get("validation_state") == "VALIDATED_EVIDENCE"
                         and o.get("extraction_status") in {"FETCHED", "RETRIEVED"}
                         and o.get("content_hash") and o.get("extracted_text")
                         and (o.get("temporal_relevance") or {}).get("active_on_edition_date") is True
                         and (o.get("source_role_resolution") or {}).get("evidence_role") == role
                         and o.get("evidence_relation") == "SUPPORTS"
                         and o.get("directness") == "DIRECT_STATEMENT"
                         and (role != "INDEPENDENT" or (o.get("source_role_resolution") or {}).get("independence_state") == "INDEPENDENT_ORIGINAL_REPORTING")]
                if not exact:
                    break
                selected.append(exact[0])
            else:
                if len({o.get("origin") for o in selected}) != len(selected) or any(not o.get("origin") for o in selected):
                    continue
                if len({_publisher_family(o) for o in selected}) != len(selected) or any(not _publisher_family(o) for o in selected):
                    continue
                # Classifier assignments must be backed by the observed pages,
                # not by a provider's headline or declared semantic function.
                linked_ids = {o.get("source_id") for o in observations
                              if o.get("validation_state") == "VALIDATED_EVIDENCE"
                              and (o.get("temporal_relevance") or {}).get("active_on_edition_date") is True
                              and o.get("evidence_relation") == "SUPPORTS" and o.get("directness") == "DIRECT_STATEMENT"
                              and o.get("content_hash") and o.get("extracted_text")}
                grounded = {f["function"] for f in candidate.get("editorial_functions", [])
                            if set(f.get("evidence_source_ids", [])) <= linked_ids}
                key = f"{section.get('section_id')}:{candidate['id']}"
                event_id = event_map.get(key, key)
                for lane in functions & grounded & set(LANES):
                    result[lane].add(str(event_id))
    # New-event bundles are already machine-gated by the native executor.
    # Require their exact observations as well; a naked state label is no proof.
    for bundle in packet.get("event_evidence_bundles", []):
        if bundle.get("state") != "EVENT_VALIDATED":
            continue
        observation_ids = set(bundle.get("observations") or [])
        evidence_ids = set(bundle.get("evidence_ids") or [])
        exact = [o for o in observations if o.get("observation_id") in observation_ids and o.get("source_id") in evidence_ids]
        if not exact or {o.get("source_id") for o in exact} != evidence_ids or any(
            o.get("validation_state") != "VALIDATED_EVIDENCE"
            or not o.get("content_hash") or not o.get("extracted_text")
            or o.get("evidence_relation") != "SUPPORTS" or o.get("directness") != "DIRECT_STATEMENT"
            or (o.get("temporal_relevance") or {}).get("active_on_edition_date") is not True for o in exact
        ):
            continue
        roles = bundle.get("source_roles", [])
        required_roles = set((bundle.get("evidence_policy") or {}).get("required_roles") or [])
        if not required_roles or not required_roles <= {r.get("role") for r in roles}:
            continue
        if any(r.get("role") == "INDEPENDENT" and r.get("independence_state") != "INDEPENDENT_ORIGINAL_REPORTING" for r in roles):
            continue
        families = [{r.get("publisher_family") for r in roles if r.get("role") == role} for role in ("PRIMARY", "INDEPENDENT")]
        if families[0] & families[1]:
            continue
        identity = bundle.get("event_id") or bundle.get("event_lead_id")
        if not identity:
            continue
        mapped = next((event_map.get(f"{s.get('section_id')}:{c.get('id')}")
                       for s in packet.get("sections", []) for c in s.get("candidates", [])
                       if c.get("event_id") == identity), None)
        for lane in validated_function_names(bundle) & set(LANES):
            result[lane].add(str(mapped or identity))
    return {lane: sorted(values) for lane, values in result.items()}


def build_research_finality(packet: dict, *, targeting: dict, epochs: list[dict],
                            config: dict, closed_at: str, provider_failure: dict | None = None,
                            other_research_need_ids: list[str] | None = None) -> dict:
    """Derive lane decisions from preserved machine inputs; no I/O or clock."""
    inputs = deepcopy({"targeting": targeting, "epochs": epochs, "config": config,
                       "closed_at": closed_at, "provider_failure": provider_failure,
                       "other_research_need_ids": other_research_need_ids})
    observations = deepcopy(_observations(epochs))
    acquisition = next((e.get('execution', {}).get('round_execution_budget', {}).get('hard_acquisition')
                        for e in reversed(epochs)
                        if e.get('execution', {}).get('round_execution_budget', {}).get('hard_acquisition')), None)
    def current_required(action):
        if not acquisition:
            return True
        from dragon.hard_acquisition import core, required_for_path
        if core(action):
            return True
        identity = acquisition.get('action_paths', {}).get(action['action_id']) or action.get('acquisition_path_id') or action.get('provider_candidate_id')
        if not identity:
            identity = next((p['path_id'] for p in acquisition['paths'].values()
                             if action['action_id'] in p['actions']), None)
        selected = acquisition['selected'].get(_lane(action))
        return bool(identity == selected and acquisition['paths'][identity]['state'] != 'FAILED'
                    and action['action_id'] in acquisition['paths'][identity]['actions']
                    and required_for_path(action, acquisition['paths'][identity]))
    all_actions = [a for epoch in epochs for job in epoch.get("execution", {}).get("jobs", []) for a in job.get("actions", [])]
    # Reconcile cross-epoch inspections in a derived view. Earlier checkpoints
    # and historical inputs remain immutable; no-event still needs exact proof.
    lead_evaluations = reconcile_discovery_leads(observations, all_actions) if any(a.get("required_protocol") for a in all_actions) else []
    events = _events(packet, observations, epochs)
    targets = targeting.get("unresolved_targets", [])
    required_lanes = sorted({t.get("semantic_lane") for t in targets
                             if t.get("hard") and t.get("mandatory") and t.get("semantic_lane") in LANES})
    audits = packet.get("provider_response_validation", {}).get("hard_targets", [])
    results = packet.get("hard_target_results", [])
    lanes = {}
    for lane in required_lanes:
        targets_for_lane = [t for t in targets if t.get("semantic_lane") == lane and t.get("hard") and t.get("mandatory")]
        target_id = targets_for_lane[0]["target_id"]
        dispositions = [r for r in results if r.get("target_id") == target_id]
        disposition = dispositions[0] if len(dispositions) == 1 else {}
        audit = next((a for a in audits if a.get("target_id") == target_id), {})
        provider_attempts = disposition.get("search_attempts", [])
        contract_errors = []
        if targeting.get("as_of_date") != packet.get("edition_date"):
            contract_errors.append("TARGET_REQUEST_DATE_MISMATCH")
        if len(targets_for_lane) != 1 or len(dispositions) != 1 or disposition.get("status") not in {"CANDIDATES_PRODUCED", "NO_QUALIFYING_CANDIDATE_FOUND"}:
            contract_errors.append("HARD_TARGET_DISPOSITION_MISSING_OR_INVALID")
        if not audit or audit.get("target_error") or audit.get("target_contract_status") not in {"PASS", "PARTIAL"}:
            contract_errors.append("TARGET_NORMALIZATION_NOT_ACCEPTED")
        if audit.get("target_disposition_effective") != disposition.get("status") or audit.get("accepted_candidate_count") != len(disposition.get("candidate_matches", [])):
            contract_errors.append("TARGET_NORMALIZATION_AUDIT_INCONSISTENT")
        if not provider_attempts or any(not a.get("query") or not a.get("purpose") for a in provider_attempts):
            contract_errors.append("PROVIDER_SEARCH_ATTEMPTS_MISSING")
        if disposition.get("status") == "NO_QUALIFYING_CANDIDATE_FOUND" and (not disposition.get("no_qualifying_reason") or disposition.get("candidate_matches")):
            contract_errors.append("NO_RESULT_DISPOSITION_INCONSISTENT")
        technical = [deepcopy(provider_failure)] if provider_failure else []
        required, executed, deferred, optional_deferred, routes, epoch_records = {}, {}, {}, [], [], []
        budget_cut = False
        protocol_errors = []
        for epoch in epochs:
            execution = epoch.get("execution", {})
            planned = [a for job in epoch.get("state", {}).get("jobs", [])
                       for a in plan_research_actions(job, config) if _lane(a) == lane and current_required(a)]
            for action in planned:
                required[action["action_id"]] = _request(action)
            actual = [a for job in execution.get("jobs", []) for a in job.get("actions", []) if _lane(a) == lane]
            all_actual = [a for job in execution.get("jobs", []) for a in job.get("actions", [])]
            budget = execution.get("round_execution_budget") or {}
            cap = config["executor"]["maximum_actions_per_round"]
            if actual and (len(all_actual) > cap or budget.get("maximum_actions_per_round", cap) != cap or budget.get("budget_increased") is True):
                protocol_errors.append("NATIVE_ROUND_BUDGET_NOT_PRESERVED")
            if actual and budget.get("executed_action_ids") is not None and set(budget["executed_action_ids"]) != {a["action_id"] for a in all_actual}:
                protocol_errors.append("EXECUTION_BUDGET_LEDGER_MISMATCH")
            if len({a["action_id"] for a in actual}) != len(actual):
                protocol_errors.append("DUPLICATE_EXECUTED_ACTION_ID")
            for action in actual:
                executed[action["action_id"]] = _request(action)
                # Dynamic follow-ups are required exact acquisitions too. They
                # cannot stand in for an unexecuted core strategy.
                required.setdefault(action["action_id"], _request(action))
                routes.append({"epoch": epoch.get("epoch"), **_request(action)})
            missing = [a for a in planned if a["action_id"] not in executed]
            all_deferred = execution.get("deferred_actions", []) or epoch.get("schedule", {}).get("deferred_actions", [])
            dynamic_deferred = [(item.get("action") or {}) for item in budget.get("dynamic_actions_deferred", [])]
            for action in dynamic_deferred:
                if _lane(action) == lane:
                    if acquisition and not current_required(action):
                        optional_deferred.append(deepcopy(action))
                        continue
                    concrete_followup = (action.get("originating_event_lead_id")
                        or action.get("required_lead_inspection") or action.get("dynamic_recovery")
                        or (action.get("provenance_requirements") or {}).get("required_role") in {"PRIMARY", "INDEPENDENT"}
                        or action.get("query_intent") == "LISTING_TO_DETAIL_EXACT_ARTIFACT")
                    if concrete_followup:
                        required.setdefault(action["action_id"], _request(action))
                        deferred[action["action_id"]] = deepcopy(action)
                        if action["action_id"] not in executed:
                            budget_cut = True
                    else:
                        # Native broad-route/channel expansions are contingent
                        # on spare capacity. The complete core ladder remains
                        # mandatory; found concrete candidates cannot disappear.
                        optional_deferred.append(deepcopy(action))
            for action in all_deferred:
                if _lane(action) == lane:
                    deferred[action["action_id"]] = deepcopy(action)
            if any(a["action_id"] in deferred for a in missing):
                budget_cut = True
            epoch_records.append({"epoch": epoch.get("epoch"), "execution_status": execution.get("status"),
                "required_core_actions": [a["action_id"] for a in planned],
                "executed_actions": [a["action_id"] for a in actual],
                "round_budget": deepcopy(execution.get("round_execution_budget") or {}),
                "job_progress": [deepcopy(j.get("recovery_strategy_progress", [])) for j in execution.get("jobs", [])
                                 if any(_lane(a) == lane for a in j.get("actions", []))]})
        for lead in lead_evaluations:
            if acquisition:
                selected = acquisition['selected'].get(lane)
                path = acquisition['paths'].get(selected, {})
                active_urls = {a.get('target') for a in path.get('actions', {}).values()}
                if lead.get('url') not in active_urls:
                    continue
            if lead["parent_action_id"] in executed and lead["state"] == "BLOCKED_CONTRACT_FAILURE":
                protocol_errors.append("REQUIRED_LEAD_CONTRACT_FAILURE:" + str(lead["observation_id"]))
        lane_observations = [o for o in observations if (o.get("provenance") or {}).get("action_id") in executed]
        response_ids = {(o.get("provenance") or {}).get("action_id") for o in lane_observations}
        for identity, request in executed.items():
            if request != required[identity]:
                protocol_errors.append("EXECUTED_REQUEST_CHANGED:" + identity)
            if identity not in response_ids:
                technical.append({"code": "EXECUTED_ACTION_WITHOUT_OBSERVATION", "action_id": identity})
        # An observed later success of the same physical request can resolve
        # a failure. An unrelated empty search cannot clear a broken backend.
        resolved_failures = []
        for o in lane_observations:
            reason = o.get("discovery_reason") or o.get("title")
            identity = (o.get("provenance") or {}).get("action_id")
            if reason in EMPTY_RESULTS and executed.get(identity, {}).get("action_type") in FETCH_ACTIONS:
                protocol_errors.append("SEARCH_EMPTY_RESULT_ON_EXACT_FETCH:" + str(identity))
            if o.get("kind") == "DEAD_END" and reason not in EMPTY_RESULTS:
                action_id = (o.get("provenance") or {}).get("action_id")
                request = executed.get(action_id, {})
                failed_at = _time(o.get("observed_at"))
                resolved = None
                for later in lane_observations:
                    other = executed.get((later.get("provenance") or {}).get("action_id"), {})
                    responded_at = _time(later.get("observed_at"))
                    if failed_at is None or responded_at is None or responded_at <= failed_at:
                        continue
                    if request.get("action_type") in FETCH_ACTIONS:
                        same_request = bool(request.get("target")) and other.get("action_type") in FETCH_ACTIONS and other.get("target") == request["target"]
                        success = later.get("extraction_status") in {"FETCHED", "RETRIEVED"} and later.get("extracted_text") and later.get("content_hash")
                    else:
                        same_request = all(request.get(k) == other.get(k) for k in ("action_type", "query", "discovery_channel", "search_language", "research_date"))
                        success = later.get("kind") != "DEAD_END" or later.get("discovery_reason") in EMPTY_RESULTS
                    if same_request and success:
                        resolved = later
                        break
                if resolved is None:
                    technical.append({"code": reason, "action_id": action_id,
                                      "detail": o.get("discovery_detail"), "observation_id": o.get("observation_id")})
                else:
                    resolved_failures.append({"code": reason, "failed_observation_id": o.get("observation_id"),
                        "resolving_observation_id": resolved.get("observation_id"), "resolved_at": resolved.get("observed_at"),
                        "content_hash": resolved.get("content_hash")})
        candidate_audit = []
        pending_candidates = []
        for match in disposition.get("candidate_matches", []):
            candidate_id = match.get("candidate_id")
            candidate_actions = [a for epoch in epochs for j in epoch.get("execution", {}).get("jobs", [])
                                 for a in j.get("actions", []) if _lane(a) == lane and str(a.get("provider_candidate_id") or "").split(":")[-1] == candidate_id]
            exact_ids = {a["action_id"] for a in candidate_actions}
            pages = [o for o in lane_observations if (o.get("provenance") or {}).get("action_id") in exact_ids and o.get("extracted_text")]
            functions = {f["function"] for o in pages for f in classify_event_functions(title=o.get("title"), facts=[o["extracted_text"]],
                         evidence_source_ids=[o.get("source_id") or o.get("observation_id")], exact_page_validated=True)}
            rejected = bool(pages) and lane not in functions
            candidate_audit.append({"candidate_id": candidate_id, "state": "SEMANTICALLY_REJECTED" if rejected else "QUALIFICATION_UNRESOLVED",
                                    "observations": [{"observation_id": o.get("observation_id"), "content_hash": o.get("content_hash")} for o in pages]})
            if not rejected and not events[lane]:
                pending_candidates.append(candidate_id)
        if not events[lane]:
            rejected_ids = {a["candidate_id"] for a in candidate_audit if a["state"] == "SEMANTICALLY_REJECTED"}
            for section in packet.get("sections", []):
                for candidate in [*section.get("candidates", []), *section.get("recovery_candidates", [])]:
                    if candidate.get("id") in rejected_ids:
                        continue
                    # Potential semantics may block absence; they never grant
                    # positive evidence. Unfinished candidate validation stays open.
                    potential = {f["function"] for f in classify_event_functions(title=candidate.get("title"),
                        facts=candidate.get("facts", []), evidence_source_ids=candidate.get("discovery_source_ids", []), exact_page_validated=True)}
                    if lane in validated_function_names(candidate) | potential:
                        pending_candidates.append(f"{section.get('section_id')}:{candidate.get('id')}")
        # Discovery-only search results remain explicitly uninspected leads.
        # A completed ladder cannot erase a plausible unresolved concrete event.
        pending_events = [o.get("observation_id") for o in lane_observations
                          if (o.get("event_state") in {"CONCRETE_EVENT", "EVENT_LEAD", "EVENT_QUALIFIED"}
                              or (o.get("kind") == "LEAD" and not o.get("extracted_text") and o.get("url")))
                          and o.get("relevance_status") != "REJECTED"
                          and o.get("validation_state") != "VALIDATED_EVIDENCE"
                          and (o.get("temporal_relevance") or {}).get("active_on_edition_date") is not False]
        if acquisition:
            # Include late selected artifacts before computing exact hash-bound
            # reuse. Receipt completion alone is never acquisition proof.
            for path in acquisition['paths'].values():
                if path['lane'] == lane and path['path_id'] == acquisition['selected'].get(lane) and path['state'] != 'FAILED':
                    for action in path['actions'].values():
                        if current_required(action):
                            required.setdefault(action['action_id'], _request(action))
        reused = {}
        # A deferred duplicate exact fetch may reuse the very same fetched,
        # hash-bound artifact from this lane/edition. Search queries are never
        # substituted, and reuse is recorded separately from execution.
        for identity, request in required.items():
            if identity in executed or request.get("action_type") not in FETCH_ACTIONS or not request.get("target"):
                continue
            equivalent_ids = {key for key, a in executed.items() if a.get("action_type") in FETCH_ACTIONS
                              and a.get("target") == request["target"] and a.get("research_date") == request.get("research_date")}
            exact = [o for o in lane_observations if (o.get("provenance") or {}).get("action_id") in equivalent_ids
                     and o.get("extraction_status") in {"FETCHED", "RETRIEVED"} and o.get("content_hash") and o.get("extracted_text")]
            if exact:
                reused[identity] = [{"observation_id": o.get("observation_id"), "content_hash": o["content_hash"],
                                     "executed_action_id": o["provenance"]["action_id"]} for o in exact]
        missing = sorted(set(required) - set(executed) - set(reused))
        recovery_actions = [r for r in required.values() if r.get("recovery_need_id")]
        checks = {
            "target_requested": len(targets_for_lane) == 1,
            "provider_disposition_observed": len(dispositions) == 1 and bool(disposition),
            "provider_search_attempts_recorded": bool(provider_attempts) and not any(not a.get("query") or not a.get("purpose") for a in provider_attempts),
            "normalization_succeeded": bool(audit) and audit.get("target_contract_status") in {"PASS", "PARTIAL"} and not audit.get("target_error"),
            "bounded_acquisition_recovery_completed": bool(recovery_actions) and not missing and not protocol_errors and set(executed).issubset(response_ids),
            "no_qualifying_candidate_survived": not pending_candidates and not pending_events,
            "no_unresolved_technical_failure": not technical,
            "no_unresolved_contract_failure": not contract_errors and not protocol_errors,
            "required_search_capacity_available": not missing,
            "no_qualifying_evidence_bundle": not events[lane] and not any(b.get("state") == "EVENT_VALIDATED" and lane in validated_function_names(b) for b in packet.get("event_evidence_bundles", [])),
            "closure_timestamp_recorded": _time(closed_at) is not None,
        }
        if technical:
            state, reason = "BLOCKED_TECHNICAL_FAILURE", "REQUIRED_RESEARCH_FAILED"
        elif contract_errors or protocol_errors:
            state, reason = "BLOCKED_CONTRACT_FAILURE", "RESEARCH_CONTRACT_NOT_SATISFIED"
        elif acquisition and acquisition.get('blocker') and not events[lane]:
            state, reason = 'BLOCKED_MANDATORY_PROTOCOL_CAPACITY', acquisition['blocker']
        elif acquisition and missing:
            state, reason = 'BLOCKED_BUDGET_BEFORE_REQUIRED_SEARCH', 'SEARCH_CUT_SHORT_BY_CAPACITY'
        elif events[lane]:
            state, reason = "VALIDATED_EVENT", "EXISTING_EVENT_EVIDENCE_GATES_PASSED"
        elif missing and budget_cut:
            state, reason = "BLOCKED_BUDGET_BEFORE_REQUIRED_SEARCH", "SEARCH_CUT_SHORT_BY_CAPACITY"
        elif all(checks.values()):
            state, reason = "VERIFIED_NO_QUALIFYING_EVENT", "BOUNDED_PROTOCOL_COMPLETED_WITH_NO_EVENT"
        else:
            state, reason = "UNRESOLVED", "UNRESOLVED_SEARCH_NOT_EXHAUSTED"
        lanes[lane] = {
            "target_id": target_id, "state": state, "reason": reason, "conditions": checks,
            **({'active_acquisition_path': acquisition['selected'].get(lane),
                'candidate_paths': [deepcopy(p) for p in acquisition['paths'].values() if p['lane'] == lane],
                'minimum_remaining_required_actions': acquisition['minimum_remaining_required_actions'],
                'capacity_blocker': acquisition.get('blocker')} if acquisition else {}),
            "missing_conditions": [key for key, passed in checks.items() if not passed],
            "provider_disposition": disposition.get("status"), "provider_attempts": deepcopy(provider_attempts),
            "provider_attempt_provenance": "PROVIDER_REPORTED_NOT_INDEPENDENTLY_OBSERVED",
            "candidate_contract_quarantine": deepcopy(audit.get("rejected_candidates", [])),
            "candidate_audit": candidate_audit, "pending_candidates": pending_candidates, "pending_events": pending_events,
            "required_actions": list(required.values()), "executed_actions": list(executed.values()),
            "missing_action_ids": missing, "deferred_actions": list(deferred.values()), "routes": routes,
            "reused_exact_acquisitions": reused,
            "deferred_optional_expansions": optional_deferred,
            "action_counts": {"required": len(required), "executed": len(executed), "missing": len(missing),
                              "reused_exact_acquisitions": len(reused), "optional_expansions_deferred": len(optional_deferred)},
            "failures": technical, "contract_failures": contract_errors + protocol_errors,
            "resolved_failures": resolved_failures,
            "recovery_epochs": epoch_records, "validated_event_ids": events[lane],
            "closed_at": closed_at if state in TERMINAL else None,
            "research_date": packet.get("edition_date"),
            "search_window": {"edition_date": packet.get("edition_date"),
                              "temporal_guidance": deepcopy(targeting.get("temporal_guidance") or {}),
                              "queries": sorted({r.get("query") for r in required.values() if r.get("query")})},
            "source_universe": "Native configured acquisition ladder and its selected exact follow-ups",
            "limitation": "No qualifying event found within the recorded protocol, source universe, time window and bounded resources; not proof of global absence.",
            "uninspected_discovery_leads": [o.get("observation_id") for o in lane_observations if o.get("kind") == "LEAD" and not o.get("extracted_text")],
        }
    complete = bool(required_lanes) and all(lanes[lane]["state"] in TERMINAL for lane in required_lanes)
    overall_complete = complete and not other_research_need_ids
    event_ids = sorted(set().union(*(set(events[lane]) for lane in required_lanes)))
    record = {"schema_version": 1, "protocol_version": "research-finality-v1", "research_date": packet.get("edition_date"),
        "packet_sha256": packet_digest(packet), "inputs": inputs, "inputs_sha256": digest(inputs),
        "required_lanes": required_lanes, "lanes": lanes,
        "combined_research_coverage_complete": complete,
        "combined_event_coverage": {"event_ids": event_ids, "count": len(event_ids), "by_lane": events},
        "hard_lane_research_finality": "COMPLETE" if complete else "BLOCKED",
        "research_finality": "COMPLETE" if overall_complete else "BLOCKED",
        "editorial_handoff_eligible": overall_complete,
        "unresolved_other_research_need_ids": sorted(other_research_need_ids or []),
        "editorial_absence_plan": [{"lane": lane, "action": "OMIT_UNSUPPORTED_STORY", "eligible_section_ids": sorted(HARD_TARGET_SECTIONS[lane]),
                                    "activate_section": False} for lane in required_lanes if lanes[lane]["state"] == "VERIFIED_NO_QUALIFYING_EVENT"]}
    if lead_evaluations:
        record["lead_evaluations"] = lead_evaluations
    record["decision_sha256"] = digest(record)
    return record


def editorial_absent_sections(research: dict) -> set[str]:
    """Negative closure allocates no full story to the absent function's desks."""
    record = (research.get("research_recovery") or {}).get("research_finality") or {}
    return {section for item in record.get("editorial_absence_plan", [])
            for section in item.get("eligible_section_ids", [])}


def validate_research_finality(record: dict, packet: dict) -> list[str]:
    try:
        expected = build_research_finality(packet, **record["inputs"])
    except (KeyError, TypeError, ValueError, AttributeError):
        return ["RESEARCH_FINALITY_INPUTS_INVALID"]
    return [] if record == expected else ["RESEARCH_FINALITY_REPLAY_MISMATCH"]


def apply_research_finality(plan: dict, record: dict) -> dict:
    """Keep historical event deficits visible; satisfy only hard research needs."""
    result = deepcopy(plan)
    result["research_finality"] = deepcopy(record)
    result["hard_lane_research_closure_state"] = {lane: value["state"] for lane, value in record["lanes"].items()}
    result["event_coverage_needs"] = deepcopy(plan["needs"])
    if record["combined_research_coverage_complete"]:
        result["needs"] = [need for need in plan["needs"]
                           if need.get("kind") != "NEED_ACCOUNTABILITY_AND_SERVICE"]
    allowed = record["combined_research_coverage_complete"] and not result["needs"]
    result["article_generation_allowed"] = allowed
    result["editorial_handoff_eligible"] = allowed
    result["status"] = "PASS" if allowed else "RESEARCH_INSUFFICIENT" if result["needs"] and all(
        n["attempt_count"] >= n["max_attempts"] for n in result["needs"]) else "RECOVERY_REQUIRED"
    return result
