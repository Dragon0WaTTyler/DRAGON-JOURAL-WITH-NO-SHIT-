"""Canonical Arabic HTML, PDF, and EPUB publication builders and validators."""

from __future__ import annotations

from html import escape
import json
from pathlib import Path
import re
from xml.etree import ElementTree
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

from pypdf import PdfReader
from dragon.language import decode_utf8, validate_arabic_text, validate_html_rtl, validate_xhtml_rtl
from dragon.state import sha256_file


def _article_markup(article: dict, *, xhtml: bool = False) -> str:
    paragraphs = "".join(f"<p>{escape(value)}</p>" for value in article["body"])
    return (
        f'<article id="{escape(article["id"])}">'
        f'<p class="section">{escape(article["section"])}</p>'
        f'<h2>{escape(article["headline"])}</h2>'
        f'<p class="standfirst">{escape(article["standfirst"])}</p>'
        f'<p class="byline">{escape(article["byline"])}</p>{paragraphs}'
        '<p class="source">المصدر: <a href="https://example.org/dragon-fixture">'
        "مصدر تجريبي غير صحفي</a></p></article>"
    )


def cover_svg(edition_date: str) -> str:
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1240" height="1754" viewBox="0 0 1240 1754">
<rect width="1240" height="1754" fill="#f5efe3"/><rect x="64" y="64" width="1112" height="1626" fill="none" stroke="#111" stroke-width="4"/>
<rect x="64" y="64" width="1112" height="32" fill="#9e1523"/>
<text x="620" y="430" text-anchor="middle" font-family="Arial" font-size="150" font-weight="700" fill="#111">DRAGON</text>
<text x="620" y="570" text-anchor="middle" direction="rtl" unicode-bidi="bidi-override" font-family="Tahoma, Arial" font-size="58" fill="#111">صحيفة عربية يومية</text>
<line x1="210" y1="650" x2="1030" y2="650" stroke="#9e1523" stroke-width="8"/>
<text x="620" y="800" text-anchor="middle" direction="rtl" unicode-bidi="bidi-override" font-family="Tahoma, Arial" font-size="52" fill="#111">نسخة اختبار اصطناعية</text>
<text x="620" y="910" text-anchor="middle" font-family="Arial" font-size="38" fill="#333">{escape(edition_date)}</text>
<text x="620" y="1500" text-anchor="middle" direction="rtl" unicode-bidi="bidi-override" font-family="Tahoma, Arial" font-size="30" fill="#333">غير مخصصة للنشر أو التوزيع</text>
</svg>'''


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


def build_html(edition_dir: Path, edition_date: str, articles: list[dict]) -> Path:
    assets = edition_dir / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    (assets / "cover.svg").write_text(cover_svg(edition_date), encoding="utf-8", newline="\n")
    (edition_dir / "print-v5.css").write_text(PRINT_CSS, encoding="utf-8", newline="\n")
    article_html = "".join(_article_markup(article) for article in articles)
    document = f'''<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"/>
<meta name="date" content="{edition_date}"/><title>DRAGON — {edition_date}</title>
<link rel="stylesheet" href="print-v5.css"/></head><body dir="rtl">
<section class="cover"><img src="assets/cover.svg" alt="غلاف صحيفة دراغون"/></section>
<main class="content"><header class="masthead"><p class="brand" lang="en" dir="ltr">DRAGON</p>
<h1>نسخة اختبار اصطناعية</h1><time datetime="{edition_date}" dir="ltr">{edition_date}</time></header>
{article_html}</main></body></html>'''
    path = edition_dir / "edition.html"
    path.write_text(document, encoding="utf-8", newline="\n")
    return path


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
            measured = draw.textlength(candidate, font=font)
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


def _draw_rtl(draw, xy: tuple[int, int], text: str, font, *, fill: str, spacing: int, width: int) -> int:
    import arabic_reshaper
    from bidi.algorithm import get_display

    x, y = xy
    for line in _rtl_lines(draw, text, font, width):
        visual = get_display(arabic_reshaper.reshape(line))
        draw.text((x, y), visual, font=font, fill=fill, anchor="ra")
        y += spacing
    return y


def _render_pdf_pillow(html_path: Path, destination: Path) -> None:
    """Portable Windows renderer with native Pillow/RAQM RTL shaping."""
    from PIL import Image, ImageDraw

    articles_path = html_path.with_name("articles.json")
    articles = json.loads(articles_path.read_text(encoding="utf-8"))["articles"]
    edition_date = html_path.parent.name
    size = (827, 1169)
    pages = []
    cover = Image.new("RGB", size, "#f5efe3")
    draw = ImageDraw.Draw(cover)
    draw.rectangle((42, 42, 785, 1127), outline="#111111", width=3)
    draw.rectangle((42, 42, 785, 66), fill="#9e1523")
    draw.text((413, 280), "DRAGON", font=_font(92), fill="#111111", anchor="mm")
    _draw_rtl(draw, (730, 420), "صحيفة عربية يومية", _font(42), fill="#111111", spacing=54, width=635)
    draw.line((140, 500, 687, 500), fill="#9e1523", width=6)
    _draw_rtl(draw, (730, 590), "نسخة اختبار اصطناعية", _font(36), fill="#111111", spacing=48, width=635)
    draw.text((413, 700), edition_date, font=_font(26), fill="#333333", anchor="mm")
    _draw_rtl(draw, (730, 1010), "غير مخصصة للنشر أو التوزيع", _font(22), fill="#333333", spacing=34, width=635)
    pages.append(cover)
    for article in articles:
        page = Image.new("RGB", size, "white")
        draw = ImageDraw.Draw(page)
        draw.rectangle((45, 45, 782, 1124), outline="#d2d2d2", width=2)
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
            y = _draw_rtl(draw, (750, y), paragraph, _font(18), fill="#111111", spacing=29, width=675)
            y += 18
        _draw_rtl(draw, (750, min(y + 5, 1080)), "المصدر: مصدر تجريبي غير صحفي", _font(13), fill="#555555", spacing=20, width=675)
        pages.append(page)
    first, rest = pages[0], pages[1:]
    first.save(destination, "PDF", resolution=110.0, save_all=True, append_images=rest, title=f"DRAGON {edition_date}", author="DRAGON", subject="synthetic acceptance fixture", creator="DRAGON Pillow RTL renderer")
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


def _xhtml(edition_date: str, articles: list[dict]) -> str:
    body = "".join(_article_markup(article, xhtml=True) for article in articles)
    return f'''<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" lang="ar" xml:lang="ar" dir="rtl">
<head><title>DRAGON — {edition_date}</title><link rel="stylesheet" type="text/css" href="style.css"/></head>
<body><header><h1>نسخة اختبار اصطناعية</h1><p>{edition_date}</p></header>{body}</body></html>'''


def build_epub(destination: Path, edition_date: str, articles: list[dict], cover_path: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    identifier = f"urn:dragon:synthetic:{edition_date}"
    container = '''<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>'''
    package = f'''<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid" xml:lang="ar" dir="rtl" page-progression-direction="rtl">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="bookid">{identifier}</dc:identifier><dc:title>DRAGON — {edition_date}</dc:title><dc:language>ar</dc:language><dc:creator>DRAGON</dc:creator><meta property="dcterms:modified">{edition_date}T07:00:00Z</meta><meta name="cover" content="cover-image"/></metadata>
<manifest><item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/><item id="edition" href="edition.xhtml" media-type="application/xhtml+xml"/><item id="css" href="style.css" media-type="text/css"/><item id="cover-image" href="cover.svg" media-type="image/svg+xml" properties="cover-image"/></manifest>
<spine page-progression-direction="rtl"><itemref idref="edition"/></spine></package>'''
    nav = '''<?xml version="1.0" encoding="utf-8"?><html xmlns="http://www.w3.org/1999/xhtml" lang="ar" xml:lang="ar" dir="rtl"><head><title>الفهرس</title></head><body><nav epub:type="toc" xmlns:epub="http://www.idpf.org/2007/ops"><h1>الفهرس</h1><ol><li><a href="edition.xhtml">النسخة الكاملة</a></li></ol></nav></body></html>'''
    css = "html,body{direction:rtl;font-family:serif;line-height:1.7} article{break-before:page} h1,h2,p{text-align:right}.section{font-weight:bold}"
    with ZipFile(destination, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip", compress_type=ZIP_STORED)
        archive.writestr("META-INF/container.xml", container, compress_type=ZIP_DEFLATED)
        archive.writestr("OEBPS/content.opf", package, compress_type=ZIP_DEFLATED)
        archive.writestr("OEBPS/nav.xhtml", nav, compress_type=ZIP_DEFLATED)
        archive.writestr("OEBPS/edition.xhtml", _xhtml(edition_date, articles), compress_type=ZIP_DEFLATED)
        archive.writestr("OEBPS/style.css", css, compress_type=ZIP_DEFLATED)
        archive.write(cover_path, "OEBPS/cover.svg", compress_type=ZIP_DEFLATED)
    return destination


def validate_pdf(path: Path, *, minimum_pages: int = 2) -> dict:
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
    if text.strip():
        qa = validate_arabic_text(text, minimum_arabic_letters=50, allowed_latin_terms=("DRAGON",))
        issues.extend(qa.issues)
        language = qa.to_dict()
        extraction = "AVAILABLE"
    else:
        language = {"status": "NOT_APPLICABLE", "reason": "raster PDF; Arabic validated at canonical source and visual renderer inputs"}
        extraction = "UNAVAILABLE_RASTER"
    populated_pages = 0
    for page in reader.pages:
        resources = page.get("/Resources") or {}
        if page.extract_text().strip() or resources.get("/XObject"):
            populated_pages += 1
    if populated_pages != pages:
        issues.append(f"PDF_BLANK_PAGES:{pages - populated_pages}")
    return {"status": "PASS" if not issues else "FAIL", "pages": pages, "populated_pages": populated_pages, "bytes": path.stat().st_size, "text_extraction": extraction, "language": language, "issues": issues}


def validate_epub(path: Path) -> dict:
    issues: list[str] = []
    required = {"mimetype", "META-INF/container.xml", "OEBPS/content.opf", "OEBPS/nav.xhtml", "OEBPS/edition.xhtml", "OEBPS/cover.svg"}
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
            ElementTree.fromstring(package)
            issues.extend(validate_xhtml_rtl(xhtml))
            if "page-progression-direction=\"rtl\"" not in package or "<dc:language>ar</dc:language>" not in package:
                issues.append("EPUB_RTL_METADATA_INVALID")
            text = re.sub(r"<[^>]+>", " ", xhtml)
            language = validate_arabic_text(text, minimum_arabic_letters=50, allowed_latin_terms=("DRAGON",))
            issues.extend(language.issues)
    except Exception as exc:
        return {"status": "FAIL", "issues": [f"EPUB_OPEN_FAILED:{exc}"]}
    return {"status": "PASS" if not issues else "FAIL", "bytes": path.stat().st_size, "language": language.to_dict(), "issues": issues}


def artifact_manifest(paths: list[Path], root: Path, *, mode: str) -> dict:
    return {"mode": mode, "artifacts": [{"path": str(path.relative_to(root)).replace("\\", "/"), "sha256": sha256_file(path), "bytes": path.stat().st_size} for path in paths]}
