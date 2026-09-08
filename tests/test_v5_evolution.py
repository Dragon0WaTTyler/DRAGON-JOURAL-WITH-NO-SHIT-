import json
from pathlib import Path

from dragon.evolution import DIMENSIONS, build_evolution_report, compare_candidate, record_feedback


def _inputs() -> dict:
    return {
        "articles": [{"body": ["كلمة عربية " * 400]}],
        "source_intelligence": {
            "source_records": [{
                "primary_evidence": True, "wire_origin": None, "duplicate_group_ids": []
            }],
            "event_clusters": [{"independent_origin_count": 2}],
        },
        "claim_graph": {"claims": [{"assessment": "SUPPORTED"}]},
        "science_report": {"passports": [{"full_text_status": "FULL_TEXT_VERIFIED"}]},
        "layout_plan": {"pages": [{"page_role": role} for role in ("LEAD", "SCIENCE", "DATA", "ANALYSIS")]},
        "pdf_report": {"status": "PASS", "issues": [], "pages": 5},
        "epub_report": {"status": "PASS"},
    }


def test_daily_evolution_is_thresholded_and_never_self_mutates(tmp_path: Path) -> None:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "evolution.yaml").write_text(
        "evaluation_interval_complete_editions: 2\nresource_versions: {source_policy: v1}\n",
        encoding="utf-8",
    )
    first = build_evolution_report(tmp_path, "2099-01-01", "production", **_inputs())
    assert first["status"] == "NOT_DUE"
    assert first["metrics"]["citation_support_rate"] == 1.0
    assert first["metrics"]["science_fulltext_rate"] == 1.0
    edition = tmp_path / "editions" / "2099" / "01" / "2099-01-01"
    edition.mkdir(parents=True)
    (edition / "final-qa.json").write_text(
        json.dumps({"status": "PASS", "mode": "production"}), encoding="utf-8"
    )
    second = build_evolution_report(tmp_path, "2099-01-02", "production", **_inputs())
    assert second["status"] == "PASS"
    assert second["evaluation_due"] is True
    assert second["control_plane"]["automatic_production_mutation"] is False
    assert second["control_plane"]["separate_schedule"] is False


def test_candidate_requires_improvement_without_any_dimension_regression() -> None:
    baseline = {name: 0.8 for name in DIMENSIONS}
    better = {name: 0.9 for name in DIMENSIONS}
    accepted = compare_candidate("source_policy", "v1", "v2", baseline, better, "test")
    assert accepted["decision"] == "PROMOTION_ELIGIBLE"
    assert accepted["automatic_promotion"] is False
    worse = dict(better)
    worse["evidence"] = 0.7
    assert compare_candidate("source_policy", "v1", "v2", baseline, worse, "test")["decision"] == "REJECT"


def test_feedback_is_queued_without_mutating_production(tmp_path: Path) -> None:
    path = record_feedback(tmp_path, "الغلاف يتكرر.", received_at="2099-01-02T07:00:00Z")
    value = json.loads(path.read_text(encoding="utf-8"))
    assert value["status"] == "QUEUED_FOR_BENCHMARK"
    assert value["production_mutated"] is False
