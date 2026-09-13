from dragon.deep_research_executor import build_event_bundles
from dragon.research_recovery import _breadth_acquisition_plan
from dragon.investigation_scope import evaluate_super_investigation_scope


def _action(mode="DISCOVER_NEW_EVENT_FOR_SEMANTIC_NEED", target="ACCOUNTABILITY", need="N1", job="J1"):
    return {
        "action_id": job, "recovery_need_id": need, "originating_recovery_need_id": need,
        "recovery_mode": mode, "target_editorial_function": target, "desk": "investigations" if target == "ACCOUNTABILITY" else "service",
        "event_acquisition_plan": {"target_editorial_function": target},
        "event_context": {"topic_terms": ["investigations" if target == "ACCOUNTABILITY" else "service"], "research_date": "2026-09-13"},
        "acceptable_story_roles": ["brief"],
    }


def _observation(action, *, title, fingerprint="EVENT-1", action_text="orders monitoring", obj="election complaints", source_id="S1"):
    return {
        "observation_id": "OBS-1", "source_id": source_id, "origin": "official.gov.ma",
        "source_class": "primary", "verification_status": "VALIDATED_EVIDENCE",
        "event_skeleton": {"state": "CONCRETE_EVENT", "event_fingerprint": fingerprint, "title": title,
            "actor": "Public authority", "action": action_text, "object": obj,
            "topic": title, "published_at": "2026-09-10", "lead_paragraphs": f"Public authority {action_text} {obj}.",
            "geography": ["Morocco"], "temporal_relevance": {"active_on_edition_date": True}},
        "source_role_resolution": {"document_type": "DIRECTIVE", "publisher_event_relation": "ISSUER"},
        "evidence_relation": "SUPPORTS", "directness": "DIRECT",
        "article_metadata": {"publisher": {"name": "Public authority"}},
        "provenance": {"action_id": action["action_id"], "originating_recovery_need_id": action["recovery_need_id"], "recovery_mode": action["recovery_mode"]},
    }


def _source(source_id="S1"):
    return {"id": source_id, "source_type": "primary", "origin": "official.gov.ma", "url": "https://official.gov.ma/directive"}


def test_mode_b_creates_need_scoped_root_and_validates_accountability():
    action = _action()
    bundles, discoveries = build_event_bundles([_observation(action, title="Monitoring directive")], [], [_source()], [action])
    assert len(bundles) == 1
    bundle = bundles[0]
    assert bundle["event_lead_state"] == "NEW_RECOVERY_EVENT_LEAD"
    assert bundle["recovery_need_id"] == "N1"
    assert bundle["state"] == "EVENT_VALIDATED"
    assert any(item["function"] == "ACCOUNTABILITY" for item in bundle["editorial_functions"])
    assert discoveries and discoveries[0]["event_id"] == bundle["event_lead_id"]


def test_mode_b_service_creates_new_root_without_existing_lead():
    action = _action(target="SERVICE")
    obs = _observation(action, title="Registration procedure", action_text="opens registration", obj="applications")
    obs["event_skeleton"]["lead_paragraphs"] = "Public service registration procedure opens for eligible applicants with a documented deadline on 2026-09-22 and access instructions. " * 3
    bundles, discoveries = build_event_bundles([obs], [], [_source()], [action])
    assert bundles[0]["new_recovery_event"] is True
    assert bundles[0]["state"] == "EVENT_VALIDATED"
    assert any(item["function"] == "SERVICE" for item in bundles[0]["editorial_functions"])
    assert discoveries


def test_mode_a_different_event_is_not_attached_or_regenerated():
    action = _action(mode="CORROBORATE_EXISTING_EVENT")
    existing = {"event_lead_id": "EV-OLD", "event_skeleton": {"state": "CONCRETE_EVENT", "event_fingerprint": "OLD", "title": "Old event", "actor": "Public authority", "action": "orders monitoring", "object": "old complaints", "published_at": "2026-09-10", "geography": ["Morocco"]}}
    obs = _observation(action, title="Different notice", fingerprint="NEW", action_text="publishes", obj="tax notice")
    obs["event_skeleton"]["geography"] = ["India"]
    obs["event_skeleton"]["published_at"] = "2026-08-01"
    bundles, _ = build_event_bundles([obs], [existing], [_source()], [action])
    assert bundles[0]["event_lead_id"] == "EV-OLD"
    assert bundles[0]["observations"] == []


def test_new_event_identity_excludes_retrieval_ids():
    a1 = _action(job="J1")
    a2 = _action(job="J2")
    o1 = _observation(a1, title="Monitoring directive")
    o2 = _observation(a2, title="Monitoring directive")
    b1, _ = build_event_bundles([o1], [], [_source()], [a1])
    b2, _ = build_event_bundles([o2], [], [_source()], [a2])
    assert b1[0]["event_lead_id"] == b2[0]["event_lead_id"]


def test_normal_breadth_scope_is_explicit_and_not_super_scope():
    need = {"kind": "NEED_ACCOUNTABILITY_AND_SERVICE", "target_editorial_function": "ACCOUNTABILITY"}
    plan = _breadth_acquisition_plan(need, {"sections": []}, {"event_clusters": [], "source_records": []})
    assert plan["geography_scope"] == "GLOBAL_WITH_MOROCCO_PRIORITY"
    assert plan["target_editorial_function"] == "ACCOUNTABILITY"


def test_super_investigation_scope_remains_isolated():
    result = evaluate_super_investigation_scope({"geography": ["India"]})
    assert result["status"] == "NOT_ELIGIBLE"
    assert result["scope_rule"] == "MOROCCO + MEKNES ONLY"
