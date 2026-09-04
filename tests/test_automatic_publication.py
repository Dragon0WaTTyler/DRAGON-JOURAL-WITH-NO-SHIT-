import json
import os
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo
from markdown_it import MarkdownIt
from scripts.publication_inputs import validate_inputs, canonical_date, safe_asset, digest
from scripts.publication_renderer import build_epub, validate_epub, render, read_json, write_json, restricted_fetcher
from scripts.auto_publish import publish, git, candidates, verify_remote
from scripts.workflow_state import fresh_production_status, validate_state, initialize_production_run

DATE = "2026-09-05"
ROOT = Path(__file__).resolve().parents[1]

def fixture(root):
    edition = root / "editions/2026/09" / DATE
    run = root / "daily-runs" / DATE
    (edition / "assets").mkdir(parents=True)
    run.mkdir(parents=True)
    (root / "config").mkdir()
    shutil.copy(ROOT / "config/editorial-depth.yaml", root / "config/editorial-depth.yaml")
    cover = edition / "assets/cover.svg"
    cover.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 1200"><rect width="900" height="1200" fill="white"/><text x="60" y="100" font-size="72">DRAGON</text><text x="60" y="180" font-size="28">{DATE}</text><rect x="60" y="300" width="780" height="400" fill="red"/><text x="60" y="850" font-size="48">TEST ONLY</text></svg>', encoding="utf-8")
    sections = [("L-Mghreb", 750), ("Meknes Radar", 350), ("Filastin w Sharq l-Awsat", 550), ("Science", 550), ("Tarikh l-Mghreb", 850), ("Adab w Culture", 850), ("L-3alam", 550)]
    md = f"# DRAGON\n\n{DATE}\n\nTEST ONLY\n\n"
    for heading, words in sections:
        md += "## " + heading + "\n\n"
        for start in range(0, words, 100):
            md += " ".join("kalma" + str(i) for i in range(start, min(words, start + 100))) + ".\n\n"
    md += "## Investigations — NEEDS_VERIFICATION\n\nTa7qiq ba9i kaytsenna dalil.\n\n[S1](https://example.org/evidence)\n"
    (edition / "edition.md").write_text(md, encoding="utf-8")
    body = MarkdownIt().render(md)
    doc = '<html xmlns="http://www.w3.org/1999/xhtml" lang="ary-Latn"><head><title>Test</title></head><body>' + body + '</body></html>'
    for name in ("edition.html", "epub-content.xhtml"):
        (edition / name).write_text(doc, encoding="utf-8")
    (edition / "print.css").write_text('@page{size:A4;margin:15mm}body{font-family:serif;font-size:11pt}p{line-height:1.4}', encoding="utf-8")
    base = {"date":DATE,"timezone":"Africa/Casablanca"}
    meta = base | {"cover_asset_type":"SVG_FALLBACK","cover_asset_path":str(cover.relative_to(root)).replace("\\","/"),"visual_qa_status":"PASS","image_generation_status":"NOT_AVAILABLE","publication_source_package":"COMPLETE"}
    status = fresh_production_status(DATE) | meta | {k:"COMPLETE" for k in ("current_research","deep_research","editorial","cover","publishing")}
    write_json(run / "status.json", status)
    write_json(run / "cover-brief.json", meta)
    write_json(edition / "manifest.json", meta)
    write_json(edition / "sources.json", base | {"sources":[{"id":"S1","url":"https://example.org/evidence"}]})
    write_json(run / "editorial-report.json", base | {"fact_check_status":"PASS","darija_status":"PASS","arabic_script_count":0,"history_topic_id":"test-history"})
    for name in ("publishing-report.json", "current-news.json", "deep-features.json"):
        write_json(run / name, base)
    return edition, run, cover

def fake_pdf(edition, cover, output):
    from reportlab.pdfgen.canvas import Canvas
    canvas = Canvas(str(output))
    canvas.drawString(30, 700, "DRAGON TEST COVER")
    canvas.showPage()
    canvas.drawString(30, 700, "TEST INTERIOR")
    canvas.save()
    return 2

class AutomaticPublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "checkout"
        self.edition, self.run, self.cover = fixture(self.root)

    def test_valid_text_package_passes(self):
        edition, cover, hashes = validate_inputs(self.root, DATE)
        self.assertEqual(cover, self.cover)
        self.assertIn("editions/2026/09/2026-09-05/edition.md", hashes)

    def test_stale_html_is_rejected(self):
        path = self.edition / "edition.html"
        path.write_text(path.read_text().replace("kalma0", "obsolete0", 1))
        with self.assertRaisesRegex(ValueError, "STALE_PUBLICATION_SOURCE"):
            validate_inputs(self.root, DATE)

    def test_missing_canonical_cover_does_not_choose_other_image(self):
        self.cover.unlink()
        (self.edition / "assets/cover.webp").write_bytes(b"wrong")
        with self.assertRaisesRegex(ValueError, "no filename fallback"):
            validate_inputs(self.root, DATE)

    def test_path_escape_and_noncanonical_dates_rejected(self):
        for value in ("2026-02-30", "20260905", "../../2026-09-05"):
            with self.assertRaises(ValueError): canonical_date(value)
        with self.assertRaises(ValueError): safe_asset(self.root, self.edition, "../secret.svg")

    def test_false_complete_cannot_bypass_depth(self):
        (self.edition / "edition.md").write_text("# DRAGON\n\nShort edition.")
        with self.assertRaisesRegex(ValueError, "depth failed"):
            validate_inputs(self.root, DATE)

    def test_renderer_blocks_network_and_secrets(self):
        failures = []
        fetch = restricted_fetcher(self.edition, failures)
        for url in ("https://example.org/image.png", "file:///etc/passwd"):
            with self.assertRaises(ValueError): fetch(url)
        self.assertEqual(len(failures), 2)

    def test_epub_metadata_cover_and_broken_links(self):
        path = self.edition / "test.epub"
        build_epub(self.edition, self.cover, path, DATE)
        validate_epub(path)
        with zipfile.ZipFile(path) as archive:
            self.assertIn(b"ary-Latn", archive.read("OEBPS/content.opf"))
            self.assertIn(b"dcterms:modified", archive.read("OEBPS/content.opf"))
            self.assertEqual(archive.read("OEBPS/canonical-cover.svg"), self.cover.read_bytes())
            self.assertNotIn("OEBPS/print.css", archive.namelist())
        source = self.edition / "epub-content.xhtml"
        source.write_text(source.read_text().replace('href="https://example.org/evidence"','href="#missing"'))
        build_epub(self.edition, self.cover, path, DATE)
        with self.assertRaisesRegex(ValueError, "unresolved EPUB fragment"):
            validate_epub(path)

    @patch("scripts.publication_renderer.render_pdf", side_effect=fake_pdf)
    def test_local_render_never_claims_publication(self, _):
        receipt = render(self.root, DATE)
        self.assertEqual(receipt["final_publication_status"], "PENDING")
        self.assertEqual(read_json(self.run / "status.json")["final_publication_status"], "PENDING")

    def setup_git(self):
        remote = Path(self.temp.name) / "remote.git"
        subprocess.run(["git","init","--bare",str(remote)], check=True, capture_output=True)
        git(self.root,"init","-b","main")
        git(self.root,"config","core.autocrlf","false")
        git(self.root,"config","user.name","Test")
        git(self.root,"config","user.email","test@example.invalid")
        git(self.root,"add",".")
        git(self.root,"commit","-m","Fixture")
        git(self.root,"remote","add","origin",str(remote))
        git(self.root,"push","-u","origin","main")

    @patch("scripts.publication_renderer.render_pdf", side_effect=fake_pdf)
    def test_git_roundtrip_and_idempotent_retry(self, _):
        self.setup_git()
        self.assertEqual(publish(self.root, DATE), "PUBLISHED")
        state = read_json(self.run / "status.json")
        self.assertEqual(state["overall_status"], "COMPLETE")
        head = git(self.root,"rev-parse","HEAD")
        self.assertEqual(publish(self.root, DATE), "ALREADY_PUBLISHED")
        self.assertEqual(head, git(self.root,"rev-parse","HEAD"))
        self.assertEqual(len(read_json(self.root / "memory/publication-ledger.json")), 1)
        with self.assertRaisesRegex(ValueError, "mismatch"):
            verify_remote(self.root, {str(self.cover.relative_to(self.root)).replace("\\","/"):"0"*64}, head)

    @patch("scripts.publication_renderer.render_pdf", side_effect=fake_pdf)
    def test_push_failure_cannot_mark_complete(self, _):
        self.setup_git()
        git(self.root,"remote","set-url","--push","origin",str(Path(self.temp.name)/"missing.git"))
        with self.assertRaises(RuntimeError): publish(self.root, DATE)
        self.assertEqual(read_json(self.run / "status.json")["final_publication_status"], "PENDING")
        self.assertFalse((self.root / "memory/publication-ledger.json").exists())

    def test_existing_state_cannot_be_reset(self):
        with self.assertRaisesRegex(ValueError, "never reset"):
            initialize_production_run(self.run / "status.json", DATE)

    def test_scheduled_complete_is_not_final_complete(self):
        state = fresh_production_status(DATE)
        state["overall_status"] = "COMPLETE"
        self.assertTrue(any("final_publication_status COMPLETE" in e for e in validate_state(state, DATE)))

    def test_casablanca_date_window_excludes_future_fixtures(self):
        for value in ("2026-09-04","2026-09-06"):
            write_json(self.root / "daily-runs" / value / "status.json", read_json(self.run / "status.json") | {"date":value})
        now = datetime(2026,9,5,0,5,tzinfo=ZoneInfo("Africa/Casablanca"))
        self.assertEqual(list(candidates(self.root, now)), ["2026-09-04",DATE])

    @unittest.skipUnless(os.environ.get("DRAGON_RENDER_SMOKE") == "1", "requires installed WeasyPrint native libraries; enabled in Linux CI")
    def test_real_pdf_epub_render(self):
        receipt = render(self.root, DATE)
        self.assertGreaterEqual(receipt["pdf_pages"], 2)
        self.assertEqual(receipt["structural_validation"], "PASS")

if __name__ == "__main__": unittest.main()
