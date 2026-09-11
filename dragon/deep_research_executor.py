"""Bounded, provider-neutral execution beneath the Deep Research Engine.

The executor can use injected adapters to discover or retrieve public material.
It never treats discovery as publication evidence and never calls an editorial
provider.  Fixture adapters make the state transitions deterministic in tests;
the optional HTTP adapter only executes direct fetch actions through DRAGON's
existing safe fetch/extract path.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from typing import Protocol
from urllib.parse import urlsplit

from dragon.deep_research import advance_research_job
from dragon.discovery import DiscoveryError, fetch_and_extract_source
from dragon.research_recovery import build_recovery_plan
from dragon.source_intelligence import build_source_intelligence, normalize_url


ACTION_TYPES = {
    "SEARCH_DISCOVERY", "FETCH_URL", "FETCH_CONFIGURED_SOURCE",
    "SEARCH_OFFICIAL_SOURCE", "SEARCH_INDEPENDENT_COVERAGE",
    "SEARCH_ARCHIVE_OR_CATALOG", "FOLLOW_REFERENCE", "EXTRACT_DOCUMENT",
    "CHECK_CONTRADICTION", "RECOVER_PRIMARY_SOURCE",
    "RECOVER_INDEPENDENT_SOURCE", "FIND_DISTINCT_EVENT",
}
SEARCH_ACTIONS = {
    "SEARCH_DISCOVERY", "SEARCH_OFFICIAL_SOURCE", "SEARCH_INDEPENDENT_COVERAGE",
    "SEARCH_ARCHIVE_OR_CATALOG", "CHECK_CONTRADICTION", "RECOVER_PRIMARY_SOURCE",
    "RECOVER_INDEPENDENT_SOURCE", "FIND_DISTINCT_EVENT",
}
FETCH_ACTIONS = {"FETCH_URL", "FETCH_CONFIGURED_SOURCE", "FOLLOW_REFERENCE", "EXTRACT_DOCUMENT"}
OBSERVATION_CLASSES = {
    "LEAD", "POTENTIAL_EVIDENCE", "CONTEXT", "CONTRADICTION", "DUPLICATE",
    "IRRELEVANT", "DEAD_END",
}


class ResearchExecutorError(RuntimeError):
    pass


class ResearchAdapter(Protocol):
    """A non-generative adapter that returns zero or more raw retrieval results."""

    def execute(self, action: dict) -> list[dict]: ...


def _stable_id(prefix: str, *parts: object) -> str:
    text = "\0".join(str(item) for item in parts)
    return f"{prefix}-{hashlib.sha256(text.encode('utf-8')).hexdigest()[:12].upper()}"


def _question(job: dict, question_id: str) -> dict:
    return next((item for item in job.get("question_tree", []) if item["question_id"] == question_id), {})


def _action_type(question: dict, need: dict | None) -> str:
    if need:
        return {
            "FIND_PRIMARY_ORIGINAL_EVIDENCE": "RECOVER_PRIMARY_SOURCE",
            "FIND_INDEPENDENT_CORROBORATION": "RECOVER_INDEPENDENT_SOURCE",
            "NEED_DISTINCT_EVENT": "FIND_DISTINCT_EVENT",
        }.get(str(need.get("kind")), "SEARCH_DISCOVERY")
    return {
        "CONTRADICTION": "CHECK_CONTRADICTION",
        "DISPUTE": "CHECK_CONTRADICTION",
        "EVIDENCE_GAP": "SEARCH_OFFICIAL_SOURCE",
        "HISTORY": "SEARCH_ARCHIVE_OR_CATALOG",
        "FOLLOW_UP": "FOLLOW_REFERENCE",
    }.get(question.get("kind"), "SEARCH_DISCOVERY")


def create_research_action(
    job: dict,
    branch: dict,
    *,
    action_type: str | None = None,
    recovery_need: dict | None = None,
    target: str | None = None,
    known_event_ids: list[str] | None = None,
) -> dict:
    """Build one reproducible action without executing it."""
    question_id = branch["question_ids"][0]
    question = _question(job, question_id)
    action_type = action_type or _action_type(question, recovery_need)
    if action_type not in ACTION_TYPES:
        raise ResearchExecutorError("RESEARCH_ACTION_TYPE_INVALID")
    seen_urls = list(job.get("executor_state", {}).get("seen_urls", []))
    seen_origins = list(job.get("executor_state", {}).get("seen_origins", []))
    known_events = sorted(set(known_event_ids or []) | ({job["lead"].get("related_event_cluster")} - {None}))
    topic = str(job["lead"].get("topic") or "")
    query_parts = [topic, str(question.get("text") or "")]
    if recovery_need:
        query_parts.extend(str(value) for value in recovery_need.get("topic_identifiers", []) if value)
    query = " | ".join(dict.fromkeys(part.strip() for part in query_parts if part.strip()))
    return {
        "schema_version": 1,
        "action_id": _stable_id("ACT", job["job_id"], job.get("round", 0), branch["branch_id"], action_type, target or query),
        "job_id": job["job_id"],
        "branch_id": branch["branch_id"],
        "question_id": question_id,
        "desk": job["lead"]["desk"],
        "research_regime": job["regime"],
        "action_type": action_type,
        "query": query,
        "target": target,
        "known_entities": list(job["lead"].get("event_entities", [])),
        "known_event_ids": known_events,
        "already_seen_urls": seen_urls,
        "already_seen_origins": seen_origins,
        "budget": {
            "class": job["budget_class"],
            "round": job.get("round", 0),
            "max_rounds": job["budget"]["max_followup_rounds"],
        },
        "timeout_seconds": 15,
        "expected_result_type": "EXTRACTED_SOURCE" if action_type in FETCH_ACTIONS else "DISCOVERY_RESULT",
        "provenance_requirements": {
            "read_only": True,
            "discovery_is_not_publication_evidence": True,
            "exact_source_page_required_for_evidence": True,
            "required_role": recovery_need.get("missing_evidence_role") if recovery_need else None,
            "must_be_distinct_event": bool(recovery_need and recovery_need.get("search_constraints", {}).get("must_be_distinct_event")),
            "science_strict": job["regime"] == "SCIENCE",
        },
        "recovery_need_id": recovery_need.get("need_id") if recovery_need else None,
        "recovery_candidate_id": recovery_need.get("candidate_id") if recovery_need else None,
    }


def plan_research_actions(job: dict, config: dict, *, known_event_ids: list[str] | None = None) -> list[dict]:
    """Plan at most one action per currently runnable branch and recovery need."""
    if job.get("status") == "STOPPED":
        return []
    branches = [item for item in job.get("branches", []) if item.get("status") == "PLANNED"]
    needs = [item for item in job.get("recovery_needs", []) if item.get("attempt_count", 0) < item.get("max_attempts", 1)]
    actions = []
    for index, branch in enumerate(branches):
        need = needs[index] if index < len(needs) else None
        action = create_research_action(job, branch, recovery_need=need, known_event_ids=known_event_ids)
        action["timeout_seconds"] = config["executor"]["action_timeout_seconds"]
        actions.append(action)
    return actions[: min(int(config["executor"]["maximum_actions_per_round"]), job["budget"]["max_branches"])]


class FixtureResearchAdapter:
    """Deterministic read-only adapter keyed by action ID or action type."""

    def __init__(self, responses: dict[str, list[dict]]) -> None:
        self.responses = deepcopy(responses)
        self.executed_actions: list[str] = []

    def execute(self, action: dict) -> list[dict]:
        self.executed_actions.append(action["action_id"])
        return deepcopy(self.responses.get(action["action_id"], self.responses.get(action["action_type"], [])))


class HttpResearchAdapter:
    """Optional direct-fetch adapter; it intentionally has no search backend."""

    def execute(self, action: dict) -> list[dict]:
        if action["action_type"] not in FETCH_ACTIONS or not action.get("target"):
            raise ResearchExecutorError("RESEARCH_ACTION_ADAPTER_UNAVAILABLE")
        try:
            return [fetch_and_extract_source(action["target"], timeout_seconds=action["timeout_seconds"])]
        except DiscoveryError as exc:
            return [{"result_type": "DEAD_END", "reason": exc.code, "detail": exc.detail}]


def _classification(raw: dict, action: dict, seen_urls: set[str]) -> tuple[str, str | None]:
    requested = str(raw.get("result_type") or "").upper()
    url = str(raw.get("canonical_url") or raw.get("url") or raw.get("discovered_url") or "").strip()
    canonical = normalize_url(url) if url else None
    if canonical and canonical in seen_urls:
        return "DUPLICATE", canonical
    if raw.get("event_id") and raw["event_id"] in set(action["known_event_ids"]):
        return "DUPLICATE", canonical
    if requested in {"DUPLICATE", "IRRELEVANT", "DEAD_END", "CONTRADICTION", "CONTEXT", "LEAD", "POTENTIAL_EVIDENCE"}:
        return requested, canonical
    if raw.get("relevant") is False:
        return "IRRELEVANT", canonical
    if raw.get("contradiction_candidates") or raw.get("contradicts"):
        return "CONTRADICTION", canonical
    source_class = str(raw.get("source_class") or raw.get("source_type") or "UNKNOWN").upper()
    if source_class in {"OFFICIAL", "PRIMARY", "INDEPENDENT", "PAPER"}:
        return "POTENTIAL_EVIDENCE", canonical
    return "LEAD", canonical


def _observation(action: dict, raw: dict, seen_urls: set[str]) -> dict:
    result_class, canonical = _classification(raw, action, seen_urls)
    title = str(raw.get("title") or raw.get("claim") or raw.get("reason") or "Untitled research result")
    source_class = str(raw.get("source_class") or raw.get("source_type") or "unknown").lower()
    source_id = _stable_id("SRC", canonical or action["action_id"], title)
    # Only deterministic fixtures may model a separately verified exact page.
    # Real retrieval stays extracted/not verified until the normal evidence path.
    fixture_verified = raw.get("verification_provenance") == "FIXTURE_VERIFIED_EXACT_PAGE"
    verification_status = "VERIFIED_EVIDENCE" if fixture_verified else "EXTRACTED_NOT_VERIFIED"
    origin = urlsplit(canonical).hostname if canonical else None
    observation_id = _stable_id("OBS", action["action_id"], canonical or title, result_class)
    kind = {
        "LEAD": "LEAD", "POTENTIAL_EVIDENCE": "POTENTIAL_EVIDENCE",
        "CONTEXT": "CONTEXT", "CONTRADICTION": "CONTRADICTION",
        "DUPLICATE": "DUPLICATE", "IRRELEVANT": "IRRELEVANT", "DEAD_END": "DEAD_END",
    }[result_class]
    return {
        "observation_id": observation_id,
        "kind": kind,
        "observation_class": result_class,
        "question_id": action["question_id"],
        "branch_id": action["branch_id"],
        "source_id": source_id if canonical else None,
        "url": canonical,
        "origin": origin,
        "title": title,
        "published_at": raw.get("published_at") or raw.get("publication_date"),
        "observed_at": raw.get("retrieved_at"),
        "extraction_status": raw.get("fetch_status") or ("NOT_RETRIEVED" if not canonical else "RETRIEVED"),
        "content_hash": raw.get("content_hash"),
        "source_class": source_class,
        "discovery_method": action["action_type"],
        "related_entities": list(raw.get("related_entities") or action["known_entities"]),
        "related_event": raw.get("event_id"),
        "claim": str(raw.get("claim") or title),
        "claim_candidates": list(raw.get("claim_candidates") or []),
        "contradiction_candidates": list(raw.get("contradiction_candidates") or []),
        "relevance_status": "REJECTED" if result_class in {"IRRELEVANT", "DUPLICATE"} else "RETAINED",
        "verification_status": verification_status,
        "provenance": {
            "action_id": action["action_id"],
            "expected_result_type": action["expected_result_type"],
            "fixture_verification": fixture_verified,
            "discovery_is_not_publication_evidence": True,
        },
        "publication_evidence": False,
        "supporting_evidence_ids": list(raw.get("supporting_evidence_ids") or []),
        "contradicting_evidence_ids": list(raw.get("contradicting_evidence_ids") or []),
        "follow_up_question": raw.get("follow_up_question"),
        "reason": raw.get("reason"),
    }


def _source_patch(observation: dict, action: dict) -> dict | None:
    if observation["observation_class"] != "POTENTIAL_EVIDENCE" or not observation.get("url"):
        return None
    source_type = observation["source_class"]
    if source_type not in {"primary", "official", "independent", "paper"}:
        return None
    return {
        "id": observation["source_id"], "url": observation["url"],
        "publisher": observation["origin"], "title": observation["title"],
        "publication_date": observation["published_at"], "accessed_at": observation["observed_at"],
        "source_type": source_type, "claim_supported": observation["claim"],
        "content_hash": observation["content_hash"],
        "executor_observation_id": observation["observation_id"],
        "verification_status": observation["verification_status"],
        "provenance": observation["provenance"],
        "recovery_need_id": action.get("recovery_need_id"),
    }


def execute_research_round(
    job: dict,
    adapter: ResearchAdapter,
    config: dict,
    *,
    actions: list[dict] | None = None,
    known_event_ids: list[str] | None = None,
) -> dict:
    """Execute one bounded round and feed observations to the state machine."""
    planned = actions if actions is not None else plan_research_actions(job, config, known_event_ids=known_event_ids)
    limits = config["executor"]["budget_action_limits"][job["budget_class"]]
    state = deepcopy(job.get("executor_state", {"search_actions": 0, "fetches": 0, "seen_urls": [], "seen_origins": []}))
    seen_urls = set(state["seen_urls"])
    branch_results: dict[str, list[dict]] = {item["branch_id"]: [] for item in job.get("branches", [])}
    observations, source_records, updates, attempted_needs = [], [], [], []
    executed = []
    for action in planned[: config["executor"]["maximum_actions_per_round"]]:
        if action["job_id"] != job["job_id"] or action["action_type"] not in ACTION_TYPES:
            raise ResearchExecutorError("RESEARCH_ACTION_INVALID")
        is_search = action["action_type"] in SEARCH_ACTIONS
        counter = "search_actions" if is_search else "fetches"
        if state[counter] >= limits[counter]:
            continue
        state[counter] += 1
        executed.append(action)
        if action.get("recovery_need_id"):
            attempted_needs.append(action["recovery_need_id"])
        try:
            raw_results = adapter.execute(action)
        except ResearchExecutorError as exc:
            raw_results = [{"result_type": "DEAD_END", "reason": str(exc)}]
        if not isinstance(raw_results, list):
            raise ResearchExecutorError("RESEARCH_ADAPTER_RESULT_INVALID")
        for raw in raw_results:
            if not isinstance(raw, dict):
                raise ResearchExecutorError("RESEARCH_ADAPTER_RESULT_INVALID")
            observation = _observation(action, raw, seen_urls)
            observations.append(observation)
            branch_results.setdefault(action["branch_id"], []).append(observation)
            if observation.get("url"):
                seen_urls.add(observation["url"])
                if observation.get("origin"):
                    state["seen_origins"].append(observation["origin"])
            patch = _source_patch(observation, action)
            if patch:
                source_records.append(patch)
                role = "PRIMARY" if patch["source_type"] in {"primary", "official", "paper"} else "INDEPENDENT"
                if action.get("recovery_candidate_id") and patch["verification_status"] == "VERIFIED_EVIDENCE":
                    updates.append({
                        "candidate_id": action["recovery_candidate_id"], "source_id": patch["id"],
                        "role": role, "recovery_need_id": action.get("recovery_need_id"),
                    })
    results = [{"branch_id": branch_id, "observations": values} for branch_id, values in branch_results.items() if values]
    advanced = advance_research_job(job, results, config)
    state["seen_urls"] = sorted(seen_urls)
    state["seen_origins"] = sorted(set(state["seen_origins"]))
    state["actions_executed"] = int(state.get("actions_executed", 0)) + len(executed)
    advanced["executor_state"] = state
    return {
        "schema_version": 1,
        "status": "EXECUTED",
        "job": advanced,
        "actions": executed,
        "observations": observations,
        "source_packet_patch": {"sources": source_records, "candidate_evidence_updates": updates},
        "recovery_attempts": sorted(set(attempted_needs)),
        "budget_consumed": {"search_actions": state["search_actions"], "fetches": state["fetches"]},
        "remaining_gaps": list(advanced["context"]["SOURCE_GAPS"]),
        "stop_reason": advanced.get("stop_condition"),
    }


def apply_executor_results_to_packet(packet: dict, execution: dict) -> dict:
    """Create a new packet for normal source intelligence/recovery evaluation.

    This is deliberately a packet patch, not a recovery-success switch. Only an
    explicit fixture-verified exact page may update a candidate evidence role;
    subsequent source intelligence and recovery planning remain authoritative.
    """
    value = deepcopy(packet)
    existing_ids = {item["id"] for item in value.get("sources", [])}
    existing_urls = {normalize_url(item["url"]) for item in value.get("sources", [])}
    for source in execution["source_packet_patch"]["sources"]:
        if source["id"] not in existing_ids and normalize_url(source["url"]) not in existing_urls:
            value.setdefault("sources", []).append(source)
            existing_ids.add(source["id"])
            existing_urls.add(normalize_url(source["url"]))
    for update in execution["source_packet_patch"]["candidate_evidence_updates"]:
        for section in value.get("sections", []):
            for candidate in [*section.get("candidates", []), *section.get("recovery_candidates", [])]:
                if candidate.get("id") != update["candidate_id"]:
                    continue
                candidate.setdefault("discovery_source_ids", []).append(update["source_id"])
                candidate.setdefault("verification_source_ids", []).append(update["source_id"])
                field = "primary_evidence_source_ids" if update["role"] == "PRIMARY" else "independent_evidence_source_ids"
                candidate.setdefault(field, []).append(update["source_id"])
    sources = {item["id"]: item for item in value.get("sources", [])}
    for section in value.get("sections", []):
        for candidate in [*section.get("candidates", []), *section.get("recovery_candidates", [])]:
            primary = [
                item for item in candidate.get("primary_evidence_source_ids", [])
                if sources.get(item, {}).get("source_type") in {"primary", "official", "paper"}
            ]
            independent = [
                item for item in candidate.get("independent_evidence_source_ids", [])
                if sources.get(item, {}).get("source_type") == "independent"
            ]
            primary_origins = {urlsplit(sources[item]["url"]).hostname for item in primary}
            independent_origins = {urlsplit(sources[item]["url"]).hostname for item in independent}
            issues = []
            if not primary:
                issues.append("PRIMARY_EVIDENCE_MISSING")
            if not independent:
                issues.append("INDEPENDENT_EVIDENCE_MISSING")
            if primary_origins & independent_origins:
                issues.append("EVIDENCE_ROLE_ORIGIN_OVERLAP")
            candidate["evidence_eligibility"] = {
                "status": "ELIGIBLE" if not issues else "INELIGIBLE",
                "issues": issues,
            }
    return value


def replay_recovery_after_execution(packet: dict, execution: dict, coverage: dict, readiness: dict) -> dict:
    """Run normal normalization, clustering, and recovery against executor output."""
    patched = apply_executor_results_to_packet(packet, execution)
    intelligence = build_source_intelligence(patched)
    attempts = {need_id: 1 for need_id in execution.get("recovery_attempts", [])}
    recovery = build_recovery_plan(patched, intelligence, coverage, readiness, attempts_by_need=attempts)
    return {
        "schema_version": 1,
        "status": "READY" if recovery["status"] == "PASS" else "RESEARCH_GAPS_REMAIN",
        "packet": patched,
        "source_intelligence": intelligence,
        "recovery": recovery,
        "article_generation_allowed": recovery["article_generation_allowed"],
    }


def science_adapter_boundary(config: dict) -> dict:
    """Expose future science routes without enabling a science runtime."""
    return deepcopy(config["science"]["adapters"])
