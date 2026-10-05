import unittest

from dragon.language import (
    decode_utf8,
    validate_arabic_text,
    validate_html_rtl,
    validate_xhtml_rtl,
)


ARABIC = (
    "تتابع جريدة دراغون تطورات هذا الملف اعتمادا على وثائق رسمية ومصادر مستقلة. "
    "وتوضح المعطيات المتاحة ما تحقق حتى الآن، وما يزال موضع خلاف أو يحتاج إلى تحقق."
)


class ArabicLanguageQAV5Tests(unittest.TestCase):
    def test_professional_arabic_passes(self):
        result = validate_arabic_text(ARABIC)
        self.assertEqual(result.status, "PASS")
        self.assertEqual(result.checks["ARABIC_LANGUAGE"], "PASS")
        self.assertGreater(result.metrics["arabic_script_characters"], 20)

    def test_latin_transliteration_cannot_be_reader_language(self):
        result = validate_arabic_text(
            "Had l-khabar maktoub kamel b-darija latin bla horof arabiya."
        )
        self.assertEqual(result.status, "FAIL")
        self.assertEqual(result.checks["ARABIC_LANGUAGE"], "FAIL")
        self.assertEqual(result.checks["FOREIGN_LANGUAGE_LEAKAGE"], "FAIL")

    def test_official_mixed_direction_terms_can_be_allowed(self):
        result = validate_arabic_text(
            ARABIC + " ونشرت OpenAI وثيقة تقنية على GitHub.",
            allowed_latin_terms=("OpenAI", "GitHub"),
        )
        self.assertEqual(result.status, "PASS")

    def test_mojibake_is_rejected(self):
        result = validate_arabic_text(ARABIC + " Ø§Ù„")
        self.assertEqual(result.checks["MOJIBAKE"], "FAIL")
        self.assertTrue(any("MOJIBAKE_DETECTED" in issue for issue in result.issues))

    def test_utf8_decode_is_strict(self):
        self.assertEqual(decode_utf8(ARABIC.encode("utf-8")), ARABIC)
        with self.assertRaisesRegex(ValueError, "UTF8_INVALID"):
            decode_utf8(b"\xff\xfe")
        with self.assertRaisesRegex(ValueError, "UTF8_BOM_NOT_ALLOWED"):
            decode_utf8(b"\xef\xbb\xbftext")

    def test_html_requires_arabic_rtl_root(self):
        self.assertEqual(validate_html_rtl('<html lang="ar" dir="rtl"></html>'), [])
        self.assertEqual(
            validate_html_rtl('<html lang="ary-Latn" dir="ltr"></html>'),
            ["RTL_HTML_LANG_INVALID", "RTL_HTML_DIRECTION_INVALID"],
        )

    def test_xhtml_requires_xml_language_and_rtl(self):
        valid = (
            '<html xmlns="http://www.w3.org/1999/xhtml" lang="ar" '
            'xml:lang="ar" dir="rtl"><head/><body/></html>'
        )
        self.assertEqual(validate_xhtml_rtl(valid), [])
        invalid = (
            '<html xmlns="http://www.w3.org/1999/xhtml" lang="ar" '
            'xml:lang="ar" dir="ltr"><head/><body/></html>'
        )
        self.assertEqual(validate_xhtml_rtl(invalid), ["RTL_XHTML_DIRECTION_INVALID"])


if __name__ == "__main__":
    unittest.main()
