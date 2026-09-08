import json
from pathlib import Path

from dragon.report import collect_operational_metrics, evaluate_deadlines


def state(publication_end: str, delivery_end: str | None, delivery: str) -> dict:
    return {
        "date": "2099-01-02",
        "publication_status": "COMPLETE",
        "delivery_status": delivery,
        "stages": {
            "final_qa": {"ended_at": publication_end},
            "whatsapp_delivery": {"ended_at": delivery_end},
        },
    }


def test_deadline_evidence_separates_publication_and_optional_delivery() -> None:
    value = evaluate_deadlines(
        state("2099-01-02T10:29:00+00:00", None, "DEGRADED"),
        "Africa/Casablanca",
        "10:30",
    )
    assert value["publication_deadline_status"] == "ON_TIME"
    assert value["delivery_deadline_status"] == "NOT_COMPLETED"
    assert value["target_deadline"] == "2099-01-02T10:30:00+00:00"


def test_late_completed_delivery_is_reported_truthfully() -> None:
    value = evaluate_deadlines(
        state(
            "2099-01-02T10:15:00+00:00",
            "2099-01-02T10:31:00+00:00",
            "COMPLETE",
        ),
        "Africa/Casablanca",
        "10:30",
    )
    assert value["publication_deadline_status"] == "ON_TIME"
    assert value["delivery_deadline_status"] == "LATE"


def test_operational_metrics_collect_evidence_counts_and_format_gates(tmp_path: Path) -> None:
    run = tmp_path / "daily-runs" / "2099-01-02"
    edition = tmp_path / "editions" / "2099" / "01" / "2099-01-02"
    for path, value in {
        run / "source-intelligence" / "report.json": {
            "summary": {"source_count": 2, "event_count": 1},
            "source_records": [{"publisher": "A"}, {"publisher": "B"}],
            "event_clusters": [{"independent_origin_groups": ["A", "B"]}],
        },
        run / "evidence" / "claim-graph.json": {
            "claims": [{"assessment": "SUPPORTED"}, {"assessment": "UNAVAILABLE"}]
        },
        run / "qa" / "arabic-language.json": {"status": "PASS"},
        run / "qa" / "pdf.json": {"status": "PASS"},
        run / "qa" / "pdf-visual.json": {"status": "PASS"},
        run / "qa" / "epub.json": {"status": "PASS"},
        run / "qa" / "epubcheck.json": {"status": "PASS"},
        edition / "cover-brief.json": {"mode": "SYMBOLIC_EDITORIAL", "accepted": True},
        edition / "layout-plan.json": {"status": "PASS"},
    }.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")
    metrics = collect_operational_metrics(tmp_path, run, {"date": "2099-01-02"})
    assert metrics["source_count"] == 2
    assert metrics["publisher_count"] == 2
    assert metrics["independent_origin_count"] == 2
    assert metrics["claim_count"] == 2
    assert metrics["unsupported_claim_count"] == 1
    assert metrics["epubcheck"] == "PASS"
