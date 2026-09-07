from dragon.report import evaluate_deadlines


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
