import json
import tempfile
import unittest
from pathlib import Path

from scripts.workflow_state import (
    EDITORIAL_FILES,
    fresh_production_status,
    initialize_production_run,
    required_remote_paths,
    validate_report_consistency,
    validate_state,
)


DATE = "2026-09-03"


def complete_status():
    status = fresh_production_status(DATE, last_updated="2026-09-03T07:00:00+01:00")
    for field in ("current_research", "deep_research", "editorial", "publishing", "cover", "overall_status"):
        status[field] = "COMPLETE"
    status["editorial_gates_passed"] = True
    status["publishing_artifacts_valid"] = True
    status["cover_artifact_valid"] = True
    return status


class WorkflowStateTests(unittest.TestCase):
    def test_fresh_run_resets_stale_same_date_state(self):
        stale = complete_status()
        stale.update({"binary_artifacts": "COMPLETE", "cover_binary_archive": "COMPLETE"})
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "status.json"
            path.write_text(json.dumps(stale), encoding="utf-8")
            initialized = initialize_production_run(path, DATE, last_updated="2026-09-03T07:45:00+01:00")
            self.assertEqual(initialized["current_research"], "PENDING")
            self.assertEqual(initialized["deep_research"], "PENDING")
            self.assertEqual(initialized["editorial"], "PENDING")
            self.assertEqual(initialized["publishing"], "PENDING")
            self.assertEqual(initialized["cover"], "PENDING")
            self.assertEqual(initialized["overall_status"], "PENDING")
            self.assertIsNone(initialized["blocking_reason"])
            self.assertNotIn("binary_artifacts", initialized)
            self.assertNotIn("cover_binary_archive", initialized)
            initialized["current_research"] = "RUNNING"
            self.assertEqual(initialized["deep_research"], "PENDING")
            self.assertEqual(initialized["editorial"], "PENDING")

    def test_explicit_resume_refuses_complete_state_without_remote_artifacts(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "status.json"
            path.write_text(json.dumps(complete_status()), encoding="utf-8")
            with self.assertRaises(ValueError):
                initialize_production_run(path, DATE, resume=True, remote_paths=())

    def test_report_pass_cannot_hide_missing_canonical_edition(self):
        status = complete_status()
        editorial_report = {
            "status": "COMPLETE",
            "required_editorial_files_exist": "PASS",
            "remote_read_back": {"status": "PASS", "paths": list(required_remote_paths(DATE, "editorial"))},
        }
        with tempfile.TemporaryDirectory() as temp:
            errors = validate_report_consistency(
                status,
                DATE,
                edition_dir=Path(temp),
                editorial_report=editorial_report,
            )
        self.assertTrue(any("canonical files" in error for error in errors))

    def test_blocked_editorial_cannot_leave_publishing_complete(self):
        status = fresh_production_status(DATE, last_updated="2026-09-03T08:50:00+01:00")
        status.update({"current_research": "COMPLETE", "deep_research": "COMPLETE", "editorial": "BLOCKED", "publishing": "COMPLETE", "cover": "COMPLETE"})
        errors = validate_state(status, DATE, remote_paths=required_remote_paths(DATE, "publishing") + required_remote_paths(DATE, "cover"), publishing_artifacts_valid=True, cover_artifact_valid=True)
        self.assertTrue(any("publishing cannot" in error for error in errors))
        self.assertTrue(any("cover cannot" in error for error in errors))

    def test_missing_canonical_files_block_editorial_persistence(self):
        status = complete_status()
        with tempfile.TemporaryDirectory() as temp:
            (Path(temp) / EDITORIAL_FILES[0]).write_text("edition", encoding="utf-8")
            errors = validate_state(status, DATE, edition_dir=Path(temp), remote_paths=(), editorial_gates_passed=True)
        self.assertTrue(any("canonical files" in error or "remote read-back" in error for error in errors))

    def test_overall_complete_is_impossible_with_invalid_prerequisite(self):
        status = complete_status()
        errors = validate_state(status, DATE)
        self.assertTrue(any("local artifacts" in error or "remote read-back" in error for error in errors))

    def test_pending_binary_artifacts_cannot_coexist_with_publishing_complete(self):
        status = complete_status()
        status["binary_artifacts"] = "PENDING"
        with tempfile.TemporaryDirectory() as temp:
            edition_dir = Path(temp)
            for name in ("edition.md", "sources.json", "manifest.json", "edition.pdf", "edition.epub", "cover.webp"):
                (edition_dir / name).write_bytes(b"artifact")
            reports = {
                "status": "COMPLETE",
                "github_text_persistence": "PASS",
                "github_binary_persistence": "PASS",
                "remote_read_back": {"paths": list(required_remote_paths(DATE, "publishing")) + list(required_remote_paths(DATE, "cover"))},
            }
            errors = validate_report_consistency(
                status,
                DATE,
                edition_dir=edition_dir,
                editorial_report={"status": "COMPLETE", "remote_read_back": {"paths": list(required_remote_paths(DATE, "editorial"))}},
                publishing_report=reports,
            )
        self.assertTrue(any("binary_artifacts cannot be pending" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
