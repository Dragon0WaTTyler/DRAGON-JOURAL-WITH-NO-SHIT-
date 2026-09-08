from dragon.media_critic import build_media_critic, validate_media_critic


def test_media_critic_reports_wire_dependence_without_motive_inference() -> None:
    articles = [{
        "id": "a1", "section_id": "world", "status": "ACTIVE",
        "headline": "تقرير يثبت نتيجة بسبب القرار", "body": ["نص تحليلي"],
        "source_ids": ["s1", "s2"],
    }]
    planning = {"plans": [{"section_id": "world", "event_id": "EVT-1"}]}
    intelligence = {
        "source_records": [
            {"source_id": "s1", "publisher": "A"},
            {"source_id": "s2", "publisher": "B"},
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
    assert item["inferences"] == item["motive_claims"] == []
