"""Evidence-aware perspective, question, and research-budget planning."""

from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator
import yaml


SECTION_PERSPECTIVES = {
    "front": ("المصلحة العامة", "المتأثرون", "الخبير المستقل", "المتشكك"),
    "siyasa_dawla": ("الحكومة", "المعارضة", "المتأثرون", "الخبير القانوني", "الإحصاء"),
    "iqtisad_flous": ("صانع السياسة", "الخبير الاقتصادي", "العامل أو المستهلك", "المقارنة الإقليمية"),
    "science": ("الباحث", "خبير المنهجية", "المتشكك", "التكرار والإجماع"),
    "investigations": ("المدقق", "الجهة المعنية", "المتضرر", "الموقف المقابل", "الخبير القانوني"),
    "meknes_local": ("المؤسسة المحلية", "الساكن", "الخبير التقني", "التنفيذ والميزانية"),
    "technology": ("الشركة", "الباحث المستقل", "المستخدم", "المنظم", "الأثر الاجتماعي"),
}
DEFAULT_PERSPECTIVES = ("الجهة الرسمية", "المتأثرون", "الخبير المستقل", "التفسير البديل")

DEFAULT_BUDGET_CONFIG = {
    "version": 1,
    "weights": {
        "base": 2, "primary_evidence": 1, "independent_origin": 1,
        "uncertainty": 1, "controversy": 1, "front_page": 2,
        "investigation": 2, "newsworthiness": 1, "public_impact": 1,
        "morocco_meknes_relevance": 1, "strategic_impact": 1,
        "evidence_quality": 1, "novelty": 1, "investigative_potential": 1,
    },
    "signal_caps": {"primary_evidence": 2, "independent_origin": 2, "provider_score": 2},
    "thresholds": {"normal": 4, "major": 7, "investigation": 9},
    "budgets": {
        "brief": {"maximum_parallel_branches": 1, "maximum_followup_questions": 2},
        "normal": {"maximum_parallel_branches": 3, "maximum_followup_questions": 4},
        "major": {"maximum_parallel_branches": 4, "maximum_followup_questions": 6},
        "investigation": {"maximum_parallel_branches": 6, "maximum_followup_questions": 8},
    },
    "context": {"maximum_items_per_bucket": 8},
}


class ResearchPlanningError(RuntimeError):
    pass


def load_research_budget_config(path: Path, schema_path: Path | None = None) -> dict:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
        schema = json.loads(
            (schema_path or path.with_name("research-budget-schema.json")).read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError, yaml.YAMLError, json.JSONDecodeError) as exc:
        raise ResearchPlanningError(str(exc)) from exc
    errors = sorted(Draft202012Validator(schema).iter_errors(value), key=lambda item: list(item.path))
    if errors:
        raise ResearchPlanningError("; ".join(error.message for error in errors))
    thresholds = value["thresholds"]
    if not thresholds["normal"] < thresholds["major"] < thresholds["investigation"]:
        raise ResearchPlanningError("research budget thresholds must be strictly increasing")
    return value


def _candidate_sources(candidate: dict) -> set[str]:
    return set().union(*(
        set(candidate.get(field, []))
        for field in (
            "discovery_source_ids", "verification_source_ids",
            "primary_evidence_source_ids", "independent_evidence_source_ids",
        )
    ))


def _provider_signal(candidate: dict, name: str, cap: int) -> int:
    value = candidate.get(name, 0)
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return min(cap, max(0, round(float(value) / 5)))
    return 0


def _budget(section_id: str, candidate: dict, independent_origins: int, config: dict) -> dict:
    weights = config["weights"]
    caps = config["signal_caps"]
    raw_signals = {
        "base": 1,
        "primary_evidence": min(caps["primary_evidence"], len(candidate.get("primary_evidence_source_ids", []))),
        "independent_origin": min(caps["independent_origin"], independent_origins),
        "uncertainty": int(bool(candidate.get("unknowns"))),
        "controversy": int(bool(candidate.get("disputed_points"))),
        "front_page": int(section_id == "front"),
        "investigation": int(section_id == "investigations"),
    }
    for name in (
        "newsworthiness", "public_impact", "morocco_meknes_relevance",
        "strategic_impact", "evidence_quality", "novelty", "investigative_potential",
    ):
        raw_signals[name] = _provider_signal(candidate, name, caps["provider_score"])
    contributions = {name: raw_signals[name] * weights[name] for name in raw_signals}
    score = sum(contributions.values())
    thresholds = config["thresholds"]
    if section_id == "investigations" or score >= thresholds["investigation"]:
        level = "investigation"
    elif score >= thresholds["major"]:
        level = "major"
    elif score >= thresholds["normal"]:
        level = "normal"
    else:
        level = "brief"
    limits = config["budgets"][level]
    return {
        "score": score,
        "level": level,
        "signal_contributions": contributions,
        **limits,
    }


def build_research_plan(packet: dict, intelligence: dict, budget_config: dict | None = None) -> dict:
    budget_config = budget_config or DEFAULT_BUDGET_CONFIG
    events_by_candidate = {
        key: event["event_id"]
        for event in intelligence.get("event_clusters", [])
        for key in event.get("candidate_keys", [])
    }
    origins_by_event = {
        event["event_id"]: event.get("independent_origin_count", 0)
        for event in intelligence.get("event_clusters", [])
    }
    plans = []
    for section in packet.get("sections", []):
        if section.get("status") == "NO_NEWS":
            reason = section.get("no_news_reason")
            plans.append({
                "section_id": section["section_id"],
                "status": "NO_NEWS",
                "candidate_id": None,
                "event_id": None,
                "perspectives": [],
                "questions": ["ما التطور الموثق الذي سيبرر إعادة فتح هذا القسم؟"],
                "research_budget": None,
                "research_branches": [],
                "source_ids": [],
                "known_facts": [],
                "reported_claims": [],
                "unknowns": [],
                "disputed_points": [],
                "research_snapshot": {
                    "what_we_know": [],
                    "what_is_strongly_supported": [],
                    "what_is_disputed": [],
                    "what_remains_unknown": [reason],
                    "what_to_search_next": "ما التطور الموثق الذي سيبرر إعادة فتح هذا القسم؟",
                },
                "dynamic_outline": [],
                "context_management": {
                    "policy": "BOUNDED_PERIODIC_COMPRESSION",
                    "maximum_items_per_bucket": budget_config["context"]["maximum_items_per_bucket"],
                    "input_items": 1,
                    "retained_items": 1,
                },
                "no_news_reason": reason,
                "fallback_action": section.get("fallback_action"),
            })
            continue
        selected_id = section.get("selected_candidate_id")
        candidate = next(
            item for item in section.get("candidates", []) if item.get("id") == selected_id
        )
        key = f"{section['section_id']}:{selected_id}"
        event_id = events_by_candidate.get(key)
        independent_origins = origins_by_event.get(event_id, 0)
        questions = [
            "ما الذي حدث، وما الدليل الأولي المباشر عليه؟",
            "ما الذي نعرفه بثقة، وما الذي لا يزال مجهولا أو متنازعا عليه؟",
            "هل تعتمد المصادر الظاهرة على أصل خبري واحد؟",
            "ما أقوى تفسير بديل، وما الدليل الذي قد يفند تفسيرنا؟",
            "من يتأثر، وما النتيجة القابلة للقياس أو المتابعة لاحقا؟",
        ]
        if candidate.get("unknowns"):
            questions.append("ما السؤال التالي الذي يمكن أن يقلص مواطن الجهل المسجلة؟")
        if candidate.get("disputed_points"):
            questions.append("كيف نصوغ نقاط الخلاف من دون تحويل ادعاء طرف إلى حقيقة؟")
        perspectives = list(SECTION_PERSPECTIVES.get(section["section_id"], DEFAULT_PERSPECTIVES))
        budget = _budget(section["section_id"], candidate, independent_origins, budget_config)
        context_limit = budget_config["context"]["maximum_items_per_bucket"]
        known = list(candidate.get("facts", []))
        reported = list(candidate.get("claims", []))
        unknowns = list(candidate.get("unknowns", []))
        disputed = list(candidate.get("disputed_points", []))
        retained = {
            "what_we_know": known[:context_limit],
            "what_is_strongly_supported": list(candidate.get("primary_evidence_source_ids", []))[:context_limit],
            "what_is_disputed": disputed[:context_limit],
            "what_remains_unknown": unknowns[:context_limit],
            "what_to_search_next": questions[-1],
        }
        plans.append({
            "section_id": section["section_id"],
            "status": "ACTIVE",
            "candidate_id": selected_id,
            "event_id": event_id,
            "perspectives": perspectives,
            "questions": questions,
            "research_budget": budget,
            "research_branches": [
                {"perspective": perspective, "question": questions[index % len(questions)]}
                for index, perspective in enumerate(perspectives[:budget["maximum_parallel_branches"]])
            ],
            "source_ids": sorted(_candidate_sources(candidate)),
            "known_facts": known[:context_limit],
            "reported_claims": reported[:context_limit],
            "unknowns": unknowns[:context_limit],
            "disputed_points": disputed[:context_limit],
            "research_snapshot": retained,
            "dynamic_outline": ["الوقائع", "الأدلة", "الخلاف", "السياق", "السؤال التالي"],
            "context_management": {
                "policy": "BOUNDED_PERIODIC_COMPRESSION",
                "maximum_items_per_bucket": context_limit,
                "input_items": len(known) + len(reported) + len(unknowns) + len(disputed),
                "retained_items": sum(len(value) for value in (known[:context_limit], reported[:context_limit], unknowns[:context_limit], disputed[:context_limit])),
            },
        })
    return {
        "schema_version": 1,
        "status": "PASS",
        "edition_date": packet.get("edition_date"),
        "plans": plans,
    }


def validate_research_plan(value: dict, expected_sections: set[str]) -> list[str]:
    issues = []
    plans = value.get("plans")
    if value.get("schema_version") != 1 or value.get("status") != "PASS" or not isinstance(plans, list):
        return ["RESEARCH_PLAN_ROOT_INVALID"]
    ids = [item.get("section_id") for item in plans if isinstance(item, dict)]
    if len(ids) != len(expected_sections) or set(ids) != expected_sections:
        issues.append("RESEARCH_PLAN_SECTION_INVENTORY_INVALID")
    for item in plans:
        if not isinstance(item, dict):
            issues.append("RESEARCH_PLAN_ITEM_INVALID")
            continue
        if item.get("status") == "NO_NEWS":
            if (
                item.get("candidate_id") is not None
                or item.get("research_branches") != []
                or not item.get("no_news_reason")
                or item.get("fallback_action") not in {
                    "RADAR", "DOSSIER_FOLLOW_UP", "PUBLIC_DATA_ANALYSIS", "SKIP"
                }
                or item.get("context_management", {}).get("policy") != "BOUNDED_PERIODIC_COMPRESSION"
            ):
                issues.append(f"RESEARCH_PLAN_NO_NEWS_INVALID:{item.get('section_id')}")
            continue
        budget = item.get("research_budget", {})
        if (
            item.get("status") != "ACTIVE"
            or not item.get("candidate_id")
            or not item.get("perspectives")
            or not item.get("questions")
            or budget.get("level") not in {"brief", "normal", "major", "investigation"}
            or not isinstance(item.get("source_ids"), list)
            or not item.get("research_branches")
            or item.get("context_management", {}).get("policy") != "BOUNDED_PERIODIC_COMPRESSION"
            or set(item.get("research_snapshot", {})) != {
                "what_we_know", "what_is_strongly_supported", "what_is_disputed",
                "what_remains_unknown", "what_to_search_next",
            }
        ):
            issues.append(f"RESEARCH_PLAN_INCOMPLETE:{item.get('section_id')}")
    return issues
