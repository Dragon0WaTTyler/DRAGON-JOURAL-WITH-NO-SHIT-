from pathlib import Path

from dragon.acceptance import _consecutive, audit_cutover


def test_consecutive_trial_dates_require_an_unbroken_sequence() -> None:
    assert _consecutive(["2099-01-01", "2099-01-02", "2099-01-04"], 3) == []
    assert _consecutive(["2099-01-04", "2099-01-02", "2099-01-03"], 3) == [
        "2099-01-02",
        "2099-01-03",
        "2099-01-04",
    ]


def test_repository_cutover_audit_is_fail_closed() -> None:
    result = audit_cutover(Path(__file__).resolve().parents[1])
    assert result["status"] == "BLOCKED"
    assert result["checks"]["editorial_provider_proven"] is False
    assert result["completion_checks"]["local_scheduler_enabled"] is False
