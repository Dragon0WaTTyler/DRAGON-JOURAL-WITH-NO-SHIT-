from dragon.science import science_integrity_report, validate_science_report


def _article(text: str = "توضح الدراسة حدود النتائج") -> dict:
    return {
        "id": "science-1", "section_id": "science", "status": "ACTIVE",
        "headline": text, "body": [text], "source_ids": ["paper"],
        "claims": [{"claim_type": "study", "source_ids": ["paper"]}],
    }


def _source(**updates) -> dict:
    value = {
        "source_id": "paper", "doi": "10.1234/test", "publication_status": "peer_reviewed",
        "full_text_status": "FULL_TEXT_VERIFIED", "methods_read": True,
        "limitations_read": True,
        "science_metadata": {
            "paper_id": "paper-1", "title": "Study", "authors": ["Researcher"],
            "journal": "Journal", "version_type": "VERSION_OF_RECORD",
            "sample": "adult participants", "sample_size": 120, "design": "cohort",
            "effect_result": "association", "statistics": "95% CI",
            "corrections_retractions": [], "conflicting_study_source_ids": [],
            "locators": ["p. 4, table 2"], "confidence": "MEDIUM",
            "doi_verified": True, "metadata_matches": True,
            "claim_alignment": "ALIGNED", "correlation_only": False,
        },
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
    source["science_metadata"]["version_type"] = "PREPRINT"
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


def test_science_passport_preserves_material_identity_and_locators() -> None:
    passport = science_integrity_report([_article()], {"source_records": [_source()]})["passports"][0]
    assert passport["paper_id"] == "paper-1"
    assert passport["sample_size"] == 120
    assert passport["design"] == "cohort"
    assert passport["locators"] == ["p. 4, table 2"]
    assert passport["metadata_verified"] is True
    assert passport["claim_alignment"] == "ALIGNED"


def test_science_gate_rejects_wrong_doi_metadata_mismatch_and_claim_misalignment() -> None:
    source = _source(doi="wrong-doi")
    source["science_metadata"].update({
        "doi_verified": False, "metadata_matches": False, "claim_alignment": "MISALIGNED",
    })
    report = science_integrity_report([_article()], {"source_records": [source]})
    assert report["status"] == "FAIL"
    assert any("SCIENCE_DOI_UNVERIFIED" in issue for issue in report["issues"])
    assert any("SCIENCE_METADATA_MISMATCH" in issue for issue in report["issues"])
    assert any("SCIENCE_CLAIM_MISALIGNED" in issue for issue in report["issues"])


def test_science_gate_labels_small_correlational_and_conflicting_evidence() -> None:
    source = _source()
    source["science_metadata"].update({
        "sample_size": 12,
        "correlation_only": True,
        "conflicting_study_source_ids": ["paper-2"],
    })
    overstated = _article("تقول الدراسة إن العامل يسبب النتيجة")
    failed = science_integrity_report([overstated], {"source_records": [source]})
    assert any("SMALL_SAMPLE_CAUTION_MISSING" in issue for issue in failed["issues"])
    assert any("CORRELATION_CAUSATION_OVERSTATEMENT" in issue for issue in failed["issues"])
    assert any("SCIENCE_LIMITATIONS_OMITTED" in issue for issue in failed["issues"])
    assert any("CONFLICTING_STUDIES_OMITTED" in issue for issue in failed["issues"])

    cautious = _article(
        "تصف الدراسة ارتباطا في عينة صغيرة وتوضح أن ذلك لا يثبت السببية، مع حدود المنهج وتعارض دراسات متضاربة"
    )
    assert science_integrity_report([cautious], {"source_records": [source]})["status"] == "PASS"


def test_science_gate_surfaces_version_partial_alignment_and_retraction_state() -> None:
    source = _source(publication_status="preprint")
    source["science_metadata"].update({
        "version_type": "VERSION_OF_RECORD",
        "claim_alignment": "PARTIAL",
        "corrections_retractions": ["Retraction notice"],
    })
    failed = science_integrity_report(
        [_article("مسودة بحث ما قبل التحكيم تشرح حدود النتائج")],
        {"source_records": [source]},
    )
    assert any("SCIENCE_VERSION_STATUS_MISMATCH" in issue for issue in failed["issues"])
    assert any("SCIENCE_PARTIAL_ALIGNMENT_UNDISCLOSED" in issue for issue in failed["issues"])
    assert any("CORRECTION_RETRACTION_OMITTED" in issue for issue in failed["issues"])


def test_science_report_validator_rejects_tampered_passport_schema() -> None:
    report = science_integrity_report([_article()], {"source_records": [_source()]})
    del report["passports"][0]["locators"]
    assert validate_science_report(report, [_article()]) == ["SCIENCE_PASSPORT_SCHEMA_INVALID"]
