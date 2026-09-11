import tempfile
import unittest
from pathlib import Path

from dragon.orchestrator import Orchestrator
from dragon.state import EXECUTION_MODE_FRESH, sha256_file
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

    def test_runtime_change_requires_explicit_rebase_from_preflight(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            calls = []
            orchestrator = self.make(root, calls)
            first = orchestrator.run()
            runtime_file = root / "dragon" / "new_runtime.py"
            runtime_file.parent.mkdir(parents=True)
            runtime_file.write_text("REVISION = 2\n", encoding="utf-8")
            calls.clear()

            blocked = orchestrator.run(resume=True)

            self.assertEqual(calls, [])
            self.assertEqual(blocked["run_result"], "BLOCKED")
            self.assertEqual(blocked["error_code"], "RUNTIME_FINGERPRINT_MISMATCH")
            self.assertEqual(blocked["publication_status"], first["publication_status"])

            rebased = orchestrator.run(from_stage="preflight")
            self.assertEqual(calls, ["preflight", "research", "pdf"])
            self.assertEqual(rebased["runtime_fingerprint"], blocked["runtime_fingerprint_current"])

    def test_fresh_run_isolated_from_legacy_state_and_binds_source_attempt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            legacy_calls = []
            legacy = self.make(root, legacy_calls)
            legacy.run()
            legacy_path = root / "daily-runs" / DATE / "state.json"
            legacy_hash = sha256_file(legacy_path)
            (root / "dragon").mkdir(exist_ok=True)
            (root / "dragon" / "changed.py").write_text("VERSION = 2\n", encoding="utf-8")

            blocked = legacy.run(resume=True)
            self.assertEqual(blocked["error_code"], "RUNTIME_FINGERPRINT_MISMATCH")
            blocked_hash = sha256_file(legacy_path)

            fresh_calls = []
            fresh = Orchestrator(
                root=root,
                edition_date=DATE,
                timezone=TZ,
                stages=definitions(fresh_calls),
                execution_mode=EXECUTION_MODE_FRESH,
                source_attempt_id="attempt-test-provider-seed",
            )
            state = fresh.run()

            self.assertEqual(fresh_calls, ["preflight", "research", "pdf"])
            self.assertEqual(state["execution_mode"], EXECUTION_MODE_FRESH)
            self.assertEqual(state["source_attempt_id"], "attempt-test-provider-seed")
            self.assertEqual(state["run_id"], fresh.store.run_id)
            self.assertEqual(fresh.store.path.parent.parent.name, "runs")
            self.assertNotEqual(fresh.store.path, legacy_path)
            self.assertEqual(sha256_file(legacy_path), blocked_hash)
            self.assertNotEqual(legacy_hash, blocked_hash)

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

    def test_declared_missing_input_fails_acceptance(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def run(context):
                output = context.run_dir / "result.txt"
                output.write_text("result", encoding="utf-8")
                return StageResult(
                    (output,), inputs=(context.run_dir / "missing-input.json",)
                )

            state = Orchestrator(
                root=root,
                edition_date=DATE,
                timezone=TZ,
                stages=[StageDefinition("final_qa", (), run)],
            ).run()
            self.assertEqual(
                state["stages"]["final_qa"]["error_code"], "STAGE_INPUT_INVALID"
            )

    def test_targeted_retry_invalidates_graph_dependents_not_later_siblings(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            calls = []
            stages = [
                StageDefinition("source", (), writer("source", calls)),
                StageDefinition("pdf", ("source",), writer("pdf", calls)),
                StageDefinition("epub", ("source",), writer("epub", calls)),
                StageDefinition("final_qa", ("pdf", "epub"), writer("final_qa", calls)),
                StageDefinition("github_archive", ("final_qa",), writer("github_archive", calls)),
                StageDefinition("whatsapp_delivery", ("final_qa",), writer("whatsapp_delivery", calls)),
            ]
            orchestrator = Orchestrator(root=root, edition_date=DATE, timezone=TZ, stages=stages)
            orchestrator.run()
            calls.clear()

            state = orchestrator.run(retry_stage="pdf")

            self.assertEqual(calls, ["pdf", "final_qa", "github_archive", "whatsapp_delivery"])
            self.assertEqual(state["stages"]["epub"]["attempt_count"], 1)

            calls.clear()
            state = orchestrator.run(retry_stage="github_archive")
            self.assertEqual(calls, ["github_archive"])
            self.assertEqual(state["stages"]["whatsapp_delivery"]["attempt_count"], 2)

    def test_archive_failure_preserves_local_publication_and_retries_only_external_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            calls = []
            fail_archive = [True]

            def final(context):
                result = writer("final_qa", calls)(context)
                return StageResult(result.outputs, metadata={"state_updates": {"publication_status": "COMPLETE"}})

            def archive(context):
                calls.append("github_archive")
                if fail_archive[0]:
                    raise StageFailure("GIT_PUSH_FAILED", "injected rejection")
                result = writer("archive_output", calls)(context)
                return StageResult(result.outputs, metadata={"state_updates": {"archive_status": "COMPLETE"}})

            stages = [
                StageDefinition("final_qa", (), final),
                StageDefinition("github_archive", ("final_qa",), archive),
                StageDefinition("whatsapp_delivery", ("final_qa",), writer("whatsapp_delivery", calls)),
            ]
            orchestrator = Orchestrator(root=root, edition_date=DATE, timezone=TZ, stages=stages)
            failed = orchestrator.run()
            self.assertEqual(failed["publication_status"], "COMPLETE")
            self.assertEqual(failed["archive_status"], "FAILED")
            self.assertEqual(failed["stages"]["whatsapp_delivery"]["status"], "PENDING")

            fail_archive[0] = False
            calls.clear()
            recovered = orchestrator.run(retry_stage="github_archive")
            self.assertEqual(calls, ["github_archive", "archive_output", "whatsapp_delivery"])
            self.assertEqual(recovered["publication_status"], "COMPLETE")
            self.assertEqual(recovered["archive_status"], "COMPLETE")


if __name__ == "__main__":
    unittest.main()
