import tempfile
import unittest
from pathlib import Path

from dragon.orchestrator import Orchestrator
from dragon.stages import StageDefinition, StageFailure, StageResult


DATE = "2026-09-08"
TZ = "Africa/Casablanca"


def writer(name, calls, *, failure=None):
    def run(context):
        calls.append(name)
        if failure:
            raise StageFailure(failure, f"{name} failed")
        output = context.run_dir / name / "result.txt"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(f"{name}:{context.attempt}", encoding="utf-8")
        return StageResult(outputs=(output,))

    return run


def definitions(calls, *, fail=None):
    return [
        StageDefinition("preflight", (), writer("preflight", calls)),
        StageDefinition(
            "research", ("preflight",), writer("research", calls, failure=fail)
        ),
        StageDefinition("pdf", ("research",), writer("pdf", calls)),
    ]


class V5OrchestratorTests(unittest.TestCase):
    def make(self, root, calls, *, fail=None):
        return Orchestrator(
            root=root,
            edition_date=DATE,
            timezone=TZ,
            stages=definitions(calls, fail=fail),
        )

    def test_success_records_hash_bound_checkpoints(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []
            orchestrator = self.make(Path(directory), calls)
            state = orchestrator.run()
            self.assertEqual(calls, ["preflight", "research", "pdf"])
            self.assertEqual(state["last_successful_checkpoint"], "pdf")
            self.assertTrue(state["stages"]["pdf"]["artifact_hashes"])
            self.assertTrue(
                (Path(directory) / "daily-runs" / DATE / "logs" / "pdf.jsonl").is_file()
            )

    def test_status_is_read_only_when_no_run_exists(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            calls = []
            value = self.make(root, calls).status()
            self.assertEqual(value["run_status"], "NO_RUN")
            self.assertFalse((root / "daily-runs" / DATE / "state.json").exists())

    def test_resume_skips_valid_checkpoints(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []
            orchestrator = self.make(Path(directory), calls)
            orchestrator.run()
            calls.clear()
            orchestrator.run(resume=True)
            self.assertEqual(calls, [])

    def test_changed_artifact_invalidates_checkpoint_and_downstream_runs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            calls = []
            orchestrator = self.make(root, calls)
            orchestrator.run()
            (root / "daily-runs" / DATE / "research" / "result.txt").write_text(
                "changed", encoding="utf-8"
            )
            calls.clear()
            state = orchestrator.run(resume=True)
            self.assertEqual(calls, ["research", "pdf"])
            self.assertEqual(state["stages"]["research"]["status"], "COMPLETE")

    def test_failure_stops_without_running_downstream(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []
            state = self.make(Path(directory), calls, fail="SOURCE_TIMEOUT").run()
            self.assertEqual(calls, ["preflight", "research"])
            self.assertEqual(state["stages"]["research"]["status"], "FAILED")
            self.assertEqual(state["stages"]["research"]["error_code"], "SOURCE_TIMEOUT")
            self.assertEqual(state["stages"]["pdf"]["status"], "PENDING")
            self.assertEqual(state["publication_status"], "FAILED")

    def test_targeted_retry_invalidates_only_selected_and_downstream(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            calls = []
            orchestrator = self.make(root, calls)
            orchestrator.run()
            calls.clear()
            state = orchestrator.run(retry_stage="research")
            self.assertEqual(calls, ["research", "pdf"])
            self.assertEqual(state["stages"]["preflight"]["attempt_count"], 1)
            self.assertEqual(state["stages"]["research"]["attempt_count"], 2)

    def test_bad_prerequisite_registry_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "STAGE_PREREQUISITE_INVALID"):
                Orchestrator(
                    root=Path(directory),
                    edition_date=DATE,
                    timezone=TZ,
                    stages=[StageDefinition("research", ("missing",), writer("x", []))],
                )


if __name__ == "__main__":
    unittest.main()
