from dragon.science import science_integrity_report, validate_science_report


def _article(text: str = "توضح الدراسة حدود النتائج") -> dict:
    return {
        "id": "science-1", "section_id": "science", "status": "ACTIVE",
        "headline": text, "body": [text], "source_ids": ["paper"],
        "claims": [{"claim_type": "study", "source_ids": ["paper"]}],
    }


def _source(**updates) -> dict:
    value = {
        "source_id": "paper", "doi": "10.1/test", "publication_status": "peer_reviewed",
        "full_text_status": "FULL_TEXT_VERIFIED", "methods_read": True,
        "limitations_read": True,
    }
    value.update(updates)
    return value


def test_science_passport_records_verified_full_text() -> None:
    report = science_integrity_report([_article()], {"source_records": [_source()]})
    assert validate_science_report(report, [_article()]) == []
    assert report["status"] == "PASS"
    assert report["passports"][0]["metadata_verified"] is True
    assert report["passports"][0]["methods_read"] is True


def test_science_gate_requires_honest_preprint_and_abstract_labels() -> None:
    source = _source(
        publication_status="preprint", full_text_status="ABSTRACT_ONLY",
        methods_read=False, limitations_read=False,
    )
    failed = science_integrity_report([_article("نتائج جديدة")], {"source_records": [source]})
    assert failed["status"] == "FAIL"
    assert any("PREPRINT_LABEL_MISSING" in issue for issue in failed["issues"])
    assert any("ABSTRACT_ONLY_LABEL_MISSING" in issue for issue in failed["issues"])
    passed = science_integrity_report(
        [_article("مسودة بحث ما قبل التحكيم مبنية على الملخص")],
        {"source_records": [source]},
    )
    assert passed["status"] == "PASS"


def test_science_gate_rejects_claimed_methods_read_without_full_text() -> None:
    source = _source(full_text_status="FULL_TEXT_UNAVAILABLE")
    report = science_integrity_report([_article()], {"source_records": [source]})
    assert any("FULL_TEXT_READING_MISREPRESENTED" in issue for issue in report["issues"])


def test_science_report_validator_rejects_missing_article() -> None:
    value = {"schema_version": 1, "status": "PASS", "passports": [], "articles": [], "issues": []}
    assert validate_science_report(value, [_article()]) == ["SCIENCE_REPORT_INVENTORY_INVALID"]
