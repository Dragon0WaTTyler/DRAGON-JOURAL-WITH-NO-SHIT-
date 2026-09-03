import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_JOBS = {
    "current-news-desk",
    "deep-features-desk",
    "chief-editor",
    "publishing-desk",
    "cover-director",
}


class ScheduledWorkflowContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = yaml.safe_load((ROOT / "config/scheduled-workflow.yaml").read_text(encoding="utf-8"))
        cls.schedule = yaml.safe_load((ROOT / "config/schedule.yaml").read_text(encoding="utf-8"))
        cls.roles = yaml.safe_load((ROOT / "config/roles.yaml").read_text(encoding="utf-8"))

    def test_contract_has_exactly_five_jobs_and_keeps_thirteen_roles(self):
        self.assertFalse(self.workflow["enabled"])
        self.assertEqual(len(self.workflow["jobs"]), 5)
        self.assertEqual({job["id"] for job in self.workflow["jobs"]}, EXPECTED_JOBS)
        self.assertEqual(len(self.roles["roles"]), 13)

    def test_all_jobs_use_casablanca_and_status_contract(self):
        self.assertEqual(self.workflow["timezone"], "Africa/Casablanca")
        self.assertTrue(all(job["timezone"] == "Africa/Casablanca" for job in self.workflow["jobs"]))
        self.assertEqual(self.workflow["daily_status"]["allowed_stage_values"], ["PENDING", "RUNNING", "COMPLETE", "BLOCKED", "FAILED"])

    def test_connector_limitations_are_explicit_and_schedule_stays_disabled(self):
        capabilities = self.workflow["connector_capabilities"]
        self.assertEqual(capabilities["github_scheduled_text_read"], "PASS")
        self.assertEqual(capabilities["github_scheduled_utf8_text_write"], "PASS")
        self.assertEqual(capabilities["github_scheduled_text_read_back"], "PASS")
        self.assertEqual(capabilities["github_binary_image_write_through_current_connector"], "UNSUPPORTED/BLOCKED")
        self.assertEqual(capabilities["scheduled_image_generation"], "UNTESTED")
        self.assertFalse(self.schedule["enabled"])
        self.assertTrue((ROOT / "design/DRAGON-COVER-STYLE.md").is_file())

    def test_forbidden_paid_or_local_execution_is_disabled(self):
        constraints = self.workflow["execution_constraints"]
        for key in (
            "openai_api_allowed",
            "openai_api_key_required",
            "pay_as_you_go_openai_allowed",
            "github_actions_allowed",
            "external_paid_services_allowed",
            "self_hosted_runner_allowed",
            "local_pc_dependency_allowed",
        ):
            self.assertFalse(constraints[key], key)


if __name__ == "__main__":
    unittest.main()
