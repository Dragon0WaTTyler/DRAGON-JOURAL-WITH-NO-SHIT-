import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VALID = ROOT / "research/2026-09-02/morocco.json"


class StoryPacketValidationTests(unittest.TestCase):
    def validate(self, payload):
        with tempfile.TemporaryDirectory() as tmp:
            packet = Path(tmp) / "packet.json"
            packet.write_text(json.dumps(payload), encoding="utf-8")
            return subprocess.run(
                ["python", "scripts/validate_story_packet.py", str(packet)],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

    def payload(self):
        return json.loads(VALID.read_text(encoding="utf-8"))

    def test_exact_source_record_passes(self):
        self.assertEqual(self.validate(self.payload()).returncode, 0)

    def test_homepage_is_rejected(self):
        payload = self.payload()
        payload["primary_sources"][0]["url"] = "https://www.maroc.ma/"
        result = self.validate(payload)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not a homepage", result.stdout)

    def test_missing_attribution_is_rejected(self):
        payload = self.payload()
        del payload["primary_sources"][0]["attribution"]
        result = self.validate(payload)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing: attribution", result.stdout)

    def test_missing_independent_trail_blocks_publishable_packet(self):
        payload = self.payload()
        payload["independent_sources"] = []
        result = self.validate(payload)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("requires an independent source trail", result.stdout)

    def test_bad_timestamp_and_uncertainty_label_are_rejected(self):
        payload = self.payload()
        payload["primary_sources"][0]["retrieved_at"] = "2026-09-02"
        payload["primary_sources"][0]["evidence_label"] = "UNLABELED"
        result = self.validate(payload)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Africa/Casablanca", result.stdout)
        self.assertIn("evidence_label is invalid", result.stdout)


if __name__ == "__main__":
    unittest.main()
