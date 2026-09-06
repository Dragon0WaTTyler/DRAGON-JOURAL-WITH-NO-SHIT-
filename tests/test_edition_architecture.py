import json
import tempfile
import unittest
from pathlib import Path

from scripts.edition_architecture import load_architecture, validate_daily_architecture, validate_plan


ROOT = Path(__file__).parents[1]
DATE = "2099-01-01"
ARCHITECTURE = load_architecture(ROOT / "config" / "edition-architecture.yaml")


def words(count: int) -> str:
    return " ".join(f"kalma{index}" for index in range(count))


def narrative_words(count: int, paragraphs: int) -> str:
    chunks = []
    base, remainder = divmod(count, paragraphs)
    for index in range(paragraphs):
        chunks.append(words(base + (1 if index < remainder else 0)))
    return "\n\n".join(chunks)


def fixture():
    sections = []
    markdown = ["# DRAGON"]
    formats = ["lead_article"] * 4 + ["standard_article"] * 6
    inventory = ARCHITECTURE["section_inventory"]
    for index, item in enumerate(inventory):
        section_id = item["id"]
        fmt = "long_form" if section_id == "history" else (formats.pop(0) if formats else "brief")
        headline = f"Headline {section_id}"
        low = ARCHITECTURE["formats"][fmt]["words"][0]
        body = []
        if "standfirst" in ARCHITECTURE["formats"][fmt]["requires"]:
            body.append("*Standfirst kay3ti ma3na dyal had l-mawdo3.*")
        if "byline" in ARCHITECTURE["formats"][fmt]["requires"]:
            body.append("Tahrir: DRAGON")
        paragraphs = ARCHITECTURE["formats"][fmt].get("narrative_paragraphs", 1)
        body.append(narrative_words(low, paragraphs))
        body.append("[S01]")
        article = {"story_id": f"story-{section_id}", "headline": headline, "format": fmt, "word_budget": low}
        sections.append({"section_id": section_id, "status": "ACTIVE", "editorial_reason": "Verified material supports this desk.", "articles": [article]})
        markdown.extend([f"## {item['reader_heading']}", f"### {headline}", "\n\n".join(body)])
        if section_id == "front":
            # The inventory has 12 brief sections. Add three source-backed front
            # briefs here, under their real reader section, to meet the floor.
            for extra in range(3):
                brief_headline = f"Front brief {extra}"
                sections[-1]["articles"].append({"story_id": f"front-brief-{extra}", "headline": brief_headline, "format": "brief", "word_budget": 80})
                markdown.extend([f"### {brief_headline}", words(80), "[S01]"])
    plan = {
        "date": DATE,
        "timezone": "Africa/Casablanca",
        "edition_architecture_version": 4,
        "edition_word_budget": 12000,
        "sections": sections,
    }
    return plan, "\n\n".join(markdown)


class EditionArchitectureTests(unittest.TestCase):
    def test_real_architecture_accepts_balanced_newspaper_plan(self):
        plan, markdown = fixture()
        report = validate_plan(plan, ARCHITECTURE, markdown, edition_date=DATE)
        self.assertEqual(report["validation_status"], "PASS", report["errors"])
        self.assertEqual(report["format_counts"]["lead_article"], 4)
        self.assertEqual(report["format_counts"]["brief"], 15)

    def test_inventory_cannot_be_silently_dropped(self):
        plan, markdown = fixture()
        plan["sections"] = plan["sections"][1:]
        report = validate_plan(plan, ARCHITECTURE, markdown, edition_date=DATE)
        self.assertEqual(report["validation_status"], "FAIL")
        self.assertTrue(any("inventory section" in error for error in report["errors"]))

    def test_active_article_needs_byline_and_citation(self):
        plan, markdown = fixture()
        markdown = markdown.replace("Tahrir: DRAGON", "", 1).replace("[S01]", "", 1)
        report = validate_plan(plan, ARCHITECTURE, markdown, edition_date=DATE)
        self.assertEqual(report["validation_status"], "FAIL")
        self.assertTrue(any("byline" in error for error in report["errors"]))
        self.assertTrue(any("citation" in error for error in report["errors"]))

    def test_long_article_cannot_use_the_legacy_briefing_card(self):
        plan, markdown = fixture()
        markdown = markdown.replace(
            "[S01]",
            "**Chno w9e3**\n**3lach mohim**\n**Chno nra9bo**\n[S01]",
            1,
        )
        report = validate_plan(plan, ARCHITECTURE, markdown, edition_date=DATE)
        self.assertEqual(report["validation_status"], "FAIL")
        self.assertTrue(any("legacy briefing template" in error for error in report["errors"]))

    def test_lead_requires_connected_narrative_paragraphs(self):
        plan, markdown = fixture()
        # The first lead has four 250-word prose blocks. Join its three
        # internal breaks while preserving all headings and metadata.
        markdown = markdown.replace("\n\nkalma0", " kalma0", 3)
        report = validate_plan(plan, ARCHITECTURE, markdown, edition_date=DATE)
        self.assertEqual(report["validation_status"], "FAIL")
        self.assertTrue(any("narrative paragraphs" in error for error in report["errors"]))

    def test_plan_article_cannot_be_placed_under_a_different_section(self):
        plan, markdown = fixture()
        markdown = markdown.replace("### Headline siyasa_dawla", "### Headline siyasa_dawla", 1)
        first = markdown.index("## Siyasa w Dawla")
        moved = markdown.index("### Headline siyasa_dawla", first)
        before = markdown[:moved]
        after = markdown[moved:]
        article_end = after.index("## I9tisad w Flous")
        article = after[:article_end]
        markdown = before + after[article_end:] + "\n\n" + article
        report = validate_plan(plan, ARCHITECTURE, markdown, edition_date=DATE)
        self.assertEqual(report["validation_status"], "FAIL")
        self.assertTrue(any("wrong reader section" in error for error in report["errors"]))

    def test_legacy_editions_are_not_retroactively_rejected(self):
        result = validate_daily_architecture(ROOT, DATE, "# DRAGON", {"edition_architecture_version": 3})
        self.assertEqual(result["validation_status"], "LEGACY_NOT_REQUIRED")

    def test_v4_report_requires_persisted_plan(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "config").mkdir()
            (root / "config" / "edition-architecture.yaml").write_text((ROOT / "config" / "edition-architecture.yaml").read_text())
            with self.assertRaisesRegex(ValueError, "edition-plan.json"):
                validate_daily_architecture(root, DATE, "# DRAGON", {"edition_architecture_version": 4})

    def test_v4_daily_plan_is_checked(self):
        plan, markdown = fixture()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "config").mkdir()
            (root / "config" / "edition-architecture.yaml").write_text((ROOT / "config" / "edition-architecture.yaml").read_text())
            run = root / "daily-runs" / DATE
            run.mkdir(parents=True)
            (run / "edition-plan.json").write_text(json.dumps(plan))
            result = validate_daily_architecture(root, DATE, markdown, {"edition_architecture_version": 4})
            self.assertEqual(result["validation_status"], "PASS", result["errors"])


if __name__ == "__main__":
    unittest.main()
