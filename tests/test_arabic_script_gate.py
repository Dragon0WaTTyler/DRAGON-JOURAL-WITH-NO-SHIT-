import unittest
from scripts.editorial_depth import (
    ARABIC_SCRIPT_RANGES, arabic_script_count, arabic_script_occurrences,
    language_has_arabic_script,
)

class ArabicScriptGateTests(unittest.TestCase):
    def test_all_required_ranges_are_covered(self):
        self.assertEqual(ARABIC_SCRIPT_RANGES, (
            (0x0600,0x06FF),(0x0750,0x077F),(0x08A0,0x08FF),
            (0xFB50,0xFDFF),(0xFE70,0xFEFF),
        ))

    def test_occurrences_are_counted_and_located(self):
        text = "latin\n" + chr(0x0627) + " x " + chr(0x0750) + chr(0x08A0) + chr(0xFB50) + chr(0xFE70)
        found = arabic_script_occurrences(text)
        self.assertEqual(len(found), 5)
        self.assertEqual(arabic_script_count(text), 5)
        self.assertTrue(all({"index","line","column","character","codepoint"} <= set(x) for x in found))
        self.assertTrue(language_has_arabic_script(text))
        self.assertFalse(language_has_arabic_script("Darija Latin only"))

if __name__ == "__main__":
    unittest.main()
