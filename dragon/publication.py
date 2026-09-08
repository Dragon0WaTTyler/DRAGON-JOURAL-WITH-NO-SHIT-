"""Canonical Arabic HTML, PDF, and EPUB publication builders and validators."""

from __future__ import annotations

from html import escape
import hashlib
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


def _article_markup(article: dict, layout: dict | None = None) -> str:
    paragraphs = "".join(f"<p>{escape(value)}</p>" for value in article["body"])
    sources = "".join(
        f'<li><a href="{escape(url, quote=True)}">{escape(url)}</a></li>'
        for url in article.get("source_urls", [])
    )
    grammar = (layout or {}).get("page_role", "NORMAL_NEWS")
    return (
        f'<article id="{escape(article["id"])}" data-page-grammar="{escape(grammar)}">'
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
    hero_art_path: Path | None = None,
    composition_variant: str = "single-symbol",
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
    if hero_art_path is not None:
        with Image.open(hero_art_path) as hero:
            hero_image = hero.convert("RGB").resize((643, 230))
        cover.paste(hero_image, (92, 520))
        hero_image.close()
        standfirst_y = 775
    else:
        standfirst_y = 550
    _draw_rtl(draw, (735, standfirst_y), standfirst, _font(24), fill="#222222", spacing=38, width=645)
    label = "نسخة اختبار اصطناعية" if mode == "synthetic" else "النسخة اليومية"
    footer = "غير مخصصة للنشر أو التوزيع" if mode == "synthetic" else "صحافة عربية مستقلة"
    _draw_rtl(draw, (735, 930), label, _font(25), fill="#9e1523", spacing=38, width=645)
    draw.text((413, 1000), edition_date, font=_font(22), fill="#333333", anchor="mm")
    _draw_rtl(draw, (735, 1060), footer, _font(17), fill="#333333", spacing=28, width=645)
    destination.parent.mkdir(parents=True, exist_ok=True)
    cover.save(destination, "PNG", optimize=True)
    cover.close()
    return destination


def build_hero_art_png(destination: Path, seed: str, mode: str, variant: str) -> Path:
    """Build text-free fallback art; it is never classified as documentary evidence."""
    from PIL import Image, ImageDraw

    digest = hashlib.sha256(f"{seed}:{mode}:{variant}".encode("utf-8")).digest()
    image = Image.new("RGB", (643, 285), "#111111")
    draw = ImageDraw.Draw(image)
    accent = "#9e1523"
    for index in range(7):
        x = 25 + (digest[index] * 2) % 560
        y = 18 + (digest[index + 7]) % 220
        radius = 18 + digest[index + 14] % 70
        if mode == "DRAMATIC_CURRENT_EVENT":
            draw.rectangle((x, y, min(642, x + radius * 2), min(284, y + radius)), fill=accent)
        elif mode == "PORTRAIT_DOSSIER":
            draw.ellipse((x, y, min(642, x + radius), min(284, y + radius * 2)), outline=accent, width=8)
        else:
            draw.polygon(((x, y), (min(642, x + radius), min(284, y + radius * 2)), (max(0, x - radius), min(284, y + radius * 2))), fill=accent)
    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination, "PNG", optimize=True)
    image.close()
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


def build_html(
    edition_dir: Path,
    edition_date: str,
    articles: list[dict],
    *,
    mode: str = "production",
    layout_plan: dict | None = None,
) -> Path:
    assets = edition_dir / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    (edition_dir / "print-v5.css").write_text(PRINT_CSS, encoding="utf-8", newline="\n")
    layouts = {
        item["article_id"]: item for item in (layout_plan or {}).get("pages", [])
    }
    article_html = "".join(_article_markup(article, layouts.get(article["id"])) for article in articles)
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


def validate_publication_source(
    document: str, articles: list[dict], layout_plan: dict | None = None
) -> list[str]:
    issues = validate_html_rtl(document)
    for article in articles:
        article_id = article.get("id")
        if not article_id or f'id="{escape(str(article_id), quote=True)}"' not in document:
            issues.append(f"HTML_ARTICLE_MISSING:{article_id}")
        if layout_plan is not None:
            page = next(
                (item for item in layout_plan.get("pages", []) if item.get("article_id") == article_id),
                None,
            )
            grammar = page.get("page_role") if page else None
            if not grammar or f'data-page-grammar="{escape(str(grammar), quote=True)}"' not in document:
                issues.append(f"HTML_PAGE_GRAMMAR_MISSING:{article_id}")
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


def _render_pdf_pillow(html_path: Path, destination: Path, *, line_height: int = 29) -> None:
    """Portable Windows renderer with explicit Arabic shaping and bidi."""
    from PIL import Image, ImageDraw

    articles_path = html_path.with_name("articles.json")
    article_data = json.loads(articles_path.read_text(encoding="utf-8"))
    mode = article_data.get("mode", "production")
    articles = [item for item in article_data["articles"] if item["status"] == "ACTIVE"]
    layout_path = html_path.with_name("layout-plan.json")
    layout = json.loads(layout_path.read_text(encoding="utf-8")) if layout_path.exists() else {"pages": []}
    layouts = {item["article_id"]: item for item in layout.get("pages", [])}
    edition_date = html_path.parent.name
    size = (827, 1169)
    pages = []
    page_links: list[list[tuple[str, int, int, int]]] = [[]]
    with Image.open(html_path.parent / "assets" / "cover.png") as source_cover:
        cover = source_cover.convert("RGB").resize(size)
    pages.append(cover)
    role_labels = {
        "LEAD": "المادة الرئيسية", "NORMAL_NEWS": "أخبار", "ANALYSIS": "تحليل",
        "INVESTIGATION_DOSSIER": "ملف تحقيق", "SCIENCE": "الدليل العلمي",
        "HISTORY": "تاريخ", "CULTURE": "ثقافة وأدب", "DATA": "بيانات وخدمات",
    }
    role_colors = {
        "SCIENCE": "#24566f", "INVESTIGATION_DOSSIER": "#55151a",
        "HISTORY": "#6d4d2f", "CULTURE": "#6b315d", "DATA": "#2f6047",
        "ANALYSIS": "#333333", "LEAD": "#9e1523", "NORMAL_NEWS": "#9e1523",
    }

    def new_content_page(role: str):
        page = Image.new("RGB", size, "white")
        draw = ImageDraw.Draw(page)
        draw.rectangle((45, 45, 782, 1124), outline="#d2d2d2", width=2)
        draw.rectangle((45, 45, 782, 66), fill=role_colors.get(role, "#9e1523"))
        _draw_rtl(
            draw, (750, 76), role_labels.get(role, "أخبار"), _font(12),
            fill=role_colors.get(role, "#9e1523"), spacing=18, width=300,
        )
        return page, draw

    for article in articles:
        page_layout = layouts.get(article["id"], {})
        role = page_layout.get("page_role", "NORMAL_NEWS")
        column_count = 2 if int(page_layout.get("columns", 1)) == 2 else 1
        column_width = 315 if column_count == 2 else 675
        column_xs = (750, 405) if column_count == 2 else (750,)
        body_font = _font(18)

        # Wrap once, then balance the immutable copy over the minimum page count.
        # Layout may reflow copy but never rewrites editorial facts or wording.
        flow: list[tuple[str, str | None]] = []
        scratch_image = Image.new("RGB", (1, 1))
        scratch = ImageDraw.Draw(scratch_image)
        for paragraph in article["body"]:
            flow.extend((line, None) for line in _rtl_lines(scratch, paragraph, body_font, column_width))
            flow.append(("", None))
        if flow and flow[-1][0] == "":
            flow.pop()
        flow.append(("المصادر:", None))
        for url in article.get("source_urls", []):
            flow.extend((line, str(url)) for line in _ltr_lines(scratch, str(url), _font(11), column_width))
        scratch_image.close()

        remaining = flow
        continuation = False
        while remaining:
            page, draw = new_content_page(role)
            links: list[tuple[str, int, int, int]] = []
            if continuation:
                y = _draw_rtl(
                    draw, (750, 87), article["headline"] + " — تابع", _font(18),
                    fill=role_colors.get(role, "#9e1523"), spacing=29, width=675,
                )
                draw.line((75, y + 3, 750, y + 3), fill="#d2d2d2", width=2)
                content_y = y + 20
            else:
                y = 85
                y = _draw_rtl(draw, (750, y), article["section"], _font(19), fill="#9e1523", spacing=30, width=675)
                y += 10
                y = _draw_rtl(draw, (750, y), article["headline"], _font(32), fill="#111111", spacing=44, width=675)
                y += 10
                y = _draw_rtl(draw, (750, y), article["standfirst"], _font(20), fill="#333333", spacing=32, width=675)
                y += 12
                y = _draw_rtl(draw, (750, y), article["byline"], _font(16), fill="#555555", spacing=25, width=675)
                draw.line((75, y + 5, 750, y + 5), fill="#9e1523", width=3)
                content_y = y + 30
            rows_per_column = max(1, (1035 - content_y) // line_height)
            page_capacity = rows_per_column * column_count
            pages_needed = max(1, (len(remaining) + page_capacity - 1) // page_capacity)
            take = min(page_capacity, (len(remaining) + pages_needed - 1) // pages_needed)
            page_flow, remaining = remaining[:take], remaining[take:]
            rows_used = (len(page_flow) + column_count - 1) // column_count
            if column_count == 2:
                draw.line((420, content_y, 420, min(1040, content_y + rows_used * line_height)), fill="#dedede", width=2)
            for column_index, x in enumerate(column_xs):
                start = column_index * rows_used
                column_flow = page_flow[start : start + rows_used]
                line_y = content_y
                for line, url in column_flow:
                    if line:
                        font = _font(11) if url else body_font
                        visual = line if url else _visual_arabic(line)
                        draw.text((x, line_y), visual, font=font, fill="#555555" if url else "#111111", anchor="ra")
                        if url:
                            links.append((url, x - column_width, x, line_y))
                    line_y += line_height
            pages.append(page)
            page_links.append(links)
            continuation = True
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
            for url, left, right, top in links_for_page:
                writer.add_uri(
                    page_number,
                    url,
                    RectangleObject(
                        (
                            left * x_scale,
                            (size[1] - (top + 18)) * y_scale,
                            right * x_scale,
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


def render_pdf(html_path: Path, destination: Path, *, line_height: int = 29) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if __import__("os").name == "nt":
        _render_pdf_pillow(html_path, destination, line_height=line_height)
    else:
        from weasyprint import HTML

        HTML(filename=str(html_path)).write_pdf(destination)
    return destination


def build_pdf_contact_sheet(path: Path, destination: Path, *, columns: int = 4) -> Path:
    """Persist a compact all-pages preview used by automated and human visual QA."""
    from PIL import Image, ImageDraw, ImageOps

    reader = PdfReader(str(path))
    thumb_size = (207, 292)
    gutter = 18
    label_height = 24
    rows = (len(reader.pages) + columns - 1) // columns
    sheet = Image.new(
        "RGB",
        (gutter + columns * (thumb_size[0] + gutter), gutter + rows * (thumb_size[1] + label_height + gutter)),
        "#d9d9d9",
    )
    draw = ImageDraw.Draw(sheet)
    for index, page in enumerate(reader.pages):
        if not page.images:
            continue
        raster = page.images[0].image.convert("RGB")
        thumb = ImageOps.contain(raster, thumb_size)
        column = index % columns
        row = index // columns
        x = gutter + column * (thumb_size[0] + gutter)
        y = gutter + row * (thumb_size[1] + label_height + gutter)
        sheet.paste(thumb, (x, y))
        draw.text((x, y + thumb_size[1] + 3), f"{index + 1}", fill="#111111", font=_font(14))
        raster.close()
        thumb.close()
    destination.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(destination, "PNG", optimize=True)
    sheet.close()
    return destination


def validate_pdf_visuals(
    structural_report: dict,
    contact_sheet: Path,
    layout_plan: dict,
    *,
    minimum_content_fill: float,
) -> dict:
    """Run deterministic raster heuristics without pretending they are human review."""
    issues: list[str] = []
    metrics = structural_report.get("page_visual_metrics", [])
    sparse = [
        item["page"]
        for item in metrics[1:]
        if item.get("vertical_fill") is not None
        and item["vertical_fill"] < minimum_content_fill
    ]
    if sparse:
        issues.append("VISUAL_SPARSE_PAGES:" + ",".join(str(page) for page in sparse))
    roles = {item.get("page_role") for item in layout_plan.get("pages", [])}
    roles.discard(None)
    if len(roles) < 4:
        issues.append(f"VISUAL_PAGE_GRAMMAR_VARIETY_LOW:{len(roles)}")
    if not contact_sheet.exists() or contact_sheet.stat().st_size < 10_000:
        issues.append("VISUAL_CONTACT_SHEET_INVALID")
    return {
        "status": "PASS" if not issues else "FAIL",
        "review_type": "AUTOMATED_RASTER_HEURISTICS",
        "human_review_status": "NOT_RUN",
        "contact_sheet": contact_sheet.name,
        "page_count": structural_report.get("pages"),
        "page_grammar_count": len(roles),
        "page_grammars": sorted(roles),
        "minimum_content_fill": minimum_content_fill,
        "sparse_pages": sparse,
        "issues": issues,
    }


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
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid" xml:lang="ar" dir="rtl">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="bookid">{identifier}</dc:identifier><dc:title>DRAGON — {edition_date}</dc:title><dc:language>ar</dc:language><dc:creator>DRAGON</dc:creator><meta property="dcterms:modified">{edition_date}T07:00:00Z</meta><meta name="cover" content="cover-image"/></metadata>
<manifest><item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/><item id="edition" href="edition.xhtml" media-type="application/xhtml+xml"/><item id="css" href="style.css" media-type="text/css"/><item id="cover-image" href="cover.png" media-type="image/png" properties="cover-image"/></manifest>
<spine page-progression-direction="rtl"><itemref idref="edition"/></spine></package>'''
    nav = '''<?xml version="1.0" encoding="utf-8"?><html xmlns="http://www.w3.org/1999/xhtml" lang="ar" xml:lang="ar" dir="rtl"><head><title>الفهرس</title></head><body><nav epub:type="toc" xmlns:epub="http://www.idpf.org/2007/ops"><h1>الفهرس</h1><ol><li><a href="edition.xhtml">النسخة الكاملة</a></li></ol></nav></body></html>'''
    css = "html,body{font-family:serif;line-height:1.7} article{break-before:page} h1,h2,p{text-align:right}.section{font-weight:bold}"
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
    minimum_content_fill: float | None = None,
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
    page_visual_metrics: list[dict] = []
    linked_urls: set[str] = set()
    for page_number, page in enumerate(reader.pages, start=1):
        resources = page.get("/Resources") or {}
        visual_fill = None
        vertical_fill = None
        try:
            from PIL import Image, ImageChops

            if page.images:
                raster = page.images[0].image.convert("RGB")
                crop = raster.crop(
                    (
                        int(raster.width * 0.085),
                        int(raster.height * 0.07),
                        int(raster.width * 0.915),
                        int(raster.height * 0.93),
                    )
                )
                white = Image.new("RGB", crop.size, "white")
                difference = ImageChops.difference(crop, white).convert("L")
                mask = difference.point(lambda value: 255 if value > 16 else 0)
                histogram = mask.histogram()
                visual_fill = histogram[255] / max(1, sum(histogram))
                bounds = mask.getbbox()
                vertical_fill = (bounds[3] / crop.height) if bounds else 0.0
                raster.close()
                crop.close()
                white.close()
                difference.close()
                mask.close()
        except Exception:
            pass
        if page.extract_text().strip() or (resources.get("/XObject") and vertical_fill):
            populated_pages += 1
        page_visual_metrics.append(
            {
                "page": page_number,
                "ink_fraction": round(visual_fill, 4) if visual_fill is not None else None,
                "vertical_fill": round(vertical_fill, 4) if vertical_fill is not None else None,
            }
        )
        if (
            minimum_content_fill is not None
            and page_number > 1
            and vertical_fill is not None
            and vertical_fill < minimum_content_fill
        ):
            issues.append(
                f"PDF_SPARSE_PAGE:{page_number}:{vertical_fill:.3f}<{minimum_content_fill:.3f}"
            )
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
        "page_visual_metrics": page_visual_metrics,
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
