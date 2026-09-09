from dragon.editorial import adversarial_review, chief_editor_report, factcheck_report


def article(identifier: str, story_key: str, *, value: str = "1") -> dict:
    return {
        "id": identifier,
        "section_id": "front",
        "status": "ACTIVE",
        "story_key": story_key,
        "headline": f"عنوان {identifier}",
        "body": ["نص عربي موثق " * 100],
        "source_ids": ["primary", "independent"],
        "claims": [
            {
                "text": "قيمة موثقة",
                "claim_type": "number",
                "classification": "FACT",
                "material": True,
                "fact_key": "shared-number",
                "value": value,
                "source_ids": ["primary", "independent"],
            }
        ],
    }


def test_chief_editor_ranks_and_rejects_duplicate_or_contradictory_stories() -> None:
    first = article("a1", "same", value="1")
    second = article("a2", "same", value="2")
    report = chief_editor_report([first, second])
    assert report["status"] == "FAIL"
    assert "DUPLICATE_STORY_KEY:same" in report["issues"]
    assert "EDITORIAL_CONTRADICTION:shared-number" in report["issues"]
    assert report["front_page_article_ids"]


def test_factcheck_requires_primary_and_independent_support_for_material_fact() -> None:
    value = article("a1", "story")
    sources = [
        {"id": "primary", "source_type": "primary"},
        {"id": "independent", "source_type": "independent"},
    ]
    assert factcheck_report([value], sources, synthetic=False)["status"] == "PASS"
    value["claims"][0]["source_ids"] = ["primary"]
    failed = factcheck_report([value], sources, synthetic=False)
    assert failed["status"] == "FAIL"
    assert failed["articles"][0]["outcome"] == "NEEDS_VERIFICATION"


def test_adversarial_review_is_independent_and_blocks_weak_material_claim() -> None:
    value = article("a1", "story")
    value["editorial_elements"] = {"uncertainty": "تبقى حدود معلومة"}
    graph = {
        "claims": [{
            "claim_id": "CLM-1", "article_id": "a1", "assessment": "PARTIALLY_SUPPORTED",
            "material": True,
        }]
    }
    plan = {"plans": [{
        "section_id": "front",
        "perspectives": ["أ", "ب", "ج"],
        "questions": ["ما أقوى تفسير بديل؟"],
    }]}
    report = adversarial_review([value], graph, plan)
    assert report["status"] == "FAIL"
    assert report["articles"][0]["outcome"] == "FIX"


def test_adversarial_review_passes_supported_claim_with_challenge_context() -> None:
    value = article("a1", "story")
    value["editorial_elements"] = {"uncertainty": "تبقى حدود معلومة"}
    graph = {"claims": [{
        "claim_id": "CLM-1", "article_id": "a1", "assessment": "SUPPORTED", "material": True,
    }]}
    plan = {"plans": [{
        "section_id": "front", "perspectives": ["أ", "ب", "ج"],
        "questions": ["ما أقوى تفسير بديل؟"],
    }]}
    assert adversarial_review([value], graph, plan)["status"] == "PASS"


def test_adversarial_review_does_not_count_one_wire_origin_as_independent() -> None:
    value = article("a1", "story")
    value["editorial_elements"] = {"uncertainty": "تبقى حدود معلومة"}
    graph = {"claims": [{
        "claim_id": "CLM-1", "article_id": "a1", "assessment": "SUPPORTED",
        "material": True, "independent_evidence_unavailable_reason": None,
    }]}
    plan = {"plans": [{
        "section_id": "front", "perspectives": ["أ", "ب", "ج"],
        "questions": ["ما أقوى تفسير بديل؟"],
    }]}
    media = {"articles": [{"article_id": "a1", "independent_origin_count": 1}]}
    report = adversarial_review([value], graph, plan, media)
    assert report["status"] == "FAIL"
    assert "WIRE_ORIGIN_INDEPENDENCE_INSUFFICIENT" in report["articles"][0]["issues"]


def test_adversarial_review_rejects_contradicted_framing_explicitly() -> None:
    value = article("a1", "story")
    value["editorial_elements"] = {"uncertainty": "تبقى حدود معلومة"}
    graph = {"claims": [{
        "claim_id": "CLM-1", "article_id": "a1", "assessment": "CONTRADICTED",
        "material": True,
    }]}
    plan = {"plans": [{
        "section_id": "front", "perspectives": ["أ", "ب", "ج"],
        "questions": ["ما أقوى تفسير بديل؟"],
        "critical_thinking_checks": {"unsupported_premise": "PLANNED"},
    }]}
    result = adversarial_review([value], graph, plan)["articles"][0]
    assert result["outcome"] == "HOLD"
    assert result["framing_decision"] == "REJECT_THE_FRAMING"
