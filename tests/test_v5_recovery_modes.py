from dragon.deep_research_executor import build_event_bundles, _observation as make_observation, classify_document_type, extract_event_skeleton, query_ladder
from dragon.deep_research_executor import apply_executor_results_to_packet
from dragon.research_recovery import _breadth_acquisition_plan, build_recovery_plan
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


def test_query_target_cannot_turn_third_party_tax_page_into_primary():
    action = _action(target="ACCOUNTABILITY", need="N-TAX")
    action.update({"known_entities": ["Supreme Audit Council"], "query": "Supreme Audit Council audit September 2026",
                   "action_type": "FETCH_URL", "question_id": "Q", "branch_id": "B", "expected_result_type": "EXTRACTED_SOURCE",
                   "provenance_requirements": {"required_role": None, "must_be_distinct_event": True}})
    raw = {"url": "https://cagurujitax.com/tax-audit-due-date-extension", "canonical_url": "https://cagurujitax.com/tax-audit-due-date-extension",
           "title": "Tax Audit Due Date Extension: Will Tax Audit Date Be Extended?", "publisher": "cagurujitax.com",
           "text": "Tax audit guidance explains the filing deadline and advises readers to verify against official government sources. " * 4,
           "published_at": "2026-09-13", "fetch_status": "FETCHED", "content_hash": "a" * 64, "source_class": "primary"}
    obs = make_observation(action, raw, set())
    assert obs["source_class"] == "unknown"
    assert obs["source_role_resolution"]["evidence_role"] == "UNRESOLVED"
    assert obs["source_role_resolution"]["publisher_event_relation"] != "PUBLISHER_IS_DOCUMENT_ISSUER"
    assert "Supreme Audit Council" not in str(obs["event_skeleton"])
    assert "Morocco" not in (obs["event_skeleton"] or {}).get("geography", [])
    assert classify_document_type(raw) == "NEWS_ARTICLE"


def test_observed_official_actor_can_still_resolve_primary():
    action = _action(target="ACCOUNTABILITY", need="N-OFFICIAL")
    action.update({"known_entities": ["Prosecution Authority"], "action_type": "FETCH_URL", "question_id": "Q", "branch_id": "B", "expected_result_type": "EXTRACTED_SOURCE",
                   "provenance_requirements": {"required_role": None, "must_be_distinct_event": True}})
    raw = {"url": "https://prosecution.gov.ma/directive", "canonical_url": "https://prosecution.gov.ma/directive",
           "title": "Prosecution Authority directive orders monitoring", "publisher": "Prosecution Authority",
           "text": "Prosecution Authority orders monitoring and rapid complaint processing during the election period. " * 4,
           "published_at": "2026-09-13", "fetch_status": "FETCHED", "content_hash": "b" * 64, "source_class": "unknown"}
    obs = make_observation(action, raw, set())
    assert obs["source_class"] == "primary"
    assert obs["source_role_resolution"]["evidence_role"] == "PRIMARY"


def test_official_portal_republication_never_auto_promotes_primary():
    action = _action(target="ACCOUNTABILITY", need="N-PORTAL")
    action.update({"action_type": "FETCH_URL", "question_id": "Q", "branch_id": "B", "expected_result_type": "EXTRACTED_SOURCE",
                   "source_route": {"route_id": "maroc-news", "verification_provenance": "official-national-portal-navigation",
                                    "semantic_capabilities": ["ACCOUNTABILITY"], "route_status": "VERIFIED_WORKING", "url": "https://maroc.ma/en/news"},
                   "provenance_requirements": {"required_role": None, "must_be_distinct_event": True}})
    raw = {"url": "https://www.maroc.ma/ar/الأخبار/prosecution-directive", "canonical_url": "https://www.maroc.ma/ar/الأخبار/prosecution-directive",
           "title": "رئاسة النيابة العامة تدعو النيابات إلى التعبئة", "publisher": "Maroc.ma",
           "article_metadata": {"publisher": {"name": "Maroc.ma", "canonical_domain": "www.maroc.ma"}},
           "text": ("أكد رئيس النيابة العامة في دورية جديدة موجهة إلى الوكلاء ضرورة تتبع مختلف مراحل الانتخابات "
                    "والتصدي للممارسات المخالفة وإنجاز الأبحاث المرتبطة بالشكايات وتأمين المداومة. "
                    "(ومع: 01 شتنبر 2026) " * 4),
           "published_at": "2026-09-01", "fetch_status": "FETCHED", "content_hash": "d" * 64, "source_class": "unknown"}
    obs = make_observation(action, raw, set())
    assert obs["origin_detail"]["portal_identity_state"] == "OFFICIAL_NATIONAL_PORTAL"
    assert obs["content_origin"] == "MAP"
    assert obs["stated_issuing_authority"] == "Public Prosecution"
    assert obs["source_role_resolution"]["evidence_role"] == "UNRESOLVED"
    assert obs["source_role_resolution"]["article_origin_state"] == "OFFICIAL_PORTAL_REPUBLICATION"


def test_verified_route_records_health_without_granting_evidence():
    action = _action(target="SERVICE", need="N-ROUTE")
    action.update({"action_type": "FETCH_URL", "question_id": "Q", "branch_id": "B", "expected_result_type": "EXTRACTED_SOURCE",
                   "source_route": {"route_id": "service-route", "url": "https://service.example/notices", "route_type": "NOTICES",
                                    "route_status": "VERIFIED_WORKING", "semantic_capabilities": ["SERVICE"], "navigation_depth": 1},
                   "provenance_requirements": {"required_role": None, "must_be_distinct_event": True}})
    raw = {"url": "https://service.example/notices", "canonical_url": "https://service.example/notices",
           "title": "Public service notice", "publisher": "Service Authority",
           "text": "Public service registration opens today and remains available through the deadline. " * 4,
           "published_at": "2026-09-13", "fetch_status": "FETCHED", "content_hash": "c" * 64, "source_class": "unknown"}
    obs = make_observation(action, raw, set())
    assert obs["route_health"]["route_id"] == "service-route"
    assert obs["route_health"]["status"] == "VERIFIED_WORKING"
    assert obs["verification_status"] != "VALIDATED_EVIDENCE"


def test_mode_b_evidence_blocked_event_retains_memory_and_marks_pivot():
    action = _action(target="ACCOUNTABILITY", need="BREADTH:accountability_and_service:1")
    blocked = _observation(action, title="Prosecution circular", source_id="blocked-source")
    blocked["source_class"] = "unknown"
    blocked["verification_status"] = "EXTRACTED_NOT_VERIFIED"
    blocked["extraction_status"] = "FETCHED"
    bundles, discoveries = build_event_bundles([blocked], [], [], [action])
    assert not discoveries
    assert bundles[0]["state"] == "EVENT_EVIDENCE_BLOCKED"
    memory = bundles[0]["blocked_event_memory"]
    assert memory["blocker"] == "MISSING_PRIMARY"
    assert memory["pivot_eligible"] is True
    packet = {"edition_date": "2026-09-13", "sources": [], "sections": [], "event_evidence_bundles": bundles}
    packet["sections"] = [
        {"section_id": "investigations", "status": "NO_NEWS", "candidates": [], "recovery_candidates": []},
        {"section_id": "opinion", "status": "NO_NEWS", "candidates": [], "recovery_candidates": []},
        {"section_id": "service", "status": "NO_NEWS", "candidates": [], "recovery_candidates": []},
    ]
    coverage = {
        "research_semantics": {"allow_open_discovery": True},
        "sources": [{"source_id": sid, "name": sid, "url": f"https://{sid}.example", "origin": f"{sid}.example", "role": "PRIMARY", "enabled": True, "authority_class": "PUBLIC", "discovery_only": True, "primary_capable": True, "independent_reporting_capable": False} for sid in ("investigations", "opinion", "service")],
        "desks": [{"section_id": sid, "source_ids": [sid], "coverage_status": "PARTIAL", "recovery_focus": ["fixture"]} for sid in ("investigations", "opinion", "service")],
    }
    plan = build_recovery_plan(packet, {"event_clusters": [], "source_records": []}, coverage, {"coverage_rules": [{"id": "accountability_and_service", "sections": ["investigations", "opinion", "service"], "minimum_active": 2}]})
    pivot_need = next(item for item in plan["needs"] if item.get("target_editorial_function") == "ACCOUNTABILITY")
    assert pivot_need["pivot_mode"] == "FIND_ALTERNATIVE_EVENT_FOR_SEMANTIC_NEED"
    assert pivot_need["blocked_event_memory"][0]["event_fingerprint"] == "EVENT-1"
    need = {
        "need_id": "BREADTH:accountability_and_service:1", "kind": "NEED_ACCOUNTABILITY_AND_SERVICE",
        "target_editorial_function": "ACCOUNTABILITY", "query_context": {"research_date": "2026-09-13"},
        "event_acquisition_plan": {"target_editorial_function": "ACCOUNTABILITY", "excluded_event_fingerprints": []},
        "pivot_mode": "FIND_ALTERNATIVE_EVENT_FOR_SEMANTIC_NEED", "blocked_event_memory": [memory],
    }
    ladder = query_ladder({"lead": {"event_entities": []}}, need)
    assert ladder[0]["variant"] == "ALTERNATIVE_ROUTE_SCOPED_ARTIFACT"
    assert "ALTERNATIVE_" in ladder[0]["intent"]


def test_mode_b_alternative_event_gets_new_bundle_without_evidence_transfer():
    action_a = _action(target="ACCOUNTABILITY", need="N-ALT", job="A")
    action_b = _action(target="ACCOUNTABILITY", need="N-ALT", job="B")
    event_a = _observation(action_a, title="Prosecution circular", fingerprint="EVENT-A", source_id="A")
    event_a["source_class"] = "unknown"
    event_a["verification_status"] = "EXTRACTED_NOT_VERIFIED"
    event_a["extraction_status"] = "FETCHED"
    event_b = _observation(action_b, title="Regulator directive adopts election integrity rules", fingerprint="EVENT-B", source_id="B", action_text="adopts", obj="election integrity rules")
    event_b["observation_id"] = "OBS-B"
    event_b["event_skeleton"]["actor"] = "Regulatory Council"
    event_b["event_skeleton"]["topic"] = "Regulator directive adopts election integrity rules"
    event_b["article_metadata"] = {"publisher": {"name": "Regulatory Council"}}
    bundles, discoveries = build_event_bundles(
        [event_a, event_b], [], [_source("B")], [action_a, action_b],
    )
    assert len(bundles) == 2
    blocked = next(item for item in bundles if item["event_fingerprint"] == "EVENT-A")
    alternative = next(item for item in bundles if item["event_fingerprint"] == "EVENT-B")
    assert blocked["state"] == "EVENT_EVIDENCE_BLOCKED"
    assert alternative["state"] == "EVENT_VALIDATED"
    assert alternative["candidate_discovery"]
    assert blocked["evidence_ids"] == []
    assert alternative["evidence_ids"] == ["B"]
    assert blocked["event_lead_id"] != alternative["event_lead_id"]
    assert all(item["event_id"] == alternative["event_lead_id"] for item in discoveries)


def test_mode_b_service_pivot_validates_first_party_operational_event():
    action_a = _action(target="SERVICE", need="N-SVC", job="SA")
    action_b = _action(target="SERVICE", need="N-SVC", job="SB")
    blocked = _observation(action_a, title="Portal republication of service notice", fingerprint="SERVICE-A", source_id="SA")
    blocked["source_class"] = "unknown"
    blocked["verification_status"] = "EXTRACTED_NOT_VERIFIED"
    blocked["extraction_status"] = "FETCHED"
    alternative = _observation(action_b, title="Ministry opens registration deadline", fingerprint="SERVICE-B", source_id="SB", action_text="opens registration", obj="applications")
    alternative["observation_id"] = "OBS-SB"
    alternative["event_skeleton"]["actor"] = "Ministry of Public Service"
    alternative["event_skeleton"]["topic"] = "Ministry opens registration deadline"
    alternative["event_skeleton"]["lead_paragraphs"] = "Ministry opens registration for eligible applicants through the deadline on 2026-09-22 with access instructions. " * 3
    alternative["article_metadata"] = {"publisher": {"name": "Ministry of Public Service"}}
    bundles, discoveries = build_event_bundles([blocked, alternative], [], [_source("SB")], [action_a, action_b])
    assert len(bundles) == 2
    winner = next(item for item in bundles if item["event_fingerprint"] == "SERVICE-B")
    assert winner["state"] == "EVENT_VALIDATED"
    assert any(item["function"] == "SERVICE" for item in winner["editorial_functions"])
    assert discoveries and discoveries[0]["event_id"] == winner["event_lead_id"]


def test_epoch_alternative_bundle_merge_preserves_blocked_event_memory():
    blocked = {"event_lead_id": "EVENT-A", "state": "EVENT_EVIDENCE_BLOCKED", "event_fingerprint": "A", "blocked_event_memory": {"pivot_eligible": True}}
    alternative = {"event_lead_id": "EVENT-B", "state": "EVENT_VALIDATED", "event_fingerprint": "B"}
    packet = {"sources": [], "sections": [], "event_evidence_bundles": [blocked]}
    execution = {"source_packet_patch": {"sources": [], "candidate_evidence_updates": [], "candidate_discoveries": [], "event_leads": [], "event_bundles": [alternative], "semantic_pivot_attempts": []}}
    merged = apply_executor_results_to_packet(packet, execution)
    assert {item["event_lead_id"] for item in merged["event_evidence_bundles"]} == {"EVENT-A", "EVENT-B"}
    assert next(item for item in merged["event_evidence_bundles"] if item["event_lead_id"] == "EVENT-A")["state"] == "EVENT_EVIDENCE_BLOCKED"
