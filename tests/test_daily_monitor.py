import json
import tempfile
import unittest
from pathlib import Path

from scripts.audit_daily_run import audit


DATE = "2099-01-01"


class DailyMonitorTests(unittest.TestCase):
    def test_before_deadline_does_not_fail_for_missing_run(self):
        with tempfile.TemporaryDirectory() as temp:
            self.assertEqual(audit(Path(temp), DATE, after_deadline=False), [])

    def test_missing_status_fails_after_deadline(self):
        with tempfile.TemporaryDirectory() as temp:
            errors = audit(Path(temp), DATE)
        self.assertTrue(any(error.startswith("MISSING_DAILY_STATUS") for error in errors))

    def test_complete_binary_archive_passes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            edition = root / "editions/2099/01" / DATE
            edition.mkdir(parents=True)
            (edition / "dragon.pdf").write_bytes(b"pdf")
            (edition / "dragon.epub").write_bytes(b"epub")
            run = root / "daily-runs" / DATE
            run.mkdir(parents=True)
            status = {"date": DATE, "timezone": "Africa/Casablanca", "final_publication_status": "COMPLETE", "overall_status": "COMPLETE", "binary_artifacts": "COMPLETE", "github_binary_read_back": "PASS", "final_binary_paths": {"pdf": "editions/2099/01/2099-01-01/dragon.pdf", "epub": "editions/2099/01/2099-01-01/dragon.epub"}}
            status.update({stage: "COMPLETE" for stage in ("current_research", "deep_research", "editorial", "cover", "publishing")})
            (run / "status.json").write_text(json.dumps(status), encoding="utf-8")
            self.assertEqual(audit(root, DATE), [])

    def test_stage_failure_exposes_recorded_reason(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run = root / "daily-runs" / DATE
            run.mkdir(parents=True)
            status = {"date": DATE, "timezone": "Africa/Casablanca", "publishing": "BLOCKED", "publishing_blocking_reason": "cover stale"}
            (run / "status.json").write_text(json.dumps(status), encoding="utf-8")
            errors = audit(root, DATE)
        self.assertTrue(any("PUBLISHING_NOT_COMPLETE: cover stale" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
