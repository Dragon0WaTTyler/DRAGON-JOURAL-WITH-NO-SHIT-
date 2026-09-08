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
    def test_scheduler_has_one_disabled_codex_local_entry(self):
        config = load_local_config(ROOT)
        value = settings(ROOT)
        self.assertEqual(config["scheduler"]["entries"], 1)
        self.assertFalse(value["enabled"])
        self.assertEqual(value["provider"], "codex-local-automation")
        self.assertEqual(value["kind"], "cron")
        self.assertEqual(value["destination"], "local")
        self.assertEqual(value["execution_environment"], "local")
        self.assertEqual(value["canonical_command"], "python dragon_watchdog.py")
        self.assertEqual(len(value["runtime_fingerprint"]), 64)
        self.assertTrue(value["source_git_revision"])

    def test_os_scheduler_helpers_are_not_part_of_v5(self):
        self.assertEqual(list((ROOT / "scripts" / "windows").glob("*.ps1")), [])

    def test_scheduler_settings_support_direct_diagnostic_execution(self):
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
        self.assertEqual(value["canonical_command"], "python dragon_watchdog.py")

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
