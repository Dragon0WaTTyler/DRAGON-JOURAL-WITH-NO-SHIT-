"""Evidence-aware perspective, question, and research-budget planning."""

from __future__ import annotations


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


def _candidate_sources(candidate: dict) -> set[str]:
    return set().union(*(
        set(candidate.get(field, []))
        for field in (
            "discovery_source_ids", "verification_source_ids",
            "primary_evidence_source_ids", "independent_evidence_source_ids",
        )
    ))


def _budget(section_id: str, candidate: dict, independent_origins: int) -> dict:
    score = 2
    score += min(2, len(candidate.get("primary_evidence_source_ids", [])))
    score += min(2, independent_origins)
    score += 1 if candidate.get("unknowns") else 0
    score += 1 if candidate.get("disputed_points") else 0
    score += 2 if section_id in {"front", "investigations"} else 0
    if section_id == "investigations" or score >= 9:
        level, branches, followups = "investigation", 6, 8
    elif score >= 7:
        level, branches, followups = "major", 4, 6
    elif score >= 4:
        level, branches, followups = "normal", 3, 4
    else:
        level, branches, followups = "brief", 1, 2
    return {
        "score": score,
        "level": level,
        "maximum_parallel_branches": branches,
        "maximum_followup_questions": followups,
    }


def build_research_plan(packet: dict, intelligence: dict) -> dict:
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
        plans.append({
            "section_id": section["section_id"],
            "candidate_id": selected_id,
            "event_id": event_id,
            "perspectives": list(SECTION_PERSPECTIVES.get(section["section_id"], DEFAULT_PERSPECTIVES)),
            "questions": questions,
            "research_budget": _budget(section["section_id"], candidate, independent_origins),
            "source_ids": sorted(_candidate_sources(candidate)),
            "known_facts": candidate.get("facts", []),
            "reported_claims": candidate.get("claims", []),
            "unknowns": candidate.get("unknowns", []),
            "disputed_points": candidate.get("disputed_points", []),
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
        budget = item.get("research_budget", {})
        if (
            not item.get("candidate_id")
            or not item.get("perspectives")
            or not item.get("questions")
            or budget.get("level") not in {"brief", "normal", "major", "investigation"}
            or not isinstance(item.get("source_ids"), list)
        ):
            issues.append(f"RESEARCH_PLAN_INCOMPLETE:{item.get('section_id')}")
    return issues
