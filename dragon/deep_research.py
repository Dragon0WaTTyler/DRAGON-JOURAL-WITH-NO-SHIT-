"""Deterministic, provider-neutral Deep Research Engine v1.

The engine plans and advances bounded research state.  It deliberately does
not perform network access or generation: adapters may return observations,
but only downstream evidence policy can promote them for publication.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator
import yaml

from dragon.investigation_scope import evaluate_super_investigation_scope
from dragon.provider_targeting import HARD_TARGET_SECTIONS


LEAD_STATES = {"NEW", "RESEARCHING", "SUPPORTED", "DISPUTED", "UNRESOLVED", "REJECTED", "PROMOTED_TO_CANDIDATE"}
OBSERVATION_KINDS = {
    "LEAD", "POTENTIAL_EVIDENCE", "CONTEXT", "SUPPORTED", "DISPUTED",
    "UNKNOWN", "CONTRADICTION", "DUPLICATE", "IRRELEVANT", "DEAD_END",
    "SOURCE_GAP",
}
TERMINAL_REASONS = {"KEY_QUESTIONS_ANSWERED", "EVIDENCE_REPETITIVE", "BUDGET_EXHAUSTED", "NO_BETTER_SOURCES", "STORY_NO_LONGER_MEANINGFUL"}

SECTION_PERSPECTIVES = {
    "science": ["الباحث الأصلي", "خبير المنهجية", "باحث مستقل", "التكرار والإجماع"],
    "investigations": ["السجل العام", "الجهة المعنية", "المتأثرون", "المدقق المستقل", "التفسير البديل"],
    "iqtisad_flous": ["صانع السياسة", "الاقتصادي المستقل", "العامل أو المستهلك", "البيانات المقارنة"],
    "meknes_local": ["المؤسسة المحلية", "الساكن", "الخبير التقني", "التنفيذ والميزانية"],
    "history": ["المصدر الأولي", "المؤرخون المختلفون", "السياق الزمني", "الذاكرة العامة"],
    "technology": ["المطور أو الشركة", "التقييم المستقل", "المستخدم", "المنظم", "الأثر الاجتماعي"],
}
HARD_DEFICIT_SECTION_FUNCTIONS = {
    section_id: lane
    for lane, section_ids in HARD_TARGET_SECTIONS.items()
    for section_id in section_ids
}
DEFAULT_PERSPECTIVES = ["المؤسسة أو صاحب الادعاء", "المتأثرون", "الخبير المستقل", "الدليل والبيانات"]


class DeepResearchError(RuntimeError):
    pass


def load_deep_research_config(path: Path, schema_path: Path | None = None) -> dict:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
        schema = json.loads((schema_path or path.with_name("deep-research-schema.json")).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError, json.JSONDecodeError) as exc:
        raise DeepResearchError(str(exc)) from exc
    errors = sorted(Draft202012Validator(schema).iter_errors(value), key=lambda item: list(item.path))
    if errors:
        raise DeepResearchError("; ".join(error.message for error in errors[:8]))
    if value["open_discovery"] != {
        "allowed": True,
        "mode": "READ_ONLY_RESEARCH",
        "configured_sources_are": "PREFERRED_SEEDS_NOT_WHITELIST",
        "untrusted_content_may_change_policy": False,
        "discovery_is_evidence": False,
    }:
        raise DeepResearchError("OPEN_DISCOVERY_POLICY_INVALID")
    if value["philosophy"] != {
        "upstream": "MAXIMUM_CURIOSITY",
        "downstream": "MAXIMUM_RIGOR",
    }:
        raise DeepResearchError("DEEP_RESEARCH_PHILOSOPHY_INVALID")
    if set(value["lead_states"]) != LEAD_STATES:
        raise DeepResearchError("DEEP_RESEARCH_LEAD_STATES_INVALID")
    if set(value["contradiction_states"]) != {"UNRESOLVED", "RESOLVED", "DISCLOSED"}:
        raise DeepResearchError("DEEP_RESEARCH_CONTRADICTION_STATES_INVALID")
    if value["context"].get("buckets") != [
        "KNOWN", "SUPPORTED", "DISPUTED", "UNKNOWN", "NEXT_QUESTIONS",
        "SOURCE_GAPS", "CONTRADICTIONS", "DEAD_ENDS",
    ]:
        raise DeepResearchError("DEEP_RESEARCH_CONTEXT_BUCKETS_INVALID")
    limits = value["executor"].get("budget_action_limits", {})
    followup_limits = value["executor"].get("lead_followup_limits", {})
    if (
        value["executor"].get("action_timeout_seconds") != 15
        or value["executor"].get("maximum_actions_per_round") != 8
        or set(limits) != set(value["budget_classes"])
        or set(followup_limits) != set(value["budget_classes"])
        or any(
            set(limit) != {"search_actions", "fetches"}
            or limit["search_actions"] > value["budget_classes"][name]["max_branches"]
            or limit["fetches"] > value["budget_classes"][name]["max_branches"]
            for name, limit in limits.items()
        )
        or any(
            set(limit) != {"total", "P0_BLOCKING_EVIDENCE", "P1_BREADTH", "P1_DISTINCT_EVENT", "P2_CONTRADICTION", "P3_CONTEXT"}
            or limit["total"] > value["budget_classes"][name]["max_branches"]
            for name, limit in followup_limits.items()
        )
    ):
        raise DeepResearchError("DEEP_RESEARCH_EXECUTOR_POLICY_INVALID")
    science = value["science"]
    if (
        science.get("strict") is not True
        or science.get("weak_sources_never_strengthen_by_repetition") is not True
        or science.get("require_original_research_when_obtainable") is not True
        or science.get("require_methods_and_limitations_for_full_text_claims") is not True
        or science.get("adapters") != {
            "feynman": {"status": "ADAPTER_READY", "enabled": False},
            "paperqa": {"status": "ADAPTER_READY", "enabled": False},
            "ars": {"status": "ADAPTER_READY", "enabled": False},
        }
    ):
        raise DeepResearchError("SCIENCE_RESEARCH_POLICY_INVALID")
    investigation = value["super_investigation"]
    if (
        set(investigation.get("geographic_scope", [])) != {"Morocco", "Meknes"}
        or investigation.get("foreign_entities_allowed_only_with_direct_scope_connection") is not True
        or set(investigation.get("allowed_conclusions", [])) != {
            "SUPPORTED", "NOT_SUPPORTED", "NO_EVIDENCE_OF_MISCONDUCT",
            "EXPLANATION_FOUND", "UNRESOLVED", "PUBLICATION_READY",
        }
    ):
        raise DeepResearchError("SUPER_INVESTIGATION_POLICY_INVALID")
    return value


def _stable_id(prefix: str, *parts: object) -> str:
    value = "\0".join(str(part) for part in parts)
    return f"{prefix}-{hashlib.sha256(value.encode('utf-8')).hexdigest()[:12].upper()}"


def create_lead(
    *, desk: str, topic: str, discovery_source: dict, observed_at: str,
    reason_interesting: str, event_entities: list[str] | None = None,
    questions: list[str] | None = None, related_event_cluster: str | None = None,
    geography: list[str] | None = None, scope_connections: list[dict] | None = None,
) -> dict:
    """Create a research lead; source familiarity never makes it evidence."""
    source_url = str(discovery_source.get("url") or "")
    return {
        # The source URL alone is not enough for synthetic recovery tracks:
        # two distinct edition-wide needs can share desk/topic/date.  Retain
        # the explicit reason in the identity so their bounded action budgets
        # and observations never merge.
        "lead_id": _stable_id("LEAD", desk, topic, source_url, observed_at, reason_interesting),
        "desk": desk,
        "topic": topic,
        "event_entities": list(event_entities or []),
        "discovery_source": deepcopy(discovery_source),
        "observed_at": observed_at,
        "reason_interesting": reason_interesting,
        "state": "NEW",
        "verification_status": "DISCOVERY_ONLY",
        "questions": list(questions or []),
        "next_research_actions": ["TRACE_ORIGINAL_SOURCE", "FIND_BETTER_COVERAGE", "CHECK_CONTRADICTIONS"],
        "linked_evidence": [],
        "related_event_cluster": related_event_cluster,
        "investigation_scope": evaluate_super_investigation_scope({
            "geography": geography or [],
            "entities": [{"name": item} for item in event_entities or []],
            "scope_connections": scope_connections or [],
        }),
        "publication_evidence": False,
    }


def build_perspective_map(lead: dict) -> list[dict]:
    perspectives = list(SECTION_PERSPECTIVES.get(lead["desk"], DEFAULT_PERSPECTIVES))
    topic = lead["topic"].casefold()
    if any(marker in topic for marker in ("قانون", "محكمة", "حقوق", "law", "court")):
        perspectives.extend(["الخبير القانوني", "ضمانات الحقوق"])
    if any(marker in topic for marker in ("ميزانية", "كلفة", "اقتصاد", "budget", "cost")):
        perspectives.extend(["الأثر المالي", "الرقابة على الإنفاق"])
    if any(marker in topic for marker in ("تاريخ", "أرشيف", "history", "archive")):
        perspectives.extend(["الوثيقة الأصلية", "تغير التفسير عبر الزمن"])
    unique = list(dict.fromkeys(perspectives))
    return [
        {"perspective_id": _stable_id("PER", lead["lead_id"], item), "name": item, "reason": f"يفحص الموضوع من زاوية {item}"}
        for item in unique
    ]


def build_question_tree(lead: dict, perspectives: list[dict], *, max_questions: int) -> list[dict]:
    catalog = [
        ("FACT", "ما الوقائع المعروفة، وما مصدرها الأصلي؟"),
        ("DISPUTE", "ما الادعاءات المتنازع عليها، وما أقوى دليل مع كل طرف؟"),
        ("EVIDENCE_GAP", "ما الدليل الأولي أو المستقل الذي لا يزال مفقودا؟"),
        ("CAUSE", "ما التفسيرات السببية البديلة، وما الذي قد يفند كل تفسير؟"),
        ("HUMAN_CONSEQUENCE", "من يتأثر، وكيف يمكن قياس الأثر دون تعميم؟"),
        ("QUANTITATIVE", "ما البيانات والمقاييس وخط الأساس اللازم للتحقق؟"),
        ("CONTRADICTION", "ما الأدلة المناقضة أو السجلات التي قد تغير الخلاصة؟"),
        ("HISTORY", "ما السياق الزمني أو التاريخي الضروري لفهم التطور؟"),
    ]
    questions = []
    for index, (kind, text) in enumerate(catalog[:max_questions]):
        perspective = perspectives[index % len(perspectives)]
        questions.append({
            "question_id": _stable_id("Q", lead["lead_id"], kind, text),
            "parent_question_id": None,
            "depth": 0,
            "kind": kind,
            "perspective_id": perspective["perspective_id"],
            "text": text,
            "status": "OPEN",
            "answer_observation_ids": [],
        })
    return questions


def _recovery_priority(need: dict) -> str:
    """Keep recovery-job identity explicit without importing the executor."""
    kind = str(need.get("kind") or "")
    if kind in {"FIND_PRIMARY_ORIGINAL_EVIDENCE", "FIND_INDEPENDENT_CORROBORATION"}:
        return "P0_BLOCKING_EVIDENCE"
    if kind == "NEED_DISTINCT_EVENT":
        return "P1_DISTINCT_EVENT"
    if kind.startswith("NEED_"):
        return "P1_BREADTH"
    if kind in {"CONTRADICTION", "CHECK_CONTRADICTION"}:
        return "P2_CONTRADICTION"
    return "P3_CONTEXT"


def start_research_job(
    lead: dict,
    config: dict,
    *,
    budget_class: str = "STANDARD",
    recovery_needs: list[dict] | None = None,
    run_scope_id: str | None = None,
    recovery_identity: str | None = None,
) -> dict:
    if lead.get("state") not in LEAD_STATES or budget_class not in config["budget_classes"]:
        raise DeepResearchError("RESEARCH_JOB_INPUT_INVALID")
    budget = deepcopy(config["budget_classes"][budget_class])
    perspectives = build_perspective_map(lead)
    questions = build_question_tree(lead, perspectives, max_questions=min(budget["max_branches"] * 2, 8))
    recovery_needs = deepcopy(recovery_needs or [])
    gaps = [need["need_id"] for need in recovery_needs]
    recovery_identity = recovery_identity or "|".join(sorted(gaps)) or "GENERAL_RESEARCH"
    recovery_job = None
    if recovery_needs:
        # A recovery job is intentionally one need per job today.  Keeping the
        # list allows a future compatible grouping only when it remains
        # observable and validated by the state invariant below.
        recovery_job = {
            "recovery_need_ids": list(gaps),
            "priority_classes": sorted({_recovery_priority(item) for item in recovery_needs}),
            "candidate_ids": sorted({str(item["candidate_id"]) for item in recovery_needs if item.get("candidate_id")}),
            "event_ids": sorted({str(item["event_id"]) for item in recovery_needs if item.get("event_id")}),
            "desk": lead["desk"],
            "need_types": sorted({str(item.get("kind") or "") for item in recovery_needs}),
            "missing_roles": sorted({str(item["missing_evidence_role"]) for item in recovery_needs if item.get("missing_evidence_role")}),
            "source_attempt_ids": sorted({str(item["source_attempt_id"]) for item in recovery_needs if item.get("source_attempt_id")}),
            "attempt_count": max((int(item.get("attempt_count", 0)) for item in recovery_needs), default=0),
            "max_attempts": max((int(item.get("max_attempts", 1)) for item in recovery_needs), default=1),
            "run_scope_id": run_scope_id,
        }
    return {
        "schema_version": 1,
        "job_id": _stable_id("JOB", run_scope_id or lead["observed_at"], lead["lead_id"], budget_class, recovery_identity),
        "lead": {**deepcopy(lead), "state": "RESEARCHING"},
        "regime": "SCIENCE" if lead["desk"] == "science" else "GENERAL_JOURNALISM",
        "budget_class": budget_class,
        "budget": budget,
        "round": 0,
        "current_depth": 0,
        "perspective_map": perspectives,
        "question_tree": questions,
        "branches": [
            {"branch_id": _stable_id("BR", lead["lead_id"], item["question_id"]), "question_ids": [item["question_id"]], "perspective_id": item["perspective_id"], "depth": 1, "status": "PLANNED"}
            for item in questions[:budget["max_branches"]]
        ],
        "context": {
            "KNOWN": [], "SUPPORTED": [], "DISPUTED": [], "UNKNOWN": [],
            "NEXT_QUESTIONS": [item["question_id"] for item in questions],
            "SOURCE_GAPS": gaps, "CONTRADICTIONS": [], "DEAD_ENDS": [],
        },
        "observations": [],
        "seen_fingerprints": [],
        "repetitive_observations": 0,
        "recovery_needs": recovery_needs,
        "recovery_job": recovery_job,
        "status": "PLANNED",
        "stop_condition": None,
        "unresolved_questions": [item["question_id"] for item in questions],
        "synthesis_candidate": None,
        "publication_gate_status": "PENDING",
    }


def _observation_fingerprint(observation: dict) -> str:
    material = {key: observation.get(key) for key in ("kind", "claim", "source_id", "question_id", "evidence_role")}
    return hashlib.sha256(json.dumps(material, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def _compress_context(job: dict, config: dict) -> None:
    limit = int(config["context"]["maximum_items_per_bucket"])
    totals = {}
    for key in config["context"]["buckets"]:
        unique = list(dict.fromkeys(job["context"].get(key, [])))
        totals[key] = len(unique)
        job["context"][key] = unique[-limit:]
    job["context_summary"] = {
        "compression_policy": "DEDUPLICATE_AND_RETAIN_MOST_RECENT_IDS",
        "maximum_items_per_bucket": limit,
        "total_items_before_window": totals,
        "retained_items": {key: len(job["context"][key]) for key in config["context"]["buckets"]},
    }


def _followup_text(record: dict) -> str | None:
    explicit = str(record.get("follow_up_question") or "").strip()
    if explicit:
        return explicit
    if record["kind"] == "CONTRADICTION":
        return "ما الدليل الذي يفسر هذا التعارض، وأي رواية تصمد أمام المصدر الأصلي؟"
    if record["kind"] in {"SOURCE_GAP", "UNKNOWN"}:
        return "ما المصدر الأولي أو المستقل القادر على سد هذه الفجوة؟"
    if record["kind"] == "DISPUTED":
        return "ما الاختبار أو الوثيقة التي ترجح بين الادعاءات المتعارضة؟"
    if record["kind"] == "SUPPORTED" and record.get("verification_status") != "VERIFIED_EVIDENCE":
        return "أين النسخة الأصلية القابلة للتحقق من هذا الادعاء؟"
    return None


def _append_bounded_followups(value: dict, followups: list[tuple[str | None, str]]) -> list[str]:
    """Append unique child questions and return the next round's question IDs."""
    budget = value["budget"]
    existing_ids = {item["question_id"] for item in value["question_tree"]}
    existing_text = {
        (item.get("parent_question_id"), item["text"].casefold())
        for item in value["question_tree"]
    }
    by_id = {item["question_id"]: item for item in value["question_tree"]}
    next_ids = []
    maximum_questions = budget["max_branches"] * (budget["max_depth"] + 1)
    for parent_id, text in followups:
        parent = by_id.get(parent_id)
        parent_depth = int(parent.get("depth", 0)) if parent else 0
        child_depth = parent_depth + 1
        if child_depth > budget["max_depth"] or len(value["question_tree"]) >= maximum_questions:
            continue
        identity = (parent_id, text.casefold())
        if identity in existing_text:
            continue
        question_id = _stable_id("Q", value["lead"]["lead_id"], parent_id, child_depth, text)
        if question_id in existing_ids:
            continue
        perspective_id = parent.get("perspective_id") if parent else value["perspective_map"][0]["perspective_id"]
        value["question_tree"].append({
            "question_id": question_id,
            "parent_question_id": parent_id,
            "depth": child_depth,
            "kind": "FOLLOW_UP",
            "perspective_id": perspective_id,
            "text": text,
            "status": "OPEN",
            "answer_observation_ids": [],
        })
        by_id[question_id] = value["question_tree"][-1]
        existing_ids.add(question_id)
        existing_text.add(identity)
        next_ids.append(question_id)
        if len(next_ids) >= budget["max_branches"]:
            break
    return next_ids


def _update_lead_state(value: dict, *, stopped: bool) -> None:
    if value.get("contradictions") or value["context"]["UNKNOWN"] or value["context"]["SOURCE_GAPS"]:
        state = "UNRESOLVED"
    elif value["context"]["DISPUTED"]:
        state = "DISPUTED"
    elif value["context"]["SUPPORTED"]:
        state = "SUPPORTED"
    elif stopped:
        state = "REJECTED"
    else:
        state = "RESEARCHING"
    value["lead"]["state"] = state


def advance_research_job(job: dict, branch_results: list[dict], config: dict) -> dict:
    """Ingest one bounded round of adapter results and produce replayable state."""
    value = deepcopy(job)
    if value.get("status") == "STOPPED":
        return value
    budget = value["budget"]
    if value["round"] >= budget["max_followup_rounds"]:
        value.update({"status": "STOPPED", "stop_condition": "BUDGET_EXHAUSTED"})
        return value
    branches_by_id = {item["branch_id"]: item for item in value["branches"]}
    new_material = 0
    story_meaningful = True
    attempted_question_ids: set[str] = set()
    followups: list[tuple[str | None, str]] = []
    for result in branch_results[:budget["max_branches"]]:
        branch_id = result.get("branch_id")
        if branch_id not in branches_by_id:
            raise DeepResearchError("RESEARCH_BRANCH_UNKNOWN")
        branch = branches_by_id[branch_id]
        branch["status"] = str(result.get("status") or "COMPLETE")
        if result.get("story_meaningful") is False:
            story_meaningful = False
        attempted_question_ids.update(branch.get("question_ids", []))
        for observation in result.get("observations", []):
            if len(value["observations"]) >= budget["max_observations"]:
                break
            if observation.get("kind") not in OBSERVATION_KINDS:
                raise DeepResearchError("RESEARCH_OBSERVATION_INVALID")
            fingerprint = observation.get("fingerprint") or _observation_fingerprint(observation)
            if fingerprint in value["seen_fingerprints"]:
                value["repetitive_observations"] += 1
                continue
            value["seen_fingerprints"].append(fingerprint)
            record = {**deepcopy(observation), "fingerprint": fingerprint}
            record.setdefault("observation_id", _stable_id("OBS", value["job_id"], fingerprint))
            value["observations"].append(record)
            kind = record["kind"]
            if kind not in {"DUPLICATE", "IRRELEVANT", "DEAD_END"}:
                new_material += 1
            question_id = record.get("question_id")
            verified = record.get("verification_status") == "VERIFIED_EVIDENCE"
            if kind == "SUPPORTED" and verified:
                value["context"]["SUPPORTED"].append(record["observation_id"])
                for question in value["question_tree"]:
                    if question["question_id"] == question_id:
                        question["status"] = "ANSWERED"
                        question["answer_observation_ids"].append(record["observation_id"])
            elif kind == "SUPPORTED":
                value["context"]["SOURCE_GAPS"].append(record["observation_id"])
                value["context"]["UNKNOWN"].append(record["observation_id"])
            elif kind == "LEAD":
                value["context"]["KNOWN"].append(record["observation_id"])
            elif kind in {"POTENTIAL_EVIDENCE", "CONTEXT"}:
                value["context"]["KNOWN"].append(record["observation_id"])
            elif kind == "DISPUTED":
                value["context"]["DISPUTED"].append(record["observation_id"])
            elif kind == "UNKNOWN":
                value["context"]["UNKNOWN"].append(record["observation_id"])
            elif kind == "SOURCE_GAP":
                value["context"]["SOURCE_GAPS"].append(record["observation_id"])
            elif kind == "DEAD_END":
                value["context"]["DEAD_ENDS"].append(record["observation_id"])
            elif kind in {"DUPLICATE", "IRRELEVANT"}:
                value["context"]["DEAD_ENDS"].append(record["observation_id"])
            elif kind == "CONTRADICTION":
                contradiction = {
                    "contradiction_id": _stable_id("CON", value["job_id"], record.get("claim"), record["observation_id"]),
                    "claim": record.get("claim"),
                    "supporting_evidence_ids": list(record.get("supporting_evidence_ids", [])),
                    "contradicting_evidence_ids": list(record.get("contradicting_evidence_ids", [])),
                    "status": "UNRESOLVED",
                    "follow_up_question": record.get("follow_up_question") or "ما الدليل الذي يفسر هذا التعارض؟",
                }
                value["context"]["CONTRADICTIONS"].append(contradiction["contradiction_id"])
                value.setdefault("contradictions", []).append(contradiction)
            followup = _followup_text(record)
            if followup:
                followups.append((question_id, followup))
    value["round"] += 1
    value["unresolved_questions"] = [
        item["question_id"] for item in value["question_tree"]
        if item["status"] != "ANSWERED"
    ]
    if not story_meaningful:
        stop = "STORY_NO_LONGER_MEANINGFUL"
    elif value["repetitive_observations"] >= budget["repetitive_observation_limit"]:
        stop = "EVIDENCE_REPETITIVE"
    elif not new_material:
        stop = "NO_BETTER_SOURCES"
    elif not value["unresolved_questions"] and not value.get("contradictions") and not value["context"]["SOURCE_GAPS"]:
        stop = "KEY_QUESTIONS_ANSWERED"
    elif value["round"] >= budget["max_followup_rounds"]:
        stop = "BUDGET_EXHAUSTED"
    else:
        stop = None
    child_ids = _append_bounded_followups(value, followups) if not stop else []
    value["unresolved_questions"] = [item["question_id"] for item in value["question_tree"] if item["status"] != "ANSWERED"]
    value["context"]["NEXT_QUESTIONS"] = value["unresolved_questions"]
    value.setdefault("branch_history", []).extend(deepcopy(value["branches"]))
    if not stop:
        next_ids = child_ids + [
            question_id for question_id in value["unresolved_questions"]
            if question_id not in child_ids and question_id not in attempted_question_ids
        ]
        next_ids = next_ids[:budget["max_branches"]]
        questions = {item["question_id"]: item for item in value["question_tree"]}
        value["branches"] = [{
            "branch_id": _stable_id("BR", value["lead"]["lead_id"], value["round"], question_id),
            "question_ids": [question_id],
            "perspective_id": questions[question_id]["perspective_id"],
            "depth": questions[question_id]["depth"],
            "status": "PLANNED",
        } for question_id in next_ids]
        value.setdefault("replan_history", []).append({
            "after_round": value["round"],
            "reason": "NEW_GAPS_OR_UNRESOLVED_QUESTIONS",
            "next_question_ids": next_ids,
        })
        if not next_ids:
            stop = "NO_BETTER_SOURCES"
    value["current_depth"] = max(
        (item["depth"] for item in value["question_tree"]), default=0
    )
    _compress_context(value, config)
    value["status"] = "STOPPED" if stop else "RESEARCHING"
    value["stop_condition"] = stop
    _update_lead_state(value, stopped=bool(stop))
    if stop and value["context"]["SUPPORTED"]:
        value["synthesis_candidate"] = {
            "supported_observation_ids": list(value["context"]["SUPPORTED"]),
            "unresolved_question_ids": list(value["unresolved_questions"]),
            "contradiction_ids": list(value["context"]["CONTRADICTIONS"]),
            "publication_ready": False,
        }
    return value


def derive_research_outcome(job: dict) -> str:
    """NO_NEWS is allowed only after a configured terminal research effort."""
    if job.get("status") != "STOPPED" or job.get("stop_condition") not in TERMINAL_REASONS:
        return "CONTINUE_RESEARCH"
    if job.get("context", {}).get("SUPPORTED"):
        return "SYNTHESIS_CANDIDATE"
    return "NO_NEWS"


def evaluate_claim_policy(claim_class: str, evidence: list[dict], config: dict, *, unresolved_contradictions: bool = False) -> dict:
    policy = config["claim_policies"][claim_class]
    primary = [item for item in evidence if item.get("source_type") in {"primary", "official", "paper"} and item.get("verification_status") == "VERIFIED_EVIDENCE"]
    independent_origins = {
        item.get("origin") for item in evidence
        if item.get("source_type") == "independent" and item.get("verification_status") == "VERIFIED_EVIDENCE" and item.get("origin")
    }
    issues = []
    if len(primary) < policy["required_primary_sources"]:
        issues.append("PRIMARY_EVIDENCE_INSUFFICIENT")
    if len(independent_origins) < policy["required_independent_origins"]:
        issues.append("INDEPENDENT_EVIDENCE_INSUFFICIENT")
    if unresolved_contradictions:
        issues.append("CONTRADICTION_UNRESOLVED")
    if claim_class == "SCIENCE_CLAIM":
        papers = [item for item in primary if item.get("source_type") == "paper"]
        if not papers or not any(
            item.get("full_text_status") == "FULL_TEXT_VERIFIED"
            and item.get("methods_read") is True and item.get("limitations_read") is True
            for item in papers
        ):
            issues.append("SCIENCE_PRIMARY_METHODS_EVIDENCE_INSUFFICIENT")
    return {
        "claim_class": claim_class,
        "status": "READY_UNDER_MODELED_POLICY" if not issues else "NOT_READY",
        "issues": sorted(set(issues)),
        "migration_status": "MODEL_ONLY_CURRENT_HARD_GATES_UNCHANGED",
    }


def build_deep_research_state(
    packet: dict, intelligence: dict, research_plan: dict, recovery_plan: dict,
    config: dict, *, discovery_signals: list[dict] | None = None,
    run_scope_id: str | None = None,
    recovery_epoch: int = 0,
    recovery_only: bool = False,
) -> dict:
    events = {key: event["event_id"] for event in intelligence.get("event_clusters", []) for key in event.get("candidate_keys", [])}
    plan_by_section = {item["section_id"]: item for item in research_plan.get("plans", [])}
    needs_by_candidate: dict[str, list[dict]] = {}
    for need in recovery_plan.get("needs", []):
        if need.get("candidate_id"):
            needs_by_candidate.setdefault(need["candidate_id"], []).append(need)
    executable_needs = [
        deepcopy(need) for need in recovery_plan.get("needs", [])
        if int(need.get("attempt_count", 0)) < int(need.get("max_attempts", 1))
        or (
            need.get("pivot_mode") == "FIND_ALTERNATIVE_EVENT_FOR_SEMANTIC_NEED"
            and int(need.get("pivot_attempt_count", 0)) < 1
        )
    ]
    executable_need_ids = [str(need.get("need_id") or "") for need in executable_needs]
    if not all(executable_need_ids) or len(set(executable_need_ids)) != len(executable_need_ids):
        raise DeepResearchError("RECOVERY_JOB_MATERIALIZATION_FAILED: invalid recovery need identity")

    candidate_records: dict[str, tuple[dict, dict]] = {}
    for section in packet.get("sections", []):
        for candidate in [*section.get("candidates", []), *section.get("recovery_candidates", [])]:
            candidate_id = str(candidate.get("id") or "")
            if not candidate_id:
                continue
            if candidate_id in candidate_records:
                raise DeepResearchError(
                    f"RECOVERY_JOB_MATERIALIZATION_FAILED: duplicate candidate identity {candidate_id}"
                )
            candidate_records[candidate_id] = (section, candidate)

    source_by_id = {str(item.get("id")): item for item in packet.get("sources", []) if item.get("id")}
    hard_needs_by_function = {
        str(need.get("target_editorial_function") or "").upper(): need
        for need in executable_needs
        if str(need.get("target_editorial_function") or "").upper() in {"ACCOUNTABILITY", "SERVICE"}
        and str(need.get("need_id") or "").startswith("BREADTH:")
    }
    jobs = []
    hard_breadth_lanes = []
    # An explicit, validated empty provider target has no candidate opportunity
    # in the initial provider round. Its unresolved acquisition need remains
    # visible and is eligible in the ordinary bounded recovery epoch.
    initial_no_result_lanes = {
        str(item.get("target_id", "")).removeprefix("HARD:")
        for item in packet.get("provider_response_validation", {}).get("hard_targets", [])
        if item.get("target_contract_status") == "PASS"
        and item.get("target_disposition_effective") == "NO_QUALIFYING_CANDIDATE_FOUND"
        and item.get("accepted_candidate_count") == 0
    } if not recovery_only and recovery_epoch == 0 else set()
    for section in ([] if recovery_only else packet.get("sections", [])):
        # Only the selected publication candidate can change an active desk's
        # readiness.  Running a full question tree for every lower-ranked
        # alternative doubled the latest replay's work (18 jobs / 144
        # questions) without creating a single useful result.  Preserve
        # curiosity for recovery-only leads, but defer non-selected active
        # alternatives until a real observation warrants promotion.
        if section.get("status") == "ACTIVE":
            candidates = [
                item for item in section.get("candidates", [])
                if item.get("id") == section.get("selected_candidate_id")
            ]
        else:
            candidates = list(section.get("recovery_candidates", []))
        for candidate in candidates:
            # Candidate-specific recovery is materialized below, one job per
            # executable need.  Do not create a second ambiguous action bucket
            # for the same need through ordinary candidate research.
            if candidate.get("id") in needs_by_candidate:
                continue
            source_ids = sorted(set(candidate.get("discovery_source_ids", [])))
            provider_candidate_id = f"{section['section_id']}:{candidate['id']}"
            hard_function = HARD_DEFICIT_SECTION_FUNCTIONS.get(str(section.get("section_id") or ""))
            hard_need = hard_needs_by_function.get(hard_function or "")
            hard_deficit = (
                {
                    "need_id": str(hard_need.get("need_id")),
                    "target_editorial_function": hard_function,
                }
                if hard_need and hard_function
                else None
            )
            exact_provider_sources = [
                {
                    "source_id": source_id,
                    "url": str(source.get("url") or ""),
                    "provider_supplied_url": str(source.get("provider_supplied_url") or source.get("url") or ""),
                    "provider_lead_id": source.get("provider_lead_id"),
                    "provider_candidate_id": provider_candidate_id,
                    "lead_origin": source.get("lead_origin") or "DETERMINISTIC_DISCOVERY",
                    "provider_source_role": (
                        "PRIMARY" if source_id in set(candidate.get("primary_evidence_source_ids", []))
                        else "INDEPENDENT" if source_id in set(candidate.get("independent_evidence_source_ids", []))
                        else "CONTEXT"
                    ),
                    **({"hard_deficit": deepcopy(hard_deficit)} if hard_deficit else {}),
                }
                for source_id in source_ids
                if (source := source_by_id.get(source_id))
                and source.get("provider_lead_id")
                and (source.get("lead_origin") or "PROVIDER_EXACT") == "PROVIDER_EXACT"
                and source.get("url")
            ]
            lead = create_lead(
                desk=section["section_id"], topic=str(candidate.get("title") or candidate["id"]),
                discovery_source={
                    "source_ids": source_ids,
                    "known_seed": bool(source_ids),
                    "provider_candidate_id": provider_candidate_id,
                    "exact_provider_sources": exact_provider_sources,
                },
                observed_at=str(packet.get("edition_date")), reason_interesting="RESEARCH_CANDIDATE",
                event_entities=list(candidate.get("entities", [])),
                geography=list(candidate.get("geography", [])),
                scope_connections=list(candidate.get("scope_connections", [])),
                related_event_cluster=events.get(f"{section['section_id']}:{candidate['id']}"),
            )
            existing = plan_by_section.get(section["section_id"], {}).get("research_budget", {}) or {}
            budget_class = {"brief": "QUICK", "normal": "STANDARD", "major": "DEEP", "investigation": "INVESTIGATIVE_LEAD"}.get(existing.get("level"), "STANDARD")
            job = start_research_job(lead, config, budget_class=budget_class, run_scope_id=run_scope_id)
            job["research_lane"] = "GENERAL_DISCOVERY"
            jobs.append(job)

    # Every executable recovery need gets exactly one visible recovery job.
    # This is deliberately independent of a section's ACTIVE/NO_NEWS status:
    # a prior recovery round may have discovered a weak candidate in a
    # NO_NEWS desk, and its P0 evidence need must not vanish before execution.
    recovery_job_mappings = []
    for need in sorted(executable_needs, key=lambda item: str(item["need_id"])):
        candidate_id = need.get("candidate_id")
        if candidate_id:
            record = candidate_records.get(str(candidate_id))
            if record is None:
                raise DeepResearchError(
                    f"RECOVERY_JOB_MATERIALIZATION_FAILED: candidate {candidate_id} for {need['need_id']} is absent"
                )
            section, candidate = record
            source_ids = sorted(set(candidate.get("discovery_source_ids", [])) | set(need.get("already_known_source_ids", [])))
            known_urls = sorted({
                str(source_by_id[source_id].get("url")) for source_id in source_ids
                if source_id in source_by_id and source_by_id[source_id].get("url")
            })
            lead = create_lead(
                desk=str(need.get("section_id") or section["section_id"]),
                topic=str(candidate.get("title") or need["need_id"]),
                discovery_source={
                    "source_ids": source_ids,
                    "known_urls": known_urls,
                    "known_seed": bool(source_ids),
                    "recovery_need_id": need["need_id"],
                },
                observed_at=str(packet.get("edition_date")),
                reason_interesting=f"RECOVERY_EVIDENCE_NEED:{need['need_id']}",
                event_entities=list(need.get("query_context", {}).get("entities", candidate.get("entities", []))),
                geography=list(need.get("query_context", {}).get("geography", candidate.get("geography", []))),
                scope_connections=list(candidate.get("scope_connections", [])),
                related_event_cluster=need.get("event_id") or candidate.get("event_id") or events.get(f"{section['section_id']}:{candidate_id}"),
            )
        else:
            # Edition-wide breadth tracks remain independent from unresolved
            # candidates, which preserves the P0+P1 fairness contract.
            sections = need.get("search_constraints", {}).get("eligible_section_ids", [])
            topic = " / ".join(str(item) for item in need.get("topic_identifiers", []) if item) or need["kind"]
            lead = create_lead(
                desk=str(sections[0] if sections else "front"),
                topic=topic,
                discovery_source={"known_seed": False, "recovery_need_id": need["need_id"]},
                observed_at=str(packet.get("edition_date")),
                reason_interesting=f"RECOVERY_BREADTH_NEED:{need['need_id']}",
            )
        priority = _recovery_priority(need)
        # Recovery needs are editorially material.  QUICK is adequate for
        # optional/context probes, but it would limit a P0/P1 discovery result
        # to one exact-page follow-up and reintroduce lead attrition by budget
        # accident.  STANDARD remains finite while allowing diverse inspection.
        budget_class = "STANDARD" if priority in {"P0_BLOCKING_EVIDENCE", "P1_BREADTH", "P1_DISTINCT_EVENT"} else "QUICK"
        job = start_research_job(
            lead, config, budget_class=budget_class, recovery_needs=[need],
            run_scope_id=run_scope_id,
            recovery_identity=f"EPOCH:{recovery_epoch}:{need['need_id']}",
        )
        if str(need.get("need_id") or "").startswith("BREADTH:"):
            target_function = str(need.get("target_editorial_function") or "") or None
            lane = target_function or f"BREADTH:{str(need.get('kind') or '').removeprefix('NEED_').lower()}"
            limits = config["executor"]["budget_action_limits"][budget_class]
            job.update({
                "research_lane": lane,
                "hard_requirement": str(need.get("kind") or "").removeprefix("NEED_").lower(),
                "budget_reservation": {
                    "mode": "REUSE_EXISTING_BOUNDED_CAPACITY",
                    "search_actions": int(limits.get("search_actions", 0)),
                    "fetches": int(limits.get("fetches", 0)),
                },
            })
            if target_function in initial_no_result_lanes and not candidate_id:
                job["action_deferral_reason"] = "PROVIDER_NO_RESULT_REQUIRES_RECOVERY_EPOCH"
            hard_breadth_lanes.append({
                "lane_id": f"HARD:{need['need_id']}",
                "need_id": need["need_id"],
                "hard_requirement": job["hard_requirement"],
                "target_editorial_function": target_function,
                "job_id": job["job_id"],
                "status": "DEFERRED" if job.get("action_deferral_reason") else "PLANNED",
                "deferral_reason": job.get("action_deferral_reason"),
                "budget_reserved": job["budget_reservation"],
            })
        else:
            job["research_lane"] = "RECOVERY"
        jobs.append(job)
        recovery_job_mappings.append({
            "recovery_need_id": need["need_id"],
            "job_id": job["job_id"],
            "priority": priority,
            "candidate_id": need.get("candidate_id"),
            "event_id": need.get("event_id"),
            "desk": job["lead"]["desk"],
            "need_type": need.get("kind"),
            "missing_role": need.get("missing_evidence_role"),
            "source_attempt_id": need.get("source_attempt_id"),
            "run_scope_id": run_scope_id,
            "recovery_epoch": recovery_epoch,
            "created_from_stage": "research_recovery" if recovery_epoch else "deep_research",
            "attempt_count": need.get("attempt_count", 0),
            "max_attempts": need.get("max_attempts", 1),
        })
    for signal in ([] if recovery_only else discovery_signals or []):
        lead = create_lead(
            desk=str(signal.get("section_id") or "front"),
            topic=str(signal.get("label") or signal.get("title") or signal.get("target_id") or "Discovery signal"),
            discovery_source={
                "url": signal.get("url"), "channel": "WATCHER_SIGNAL",
                "known_seed": bool(signal.get("target_id")),
            },
            observed_at=str(signal.get("observed_at") or packet.get("edition_date")),
            reason_interesting=str(signal.get("change_status") or "DISCOVERY_SIGNAL"),
        )
        job = start_research_job(lead, config, budget_class="QUICK", run_scope_id=run_scope_id)
        job["research_lane"] = "GENERAL_DISCOVERY"
        jobs.append(job)
    for job in jobs:
        job["research_date"] = packet.get("edition_date")
    return {
        "schema_version": 1,
        "status": "PLANNED",
        "edition_date": packet.get("edition_date"),
        "philosophy": config["philosophy"],
        "open_discovery": config["open_discovery"],
        "jobs": jobs,
        "hard_breadth_lanes": hard_breadth_lanes,
        "general_discovery_job_count": sum(job.get("research_lane") == "GENERAL_DISCOVERY" for job in jobs),
        "budget_allocation": {
            "mode": "REUSE_EXISTING_BOUNDED_CAPACITY",
            "budget_increased": False,
            "hard_breadth_lane_count": len(hard_breadth_lanes),
            "general_discovery_job_count": sum(job.get("research_lane") == "GENERAL_DISCOVERY" for job in jobs),
        },
        "executable_recovery_need_ids": sorted(executable_need_ids),
        "recovery_job_mappings": recovery_job_mappings,
        "recovery_plan_status": recovery_plan.get("status"),
        # The planning-stage objective makes the semantic gap visible before
        # recovery executes; each bounded recovery job retains its own target.
        "semantic_acquisition_objectives": deepcopy(research_plan.get("semantic_acquisition_objectives", [])),
        "recovery_epoch": recovery_epoch,
        "publication_gate_status": "NOT_EVALUATED",
    }


def validate_deep_research_state(value: dict) -> list[str]:
    if not isinstance(value, dict) or value.get("schema_version") != 1 or value.get("status") not in {"PLANNED", "RESEARCHING", "STOPPED"}:
        return ["DEEP_RESEARCH_ROOT_INVALID"]
    issues = []
    hard_lanes = value.get("hard_breadth_lanes", [])
    if "hard_breadth_lanes" in value and not isinstance(hard_lanes, list):
        issues.append("DEEP_RESEARCH_HARD_BREADTH_LANES_INVALID")
    allocation = value.get("budget_allocation", {})
    if "budget_allocation" in value and (not isinstance(allocation, dict) or allocation.get("budget_increased") is not False):
        issues.append("DEEP_RESEARCH_BUDGET_ALLOCATION_INVALID")
    for job in value.get("jobs", []):
        budget = job.get("budget", {})
        if (
            job.get("lead", {}).get("publication_evidence") is not False
            or job.get("publication_gate_status") != "PENDING"
            or len(job.get("branches", [])) > budget.get("max_branches", -1)
            or job.get("round", 0) > budget.get("max_followup_rounds", -1)
            or job.get("current_depth", 0) > budget.get("max_depth", -1)
            or set(job.get("context", {})) != {"KNOWN", "SUPPORTED", "DISPUTED", "UNKNOWN", "NEXT_QUESTIONS", "SOURCE_GAPS", "CONTRADICTIONS", "DEAD_ENDS"}
        ):
            issues.append(f"DEEP_RESEARCH_JOB_INVALID:{job.get('job_id')}")
        if "research_lane" in job and (not isinstance(job.get("research_lane"), str) or not job.get("research_lane")):
            issues.append(f"DEEP_RESEARCH_RESEARCH_LANE_INVALID:{job.get('job_id')}")
    if isinstance(hard_lanes, list):
        job_ids = {str(job.get("job_id")) for job in value.get("jobs", []) if job.get("job_id")}
        for lane in hard_lanes:
            if (
                not isinstance(lane, dict)
                or not lane.get("lane_id")
                or not lane.get("need_id")
                or str(lane.get("job_id")) not in job_ids
                or lane.get("status") not in {"PLANNED", "EXECUTED", "DEFERRED"}
                or not isinstance(lane.get("budget_reserved"), dict)
                or lane["budget_reserved"].get("mode") != "REUSE_EXISTING_BOUNDED_CAPACITY"
            ):
                issues.append("DEEP_RESEARCH_HARD_BREADTH_LANE_INVALID")
    expected_need_ids = value.get("executable_recovery_need_ids")
    mappings = value.get("recovery_job_mappings")
    if expected_need_ids is not None or mappings is not None:
        expected = set(expected_need_ids or [])
        materialized = [
            str(need.get("need_id"))
            for job in value.get("jobs", [])
            for need in job.get("recovery_needs", [])
            if isinstance(need, dict) and need.get("need_id")
        ]
        mapped = [str(item.get("recovery_need_id")) for item in (mappings or []) if item.get("recovery_need_id")]
        if expected != set(materialized) or len(materialized) != len(set(materialized) or ()) or expected != set(mapped) or len(mapped) != len(set(mapped) or ()):
            issues.append("RECOVERY_JOB_MATERIALIZATION_FAILED")
    return issues
