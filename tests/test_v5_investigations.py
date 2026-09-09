import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from dragon.investigations import InvestigationError, update_investigation_dossiers
from dragon.state import sha256_file


ROOT = Path(__file__).resolve().parents[1]


def _article() -> dict:
    return {
        "id": "inv-1", "section_id": "investigations", "status": "ACTIVE",
        "story_key": "procurement-case", "investigation_checks": {
            "serious_accountability_claim": True,
            "counter_evidence_checked": True,
            "response_status": "SOUGHT",
            "publication_ready": True,
        },
        "investigation_data": {
            "question": "كيف نُفذ عقد الاختبار؟",
            "entities": [
                {"entity_id": "buyer", "entity_type": "PublicBody", "name": "جهة عامة", "aliases": ["الجهة"], "confidence": "HIGH", "source_ids": ["official"]},
                {"entity_id": "supplier", "entity_type": "Company", "name": "شركة اختبار", "aliases": ["الشركة"], "confidence": "HIGH", "source_ids": ["official", "news"]},
            ],
            "relationships": [
                {"from_entity_id": "buyer", "to_entity_id": "supplier", "relationship_type": "AWARDED_CONTRACT", "source_ids": ["official"], "confidence": "HIGH", "ambiguity": None},
            ],
            "contracts": [
                {"contract_id": "contract-1", "buyer_entity_id": "buyer", "supplier_entity_id": "supplier", "amount": 1200000, "currency": "MAD", "award_date": "2098-12-20", "amendments": [50000], "execution_status": "ONGOING", "source_ids": ["official"]},
            ],
            "timeline": [
                {"event_id": "award", "date": "2098-12-20", "description": "إسناد العقد", "source_ids": ["official"]},
            ],
            "archive_references": [
                {"source_id": "official", "canonical_url": "https://gov.example/doc", "retrieved_at": "2099-01-01T08:00:00+01:00", "sha256": "a" * 64, "archive_locator": "archive/official.pdf"},
            ],
            "leads": [
                {"description": "نمط يحتاج إلى مزيد من الفحص", "confidence": "LOW", "source_ids": ["news"], "not_proof_of_wrongdoing": True},
            ],
            "material_uncertainties": [],
        },
    }


def _graph() -> dict:
    return {"claims": [{
        "claim_id": "CLM-1", "article_id": "inv-1", "text": "ادعاء موثق",
        "classification": "FACT", "assessment": "SUPPORTED", "disputed": False,
        "evidence": [
            {"source_id": "official", "source_type": "official", "supports": True, "url": "https://gov.example/doc", "alignment": "SUPPORTED", "independent_origin_group": "DOMAIN:gov.example"},
            {"source_id": "news", "source_type": "independent", "supports": True, "url": "https://news.example/report", "alignment": "SUPPORTED", "independent_origin_group": "DOMAIN:news.example"},
        ],
    }]}


def test_investigation_dossier_survives_days_and_is_idempotent(tmp_path) -> None:
    first, paths = update_investigation_dossiers(
        tmp_path, "2099-01-01", [_article()], _graph(), {"source_records": []}
    )
    assert first["status"] == "PASS"
    assert len(paths) == 8
    second, second_paths = update_investigation_dossiers(
        tmp_path, "2099-01-02", [_article()], _graph(), {"source_records": []}
    )
    assert second["status"] == "PASS" and second_paths == paths
    dossier = json.loads(paths[0].read_text(encoding="utf-8"))
    schema = json.loads((ROOT / "config" / "investigation-schema.json").read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(dossier)
    assert dossier["dates_observed"] == ["2099-01-01", "2099-01-02"]
    assert len(dossier["claims"]) == 1
    assert len(dossier["evidence_index"]) == 2
    assert dossier["entities"][1]["aliases"] == ["الشركة"]
    assert dossier["contracts"][0]["amount"] == 1200000
    assert dossier["relationships"][0]["source_ids"] == ["official"]
    assert dossier["archive_references"][0]["sha256"] == "a" * 64
    assert set(dossier["modular_artifacts"]) == {
        "entities.json", "timeline.json", "claims.json", "evidence-index.json",
        "contradictions.json", "unanswered-questions.json", "publication-state.json",
    }
    assert all(
        dossier["modular_artifacts"][path.name] == sha256_file(path)
        for path in paths[1:]
    )
    assert (paths[0].parent / "evidence").is_dir()
    assert (paths[0].parent / "archive").is_dir()
    assert dossier["publication_state"]["publication_ready"] is True


def test_investigation_readiness_refuses_unsupported_accusation(tmp_path) -> None:
    graph = _graph()
    graph["claims"][0]["assessment"] = "PARTIALLY_SUPPORTED"
    report, _ = update_investigation_dossiers(
        tmp_path, "2099-01-01", [_article()], graph, {"source_records": []}
    )
    assert report["status"] == "FAIL"
    assert report["not_ready_article_ids"] == ["inv-1"]


def test_corrupt_existing_dossier_is_never_overwritten(tmp_path) -> None:
    _, paths = update_investigation_dossiers(
        tmp_path, "2099-01-01", [_article()], _graph(), {"source_records": []}
    )
    paths[0].write_text("not-json", encoding="utf-8")
    with pytest.raises(InvestigationError):
        update_investigation_dossiers(
            tmp_path, "2099-01-02", [_article()], _graph(), {"source_records": []}
        )
    assert paths[0].read_text(encoding="utf-8") == "not-json"


def test_timeline_updates_and_material_uncertainty_blocks_publication(tmp_path) -> None:
    article = _article()
    update_investigation_dossiers(
        tmp_path, "2099-01-01", [article], _graph(), {"source_records": []}
    )
    article["investigation_data"]["timeline"].append({
        "event_id": "amendment", "date": "2099-01-02",
        "description": "تعديل قيمة العقد", "source_ids": ["official"],
    })
    article["investigation_data"]["material_uncertainties"] = [
        "لا تزال وثيقة التنفيذ النهائية غير متاحة"
    ]
    report, paths = update_investigation_dossiers(
        tmp_path, "2099-01-02", [article], _graph(), {"source_records": []}
    )
    assert report["status"] == "FAIL"
    dossier = json.loads(paths[0].read_text(encoding="utf-8"))
    assert [item["event_id"] for item in dossier["timeline"]] == ["amendment", "award"]
    assert dossier["publication_state"]["evidence_quality"] == "HIGH"
    assert dossier["publication_state"]["material_uncertainties"]
