from dragon.investigation_scope import evaluate_super_investigation_scope


def test_morocco_and_meknes_leads_are_super_investigation_eligible() -> None:
    assert evaluate_super_investigation_scope({"geography": ["Morocco"]})["status"] == "ELIGIBLE"
    result = evaluate_super_investigation_scope({"geography": ["Meknes"]})
    assert result["status"] == "ELIGIBLE"
    assert result["scope_rule"] == "MOROCCO + MEKNES ONLY"


def test_unrelated_foreign_investigation_is_normal_deep_research_only() -> None:
    result = evaluate_super_investigation_scope({"geography": ["France"], "entities": [{"name": "Municipality", "geography": "France"}]})
    assert result["status"] == "NOT_ELIGIBLE"
    assert result["mode"] == "NORMAL_DEEP_RESEARCH"


def test_foreign_entity_directly_tied_to_morocco_is_supporting_scope_eligible() -> None:
    result = evaluate_super_investigation_scope({
        "geography": ["Spain"],
        "entities": [{"name": "Contractor", "geography": "Spain"}],
        "scope_connections": [{
            "entity": "Contractor", "connected_scope": "Morocco public project",
            "relationship": "contractor", "direct_evidence_source_ids": ["tender-1"],
        }],
    })
    assert result["status"] == "ELIGIBLE"
    assert result["foreign_entities"][0]["name"] == "Contractor"
    assert "NO_EVIDENCE_OF_MISCONDUCT" in result["allowed_conclusions"]


def test_unlinked_foreign_entity_is_rejected_even_inside_morocco_case() -> None:
    result = evaluate_super_investigation_scope({
        "geography": ["Morocco"],
        "entities": [{"name": "Unrelated actor", "geography": "United States"}],
    })
    assert result["status"] == "NOT_ELIGIBLE"
    assert result["foreign_entities"] == []
    assert result["excluded_foreign_entities"][0]["name"] == "Unrelated actor"
