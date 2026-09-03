import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts.reader_facing_qa import lint_text
from scripts.validate_edition import validate_epub


CONTAINER = b'<?xml version="1.0" encoding="utf-8"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>'
OPF = b'<?xml version="1.0" encoding="utf-8"?><package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="id">test</dc:identifier><dc:language>ary-Latn</dc:language></metadata><manifest><item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/><item id="section" href="section.xhtml" media-type="application/xhtml+xml"/><item id="sources" href="sources.xhtml" media-type="application/xhtml+xml"/><item id="cover" href="cover.xhtml" media-type="application/xhtml+xml"/><item id="image" href="cover.webp" media-type="image/webp" properties="cover-image"/></manifest><spine><itemref idref="cover"/><itemref idref="section"/><itemref idref="sources"/></spine></package>'


def xhtml(body: str) -> bytes:
    return f'<?xml version="1.0" encoding="utf-8"?><html xmlns="http://www.w3.org/1999/xhtml"><head><title>Test</title></head><body>{body}</body></html>'.encode("utf-8")


def make_epub(path: Path, *, nav: bytes | None = None, section: bytes | None = None) -> None:
    nav = nav or xhtml('<nav id="toc"><h1>TOC</h1><ol><li><a href="section.xhtml">Section</a></li><li><a href="sources.xhtml">Sources</a></li></ol></nav>')
    section = section or xhtml('<article id="section"><h1>Section</h1><p>français, grève, mostašfa, ə.</p><p><a href="sources.xhtml#source-S1">[S1]</a></p></article>')
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("mimetype", b"application/epub+zip", compress_type=zipfile.ZIP_STORED)
        archive.writestr("META-INF/container.xml", CONTAINER)
        archive.writestr("OEBPS/content.opf", OPF)
        archive.writestr("OEBPS/nav.xhtml", nav)
        archive.writestr("OEBPS/cover.xhtml", xhtml('<section id="cover"><img src="cover.webp" alt="cover" /></section>'))
        archive.writestr("OEBPS/section.xhtml", section)
        archive.writestr("OEBPS/sources.xhtml", xhtml('<section id="sources"><h1>Sources</h1><ol><li id="source-S1"><a href="https://example.com/source">https://example.com/source</a></li></ol></section>'))
        archive.writestr("OEBPS/cover.webp", b"RIFF\x04\x00\x00\x00WEBP")


class ReaderFacingPublishingTests(unittest.TestCase):
    def validate(self, *, nav=None, section=None):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "edition.epub"
            make_epub(path, nav=nav, section=section)
            errors = []
            validate_epub(path, errors)
            return errors

    def test_valid_epub_passes(self):
        self.assertEqual(self.validate(), [])

    def test_malformed_xhtml_fails(self):
        errors = self.validate(section=b'<!doctype html><html><body><h1>Bad</h1></body></html>')
        self.assertTrue(any("malformed XML/XHTML" in error for error in errors))

    def test_invalid_xml_entity_fails(self):
        errors = self.validate(section=xhtml('<article id="section"><h1>Section</h1><p>fish & chips</p></article>'))
        self.assertTrue(any("malformed XML/XHTML" in error for error in errors))

    def test_broken_toc_reference_fails(self):
        errors = self.validate(nav=xhtml('<nav id="toc"><h1>TOC</h1><ol><li><a href="missing.xhtml">Missing</a></li></ol></nav>'))
        self.assertTrue(any("unresolved link" in error for error in errors))

    def test_mojibake_fixture_fails(self):
        self.assertTrue(any("mojibake" in error for error in lint_text("grA ve communiquA mostaAfa", "fixture")))

    def test_normal_utf8_latin_text_passes(self):
        self.assertEqual(lint_text("français, grève, mostašfa, ə", "fixture"), [])

    def test_engineering_text_in_reader_body_is_detected(self):
        self.assertTrue(any("engineering" in error for error in lint_text("Had execution test f Codex Cloud kayst3mel GitHub Actions", "fixture")))

    def test_arabic_script_still_fails(self):
        self.assertTrue(any("Arabic-script" in error for error in lint_text("had كتاب", "fixture")))


if __name__ == "__main__":
    unittest.main()
