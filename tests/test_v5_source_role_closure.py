from dragon.deep_research_executor import build_event_bundles


def _action(target="ACCOUNTABILITY"):
    return {
        "action_id": "A1", "recovery_need_id": "BREADTH:accountability_and_service:1",
        "recovery_mode": "DISCOVER_NEW_EVENT_FOR_SEMANTIC_NEED",
        "target_editorial_function": target, "desk": "investigations" if target == "ACCOUNTABILITY" else "service",
        "event_acquisition_plan": {"target_editorial_function": target},
        "event_context": {"research_date": "2026-09-13", "topic_terms": [target]},
    }


def test_direct_support_republication_survives_as_observation_without_primary():
    action = _action()
    observation = {
        "observation_id": "OBS-1", "source_id": "SRC-1", "origin": "maroc.ma",
        "source_class": "unknown", "verification_status": "EXTRACTED_NOT_VERIFIED",
        "event_skeleton": {
            "state": "CONCRETE_EVENT", "event_fingerprint": "EVENT-1", "title": "Monitoring directive",
            "actor": "Public Prosecution", "action": "orders monitoring", "object": "election complaints",
            "published_at": "2026-09-01", "geography": ["Morocco"],
            "lead_paragraphs": "Public Prosecution orders monitoring of election complaints.",
            "temporal_relevance": {"active_on_edition_date": True},
        },
        "support_observation": {
            "state": "OBSERVATION_CREATED",
            "claim_support": {"support_type": "DIRECT_SUPPORT", "locator": {"paragraph": 1}},
            "role": "REPUBLICATION", "primary_requirement_satisfied": False,
            "requirement_state": "NOT_MET", "observation_id": "OBS-1",
        },
        "provenance": {"action_id": "A1", "originating_recovery_need_id": "BREADTH:accountability_and_service:1", "recovery_mode": "DISCOVER_NEW_EVENT_FOR_SEMANTIC_NEED"},
        "provenance_edges": [
            {"type": "PUBLISHED_BY", "from": "artifact", "to": "Maroc.ma"},
            {"type": "CONTENT_ORIGINATED_BY", "from": "artifact", "to": "MAP"},
            {"type": "DOCUMENT_ISSUED_BY", "from": "artifact", "to": "Public Prosecution"},
        ],
        "publisher_profile": {"canonical_domain": "maroc.ma"},
        "article_metadata": {"publisher": {"name": "Maroc.ma"}},
        "evidence_relation": "SUPPORTS", "directness": "DIRECT_STATEMENT",
    }
    bundles, _ = build_event_bundles([observation], [], [], [action])
    assert bundles[0]["observations"] == ["OBS-1"]
    assert bundles[0]["support_observations"][0]["role"] == "REPUBLICATION"
    assert bundles[0]["support_observations"][0]["primary_requirement_satisfied"] is False
    assert bundles[0]["state"] in {"EVENT_LEAD_DISCOVERY_ONLY", "EVENT_EVIDENCE_BLOCKED", "EVENT_EVIDENCE_PARTIAL"}
    assert bundles[0]["candidate_discovery"] is None


def test_support_observation_does_not_turn_a_bundle_into_closure():
    action = _action("SERVICE")
    observation = {
        "observation_id": "OBS-2", "source_id": "SRC-2", "origin": "portal.gov.ma",
        "source_class": "unknown", "verification_status": "EXTRACTED_NOT_VERIFIED",
        "event_skeleton": {
            "state": "CONCRETE_EVENT", "event_fingerprint": "EVENT-2", "title": "Registration deadline",
            "actor": "Public Agency", "action": "opens registration", "object": "applications",
            "published_at": "2026-09-01", "geography": ["Morocco"],
            "lead_paragraphs": "Public Agency opens registration applications until 2026-09-22.",
            "temporal_relevance": {"active_on_edition_date": True},
        },
        "support_observation": {"state": "OBSERVATION_CREATED", "claim_support": {"support_type": "DIRECT_SUPPORT", "locator": {"paragraph": 1}}, "role": "SECONDARY", "primary_requirement_satisfied": False, "requirement_state": "NOT_MET", "observation_id": "OBS-2"},
        "provenance": {"action_id": "A1", "originating_recovery_need_id": "BREADTH:accountability_and_service:1", "recovery_mode": "DISCOVER_NEW_EVENT_FOR_SEMANTIC_NEED"},
        "publisher_profile": {"canonical_domain": "portal.gov.ma"},
        "article_metadata": {"publisher": {"name": "Portal"}},
    }
    bundles, discoveries = build_event_bundles([observation], [], [], [action])
    assert bundles[0]["support_observations"]
    assert bundles[0]["candidate_discovery"] is None
    assert discoveries == []
