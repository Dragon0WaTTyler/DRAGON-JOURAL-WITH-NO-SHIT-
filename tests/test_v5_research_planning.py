from dragon.research_planning import build_research_plan, validate_research_plan


def _candidate(identifier: str, *, disputed: bool = False) -> dict:
    return {
        "id": identifier,
        "facts": ["واقعة موثقة"],
        "claims": ["ادعاء يحتاج إلى نسبة واضحة"],
        "unknowns": ["معلومة غير متاحة"],
        "disputed_points": ["نقطة خلاف"] if disputed else [],
        "discovery_source_ids": ["s1"],
        "verification_source_ids": ["s2"],
        "primary_evidence_source_ids": ["s2"],
        "independent_evidence_source_ids": ["s1"],
    }


def test_research_plan_is_stable_relevant_and_evidence_budgeted() -> None:
    sections = []
    intelligence_events = []
    for section_id in ("front", "science", "investigations"):
        candidate = _candidate(f"{section_id}-lead", disputed=section_id == "investigations")
        sections.append({
            "section_id": section_id,
            "selected_candidate_id": candidate["id"],
            "candidates": [candidate],
        })
        intelligence_events.append({
            "event_id": f"EVT-{section_id.upper()}",
            "candidate_keys": [f"{section_id}:{candidate['id']}"],
            "independent_origin_count": 2,
        })
    packet = {"edition_date": "2099-01-02", "sections": sections}
    intelligence = {"event_clusters": intelligence_events}

    value = build_research_plan(packet, intelligence)
    assert value == build_research_plan(packet, intelligence)
    assert validate_research_plan(value, {"front", "science", "investigations"}) == []
    plans = {item["section_id"]: item for item in value["plans"]}
    assert "خبير المنهجية" in plans["science"]["perspectives"]
    assert "الموقف المقابل" in plans["investigations"]["perspectives"]
    assert plans["investigations"]["research_budget"]["level"] == "investigation"
    assert plans["front"]["event_id"] == "EVT-FRONT"
    assert any("أصل خبري واحد" in item for item in plans["front"]["questions"])


def test_research_plan_validator_rejects_missing_inventory() -> None:
    value = {"schema_version": 1, "status": "PASS", "plans": []}
    assert "RESEARCH_PLAN_SECTION_INVENTORY_INVALID" in validate_research_plan(
        value, {"front"}
    )
