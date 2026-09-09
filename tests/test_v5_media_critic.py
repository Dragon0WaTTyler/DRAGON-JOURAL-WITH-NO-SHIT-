from dragon.media_critic import build_media_critic, validate_media_critic


def test_media_critic_reports_wire_dependence_without_motive_inference() -> None:
    articles = [{
        "id": "a1", "section_id": "world", "status": "ACTIVE",
        "headline": "تقرير يثبت نتيجة بسبب القرار", "body": ["نص تحليلي"],
        "source_ids": ["s1", "s2"],
    }]
    planning = {"plans": [{
        "section_id": "world", "event_id": "EVT-1",
        "known_facts": ["واقعة مشتركة"], "reported_claims": ["ادعاء منسوب"],
        "disputed_points": ["نقطة خلاف"], "unknowns": ["فاعل غير معروف"],
        "questions": ["ما الدليل الأولي؟"],
    }]}
    intelligence = {
        "source_records": [
            {"source_id": "s1", "publisher": "A", "authority_level": "SECONDARY", "primary_evidence": False, "independent_origin_group": "WIRE:REUTERS", "wire_origin": "REUTERS", "published_at": "2099-01-01", "claims_supported": ["واقعة مشتركة", "تفصيل أول"]},
            {"source_id": "s2", "publisher": "B", "authority_level": "SECONDARY", "primary_evidence": False, "independent_origin_group": "WIRE:REUTERS", "wire_origin": "REUTERS", "published_at": "2099-01-02", "claims_supported": ["واقعة مشتركة", "تفصيل ثان"]},
        ],
        "event_clusters": [{
            "event_id": "EVT-1", "candidate_keys": ["world:c1"],
            "independent_origin_count": 1, "wire_origins": ["REUTERS"],
        }],
    }
    report = build_media_critic(articles, planning, intelligence)
    assert validate_media_critic(report, articles) == []
    item = report["articles"][0]
    assert "WIRE_DEPENDENCE_PRESENT" in item["observations"]
    assert "INDEPENDENT_ORIGIN_COUNT_BELOW_TWO" in item["observations"]
    assert "CAUSAL_LANGUAGE_PRESENT" in item["observations"]
    assert item["inferences"] == ["WIRE_DEPENDENCE_LIMITS_APPARENT_SOURCE_DIVERSITY"]
    assert item["motive_claims"] == []
    assert item["shared_factual_claims"][0]["source_ids"] == ["s1", "s2"]
    assert len(item["source_specific_claims"]) == 2
    assert item["explicitly_unresolved_context"] == ["فاعل غير معروف"]
    assert item["analysis_layers"]["EDITORIAL_INFERENCE"] == item["inferences"]


def test_media_critic_preserves_independent_reporting_without_inventing_omissions() -> None:
    articles = [{
        "id": "a1", "section_id": "front", "status": "ACTIVE",
        "headline": "عنوان محايد", "body": ["متن موثق"], "source_ids": ["official", "independent"],
    }]
    planning = {"plans": [{
        "section_id": "front", "event_id": "EVT-2", "known_facts": [],
        "reported_claims": [], "disputed_points": [], "unknowns": [], "questions": [],
    }]}
    intelligence = {
        "source_records": [
            {"source_id": "official", "publisher": "Official", "authority_level": "PRIMARY", "primary_evidence": True, "independent_origin_group": "DOMAIN:official", "wire_origin": None, "published_at": "2099-01-01", "claims_supported": ["قرار منشور"]},
            {"source_id": "independent", "publisher": "News", "authority_level": "SECONDARY", "primary_evidence": False, "independent_origin_group": "DOMAIN:news", "wire_origin": None, "published_at": "2099-01-02", "claims_supported": ["تحقق مستقل"]},
        ],
        "event_clusters": [{
            "event_id": "EVT-2", "candidate_keys": ["front:c1"],
            "independent_origin_count": 2, "wire_origins": [],
        }],
    }
    item = build_media_critic(articles, planning, intelligence)["articles"][0]
    assert item["inferences"] == []
    assert item["missing_actors"] == {"status": "NOT_INFERRED", "actors": []}
    assert item["primary_evidence_source_ids"] == ["official"]
