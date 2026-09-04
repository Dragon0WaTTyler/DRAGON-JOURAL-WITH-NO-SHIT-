#!/usr/bin/env python3
"""Manual final binary publisher for DRAGON production editions.

This script is intentionally NOT part of Scheduled Work. It is designed for a
manual Codex Cloud run after the text-only publication source package exists.
It renders the canonical edition.html + print.css to PDF, prepends the canonical
cover as page 1, packages epub-content.xhtml + the canonical cover as EPUB 3,
validates both binaries, and updates text status/report metadata truthfully.
"""
from __future__ import annotations

import argparse
import base64
import html
import json
import os
import shutil
import subprocess
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree as ET

from pypdf import PdfReader, PdfWriter

try:
    from weasyprint import HTML as WeasyHTML
except ImportError:  # optional until manual binary runtime installs requirements
    WeasyHTML = None

ROOT = Path(__file__).resolve().parents[1]
PDF_OK = "GENERATED_VALIDATED"
EPUB_OK = "GENERATED_VALIDATED"
BINARY_OK = "COMPLETE"


def edition_dir(edition_date: str) -> Path:
    year, month, day = edition_date.split("-")
    if len(year) != 4 or len(month) != 2 or len(day) != 2:
        raise ValueError("date must be YYYY-MM-DD")
    return ROOT / "editions" / year / month / edition_date


def require_file(path: Path) -> Path:
    if not path.is_file() or path.stat().st_size == 0:
        raise FileNotFoundError(f"required non-empty file missing: {path.relative_to(ROOT)}")
    return path


def read_json(path: Path) -> dict:
    return json.loads(require_file(path).read_text(encoding="utf-8"))


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def resolve_cover(manifest: dict, edition: Path) -> Path:
    declared = manifest.get("cover_asset_path")
    candidates: list[Path] = []
    if isinstance(declared, str) and declared.strip():
        declared_path = Path(declared)
        candidates.append(declared_path if declared_path.is_absolute() else ROOT / declared_path)
    candidates.extend(
        [
            edition / "assets" / "cover.webp",
            edition / "assets" / "cover.png",
            edition / "assets" / "cover.jpg",
            edition / "assets" / "cover.jpeg",
            edition / "assets" / "cover.svg",
            edition / "cover.webp",
            edition / "cover.png",
            edition / "cover.jpg",
            edition / "cover.svg",
        ]
    )
    for candidate in candidates:
        if candidate.is_file() and candidate.stat().st_size > 0:
            return candidate.resolve()
    raise FileNotFoundError("no canonical cover asset found")


def cover_is_fallback(manifest: dict, cover: Path) -> bool:
    asset_type = str(manifest.get("cover_asset_type", "")).upper()
    return "FALLBACK" in asset_type or cover.suffix.lower() == ".svg" and asset_type == "SVG_FALLBACK"


def chromium_binary() -> str:
    configured = os.environ.get("DRAGON_CHROMIUM")
    candidates = [configured] if configured else []
    candidates += ["chromium", "chromium-browser", "google-chrome", "google-chrome-stable", "chrome"]
    for candidate in candidates:
        if candidate and shutil.which(candidate):
            return shutil.which(candidate) or candidate
    raise RuntimeError(
        "NO_HTML_TO_PDF_ENGINE: install/enable Chromium in the manual Codex Cloud environment "
        "or set DRAGON_CHROMIUM. Do not substitute a different document source."
    )


def render_html_pdf(source_html: Path, output_pdf: Path) -> None:
    if output_pdf.exists():
        output_pdf.unlink()
    if WeasyHTML is not None:
        WeasyHTML(filename=str(source_html), base_url=str(source_html.parent)).write_pdf(str(output_pdf))
        if output_pdf.is_file() and output_pdf.stat().st_size > 1024:
            return
        raise RuntimeError("WeasyPrint returned without a valid PDF")

    browser = chromium_binary()
    common = [
        browser,
        "--no-sandbox",
        "--disable-gpu",
        "--disable-dev-shm-usage",
        "--allow-file-access-from-files",
        "--no-pdf-header-footer",
        "--virtual-time-budget=1500",
        f"--print-to-pdf={output_pdf}",
        source_html.resolve().as_uri(),
    ]
    attempts = [[browser, "--headless=new", *common[1:]], [browser, "--headless", *common[1:]]]
    errors: list[str] = []
    for command in attempts:
        if output_pdf.exists():
            output_pdf.unlink()
        try:
            result = subprocess.run(command, cwd=source_html.parent, capture_output=True, text=True, timeout=60)
        except subprocess.TimeoutExpired:
            errors.append("timeout")
            continue
        if result.returncode == 0 and output_pdf.is_file() and output_pdf.stat().st_size > 1024:
            return
        errors.append((result.stderr or result.stdout or f"exit {result.returncode}").strip())
    raise RuntimeError("HTML-to-PDF render failed: " + " | ".join(errors[-2:]))


def image_data_uri(path: Path) -> str:
    media = {
        ".webp": "image/webp",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
    }.get(path.suffix.lower())
    if not media:
        raise ValueError(f"unsupported raster cover type: {path.suffix}")
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{media};base64,{encoded}"


def cover_html(cover: Path) -> str:
    if cover.suffix.lower() == ".svg":
        visual = cover.read_text(encoding="utf-8")
    else:
        visual = f'<img src="{image_data_uri(cover)}" alt="DRAGON cover" />'
    return f"""<!doctype html>
<html><head><meta charset="utf-8" />
<style>
@page {{ size: A4 portrait; margin: 0; }}
html,body {{ margin:0; padding:0; width:210mm; height:297mm; overflow:hidden; background:white; }}
.cover {{ width:210mm; height:297mm; display:flex; align-items:stretch; justify-content:stretch; }}
.cover svg,.cover img {{ display:block; width:210mm; height:297mm; object-fit:cover; }}
</style></head><body><div class="cover">{visual}</div></body></html>"""


def body_html(edition_html_text: str, print_css_text: str) -> str:
    style = f"<style id=\"dragon-manual-print-css\">\n{print_css_text}\n</style>"
    marker = "</head>"
    if marker.lower() not in edition_html_text.lower():
        raise ValueError("edition.html has no closing </head>")
    index = edition_html_text.lower().index(marker.lower())
    return edition_html_text[:index] + style + edition_html_text[index:]


def render_pdf(edition: Path, cover: Path, output: Path) -> int:
    edition_html_text = require_file(edition / "edition.html").read_text(encoding="utf-8")
    print_css_text = require_file(edition / "print.css").read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory(prefix="dragon-final-pdf-") as temp_name:
        temp = Path(temp_name)
        cover_source = temp / "cover.html"
        body_source = temp / "edition.html"
        cover_pdf = temp / "cover.pdf"
        body_pdf = temp / "body.pdf"
        cover_source.write_text(cover_html(cover), encoding="utf-8")
        body_source.write_text(body_html(edition_html_text, print_css_text), encoding="utf-8")
        render_html_pdf(cover_source, cover_pdf)
        render_html_pdf(body_source, body_pdf)

        writer = PdfWriter()
        cover_reader = PdfReader(str(cover_pdf))
        body_reader = PdfReader(str(body_pdf))
        if len(cover_reader.pages) != 1:
            raise RuntimeError(f"cover renderer produced {len(cover_reader.pages)} pages; expected exactly 1")
        if len(body_reader.pages) < 1:
            raise RuntimeError("edition renderer produced zero pages")
        writer.add_page(cover_reader.pages[0])
        for page in body_reader.pages:
            writer.add_page(page)
        with output.open("wb") as handle:
            writer.write(handle)

    reader = PdfReader(str(require_file(output)))
    if len(reader.pages) < 2:
        raise RuntimeError("final PDF validation failed: expected cover + body")
    return len(reader.pages)


def epub_cover_media_type(cover: Path) -> tuple[str, str]:
    mapping = {
        ".svg": ("image/svg+xml", "cover.svg"),
        ".webp": ("image/webp", "cover.webp"),
        ".png": ("image/png", "cover.png"),
        ".jpg": ("image/jpeg", "cover.jpg"),
        ".jpeg": ("image/jpeg", "cover.jpg"),
    }
    try:
        return mapping[cover.suffix.lower()]
    except KeyError as exc:
        raise ValueError(f"unsupported EPUB cover type: {cover.suffix}") from exc


def build_epub(edition: Path, cover: Path, output: Path, edition_date: str) -> None:
    source_xhtml = require_file(edition / "epub-content.xhtml").read_text(encoding="utf-8")
    css = require_file(edition / "print.css").read_text(encoding="utf-8")
    media_type, cover_name = epub_cover_media_type(cover)
    title = f"DRAGON Daily Newspaper - {edition_date}"
    escaped_title = html.escape(title)
    cover_page = f'''<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml"><head><title>{escaped_title} cover</title><style>html,body{{margin:0;padding:0}}img{{display:block;max-width:100%;height:auto;margin:auto}}</style></head><body><img src="{cover_name}" alt="DRAGON cover" /></body></html>'''
    nav = f'''<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"><head><title>{escaped_title} contents</title></head><body><nav epub:type="toc"><h1>Contents</h1><ol><li><a href="cover.xhtml">Cover</a></li><li><a href="edition.xhtml">Edition</a></li></ol></nav></body></html>'''
    opf = f'''<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="pub-id"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="pub-id">dragon-{edition_date}</dc:identifier><dc:title>{escaped_title}</dc:title><dc:language>zgh-Latn</dc:language><dc:creator>DRAGON Editorial Desk</dc:creator><dc:date>{edition_date}</dc:date><meta name="cover" content="cover-image"/></metadata><manifest><item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/><item id="cover-image" href="{cover_name}" media-type="{media_type}" properties="cover-image"/><item id="cover-page" href="cover.xhtml" media-type="application/xhtml+xml"/><item id="edition" href="edition.xhtml" media-type="application/xhtml+xml"/><item id="style" href="print.css" media-type="text/css"/></manifest><spine><itemref idref="cover-page"/><itemref idref="edition"/></spine></package>'''
    container_xml = '''<?xml version="1.0" encoding="utf-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>'''

    if output.exists():
        output.unlink()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("mimetype", b"application/epub+zip", compress_type=zipfile.ZIP_STORED)
        archive.writestr("META-INF/container.xml", container_xml.encode("utf-8"))
        archive.writestr("OEBPS/content.opf", opf.encode("utf-8"))
        archive.writestr("OEBPS/nav.xhtml", nav.encode("utf-8"))
        archive.writestr("OEBPS/cover.xhtml", cover_page.encode("utf-8"))
        archive.writestr("OEBPS/edition.xhtml", source_xhtml.encode("utf-8"))
        archive.writestr("OEBPS/print.css", css.encode("utf-8"))
        archive.writestr(f"OEBPS/{cover_name}", cover.read_bytes())


def validate_epub(path: Path) -> None:
    require_file(path)
    with zipfile.ZipFile(path, "r") as archive:
        names = archive.namelist()
        required = {
            "mimetype",
            "META-INF/container.xml",
            "OEBPS/content.opf",
            "OEBPS/nav.xhtml",
            "OEBPS/cover.xhtml",
            "OEBPS/edition.xhtml",
        }
        missing = sorted(required - set(names))
        if missing:
            raise RuntimeError("EPUB validation missing: " + ", ".join(missing))
        first = archive.infolist()[0]
        if first.filename != "mimetype" or first.compress_type != zipfile.ZIP_STORED:
            raise RuntimeError("EPUB validation failed: mimetype must be first and uncompressed")
        if archive.read("mimetype") != b"application/epub+zip":
            raise RuntimeError("EPUB validation failed: invalid mimetype")
        for name in ["META-INF/container.xml", "OEBPS/content.opf", "OEBPS/nav.xhtml", "OEBPS/cover.xhtml", "OEBPS/edition.xhtml"]:
            ET.fromstring(archive.read(name))


def update_metadata(edition: Path, edition_date: str, cover: Path, pdf: Path, epub: Path, pages: int, fallback: bool) -> None:
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    pdf_rel = str(pdf.relative_to(ROOT)).replace("\\", "/")
    epub_rel = str(epub.relative_to(ROOT)).replace("\\", "/")
    cover_rel = str(cover.relative_to(ROOT)).replace("\\", "/")

    manifest_path = edition / "manifest.json"
    manifest = read_json(manifest_path)
    manifest.update(
        {
            "pdf_binary": PDF_OK,
            "epub_binary": EPUB_OK,
            "binary_artifacts": BINARY_OK,
            "ready_for_codex_rendering": False,
            "final_publication_status": "COMPLETE_WITH_SVG_FALLBACK" if fallback else "COMPLETE",
            "final_binary_paths": {"pdf": pdf_rel, "epub": epub_rel},
            "final_cover_path": cover_rel,
            "binary_validation": {"pdf_pages": pages, "pdf_readable": True, "epub_structure": "PASS", "epub_xml": "PASS"},
            "manual_binary_render_completed_at": now,
        }
    )
    write_json(manifest_path, manifest)

    report_path = ROOT / "daily-runs" / edition_date / "publishing-report.json"
    if report_path.is_file():
        report = read_json(report_path)
        report.update(
            {
                "pdf_binary": PDF_OK,
                "epub_binary": EPUB_OK,
                "binary_artifacts": BINARY_OK,
                "ready_for_codex_rendering": False,
                "final_publication_status": "COMPLETE_WITH_SVG_FALLBACK" if fallback else "COMPLETE",
                "final_binary_paths": {"pdf": pdf_rel, "epub": epub_rel},
                "binary_validation": {"pdf_pages": pages, "pdf_readable": True, "epub_structure": "PASS", "epub_xml": "PASS"},
                "manual_binary_render_completed_at": now,
            }
        )
        write_json(report_path, report)

    status_path = ROOT / "daily-runs" / edition_date / "status.json"
    if status_path.is_file():
        status = read_json(status_path)
        status.update(
            {
                "pdf_binary": PDF_OK,
                "epub_binary": EPUB_OK,
                "binary_artifacts": BINARY_OK,
                "ready_for_codex_rendering": False,
                "final_publication_status": "COMPLETE_WITH_SVG_FALLBACK" if fallback else "COMPLETE",
                "final_binary_paths": {"pdf": pdf_rel, "epub": epub_rel},
                "manual_binary_render_completed_at": now,
            }
        )
        write_json(status_path, status)


def main() -> None:
    parser = argparse.ArgumentParser(description="Render and validate final DRAGON PDF/EPUB binaries in a manual runtime")
    parser.add_argument("--date", required=True, help="Edition date YYYY-MM-DD")
    parser.add_argument(
        "--allow-svg-fallback",
        action="store_true",
        help="Allow a historical SVG_FALLBACK cover. Without this flag, fallback covers block final publication.",
    )
    args = parser.parse_args()

    edition = edition_dir(args.date)
    require_file(edition / "edition.html")
    require_file(edition / "print.css")
    require_file(edition / "epub-content.xhtml")
    manifest = read_json(edition / "manifest.json")
    if manifest.get("publication_source_package") != "COMPLETE" and manifest.get("ready_for_codex_rendering") is not True:
        raise RuntimeError("publication source package is not marked ready")

    cover = resolve_cover(manifest, edition)
    fallback = cover_is_fallback(manifest, cover)
    if fallback and not args.allow_svg_fallback:
        raise RuntimeError(
            "COVER_POLICY_BLOCK: canonical cover is SVG_FALLBACK, not a successful generated cover. "
            "Fix/regenerate the cover first, or use --allow-svg-fallback only for an explicit historical repair."
        )

    pdf = edition / f"dragon-{args.date}.pdf"
    epub = edition / f"dragon-{args.date}.epub"
    pages = render_pdf(edition, cover, pdf)
    build_epub(edition, cover, epub, args.date)
    validate_epub(epub)
    update_metadata(edition, args.date, cover, pdf, epub, pages, fallback)
    print(json.dumps({"date": args.date, "pdf": str(pdf.relative_to(ROOT)), "pdf_pages": pages, "epub": str(epub.relative_to(ROOT)), "cover": str(cover.relative_to(ROOT)), "fallback_cover": fallback, "status": "PASS"}, indent=2))


if __name__ == "__main__":
    main()
