import json
import tempfile
import unittest
from pathlib import Path

from dragon.state import StateStore, atomic_write_json, new_state, validate_state


STAGES = ["preflight", "research", "pdf"]


class V5StateTests(unittest.TestCase):
    def test_new_state_has_uniform_stage_records(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            value = new_state(
                edition_date="2026-09-08",
                timezone="Africa/Casablanca",
                stages=STAGES,
                root=root,
            )
            self.assertEqual(validate_state(value, STAGES), [])
            record = value["stages"]["research"]
            self.assertEqual(record["prerequisites"], ["preflight"])
            self.assertEqual(record["attempt_count"], 0)
            self.assertEqual(record["artifact_hashes"], {})

    def test_atomic_write_retains_previous_good_copy(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            atomic_write_json(path, {"revision": 1})
            atomic_write_json(path, {"revision": 2})
            self.assertEqual(json.loads(path.read_text())["revision"], 2)
            self.assertEqual(
                json.loads(path.with_suffix(".json.bak").read_text())["revision"], 1
            )
            self.assertEqual(list(path.parent.glob("*.tmp")), [])

    def test_corrupt_primary_recovers_from_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = StateStore(root, "2026-09-08", "Africa/Casablanca", STAGES)
            value = store.initialize()
            value["publication_status"] = "DEGRADED"
            store.save(value)
            store.path.write_text("{broken", encoding="utf-8")
            recovered = store.load()
            self.assertEqual(recovered["schema_version"], 5)
            self.assertEqual(
                json.loads(store.path.read_text(encoding="utf-8"))["schema_version"], 5
            )
            self.assertTrue((store.run_dir / "state.json.corrupt").is_file())

    def test_legacy_status_is_hashed_but_not_imported_as_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = root / "daily-runs" / "2026-09-08"
            run.mkdir(parents=True)
            legacy = run / "status.json"
            legacy.write_text('{"editorial":"COMPLETE"}', encoding="utf-8")
            store = StateStore(root, "2026-09-08", "Africa/Casablanca", STAGES)
            value = store.initialize()
            self.assertFalse(value["legacy_status"]["imported_as_checkpoint"])
            self.assertEqual(value["stages"]["research"]["status"], "PENDING")
            self.assertEqual(legacy.read_text(), '{"editorial":"COMPLETE"}')


if __name__ == "__main__":
    unittest.main()
