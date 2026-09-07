"""Canonical Arabic HTML, PDF, and EPUB publication builders and validators."""

from __future__ import annotations

from html import escape
import json
import os
from pathlib import Path
import re
from xml.etree import ElementTree
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

from pypdf import PdfReader, PdfWriter
from pypdf.generic import RectangleObject
from dragon.language import decode_utf8, validate_arabic_text, validate_html_rtl, validate_xhtml_rtl
from dragon.state import sha256_file


def _article_markup(article: dict) -> str:
    paragraphs = "".join(f"<p>{escape(value)}</p>" for value in article["body"])
    sources = "".join(
        f'<li><a href="{escape(url, quote=True)}">{escape(url)}</a></li>'
        for url in article.get("source_urls", [])
    )
    return (
        f'<article id="{escape(article["id"])}">'
        f'<p class="section">{escape(article["section"])}</p>'
        f'<h2>{escape(article["headline"])}</h2>'
        f'<p class="standfirst">{escape(article["standfirst"])}</p>'
        f'<p class="byline">{escape(article["byline"])}</p>{paragraphs}'
        f'<div class="source"><p>المصادر</p><ul>{sources}</ul></div></article>'
    )


def build_cover_png(
    destination: Path,
    edition_date: str,
    headline: str,
    standfirst: str,
    *,
    mode: str = "production",
) -> Path:
    """Build the one canonical cover image consumed by every output format."""
    from PIL import Image, ImageDraw

    size = (827, 1169)
    cover = Image.new("RGB", size, "#f5efe3")
    draw = ImageDraw.Draw(cover)
    draw.rectangle((42, 42, 785, 1127), outline="#111111", width=3)
    draw.rectangle((42, 42, 785, 66), fill="#9e1523")
    draw.text((413, 185), "DRAGON", font=_font(82), fill="#111111", anchor="mm")
    _draw_rtl(draw, (735, 305), headline, _font(42), fill="#111111", spacing=57, width=645)
    draw.line((92, 495, 735, 495), fill="#9e1523", width=6)
    _draw_rtl(draw, (735, 550), standfirst, _font(24), fill="#222222", spacing=38, width=645)
    label = "نسخة اختبار اصطناعية" if mode == "synthetic" else "النسخة اليومية"
    footer = "غير مخصصة للنشر أو التوزيع" if mode == "synthetic" else "صحافة عربية مستقلة"
    _draw_rtl(draw, (735, 880), label, _font(25), fill="#9e1523", spacing=38, width=645)
    draw.text((413, 955), edition_date, font=_font(22), fill="#333333", anchor="mm")
    _draw_rtl(draw, (735, 1050), footer, _font(17), fill="#333333", spacing=28, width=645)
    destination.parent.mkdir(parents=True, exist_ok=True)
    cover.save(destination, "PNG", optimize=True)
    cover.close()
    return destination


PRINT_CSS = """
@page { size: A4; margin: 15mm; }
@page:first { margin: 0; }
html, body { direction: rtl; font-family: Tahoma, Arial, sans-serif; color: #111; }
body { margin: 0; }
.cover { page: cover; break-after: page; height: 297mm; }
.cover img { width: 210mm; height: 297mm; object-fit: cover; }
.content { padding: 0; }
.masthead { border-bottom: 4px solid #9e1523; margin-bottom: 8mm; }
.brand { direction: ltr; font: 800 26pt Arial; letter-spacing: .08em; }
article { break-before: page; }
h1, h2, .standfirst, .byline, .section { break-after: avoid; text-align: right; }
h2 { font-size: 24pt; line-height: 1.35; }
.section { color: #9e1523; font-weight: bold; }
p { font-size: 12pt; line-height: 1.8; orphans: 3; widows: 3; text-align: right; }
.source { border-top: 1px solid #aaa; padding-top: 3mm; font-size: 9pt; }
a { color: #333; overflow-wrap: anywhere; }
"""


def build_html(edition_dir: Path, edition_date: str, articles: list[dict], *, mode: str = "production") -> Path:
    assets = edition_dir / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    (edition_dir / "print-v5.css").write_text(PRINT_CSS, encoding="utf-8", newline="\n")
    article_html = "".join(_article_markup(article) for article in articles)
    document = f'''<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"/>
<meta name="date" content="{edition_date}"/><title>DRAGON — {edition_date}</title>
<link rel="stylesheet" href="print-v5.css"/></head><body dir="rtl">
<section class="cover"><img src="assets/cover.png" alt="غلاف صحيفة دراغون"/></section>
<main class="content"><header class="masthead"><p class="brand" lang="en" dir="ltr">DRAGON</p>
<h1>{'نسخة اختبار اصطناعية' if mode == 'synthetic' else 'النسخة اليومية'}</h1><time datetime="{edition_date}" dir="ltr">{edition_date}</time></header>
{article_html}</main></body></html>'''
    path = edition_dir / "edition.html"
    path.write_text(document, encoding="utf-8", newline="\n")
    return path


def validate_publication_source(document: str, articles: list[dict]) -> list[str]:
    issues = validate_html_rtl(document)
    for article in articles:
        article_id = article.get("id")
        if not article_id or f'id="{escape(str(article_id), quote=True)}"' not in document:
            issues.append(f"HTML_ARTICLE_MISSING:{article_id}")
        source_urls = article.get("source_urls")
        if not isinstance(source_urls, list) or not source_urls:
            issues.append(f"HTML_SOURCES_MISSING:{article_id}")
            continue
        for url in source_urls:
            if f'href="{escape(str(url), quote=True)}"' not in document:
                issues.append(f"HTML_SOURCE_LINK_MISSING:{article_id}:{url}")
    if 'src="assets/cover.png"' not in document:
        issues.append("HTML_CANONICAL_COVER_MISSING")
    return issues


def _font(size: int):
    from PIL import ImageFont

    candidates = (
        Path("C:/Windows/Fonts/tahoma.ttf"),
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("C:/Windows/Fonts/segoeui.ttf"),
    )
    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size)
    return ImageFont.load_default(size=size)


def _rtl_lines(draw, text: str, font, width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        try:
            measured = draw.textlength(_visual_arabic(candidate), font=font)
        except ValueError:
            measured = 0
        if measured <= width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _visual_arabic(text: str) -> str:
    import arabic_reshaper
    from bidi.algorithm import get_display

    return get_display(arabic_reshaper.reshape(text))


def _draw_rtl(draw, xy: tuple[int, int], text: str, font, *, fill: str, spacing: int, width: int) -> int:
    x, y = xy
    for line in _rtl_lines(draw, text, font, width):
        draw.text((x, y), _visual_arabic(line), font=font, fill=fill, anchor="ra")
        y += spacing
    return y


def _ltr_lines(draw, text: str, font, width: int) -> list[str]:
    lines: list[str] = []
    remaining = text
    while remaining:
        low, high = 1, len(remaining)
        while low < high:
            middle = (low + high + 1) // 2
            if draw.textlength(remaining[:middle], font=font) <= width:
                low = middle
            else:
                high = middle - 1
        lines.append(remaining[:low])
        remaining = remaining[low:]
    return lines


def _render_pdf_pillow(html_path: Path, destination: Path) -> None:
    """Portable Windows renderer with explicit Arabic shaping and bidi."""
    from PIL import Image, ImageDraw

    articles_path = html_path.with_name("articles.json")
    article_data = json.loads(articles_path.read_text(encoding="utf-8"))
    mode = article_data.get("mode", "production")
    articles = [item for item in article_data["articles"] if item["status"] == "ACTIVE"]
    edition_date = html_path.parent.name
    size = (827, 1169)
    pages = []
    page_links: list[list[tuple[str, int]]] = [[]]
    with Image.open(html_path.parent / "assets" / "cover.png") as source_cover:
        cover = source_cover.convert("RGB").resize(size)
    pages.append(cover)
    def new_content_page():
        page = Image.new("RGB", size, "white")
        draw = ImageDraw.Draw(page)
        draw.rectangle((45, 45, 782, 1124), outline="#d2d2d2", width=2)
        return page, draw

    for article in articles:
        page, draw = new_content_page()
        links: list[tuple[str, int]] = []
        y = 85
        y = _draw_rtl(draw, (750, y), article["section"], _font(19), fill="#9e1523", spacing=30, width=675)
        y += 10
        y = _draw_rtl(draw, (750, y), article["headline"], _font(32), fill="#111111", spacing=44, width=675)
        y += 10
        y = _draw_rtl(draw, (750, y), article["standfirst"], _font(20), fill="#333333", spacing=32, width=675)
        y += 12
        y = _draw_rtl(draw, (750, y), article["byline"], _font(16), fill="#555555", spacing=25, width=675)
        draw.line((75, y + 5, 750, y + 5), fill="#9e1523", width=3)
        y += 30
        for paragraph in article["body"]:
            font = _font(18)
            lines = _rtl_lines(draw, paragraph, font, 675)
            for line in lines:
                if y + 29 > 1030:
                    pages.append(page)
                    page_links.append(links)
                    page, draw = new_content_page()
                    links = []
                    y = 85
                    y = _draw_rtl(
                        draw,
                        (750, y),
                        article["headline"] + " — تابع",
                        _font(18),
                        fill="#9e1523",
                        spacing=29,
                        width=675,
                    )
                    draw.line((75, y + 3, 750, y + 3), fill="#d2d2d2", width=2)
                    y += 20
                draw.text(
                    (750, y),
                    _visual_arabic(line),
                    font=font,
                    fill="#111111",
                    anchor="ra",
                )
                y += 29
            y += 18
        if y + 75 > 1070:
            pages.append(page)
            page_links.append(links)
            page, draw = new_content_page()
            links = []
            y = 85
        source_y = _draw_rtl(
            draw,
            (750, min(y + 5, 1035)),
            "المصادر:",
            _font(13),
            fill="#555555",
            spacing=20,
            width=675,
        )
        for url in article.get("source_urls", []):
            font = _font(11)
            for line in _ltr_lines(draw, url, font, 675):
                if source_y + 18 > 1090:
                    pages.append(page)
                    page_links.append(links)
                    page, draw = new_content_page()
                    links = []
                    source_y = 85
                draw.text((750, source_y), line, font=font, fill="#555555", anchor="ra")
                links.append((str(url), source_y))
                source_y += 18
        pages.append(page)
        page_links.append(links)
    first, rest = pages[0], pages[1:]
    subject = "synthetic acceptance fixture" if mode == "synthetic" else "Arabic daily newspaper"
    raster_destination = destination.with_name(f".{destination.name}.raster.pdf")
    linked_destination = destination.with_name(f".{destination.name}.linked.pdf")
    try:
        first.save(raster_destination, "PDF", resolution=110.0, save_all=True, append_images=rest, title=f"DRAGON {edition_date}", author="DRAGON", subject=subject, creator="DRAGON Pillow RTL renderer")
        reader = PdfReader(str(raster_destination))
        writer = PdfWriter()
        writer.clone_document_from_reader(reader)
        x_scale = float(reader.pages[0].mediabox.width) / size[0]
        y_scale = float(reader.pages[0].mediabox.height) / size[1]
        for page_number, links_for_page in enumerate(page_links):
            for url, top in links_for_page:
                writer.add_uri(
                    page_number,
                    url,
                    RectangleObject(
                        (
                            75 * x_scale,
                            (size[1] - (top + 18)) * y_scale,
                            750 * x_scale,
                            (size[1] - top) * y_scale,
                        )
                    ),
                )
        with linked_destination.open("wb") as stream:
            writer.write(stream)
        if len(PdfReader(str(linked_destination)).pages) != len(pages):
            raise ValueError("linked PDF page count changed")
        os.replace(linked_destination, destination)
    finally:
        raster_destination.unlink(missing_ok=True)
        linked_destination.unlink(missing_ok=True)
        for page in pages:
            page.close()


def render_pdf(html_path: Path, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if __import__("os").name == "nt":
        _render_pdf_pillow(html_path, destination)
    else:
        from weasyprint import HTML

        HTML(filename=str(html_path)).write_pdf(destination)
    return destination


def _xhtml(edition_date: str, articles: list[dict], *, mode: str) -> str:
    body = "".join(_article_markup(article) for article in articles)
    return f'''<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" lang="ar" xml:lang="ar" dir="rtl">
<head><title>DRAGON — {edition_date}</title><link rel="stylesheet" type="text/css" href="style.css"/></head>
<body><header><h1>{'نسخة اختبار اصطناعية' if mode == 'synthetic' else 'النسخة اليومية'}</h1><p>{edition_date}</p></header>{body}</body></html>'''


def build_epub(destination: Path, edition_date: str, articles: list[dict], cover_path: Path, *, mode: str = "production") -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    identifier = f"urn:dragon:{mode}:{edition_date}"
    container = '''<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>'''
    package = f'''<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid" xml:lang="ar" dir="rtl" page-progression-direction="rtl">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="bookid">{identifier}</dc:identifier><dc:title>DRAGON — {edition_date}</dc:title><dc:language>ar</dc:language><dc:creator>DRAGON</dc:creator><meta property="dcterms:modified">{edition_date}T07:00:00Z</meta><meta name="cover" content="cover-image"/></metadata>
<manifest><item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/><item id="edition" href="edition.xhtml" media-type="application/xhtml+xml"/><item id="css" href="style.css" media-type="text/css"/><item id="cover-image" href="cover.png" media-type="image/png" properties="cover-image"/></manifest>
<spine page-progression-direction="rtl"><itemref idref="edition"/></spine></package>'''
    nav = '''<?xml version="1.0" encoding="utf-8"?><html xmlns="http://www.w3.org/1999/xhtml" lang="ar" xml:lang="ar" dir="rtl"><head><title>الفهرس</title></head><body><nav epub:type="toc" xmlns:epub="http://www.idpf.org/2007/ops"><h1>الفهرس</h1><ol><li><a href="edition.xhtml">النسخة الكاملة</a></li></ol></nav></body></html>'''
    css = "html,body{direction:rtl;font-family:serif;line-height:1.7} article{break-before:page} h1,h2,p{text-align:right}.section{font-weight:bold}"
    with ZipFile(destination, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip", compress_type=ZIP_STORED)
        archive.writestr("META-INF/container.xml", container, compress_type=ZIP_DEFLATED)
        archive.writestr("OEBPS/content.opf", package, compress_type=ZIP_DEFLATED)
        archive.writestr("OEBPS/nav.xhtml", nav, compress_type=ZIP_DEFLATED)
        archive.writestr("OEBPS/edition.xhtml", _xhtml(edition_date, articles, mode=mode), compress_type=ZIP_DEFLATED)
        archive.writestr("OEBPS/style.css", css, compress_type=ZIP_DEFLATED)
        archive.write(cover_path, "OEBPS/cover.png", compress_type=ZIP_DEFLATED)
    return destination


def validate_pdf(
    path: Path,
    *,
    minimum_pages: int = 2,
    canonical_cover: Path | None = None,
    expected_source_urls: tuple[str, ...] = (),
) -> dict:
    issues: list[str] = []
    try:
        reader = PdfReader(str(path))
        pages = len(reader.pages)
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as exc:
        return {"status": "FAIL", "issues": [f"PDF_OPEN_FAILED:{exc}"]}
    if pages < minimum_pages:
        issues.append(f"PDF_PAGE_COUNT_LOW:{pages}")
    if path.stat().st_size < 10_000:
        issues.append("PDF_FILE_TOO_SMALL")
    cover_rms = None
    if canonical_cover is not None:
        try:
            from PIL import Image, ImageChops, ImageStat

            if len(reader.pages[0].images) != 1:
                raise ValueError("first page must contain exactly one canonical image")
            with Image.open(canonical_cover) as source:
                expected_cover = source.convert("RGB")
            actual_cover = reader.pages[0].images[0].image.convert("RGB")
            if actual_cover.size != expected_cover.size:
                raise ValueError(
                    f"cover dimensions differ: {actual_cover.size} != {expected_cover.size}"
                )
            cover_rms = max(
                ImageStat.Stat(ImageChops.difference(expected_cover, actual_cover)).rms
            )
            if cover_rms > 8:
                raise ValueError(f"cover visual RMS {cover_rms:.3f} exceeds 8")
        except Exception as exc:
            issues.append(f"PDF_CANONICAL_COVER_MISMATCH:{exc}")
    if text.strip():
        qa = validate_arabic_text(text, minimum_arabic_letters=50, allowed_latin_terms=("DRAGON",))
        issues.extend(qa.issues)
        language = qa.to_dict()
        extraction = "AVAILABLE"
    else:
        language = {"status": "NOT_APPLICABLE", "reason": "raster PDF; Arabic validated at canonical source and visual renderer inputs"}
        extraction = "UNAVAILABLE_RASTER"
    populated_pages = 0
    linked_urls: set[str] = set()
    for page in reader.pages:
        resources = page.get("/Resources") or {}
        if page.extract_text().strip() or resources.get("/XObject"):
            populated_pages += 1
        for annotation_reference in page.get("/Annots", []):
            annotation = annotation_reference.get_object()
            action = annotation.get("/A") or {}
            uri = action.get("/URI")
            if uri:
                linked_urls.add(str(uri))
    if populated_pages != pages:
        issues.append(f"PDF_BLANK_PAGES:{pages - populated_pages}")
    for url in expected_source_urls:
        if url not in linked_urls:
            issues.append(f"PDF_SOURCE_LINK_MISSING:{url}")
    return {
        "status": "PASS" if not issues else "FAIL",
        "pages": pages,
        "populated_pages": populated_pages,
        "bytes": path.stat().st_size,
        "text_extraction": extraction,
        "language": language,
        "canonical_cover_sha256": sha256_file(canonical_cover) if canonical_cover else None,
        "cover_visual_rms": round(cover_rms, 4) if cover_rms is not None else None,
        "source_links": len(linked_urls),
        "issues": issues,
    }


def validate_epub(
    path: Path,
    *,
    canonical_cover: Path | None = None,
    expected_article_ids: tuple[str, ...] = (),
    expected_source_urls: tuple[str, ...] = (),
) -> dict:
    issues: list[str] = []
    required = {"mimetype", "META-INF/container.xml", "OEBPS/content.opf", "OEBPS/nav.xhtml", "OEBPS/edition.xhtml", "OEBPS/cover.png"}
    try:
        with ZipFile(path) as archive:
            names = set(archive.namelist())
            missing = sorted(required - names)
            if missing:
                issues.append("EPUB_MEMBERS_MISSING:" + ",".join(missing))
            if archive.namelist()[0] != "mimetype" or archive.getinfo("mimetype").compress_type != ZIP_STORED:
                issues.append("EPUB_MIMETYPE_INVALID")
            package = decode_utf8(archive.read("OEBPS/content.opf"))
            xhtml = decode_utf8(archive.read("OEBPS/edition.xhtml"))
            if canonical_cover is not None and archive.read("OEBPS/cover.png") != canonical_cover.read_bytes():
                issues.append("EPUB_CANONICAL_COVER_MISMATCH")
            for article_id in expected_article_ids:
                if f'id="{article_id}"' not in xhtml:
                    issues.append(f"EPUB_ARTICLE_MISSING:{article_id}")
            for url in expected_source_urls:
                if f'href="{escape(url, quote=True)}"' not in xhtml:
                    issues.append(f"EPUB_SOURCE_LINK_MISSING:{url}")
            ElementTree.fromstring(package)
            issues.extend(validate_xhtml_rtl(xhtml))
            if "page-progression-direction=\"rtl\"" not in package or "<dc:language>ar</dc:language>" not in package:
                issues.append("EPUB_RTL_METADATA_INVALID")
            text = re.sub(r"<[^>]+>", " ", xhtml)
            language = validate_arabic_text(text, minimum_arabic_letters=50, allowed_latin_terms=("DRAGON",))
            issues.extend(language.issues)
    except Exception as exc:
        return {"status": "FAIL", "issues": [f"EPUB_OPEN_FAILED:{exc}"]}
    return {
        "status": "PASS" if not issues else "FAIL",
        "bytes": path.stat().st_size,
        "canonical_cover_sha256": sha256_file(canonical_cover) if canonical_cover else None,
        "article_count": len(expected_article_ids),
        "language": language.to_dict(),
        "issues": issues,
    }


def artifact_manifest(paths: list[Path], root: Path, *, mode: str) -> dict:
    return {"mode": mode, "artifacts": [{"path": str(path.relative_to(root)).replace("\\", "/"), "sha256": sha256_file(path), "bytes": path.stat().st_size} for path in paths]}
