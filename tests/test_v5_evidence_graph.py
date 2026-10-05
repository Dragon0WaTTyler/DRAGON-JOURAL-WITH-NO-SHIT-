from dragon.evidence import build_claim_graph, validate_claim_graph


def _article(value: str = "1") -> dict:
    return {
        "id": f"a-{value}", "section_id": "front", "status": "ACTIVE",
        "claims": [{
            "text": "قيمة موثقة", "claim_type": "number", "classification": "FACT",
            "material": True, "fact_key": "amount", "value": value,
            "source_ids": ["official", "independent"],
            "independent_evidence_unavailable_reason": None,
        }],
    }


def _intelligence() -> dict:
    return {"source_records": [
        {"source_id": "official", "canonical_url": "https://gov.example/report", "source_type": "official", "independent_origin_group": "DOMAIN:gov.example", "wire_origin": None, "claims_supported": ["قيمة رسمية موثقة"]},
        {"source_id": "independent", "canonical_url": "https://news.example/story", "source_type": "independent", "independent_origin_group": "DOMAIN:news.example", "wire_origin": None, "claims_supported": ["مراجعة مستقلة للقيمة الموثقة"]},
    ]}


def test_claim_graph_maps_exact_evidence_and_confidence() -> None:
    articles = [_article()]
    value = build_claim_graph(articles, _intelligence())
    assert validate_claim_graph(value, articles) == []
    claim = value["claims"][0]
    assert claim["assessment"] == "SUPPORTED"
    assert claim["confidence"] == "HIGH"
    assert claim["independent_origins"] == 2
    assert {item["source_id"] for item in claim["evidence"]} == {"official", "independent"}


def test_claim_graph_marks_contradictions_and_missing_provenance() -> None:
    first, second = _article("1"), _article("2")
    second["claims"][0]["source_ids"] = ["missing"]
    value = build_claim_graph([first, second], _intelligence())
    assert value["summary"]["disputed_fact_keys"] == ["amount"]
    assert all(item["assessment"] == "CONTRADICTED" for item in value["claims"])
    assert any(
        evidence["alignment"] == "PROVENANCE_UNAVAILABLE"
        for evidence in value["claims"][1]["evidence"]
    )


def test_existing_citation_that_does_not_support_claim_fails_semantically() -> None:
    article = _article()
    article["claims"][0]["text"] = "ارتفعت الميزانية بنسبة كبيرة"
    value = build_claim_graph([article], _intelligence())
    claim = value["claims"][0]
    assert claim["assessment"] == "NOT_SUPPORTED"
    assert claim["independent_origins"] == 0
    assert all(not item["supports"] for item in claim["evidence"])
    assert {item["alignment"] for item in claim["evidence"]} == {
        "CITATION_DOES_NOT_SUPPORT_CLAIM"
    }
