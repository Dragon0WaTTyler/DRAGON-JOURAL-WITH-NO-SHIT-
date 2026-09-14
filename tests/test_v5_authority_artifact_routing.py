from dragon.authority_routing import (
    artifact_family_for_route,
    authority_artifact_preferences,
    authority_capability_from_text,
    authority_route_metadata,
)
from dragon.deep_research_executor import _breadth_event_queries, create_research_action


def test_prosecution_claim_targets_public_prosecution_artifacts():
    assert authority_capability_from_text("Presidency of the Public Prosecution") == "PUBLIC_PROSECUTION"
    branches = authority_artifact_preferences("ACCOUNTABILITY", actor="Public Prosecution")
    assert branches[0] == {"authority_capability": "PUBLIC_PROSECUTION", "artifact_families": ["CIRCULAR", "DIRECTIVE", "COMMUNIQUE"]}


def test_audit_route_is_audit_not_prosecution():
    route = {"source_family": "JUDICIAL_PROSECUTORIAL", "authority_type": "AUDIT_INSTITUTION", "route_type": "AUDIT_PUBLICATIONS", "source_id": "cour-des-comptes"}
    metadata = authority_route_metadata(route, "ACCOUNTABILITY", actor="Cour des comptes")
    assert metadata["authority_capability"] == "AUDIT_INSTITUTION"
    assert metadata["artifact_family"] == "AUDIT_REPORT"
    assert authority_route_metadata({**route, "authority_type": "PUBLIC_PROSECUTION"}, "ACCOUNTABILITY")["artifact_family"] == "AUDIT_REPORT"


def test_hcp_and_bam_have_narrow_artifact_targets():
    assert authority_route_metadata({"source_family": "PUBLIC_STATISTICS", "authority_type": "STATISTICS_AUTHORITY", "route_type": "PUBLICATIONS", "source_id": "hcp"}, "SERVICE")["artifact_family"] == "STATISTICAL_RELEASE"
    assert artifact_family_for_route({"authority_type": "CENTRAL_BANK", "route_type": "OTHER_PUBLIC_INDEX"}, "ACCOUNTABILITY") == "DECISION"


def test_explicit_prosecution_actor_rejects_unrelated_audit_route():
    routes = [{"route_id": "audit", "url": "https://audit.example/reports", "origin": "audit.example", "route_type": "AUDIT_PUBLICATIONS", "source_family": "JUDICIAL_PROSECUTORIAL", "authority_type": "AUDIT_INSTITUTION", "semantic_capabilities": ["ACCOUNTABILITY"]}]
    need = {"need_id": "BREADTH:accountability_and_service:1", "kind": "NEED_ACCOUNTABILITY_AND_SERVICE", "target_editorial_function": "ACCOUNTABILITY", "query_context": {"research_date": "2026-09-14", "entities": ["Public Prosecution"]}, "search_constraints": {"configured_source_routes": routes}, "event_acquisition_plan": {"target_editorial_function": "ACCOUNTABILITY"}, "recovery_mode": "DISCOVER_NEW_EVENT_FOR_SEMANTIC_NEED"}
    strategies = _breadth_event_queries({}, need, month="2026-09", primary_language="en", alternate_language="fr", route=None)
    assert all((item.get("source_route") or {}).get("route_id") != "audit" for item in strategies)


def test_authority_and_artifact_metadata_survives_action_materialization():
    route = {"route_id": "audit", "url": "https://audit.example/reports", "origin": "audit.example", "route_type": "AUDIT_PUBLICATIONS", "source_family": "JUDICIAL_PROSECUTORIAL", "authority_type": "AUDIT_INSTITUTION", "semantic_capabilities": ["ACCOUNTABILITY"]}
    need = {"need_id": "BREADTH:accountability_and_service:1", "kind": "NEED_ACCOUNTABILITY_AND_SERVICE", "target_editorial_function": "ACCOUNTABILITY", "query_context": {"research_date": "2026-09-14"}, "search_constraints": {"configured_source_routes": [route]}, "event_acquisition_plan": {"target_editorial_function": "ACCOUNTABILITY"}, "recovery_mode": "DISCOVER_NEW_EVENT_FOR_SEMANTIC_NEED"}
    job = {"job_id": "J", "round": 0, "regime": "GENERAL_JOURNALISM", "budget_class": "STANDARD", "budget": {"max_followup_rounds": 2}, "lead": {"desk": "investigations", "topic": "audit", "event_entities": [], "related_event_cluster": None}, "question_tree": [{"question_id": "Q", "kind": "FUNCTION"}], "branches": [{"branch_id": "B", "question_ids": ["Q"]}], "executor_state": {}}
    strategy = _breadth_event_queries(job, need, month="2026-09", primary_language="en", alternate_language="fr", route=None)[0]
    action = create_research_action(job, job["branches"][0], recovery_need=need, query_strategy=strategy)
    assert action["authority_capability"] == "AUDIT_INSTITUTION"
    assert action["selected_authority_id"] == "audit"
    assert action["artifact_family"] == "AUDIT_REPORT"
