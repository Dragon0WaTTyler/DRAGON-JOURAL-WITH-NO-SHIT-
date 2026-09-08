import json

import pytest

from dragon.investigations import InvestigationError, update_investigation_dossiers


def _article() -> dict:
    return {
        "id": "inv-1", "section_id": "investigations", "status": "ACTIVE",
        "story_key": "procurement-case", "investigation_checks": {
            "serious_accountability_claim": True,
            "counter_evidence_checked": True,
            "response_status": "SOUGHT",
            "publication_ready": True,
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
    assert len(paths) == 1
    second, second_paths = update_investigation_dossiers(
        tmp_path, "2099-01-02", [_article()], _graph(), {"source_records": []}
    )
    assert second["status"] == "PASS" and second_paths == paths
    dossier = json.loads(paths[0].read_text(encoding="utf-8"))
    assert dossier["dates_observed"] == ["2099-01-01", "2099-01-02"]
    assert len(dossier["claims"]) == 1
    assert len(dossier["evidence_index"]) == 2
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
