import unittest

from scripts.current_news_handoff import validate


def candidate(story_id, url):
    return {
        "STORY_ID": story_id,
        "SECTION_ID": "world",
        "RECOMMENDATION": "BRIEF",
        "INDEPENDENT_SOURCES": [{"url": url}],
    }


class CurrentNewsHandoffTests(unittest.TestCase):
    def packet(self):
        candidates = [candidate(f"story-{index}", f"https://example.test/article-{index}") for index in range(30)]
        return {
            "quality_gate": {
                "publishable_candidate_count": 30,
                "lead_capable_candidate_count": 4,
                "brief_capable_candidate_count": 20,
            },
            "section_packets": {"world": {"candidates": candidates}},
        }

    def test_accepts_a_complete_exact_url_inventory(self):
        self.assertEqual(validate(self.packet()), [])

    def test_rejects_missing_quality_gate(self):
        packet = self.packet()
        packet.pop("quality_gate")
        self.assertEqual(validate(packet), ["missing quality_gate"])

    def test_rejects_a_generic_source_url(self):
        packet = self.packet()
        packet["section_packets"]["world"]["candidates"][0]["INDEPENDENT_SOURCES"][0]["url"] = "https://example.test/news-2"
        self.assertTrue(any("exact article" in error for error in validate(packet)))


if __name__ == "__main__":
    unittest.main()
