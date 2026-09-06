import unittest
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = [
    ("current-news-desk", 1, "07:45"),
    ("deep-features-desk", 2, "08:00"),
    ("chief-editor", 3, "08:50"),
    ("cover-director", 4, "09:25"),
    ("publication-builder", 5, "09:55"),
]

class ScheduledWorkflowContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = yaml.safe_load((ROOT/"config/scheduled-workflow.yaml").read_text())
        cls.schedule = yaml.safe_load((ROOT/"config/schedule.yaml").read_text())
        cls.roles = yaml.safe_load((ROOT/"config/roles.yaml").read_text())
        cls.architecture = yaml.safe_load((ROOT/"config/edition-architecture.yaml").read_text())

    def test_exactly_five_jobs_and_thirteen_roles(self):
        jobs = self.workflow["jobs"]
        self.assertEqual([(j["id"], j["task_number"], j["local_time"]) for j in jobs], EXPECTED)
        self.assertEqual(len(self.roles["roles"]), 13)

    def test_timezone_and_schedule_disabled(self):
        self.assertEqual(self.workflow["timezone"], "Africa/Casablanca")
        self.assertTrue(all(j["timezone"] == "Africa/Casablanca" for j in self.workflow["jobs"]))
        self.assertFalse(self.workflow["enabled"])
        self.assertFalse(self.schedule["enabled"])

    def test_publication_builder_is_text_only(self):
        job = self.workflow["jobs"][4]
        self.assertEqual(job["id"], "publication-builder")
        self.assertEqual(job["mode"], "TEXT_ONLY")
        paths = {o["path"] for o in job["outputs"]}
        self.assertEqual(paths, {
            "editions/YYYY/MM/YYYY-MM-DD/edition.html",
            "editions/YYYY/MM/YYYY-MM-DD/print.css",
            "editions/YYYY/MM/YYYY-MM-DD/epub-content.xhtml",
            "daily-runs/YYYY-MM-DD/publishing-report.json",
            "editions/YYYY/MM/YYYY-MM-DD/manifest.json",
        })
        state = job["completion"]["set_binary_state"]
        self.assertEqual(state["pdf_binary"], "NOT_GENERATED_NO_RUNTIME")
        self.assertEqual(state["epub_binary"], "NOT_GENERATED_NO_RUNTIME")
        self.assertEqual(state["binary_artifacts"], "PENDING_AUTOMATIC_RENDER")
        self.assertTrue(state["ready_for_codex_rendering"])

    def test_cover_completion_does_not_require_archive(self):
        job = self.workflow["jobs"][3]
        state = job["completion"]["set_binary_state"]
        self.assertEqual(state["github_image_archive"], "TYPE_DEPENDENT")
        self.assertEqual(state["cover_binary_archive"], "PERSISTED_CANONICAL_ASSET")
        self.assertEqual(self.workflow["tested_capabilities"]["task_4_cover_director"]["retry_limit"], 1)

    def test_connector_limitations_are_tested_facts(self):
        c = self.workflow["connector_capabilities"]
        self.assertEqual(c["github_scheduled_text_read"], "PASS")
        self.assertEqual(c["github_scheduled_utf8_text_write"], "PASS")
        self.assertEqual(c["github_scheduled_text_read_back"], "PASS")
        self.assertEqual(c["github_binary_image_write"], "UNSUPPORTED")
        self.assertEqual(c["pdf_binary_write"], "UNSUPPORTED")
        self.assertEqual(c["epub_binary_write"], "UNSUPPORTED")
        self.assertEqual(c["scheduled_repository_executable_runtime"], "NOT_AVAILABLE")
        self.assertEqual(c["scheduled_image_generation"], "PASS")

    def test_no_forbidden_runtime_requirements(self):
        self.assertTrue(self.workflow["execution_constraints"]["github_actions_allowed"])
        c = self.workflow["execution_constraints"]
        for key in ("openai_api_allowed","openai_api_key_required","pay_as_you_go_openai_allowed",
                    "external_paid_services_allowed",
                    "self_hosted_runner_allowed","local_pc_dependency_allowed"):
            self.assertFalse(c[key])

    def test_version_four_plan_is_owned_by_chief_editor(self):
        chief = self.workflow["jobs"][2]
        paths = {item["path"] for item in chief["outputs"]}
        self.assertIn("daily-runs/YYYY-MM-DD/edition-plan.json", paths)
        self.assertEqual(self.architecture["version"], 4)
        self.assertGreaterEqual(len(self.architecture["section_inventory"]), 20)
        self.assertEqual(self.architecture["edition"]["hard_min_words"], 10000)

    def test_finality_guard_protects_published_editions(self):
        required = [
            ROOT / "prompts" / "production-master.md",
            ROOT / "AGENTS.md",
            ROOT / "SPEC-v1.md",
            ROOT / "prompts" / "scheduled" / "03-chief-editor.md",
            ROOT / "prompts" / "scheduled" / "04-cover.md",
            ROOT / "prompts" / "scheduled" / "05-publication.md",
        ]
        for path in required:
            text = path.read_text(encoding="utf-8")
            self.assertIn("FINALITY GUARD" if "scheduled" in path.parts else "Finality guard", text, path)
            self.assertIn("ALREADY_PUBLISHED", text, path)
            self.assertIn("binary_artifacts", text, path)

    def test_v4_publication_template_has_no_noncanonical_tagline(self):
        template = (ROOT / "templates" / "publication-v4.html").read_text(encoding="utf-8")
        self.assertIn("YYYY-MM-DD · Africa/Casablanca", template)
        self.assertNotIn("Jarida youmiya", template)

    def test_chief_editor_labels_legacy_depth_and_briefing_handoff(self):
        prompt = (ROOT / "prompts" / "scheduled" / "03-chief-editor.md").read_text(encoding="utf-8")
        self.assertIn("VERSION-4 TOTAL: 10,000+ useful words", prompt)
        self.assertIn("legacy archive safety floor", prompt)
        self.assertIn("Never copy their labels into `edition.md`", prompt)

if __name__ == "__main__":
    unittest.main()
