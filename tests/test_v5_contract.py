import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
STAGES = [
    "preflight",
    "source_monitoring",
    "research",
    "source_intelligence",
    "research_planning",
    "deep_research",
    "deep_research_execution",
    "research_recovery",
    "article_generation",
    "claim_evidence_graph",
    "media_critic",
    "science_integrity",
    "investigation_engine",
    "adversarial_review",
    "factcheck",
    "chief_editor",
    "arabic_language_qa",
    "cover_direction",
    "cover",
    "layout_direction",
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

    def test_legacy_reader_language_workflow_is_scoped_to_v4_manifests(self):
        workflow = (ROOT / ".github" / "workflows" / "reader-language.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn('manifest.get("language", "")', workflow)
        self.assertIn('"darija-latin"', workflow)
        self.assertIn("V5 Arabic editions are outside this legacy V4 gate", workflow)

    def test_unconfigured_providers_are_not_claimed_available(self):
        providers = self.config["providers"]
        self.assertEqual(providers["ai"]["type"], "local-command")
        self.assertEqual(providers["ai"]["integration_test_status"], "NOT_RUN")
        self.assertFalse(providers["ai"]["paid_service_auto_enable"])
        self.assertEqual(providers["repair"]["type"], "unconfigured")
        self.assertEqual(providers["whatsapp"]["type"], "unconfigured")

    def test_generation_budget_is_derived_from_editorial_depth_contract(self):
        from dragon.config import load_local_config

        value = load_local_config(ROOT)["editorial_word_budget"]
        self.assertEqual(value, {
            "acceptance_floor_words": 4000,
            "generation_target_edition_words": 6000,
            "generation_maximum_edition_words": 9000,
            "role_quality_targets": {
                "LEAD": {"target_words": 1000, "maximum_words": 1400},
                "STANDARD": {"target_words": 700, "maximum_words": 1000},
                "INVESTIGATION": {"target_words": 1200, "maximum_words": 1600},
            },
        })

    def test_executable_stage_graph_matches_authoritative_config(self):
        from dragon.pipeline import build_stage_definitions
        from dragon.providers import SyntheticEditorialProvider

        actual = [
            stage.name
            for stage in build_stage_definitions(
                SyntheticEditorialProvider(), synthetic=True
            )
        ]
        self.assertEqual(actual, self.config["orchestrator"]["stages"])


if __name__ == "__main__":
    unittest.main()
