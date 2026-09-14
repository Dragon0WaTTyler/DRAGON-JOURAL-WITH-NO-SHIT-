from dragon.claim_support import normalize_claim, resolve_claim_support


def test_direct_support_returns_exact_paragraph_locator():
    result = resolve_claim_support({"text": "The Institution issued circular X on 2026-09-10."}, claim="Institution issued circular X")
    assert result["support_type"] == "DIRECT_SUPPORT"
    assert result["locator"] == {"paragraph": 1}


def test_context_only_does_not_support_unstated_issuance():
    result = resolve_claim_support({"text": "The controversy concerned a possible circular and public reaction."}, claim="Institution issued circular X")
    assert result["support_type"] == "NO_SUPPORT"
    assert result["locator"] is None


def test_negation_is_contradictory_not_direct_support():
    result = resolve_claim_support({"text": "The Institution did not issue circular X."}, claim="Institution issued circular X")
    assert result["support_type"] == "CONTRADICTS"
    assert result["locator"] == {"paragraph": 1}


def test_allegation_and_modality_are_not_direct_support():
    alleged = resolve_claim_support({"text": "Opposition alleges Institution issued circular X."}, claim="Institution issued circular X")
    assert alleged["support_type"] == "PARTIAL_SUPPORT"
    modal = resolve_claim_support({"text": "The Institution may issue circular X."}, claim="Institution issued circular X")
    assert modal["support_type"] == "AMBIGUOUS"


def test_numeric_equivalence_is_supported_but_mismatch_is_ambiguous():
    equivalent = resolve_claim_support({"text": "The report records 1,200 million dirhams in spending."}, claim="The report records 1.2 billion dirhams in spending")
    assert equivalent["support_type"] == "DIRECT_SUPPORT"
    mismatch = resolve_claim_support({"text": "The report records 1.5 billion dirhams in spending."}, claim="The report records 1.2 billion dirhams in spending")
    assert mismatch["support_type"] == "AMBIGUOUS"
    assert mismatch["reason"] == "NUMERIC_MISMATCH"


def test_date_and_tense_are_not_collapsed():
    result = resolve_claim_support({"text": "The service will open on September 20."}, claim="The service opened on September 20")
    assert result["support_type"] in {"NO_SUPPORT", "AMBIGUOUS"}
    assert result["support_type"] != "DIRECT_SUPPORT"


def test_structured_list_recovers_locator_when_body_extraction_lost_support():
    result = resolve_claim_support(
        {"text": "Summary omitted the operative row.", "structured_fields": {"rows": [{"issuer": "Institution", "action": "issued circular X"}]}},
        claim="Institution issued circular X",
    )
    assert result["support_type"] == "DIRECT_SUPPORT"
    assert result["locator"] == {"structure": "rows", "index": 1}
    assert result["passage"] == "Institution issued circular X"
    assert result["diagnosis"] == "SUPPORT_PRESENT_EXTRACTION_LOSS"


def test_attributed_portal_copy_is_partial_and_preserves_claim_components():
    result = resolve_claim_support({"text": "According to MAP, the Institution issued circular X."}, claim="Institution issued circular X")
    assert result["support_type"] == "PARTIAL_SUPPORT"
    assert normalize_claim("Institution issued circular X")["tokens"]
