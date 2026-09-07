from pathlib import Path

import json

from dragon.acceptance import _checkpointed_receipt, _consecutive, audit_cutover
from dragon.state import sha256_file


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


def test_external_receipt_must_match_its_complete_checkpoint(tmp_path: Path) -> None:
    receipt = tmp_path / "daily-runs" / "2099-01-02" / "archive-receipt.json"
    receipt.parent.mkdir(parents=True)
    receipt.write_text(json.dumps({"status": "COMPLETE"}), encoding="utf-8")
    relative = "daily-runs/2099-01-02/archive-receipt.json"
    state = {
        "date": "2099-01-02",
        "stages": {
            "github_archive": {
                "status": "COMPLETE",
                "artifact_hashes": {relative: sha256_file(receipt)},
            }
        },
    }

    assert _checkpointed_receipt(
        tmp_path, state, "github_archive", "archive-receipt.json"
    ) == {"status": "COMPLETE"}

    receipt.write_text(json.dumps({"status": "COMPLETE", "tampered": True}), encoding="utf-8")
    assert _checkpointed_receipt(
        tmp_path, state, "github_archive", "archive-receipt.json"
    ) is None
