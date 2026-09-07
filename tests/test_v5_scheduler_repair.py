import unittest
from pathlib import Path
import json
import subprocess
import sys

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
        self.assertEqual(len(value["runtime_fingerprint"]), 64)
        self.assertTrue(value["source_git_revision"])

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
        verifier = files[2].read_text(encoding="utf-8")
        self.assertIn("EnabledMatching.Count -ne 1", verifier)
        self.assertIn("Repetition.Interval", verifier)
        self.assertIn("MultipleInstances", verifier)
        self.assertIn("acceptance\\machine\\scheduler\\inventory.json", verifier)

    def test_scheduler_settings_support_the_direct_path_used_by_windows_helpers(self):
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "dragon" / "scheduler.py"),
                "--root",
                str(ROOT),
            ],
            cwd=ROOT.parent,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        value = json.loads(result.stdout)
        self.assertEqual(value["task_name"], "DRAGON V5 Daily Newspaper")
        self.assertTrue(value["watchdog"].endswith("dragon_watchdog.py"))

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
