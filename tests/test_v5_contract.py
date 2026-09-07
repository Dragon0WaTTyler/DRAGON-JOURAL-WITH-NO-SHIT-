import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
STAGES = [
    "preflight",
    "research",
    "article_generation",
    "chief_editor",
    "factcheck",
    "arabic_language_qa",
    "cover",
    "publication_source",
    "pdf",
    "epub",
    "final_qa",
    "github_archive",
    "whatsapp_delivery",
]


class V5ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = yaml.safe_load(
            (ROOT / "config" / "local-automation.yaml").read_text(encoding="utf-8")
        )

    def test_v5_is_authoritative_for_new_implementation(self):
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        legacy = (ROOT / "SPEC-v1.md").read_text(encoding="utf-8")
        self.assertIn("SPEC-v5.md", agents)
        self.assertIn("V5 is the authoritative implementation target", readme)
        self.assertIn("legacy technical specification", legacy)

    def test_one_local_orchestrator_contract(self):
        self.assertEqual(self.config["version"], 5)
        self.assertEqual(self.config["primary_runtime"], "local-windows")
        self.assertEqual(self.config["scheduler"]["entries"], 1)
        self.assertEqual(self.config["orchestrator"]["instances"], 1)
        self.assertEqual(self.config["orchestrator"]["stages"], STAGES)

    def test_arabic_rtl_contract(self):
        publication = self.config["publication"]
        self.assertEqual(publication["language"], "ar")
        self.assertEqual(publication["direction"], "rtl")
        self.assertIn("تحرير:", publication["byline_template"])

    def test_archive_and_delivery_are_independent(self):
        publication = self.config["publication"]
        self.assertTrue(publication["archive_status_is_independent"])
        self.assertTrue(publication["delivery_status_is_independent"])

    def test_build_behind_does_not_claim_cutover(self):
        self.assertEqual(self.config["mode"], "build-behind")
        self.assertFalse(self.config["scheduler"]["enabled"])
        self.assertTrue(self.config["cutover"]["legacy_v4_fallback_enabled"])
        self.assertFalse(self.config["cutover"]["local_scheduler_enabled"])
        self.assertFalse(
            self.config["cutover"]["competing_github_production_disabled"]
        )

    def test_unconfigured_providers_are_not_claimed_available(self):
        providers = self.config["providers"]
        self.assertEqual(providers["ai"]["type"], "unconfigured")
        self.assertFalse(providers["ai"]["paid_service_auto_enable"])
        self.assertEqual(providers["repair"]["type"], "unconfigured")
        self.assertEqual(providers["whatsapp"]["type"], "unconfigured")


if __name__ == "__main__":
    unittest.main()
