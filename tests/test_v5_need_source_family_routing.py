from dragon.deep_research_executor import _breadth_event_queries, create_research_action, schedule_research_actions


def _need(function, routes):
    return {
        "need_id": f"BREADTH:accountability_and_service:{function}",
        "kind": "NEED_ACCOUNTABILITY_AND_SERVICE",
        "recovery_mode": "DISCOVER_NEW_EVENT_FOR_SEMANTIC_NEED",
        "target_editorial_function": function,
        "query_context": {"research_date": "2026-09-14"},
        "search_constraints": {"configured_source_routes": routes},
        "event_acquisition_plan": {"target_editorial_function": function},
    }


def _job():
    return {
        "job_id": "JOB-FAMILY", "round": 0, "regime": "GENERAL_JOURNALISM",
        "budget_class": "STANDARD", "budget": {"max_followup_rounds": 2},
        "lead": {"desk": "investigations", "topic": "gap", "event_entities": [], "related_event_cluster": None},
        "question_tree": [{"question_id": "Q", "kind": "FUNCTION"}],
        "branches": [{"branch_id": "B", "question_ids": ["Q"], "status": "PLANNED"}], "executor_state": {},
    }


def test_accountability_routes_diversify_across_relevant_families():
    routes = [
        {"route_id": "news", "url": "https://maroc.ma/en/news", "origin": "maroc.ma", "route_type": "NEWS_LISTING", "source_family": "OFFICIAL_GOVERNMENT", "semantic_capabilities": ["ACCOUNTABILITY", "SERVICE"]},
        {"route_id": "audit", "url": "https://audit.example/reports", "origin": "audit.example", "route_type": "AUDIT_PUBLICATIONS", "source_family": "JUDICIAL_PROSECUTORIAL", "semantic_capabilities": ["ACCOUNTABILITY"]},
        {"route_id": "parliament", "url": "https://parliament.example/", "origin": "parliament.example", "route_type": "OTHER_PUBLIC_INDEX", "source_family": "PARLIAMENTARY", "semantic_capabilities": ["ACCOUNTABILITY"]},
        {"route_id": "independent", "url": "https://news.example/", "origin": "news.example", "route_type": "NEWS_LISTING", "source_family": "INDEPENDENT_MEDIA", "semantic_capabilities": ["ACCOUNTABILITY"]},
    ]
    strategies = _breadth_event_queries({}, _need("ACCOUNTABILITY", routes), month="2026-09", primary_language="en", alternate_language="fr", route=None)
    assert [item["source_route"]["route_id"] for item in strategies] == ["audit", "parliament", "independent", "news"]
    assert len({item["source_family"] for item in strategies}) == 4


def test_service_routes_do_not_use_statistics_without_a_matching_subject():
    routes = [
        {"route_id": "news", "url": "https://maroc.ma/en/news", "origin": "maroc.ma", "route_type": "NEWS_LISTING", "source_family": "OFFICIAL_GOVERNMENT", "semantic_capabilities": ["SERVICE"]},
        {"route_id": "hcp", "url": "https://hcp.example/data", "origin": "hcp.example", "route_type": "PUBLICATIONS", "source_family": "PUBLIC_STATISTICS", "semantic_capabilities": ["SERVICE"]},
        {"route_id": "bam", "url": "https://bam.example/notices", "origin": "bam.example", "route_type": "PRESS_RELEASES", "source_family": "PUBLIC_FINANCE", "semantic_capabilities": ["SERVICE"]},
    ]
    strategies = _breadth_event_queries({}, _need("SERVICE", routes), month="2026-09", primary_language="en", alternate_language="fr", route=None)
    assert strategies[0]["source_route"]["route_id"] == "news"
    assert all((item.get("source_route") or {}).get("route_id") not in {"hcp", "bam"} for item in strategies)


def test_action_persists_need_family_routing_telemetry():
    routes = [{"route_id": "audit", "url": "https://audit.example/reports", "origin": "audit.example", "route_type": "AUDIT_PUBLICATIONS", "source_family": "JUDICIAL_PROSECUTORIAL", "semantic_capabilities": ["ACCOUNTABILITY"]}]
    need = _need("ACCOUNTABILITY", routes)
    need["candidate_source_families"] = ["JUDICIAL_PROSECUTORIAL"]
    strategy = _breadth_event_queries({}, need, month="2026-09", primary_language="en", alternate_language="fr", route=None)[0]
    action = create_research_action(_job(), _job()["branches"][0], recovery_need=need, query_strategy=strategy)
    assert action["candidate_source_families"] == ["JUDICIAL_PROSECUTORIAL"]
    assert action["selected_source_family"] == "JUDICIAL_PROSECUTORIAL"
    assert action["selection_reason"] == "NEED_SOURCE_FAMILY_POLICY"
    assert action["expected_information_gain"] == "EXACT_AUTHORITY_ROUTE"


def test_legacy_routes_without_family_keep_compatibility():
    routes = [{"route_id": "portal", "url": "https://maroc.ma/en/news", "origin": "maroc.ma", "route_type": "NEWS_LISTING", "semantic_capabilities": ["SERVICE"]}]
    strategies = _breadth_event_queries({}, _need("SERVICE", routes), month="2026-09", primary_language="en", alternate_language="fr", route=None)
    assert strategies[0]["source_route"]["route_id"] == "portal"


def test_scheduler_reserves_second_semantic_family_branch_within_existing_cap():
    job = _job()
    need = _need("SERVICE", [{"route_id": "news", "url": "https://maroc.ma/en/news", "origin": "maroc.ma", "route_type": "NEWS_LISTING", "source_family": "OFFICIAL_GOVERNMENT", "semantic_capabilities": ["SERVICE"]}, {"route_id": "stats", "url": "https://hcp.example/data", "origin": "hcp.example", "route_type": "PUBLICATIONS", "source_family": "PUBLIC_STATISTICS", "semantic_capabilities": ["SERVICE"]}])
    need.update({"attempt_count": 0, "max_attempts": 1})
    job["recovery_needs"] = [need]
    actions = schedule_research_actions([job], {"executor": {"action_timeout_seconds": 15, "maximum_actions_per_round": 8, "lead_followup_limits": {"STANDARD": {"total": 4}}, "budget_action_limits": {"STANDARD": {"search_actions": 4, "fetches": 4}}}})["actions"]
    semantic = [a for a in actions if a.get("recovery_need_id") == need["need_id"]]
    assert {a.get("strategy_index") for a in semantic} >= {0, 1}
