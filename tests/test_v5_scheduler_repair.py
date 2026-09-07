import unittest
from pathlib import Path

from dragon.config import load_local_config
from dragon.repair import RepairRequest, repair_agent_from_config
from dragon.scheduler import settings


ROOT = Path(__file__).resolve().parents[1]


class V5SchedulerRepairTests(unittest.TestCase):
    def test_scheduler_has_one_disabled_build_behind_entry(self):
        config = load_local_config(ROOT)
        value = settings(ROOT)
        self.assertEqual(config["scheduler"]["entries"], 1)
        self.assertFalse(value["enabled"])
        self.assertTrue(str(value["watchdog"]).endswith("dragon_watchdog.py"))
        self.assertEqual(value["interval_minutes"], 15)

    def test_windows_helpers_manage_the_same_single_task(self):
        files = [
            ROOT / "scripts" / "windows" / name
            for name in (
                "install-scheduler.ps1",
                "remove-scheduler.ps1",
                "test-scheduler.ps1",
                "run-now.ps1",
            )
        ]
        for path in files:
            text = path.read_text(encoding="utf-8")
            self.assertIn("dragon\\scheduler.py", text)
            self.assertIn("task_name", text)
        install = files[0].read_text(encoding="utf-8")
        self.assertIn("MultipleInstances IgnoreNew", install)
        self.assertIn("AllowBeforeCutover", install)

    def test_unproved_repair_provider_is_unavailable(self):
        config = load_local_config(ROOT)
        agent = repair_agent_from_config(config)
        self.assertFalse(agent.available)
        result = agent.repair(
            RepairRequest(Path("incident-001"), "abc", "pdf", "UNKNOWN_CODE_DEFECT")
        )
        self.assertEqual(result.status, "REQUIRES_INTERVENTION")


if __name__ == "__main__":
    unittest.main()
