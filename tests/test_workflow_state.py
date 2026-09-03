import tempfile
import unittest
from pathlib import Path
from scripts.workflow_state import (
    fresh_production_status, required_remote_paths, validate_state,
    EDITORIAL_FILES, PUBLICATION_SOURCE_FILES, PUBLICATION_REPORT, COVER_BRIEF,
)

DATE = "2026-09-03"

def complete_status():
    s = fresh_production_status(DATE, last_updated="2026-09-03T07:00:00+01:00")
    s.update({
        "current_research":"COMPLETE","deep_research":"COMPLETE","editorial":"COMPLETE",
        "publishing":"COMPLETE","cover":"COMPLETE","overall_status":"COMPLETE",
        "editorial_gates_passed":True,"arabic_script_count":0,
        "publication_source_package":"COMPLETE","ready_for_codex_rendering":True,
        "image_generation_status":"PASS","visual_qa_status":"PASS",
    })
    return s

class WorkflowStateTests(unittest.TestCase):
    def test_fresh_status_exposes_binary_states(self):
        s = fresh_production_status(DATE)
        self.assertEqual(s["pdf_binary"], "NOT_GENERATED_NO_RUNTIME")
        self.assertEqual(s["epub_binary"], "NOT_GENERATED_NO_RUNTIME")
        self.assertEqual(s["binary_artifacts"], "PENDING_MANUAL_CODEX_RENDER")
        self.assertEqual(s["cover_binary_archive"], "PENDING_MANUAL_ARCHIVE")

    def test_editorial_complete_requires_zero_arabic(self):
        s = complete_status()
        s["arabic_script_count"] = 1
        errors = validate_state(s, DATE)
        self.assertTrue(any("arabic_script_count == 0" in e for e in errors))

    def test_publishing_complete_does_not_require_pdf_epub(self):
        s = complete_status()
        with tempfile.TemporaryDirectory() as td, tempfile.TemporaryDirectory() as rd:
            edition = Path(td); run = Path(rd)
            for name in EDITORIAL_FILES + PUBLICATION_SOURCE_FILES:
                (edition/name).write_text("x")
            (run/PUBLICATION_REPORT).write_text("{}")
            (run/COVER_BRIEF).write_text("{}")
            remote = ()
            for stage in ("editorial","publishing","cover"):
                remote += required_remote_paths(DATE, stage)
            errors = validate_state(s, DATE, edition_dir=edition, run_dir=run, remote_paths=remote)
        self.assertEqual(errors, [])

    def test_cover_complete_requires_generation_and_visual_qa_not_archive(self):
        s = complete_status()
        s["image_generation_status"] = "FAILED"
        errors = validate_state(s, DATE)
        self.assertTrue(any("image_generation_status == PASS" in e for e in errors))
        s = complete_status()
        self.assertEqual(s["github_image_archive"], "UNSUPPORTED_BY_CONNECTOR")
        self.assertEqual(s["cover_binary_archive"], "PENDING_MANUAL_ARCHIVE")

if __name__ == "__main__":
    unittest.main()
