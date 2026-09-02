import unittest
from pathlib import Path

from scripts.editorial_depth import evaluate, language_has_arabic_script, load_policy
from scripts.validate_edition import validate_real


POLICY = load_policy(Path(__file__).parents[1] / "config/editorial-depth.yaml")


def body(label: str, words: int) -> str:
    """Create deterministic, non-source narrative for policy tests."""
    return " ".join(f"{label}{index}" for index in range(words))


def markdown(*, history=850, literature=850, morocco=750, palestine=550, meknes=350, science=550, source_words=0):
    sections = [
        ("Kalmat Ra2is t-Ta7rir", body("ra2is", 100)),
        ("L-Mghreb — dossier", body("morocco", morocco)),
        ("Meknes Radar — dossier", body("meknes", meknes)),
        ("Filastin w Sharq l-Awsat — dossier", body("palestine", palestine)),
        ("L-3alam — dossier", body("world", 550)),
        ("AI w Technology — dossier", body("ai", 550)),
        ("Science — dossier", body("science", science)),
        ("Tarikh l-Mghreb — dossier", body("history", history)),
        ("Adab w Culture — dossier", body("culture", literature)),
        ("Investigations — dossier NEEDS_VERIFICATION", body("investigation", 80)),
    ]
    if source_words:
        sections.append(("Sources", body("source record", source_words)))
    return "# DRAGON\n\n**PRE-PRODUCTION — NOT YET DAILY PRODUCTION**\n\n" + "\n\n".join(
        f"## {heading}\n\n{text}" for heading, text in sections
    )


class EditorialDepthTests(unittest.TestCase):
    def test_short_history_fails(self):
        report = evaluate(markdown(history=799), POLICY, edition_date="2099-01-01")
        self.assertEqual(report["validation_status"], "FAIL")
        self.assertTrue(any("history section has" in item for item in report["chief_editor_regeneration_requests"]))

    def test_short_literature_fails(self):
        report = evaluate(markdown(literature=799), POLICY)
        self.assertTrue(any("literature_culture section has" in item for item in report["chief_editor_regeneration_requests"]))

    def test_history_hold_cannot_override_hard_minimum(self):
        text = markdown(history=56).replace("## Tarikh l-Mghreb — dossier", "## Tarikh l-Mghreb — HOLD")
        report = evaluate(text, POLICY)
        self.assertFalse(report["per_section_word_counts"]["history"]["pass"])
        self.assertFalse(report["allowed_exceptions"]["history"]["used"])
        self.assertTrue(any("history section has 56 words" in item for item in report["chief_editor_regeneration_requests"]))

    def test_literature_hold_cannot_override_hard_minimum(self):
        text = markdown(literature=144).replace("## Adab w Culture — dossier", "## Adab w Culture — HOLD")
        report = evaluate(text, POLICY)
        self.assertFalse(report["per_section_word_counts"]["literature_culture"]["pass"])
        self.assertFalse(report["allowed_exceptions"]["literature_culture"]["used"])
        self.assertTrue(any("literature_culture section has 144 words" in item for item in report["chief_editor_regeneration_requests"]))

    def test_history_800_useful_words_passes_without_exception(self):
        report = evaluate(markdown(history=800), POLICY)
        self.assertTrue(report["per_section_word_counts"]["history"]["pass"])
        self.assertFalse(report["allowed_exceptions"]["history"]["used"])

    def test_literature_800_useful_words_passes_without_exception(self):
        report = evaluate(markdown(literature=800), POLICY)
        self.assertTrue(report["per_section_word_counts"]["literature_culture"]["pass"])
        self.assertFalse(report["allowed_exceptions"]["literature_culture"]["used"])

    def test_arabic_script_is_hard_failure_signal(self):
        self.assertTrue(language_has_arabic_script("Had l-jملة فيها كتاب b-script 3arabi"))
        self.assertFalse(language_has_arabic_script("Had l-jomla kamla b-Darija Latin"))

    def test_edition_validator_rejects_arabic_script(self):
        errors = []
        validate_real(
            Path("2026-01-01"),
            {
                "date": "2026-01-01",
                "mode": "preproduction",
                "status": "pre-production",
                "language": "darija-latin",
                "fact_check": "passed",
                "language_check": "passed",
                "smoke_test": False,
                "label": "PRE-PRODUCTION — NOT YET DAILY PRODUCTION",
                "sources_count": 1,
                "citations_count": 1,
                "sections": ["Test"],
            },
            [{
                "id": "S01",
                "url": "https://example.com/source",
                "publisher": "Example",
                "publication_date": "2026-01-01",
                "accessed_at": "2026-01-01T00:00:00Z",
                "source_type": "primary",
                "claim_supported": "test",
            }],
            "# DRAGON\n\n## Test\n\nHad l-jomla فيها كتاب [S01]",
            errors,
        )
        self.assertIn("edition.md contains Arabic-script characters", errors)

    def test_valid_long_sections_pass(self):
        report = evaluate(markdown(), POLICY)
        self.assertEqual(report["validation_status"], "PASS")
        self.assertEqual(report["chief_editor_regeneration_requests"], [])
        self.assertGreaterEqual(report["total_word_count"], 4000)

    def test_meknes_thin_news_exception_is_explicit(self):
        text = markdown(meknes=20).replace(
            "## Meknes Radar — dossier\n\n",
            "## Meknes Radar — dossier\n\n**THIN-NEWS EXCEPTION:** ma l9inach developments verified kafiya.\n\n",
        )
        report = evaluate(text, POLICY)
        self.assertTrue(report["per_section_word_counts"]["meknes"]["pass"])
        self.assertTrue(report["allowed_exceptions"]["meknes"]["used"])
        self.assertFalse(any(item.startswith("meknes section") for item in report["chief_editor_regeneration_requests"]))

    def test_sources_filler_does_not_satisfy_total_minimum(self):
        report = evaluate(markdown(history=100, literature=100, morocco=100, palestine=100, meknes=100, science=100, source_words=5000), POLICY)
        self.assertLess(report["total_word_count"], 4000)
        self.assertFalse(report["total"]["pass"])
        self.assertTrue(report["chief_editor_regeneration_requests"])


if __name__ == "__main__":
    unittest.main()
