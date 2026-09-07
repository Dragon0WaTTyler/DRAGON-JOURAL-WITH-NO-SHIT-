import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from dragon.lock import DuplicateRunError, RunLock
from dragon.watchdog import WatchdogAssessment, assess, launch_orchestrator, recover


DATE = "2026-09-08"
TZ = "Africa/Casablanca"
CONFIG = {
    "version": 5,
    "timezone": TZ,
    "orchestrator": {"stages": ["research"]},
    "watchdog": {
        "default_stage_timeout_seconds": 60,
        "stage_timeouts_seconds": {"research": 30},
    },
}


def write_state(root, status="RUNNING"):
    path = root / "daily-runs" / DATE / "state.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"stages": {"research": {"status": status}}}), encoding="utf-8")
    return path


def write_lock(root, *, pid=123, heartbeat=None):
    path = root / "daily-runs" / DATE / "run.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = heartbeat or datetime.now(ZoneInfo(TZ)).isoformat()
    path.write_text(
        json.dumps({"schema_version": 5, "token": "owner", "pid": pid, "acquired_at": timestamp, "heartbeat_at": timestamp}),
        encoding="utf-8",
    )
    return path


class V5LockWatchdogTests(unittest.TestCase):
    def test_watchdog_marks_spawned_runs_as_unattended(self):
        process = type("Process", (), {"pid": 456})()
        with tempfile.TemporaryDirectory() as directory, patch(
            "dragon.watchdog.subprocess.Popen", return_value=process
        ) as popen:
            root = Path(directory)
            (root / "dragon_daily.py").write_text("", encoding="utf-8")
            self.assertEqual(launch_orchestrator(root, DATE, resume=False), 456)
            self.assertEqual(popen.call_args.kwargs["env"]["DRAGON_TRIGGER"], "watchdog")

    def test_lock_is_exclusive_and_owner_releases_it(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run.lock"
            first = RunLock(path, TZ, pid=101, alive=lambda _: True).acquire()
            with self.assertRaisesRegex(DuplicateRunError, "DUPLICATE_RUN"):
                RunLock(path, TZ, pid=202, alive=lambda _: True).acquire()
            first.release()
            self.assertFalse(path.exists())

    def test_lock_does_not_reclaim_dead_owner_without_watchdog(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run.lock"
            path.write_text('{"pid":999,"token":"old"}', encoding="utf-8")
            with self.assertRaisesRegex(DuplicateRunError, "watchdog must arbitrate"):
                RunLock(path, TZ, pid=202, alive=lambda _: False).acquire()

    def test_missing_daily_state_is_safe_to_start(self):
        with tempfile.TemporaryDirectory() as directory, patch(
            "dragon.watchdog.load_local_config", return_value=CONFIG
        ):
            result = assess(Path(directory), DATE)
            self.assertEqual(result.action, "START")

    def test_dead_owner_before_state_creation_is_safe_to_resume(self):
        with tempfile.TemporaryDirectory() as directory, patch(
            "dragon.watchdog.load_local_config", return_value=CONFIG
        ):
            root = Path(directory)
            write_lock(root)
            result = assess(root, DATE, alive=lambda _: False)
            self.assertEqual(result.action, "RESUME")

    def test_corrupt_state_with_backup_and_no_owner_is_safe_to_resume(self):
        with tempfile.TemporaryDirectory() as directory, patch(
            "dragon.watchdog.load_local_config", return_value=CONFIG
        ):
            root = Path(directory)
            state = write_state(root)
            (state.parent / "state.json.bak").write_text(state.read_text(), encoding="utf-8")
            state.write_text("{broken", encoding="utf-8")
            result = assess(root, DATE)
            self.assertEqual(result.action, "RESUME")

    def test_dead_owner_with_running_stage_is_safe_to_resume(self):
        with tempfile.TemporaryDirectory() as directory, patch(
            "dragon.watchdog.load_local_config", return_value=CONFIG
        ):
            root = Path(directory)
            write_state(root)
            write_lock(root)
            result = assess(root, DATE, alive=lambda _: False)
            self.assertEqual(result.action, "RESUME")
            self.assertEqual(result.stage, "research")

    def test_live_stale_owner_is_never_duplicated(self):
        with tempfile.TemporaryDirectory() as directory, patch(
            "dragon.watchdog.load_local_config", return_value=CONFIG
        ):
            root = Path(directory)
            write_state(root)
            now = datetime.now(ZoneInfo(TZ))
            write_lock(root, heartbeat=(now - timedelta(minutes=10)).isoformat())
            result = assess(root, DATE, now=now, alive=lambda _: True)
            self.assertEqual(result.action, "NO_ACTION")
            self.assertIn("without duplicate restart", result.reason)

    def test_recovery_quarantines_dead_lock_and_launches_once(self):
        with tempfile.TemporaryDirectory() as directory, patch(
            "dragon.watchdog.load_local_config", return_value=CONFIG
        ):
            root = Path(directory)
            write_state(root)
            lock = write_lock(root)
            launches = []
            assessment = WatchdogAssessment(
                "RESUME", "dead", "research", 123, f"daily-runs/{DATE}/run.lock"
            )
            report = recover(
                root,
                DATE,
                assessment=assessment,
                launcher=lambda launch_root, day: launches.append((launch_root, day)) or 456,
            )
            self.assertEqual(len(launches), 1)
            self.assertEqual(report["launched_pid"], 456)
            self.assertFalse(lock.exists())
            self.assertTrue((root / report["quarantined_lock"]).is_file())
            self.assertTrue((root / "daily-runs" / DATE / "recovery" / "watchdog-latest.json").is_file())


if __name__ == "__main__":
    unittest.main()
