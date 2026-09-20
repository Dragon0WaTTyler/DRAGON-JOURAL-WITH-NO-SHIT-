import json
import tempfile
import unittest
from pathlib import Path

from dragon.incidents import IncidentWriter
from dragon.orchestrator import Orchestrator
from dragon.recovery import ErrorCategory, RecoveryEngine, RecoveryPolicy
from dragon.stages import StageDefinition, StageFailure, StageResult


ROOT = Path(__file__).resolve().parents[1]
POLICY = RecoveryPolicy.load(ROOT / "config" / "recovery-policy.yaml")


class V5RecoveryTests(unittest.TestCase):
    def test_policy_covers_every_category_and_documented_code(self):
        self.assertEqual(set(POLICY.categories), {item.value for item in ErrorCategory})
        catalog = (ROOT / "docs" / "FAILURE-CATALOG.md").read_text(encoding="utf-8")
        runbook = (ROOT / "docs" / "RECOVERY-RUNBOOK.md").read_text(encoding="utf-8")
        for code in POLICY.codes:
            self.assertIn(code, catalog)
            self.assertIn(code, runbook)

    def test_transient_retry_is_finite_with_exponential_backoff(self):
        engine = RecoveryEngine(POLICY)
        first = engine.decide("SOURCE_TIMEOUT", 1)
        second = engine.decide("SOURCE_TIMEOUT", 2)
        exhausted = engine.decide("SOURCE_TIMEOUT", 3)
        self.assertEqual(first.action, "RETRY")
        self.assertEqual(second.delay_seconds, first.delay_seconds * 2)
        self.assertEqual(exhausted.action, "INCIDENT")

    def test_delivery_and_code_defect_classification(self):
        engine = RecoveryEngine(POLICY)
        self.assertEqual(
            engine.decide("WHATSAPP_SEND_FAILED", 1).category,
            ErrorCategory.DELIVERY,
        )
        self.assertEqual(
            engine.decide("UNHANDLED_STAGE_EXCEPTION", 1).category,
            ErrorCategory.CODE_DEFECT,
        )

    def test_research_recovery_required_is_content_but_remains_an_incident(self):
        decision = RecoveryEngine(POLICY).decide("RESEARCH_RECOVERY_REQUIRED", 1)
        self.assertEqual(decision.category, ErrorCategory.CONTENT)
        self.assertEqual(decision.action, "INCIDENT")
        self.assertEqual(decision.max_attempts, 1)
        self.assertEqual(decision.delay_seconds, 0)

    def test_unsafe_source_targets_are_validation_blocks_without_retry(self):
        engine = RecoveryEngine(POLICY)
        for code in (
            "SOURCE_URL_UNSAFE",
            "SOURCE_REDIRECT_UNSAFE",
            "SOURCE_RESPONSE_TOO_LARGE",
        ):
            decision = engine.decide(code, 1)
            self.assertEqual(decision.category, ErrorCategory.VALIDATION)
            self.assertEqual(decision.action, "BLOCK")
            self.assertEqual(decision.max_attempts, 1)
            self.assertEqual(decision.delay_seconds, 0)

    def test_orchestrator_retries_transient_stage_only_until_success(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            calls = []

            def flaky(context):
                calls.append(context.attempt)
                if context.attempt < 3:
                    raise StageFailure("SOURCE_TIMEOUT", "temporary")
                output = context.run_dir / "research" / "packet.json"
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text("{}", encoding="utf-8")
                return StageResult(outputs=(output,))

            orchestrator = Orchestrator(
                root=root,
                edition_date="2026-09-08",
                timezone="Africa/Casablanca",
                stages=[StageDefinition("research", (), flaky)],
                recovery_engine=RecoveryEngine(POLICY, sleeper=lambda _: None),
            )
            state = orchestrator.run()
            self.assertEqual(calls, [1, 2, 3])
            self.assertEqual(state["stages"]["research"]["status"], "COMPLETE")
            self.assertEqual(state["stages"]["research"]["attempt_count"], 3)
            self.assertEqual(len(state["failure_history"]), 2)

    def test_code_defect_creates_redacted_incident(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def broken(_):
                raise RuntimeError("DRAGON_API_KEY=top-secret")

            orchestrator = Orchestrator(
                root=root,
                edition_date="2026-09-08",
                timezone="Africa/Casablanca",
                stages=[StageDefinition("research", (), broken)],
                recovery_engine=RecoveryEngine(POLICY, sleeper=lambda _: None),
            )
            state = orchestrator.run()
            incident = root / state["incidents"][0]
            self.assertTrue((incident / "incident.json").is_file())
            all_text = "\n".join(
                path.read_text(encoding="utf-8") for path in incident.iterdir()
            )
            self.assertNotIn("top-secret", all_text)
            self.assertIn("[REDACTED]", all_text)
            self.assertEqual(
                state["stages"]["research"]["repair_status"],
                "REQUIRES_INTERVENTION",
            )

    def test_incident_rejects_relevant_paths_outside_repository(self):
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as outside:
            root = Path(directory)
            run = root / "daily-runs" / "2026-09-08"
            state = {"date": "2026-09-08", "run_id": "run", "stages": {"pdf": {}}}
            packet = IncidentWriter(root, run, "Africa/Casablanca").create(
                stage="pdf",
                state=state,
                error_code="PDF_BROWSER_CRASH",
                error_detail="failed",
                relevant_files=[Path(outside) / "secret.txt"],
            )
            value = json.loads((packet / "incident.json").read_text(encoding="utf-8"))
            self.assertEqual(value["relevant_files"], [])


if __name__ == "__main__":
    unittest.main()
