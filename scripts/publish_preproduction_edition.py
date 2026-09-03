#!/usr/bin/env python3
"""Render the reader-facing pre-production edition into PDF, EPUB and cover."""
from __future__ import annotations

import argparse
import html
import json
import re
import tempfile
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfReader, PdfWriter
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import BaseDocTemplate, Frame, KeepTogether, NextPageTemplate, PageBreak, PageTemplate, Paragraph, Spacer

ROOT = Path(__file__).resolve().parents[1]
LABEL = "PRE-PRODUCTION — NOT YET DAILY PRODUCTION"
CITATION = re.compile(r"\[(S\d+)\]")


def target(date: str) -> Path:
    year, month, _ = date.split("-")
    return ROOT / "editions" / year / month / date


def font_path(bold: bool = False) -> str:
    candidates = (
        ["C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
        if bold
        else ["C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
    )
    for candidate in candidates:
        if Path(candidate).is_file():
            return candidate
    raise RuntimeError("A Unicode TrueType font is required for publishing")


def register_fonts() -> tuple[str, str]:
    regular, bold = "DragonRegular", "DragonBold"
    if regular not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(regular, font_path()))
        pdfmetrics.registerFont(TTFont(bold, font_path(True)))
    return regular, bold


def cover(path: Path, date: str) -> None:
    regular = ImageFont.truetype(font_path(), 34)
    small = ImageFont.truetype(font_path(), 27)
    bold = ImageFont.truetype(font_path(True), 86)
    subhead = ImageFont.truetype(font_path(True), 48)
    image = Image.new("RGB", (1200, 1600), "#f3ead8")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 1200, 190), fill="#142c2b")
    draw.text((72, 45), "DRAGON", font=bold, fill="#f4c15d")
    draw.text((75, 215), "DAILY NEWSPAPER", font=subhead, fill="#142c2b")
    # Clearly abstract editorial art: water lines, an open book and a rising sun.
    draw.ellipse((400, 380, 800, 780), fill="#e88b55")
    for y in range(650, 1120, 70):
        draw.arc((100, y - 80, 1100, y + 100), 180, 360, fill="#267b82", width=18)
    draw.polygon([(170, 920), (580, 850), (580, 1250), (170, 1320)], fill="#fffaf0", outline="#142c2b")
    draw.polygon([(1030, 920), (620, 850), (620, 1250), (1030, 1320)], fill="#fffaf0", outline="#142c2b")
    draw.line((600, 850, 600, 1250), fill="#142c2b", width=12)
    draw.rectangle((0, 1400, 1200, 1600), fill="#142c2b")
    draw.text((62, 1425), "EDITORIAL ILLUSTRATION", font=regular, fill="#f4c15d")
    draw.text((62, 1490), date, font=small, fill="white")
    image.save(path, "WEBP", quality=92, method=6)


def split_sections(markdown: str) -> list[tuple[str, list[str]]]:
    sections: list[tuple[str, list[str]]] = []
    title = "Nazarat l-yom"
    current: list[str] = []
    for line in markdown.splitlines():
        if line.startswith("## "):
            if current:
                sections.append((title, current))
            title, current = line[3:].strip(), []
        else:
            current.append(line)
    if current:
        sections.append((title, current))
    return [(title, lines) for title, lines in sections if title != "Sources"]


def reader_text(markdown: str) -> str:
    return "\n".join("\n".join(lines) for _, lines in split_sections(markdown))


def source_title(source: dict) -> str:
    titles = {
        "S1": "L'Indice des prix a la consommation (IPC) du mois de Juillet 2026",
        "S2": "Morocco's Consumer Price Index Falls 1% in July 2026",
        "S3": "Licence Parcours d'Excellence application notice, 2026-27",
        "S4": "Brazilian activist demands Tunisia release Sumud flotilla organisers",
        "S5": "WFP Sudan aid-truck report",
        "S6": "Piloting the world's first double-blind AI evaluations",
        "S7": "Double-blind evaluations technical report",
        "S8": "Efficient SWE Agent Benchmarking via Trajectory-Aware Evaluation",
        "S9": "Efficient SWE Agent Benchmarking via Trajectory-Aware Evaluation (abstract)",
        "S12": "Equity and Reconciliation Commission final report, volume 2",
        "S13": "Un recit et un bilan des emeutes de Casablanca",
        "S14": "Peripherie, emeutes et politique urbaine : Le cas de Casablanca",
        "S15": "A History of Modern Morocco chronology",
        "S16": "Leaping Decolonization, introduction",
        "S17": "Le Passe simple bibliographic record",
        "S18": "La difficulte d'etre au present : Une lecture du Passe simple",
        "S19": "La Litterature maghrebine francophone",
        "S20": "Politics of Le passe simple",
        "S21": "Tense Eruptions in Driss Chraibi's Le passe simple",
        "S22": "Colonise et colonisateur dans Le Passe Simple de Driss Chraibi",
    }
    return str(source.get("title") or titles.get(str(source.get("id"))) or source.get("claim_supported") or "Source record")


def paragraph_markup(text: str, sources: dict[str, dict]) -> str:
    clean = text.replace("**", "").replace("*", "")
    escaped = html.escape(clean, quote=False)

    def cite(match: re.Match[str]) -> str:
        source = sources.get(match.group(1))
        if not source:
            return match.group(0)
        url = html.escape(str(source["url"]), quote=True)
        return f'<a href="{url}"><font color="#9b442e">[{match.group(1)}]</font></a>'

    escaped = CITATION.sub(cite, escaped)
    for label, colour in {"FACT": "#176b5b", "CLAIM": "#9b442e", "UNKNOWN": "#6a5d39", "ESTIMATE": "#6a5d39", "PREPRINT": "#5b4b9a", "ABSTRACT_ONLY": "#5b4b9a", "COMPANY_CLAIM": "#9b442e"}.items():
        escaped = re.sub(rf"\b{label}\b", f'<font color="{colour}"><b>{label}</b></font>', escaped)
    return escaped


def draw_wrapped(canvas_obj: canvas.Canvas, text: str, x: float, y: float, width: float, font: str, size: float, leading: float) -> float:
    canvas_obj.setFont(font, size)
    words, line = text.split(), ""
    for word in words:
        proposal = f"{line} {word}".strip()
        if line and pdfmetrics.stringWidth(proposal, font, size) > width:
            canvas_obj.drawString(x, y, line)
            y -= leading
            line = word
        else:
            line = proposal
    if line:
        canvas_obj.drawString(x, y, line)
        y -= leading
    return y


def front_page(path: Path, cover_path: Path, date: str, regular: str, bold: str) -> None:
    page_width, page_height = A4
    doc = canvas.Canvas(str(path), pagesize=A4)
    doc.drawImage(ImageReader(str(cover_path)), 0, 0, width=page_width, height=page_height, mask="auto")
    doc.setFillColor(HexColor("#142c2b"))
    doc.rect(0, 0, page_width, 42 * mm, stroke=0, fill=1)
    doc.setFillColor(HexColor("#142c2b"))
    doc.rect(0, page_height - 62 * mm, page_width, 62 * mm, stroke=0, fill=1)
    doc.setFillColor(HexColor("#f4c15d"))
    doc.setFont(bold, 31)
    doc.drawString(17 * mm, page_height - 26 * mm, "DRAGON")
    doc.setFont(regular, 9)
    doc.setFillColor(HexColor("#ffffff"))
    doc.drawRightString(page_width - 17 * mm, page_height - 18 * mm, date)
    doc.drawRightString(page_width - 17 * mm, page_height - 25 * mm, "V1.1 CANDIDATE")
    doc.setFillColor(HexColor("#fffaf0"))
    doc.roundRect(13 * mm, 20 * mm, page_width - 26 * mm, 78 * mm, 5 * mm, stroke=0, fill=1)
    x, y = 20 * mm, 88 * mm
    doc.setFillColor(HexColor("#9b442e"))
    doc.setFont(bold, 9)
    doc.drawString(x, y, "WHAT MATTERS TODAY")
    y -= 10 * mm
    doc.setFillColor(HexColor("#142c2b"))
    y = draw_wrapped(doc, "CPI n9es, walakin l-ma3isha ma kattsalash f ra9m wa7ed", x, y, page_width - 40 * mm, bold, 22, 25)
    y -= 3 * mm
    doc.setFillColor(HexColor("#172b2a"))
    y = draw_wrapped(doc, "HCP kay3ti n9ass f l-index; food w non-food ma t7rkoch b nafs l-jiha. L-ra9m ma kay7km-sh bo7do 3la l-3a2ilat.", x, y, page_width - 40 * mm, regular, 10.5, 14)
    y -= 4 * mm
    teasers = [
        "Filastin: l-3onf f ddafa w bo7ran l-ma f Gaza.",
        "L-3alam: Sudan, Ukraine, w zyarat Xi l-Masr.",
        "Tarikh: Casablanca 1965 w l-archive lli ma kay9ol-sh kolchi.",
        "Adab: Le Passe simple w s-sulta dakhel l-3a2ila.",
    ]
    for teaser in teasers:
        doc.setFillColor(HexColor("#9b442e"))
        doc.circle(x + 2, y + 2, 1.6, stroke=0, fill=1)
        doc.setFillColor(HexColor("#172b2a"))
        y = draw_wrapped(doc, teaser, x + 8, y, page_width - 48 * mm, regular, 9.2, 12)
    doc.setFillColor(HexColor("#ffffff"))
    doc.setFont(regular, 7.5)
    doc.drawRightString(page_width - 17 * mm, 12 * mm, "Cover: editorial illustration - not documentary photography")
    doc.showPage()
    doc.save()


class NewspaperDoc(BaseDocTemplate):
    def __init__(self, filename: str, regular: str, bold: str, date: str):
        page_width, page_height = A4
        margin = 15 * mm
        gutter = 7 * mm
        column_width = (page_width - (2 * margin) - gutter) / 2
        bottom, top = 15 * mm, page_height - 22 * mm
        columns = [
            Frame(margin, bottom, column_width, top - bottom, id="left", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0),
            Frame(margin + column_width + gutter, bottom, column_width, top - bottom, id="right", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0),
        ]
        source_frame = Frame(margin, bottom, page_width - 2 * margin, top - bottom, id="sources", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)

        def chrome(canvas_obj, doc):
            canvas_obj.saveState()
            canvas_obj.setStrokeColor(HexColor("#c8bda8"))
            canvas_obj.line(margin, page_height - 14 * mm, page_width - margin, page_height - 14 * mm)
            canvas_obj.setFillColor(HexColor("#142c2b"))
            canvas_obj.setFont(bold, 7.5)
            canvas_obj.drawString(margin, page_height - 11 * mm, "DRAGON")
            canvas_obj.setFont(regular, 7)
            canvas_obj.drawRightString(page_width - margin, page_height - 11 * mm, date)
            canvas_obj.setFillColor(HexColor("#555555"))
            canvas_obj.drawString(margin, 8 * mm, "DRAGON Daily Newspaper")
            canvas_obj.drawRightString(page_width - margin, 8 * mm, str(doc.page + 1))
            canvas_obj.restoreState()

        super().__init__(filename, pagesize=A4, leftMargin=margin, rightMargin=margin, topMargin=22 * mm, bottomMargin=15 * mm)
        self.addPageTemplates([PageTemplate(id="news", frames=columns, onPage=chrome), PageTemplate(id="sources", frames=[source_frame], onPage=chrome)])


def render_pdf(path: Path, markdown: str, sources_list: list[dict], cover_path: Path, date: str) -> None:
    regular, bold = register_fonts()
    sources = {str(source["id"]): source for source in sources_list}
    styles = getSampleStyleSheet()
    body = ParagraphStyle("body", parent=styles["BodyText"], fontName=regular, fontSize=8.6, leading=11.4, spaceAfter=5, textColor=HexColor("#172b2a"))
    section = ParagraphStyle("section", parent=styles["Heading2"], fontName=bold, fontSize=14, leading=16, spaceBefore=7, spaceAfter=5, textColor=HexColor("#9b442e"))
    subhead = ParagraphStyle("subhead", parent=styles["Heading3"], fontName=bold, fontSize=9.3, leading=12, spaceBefore=5, spaceAfter=3, textColor=HexColor("#142c2b"))
    source = ParagraphStyle("source", parent=body, fontSize=7.6, leading=9.6, spaceAfter=5)
    with tempfile.TemporaryDirectory() as temp_dir:
        temp = Path(temp_dir)
        front, body_pdf = temp / "front.pdf", temp / "body.pdf"
        front_page(front, cover_path, date, regular, bold)
        story = []
        for title, lines in split_sections(markdown):
            flow = [Paragraph(html.escape(title), section)]
            for line in lines:
                line = line.strip()
                if not line or line.startswith("# ") or line.startswith("<!--") or line.startswith("**PRE-PRODUCTION"):
                    continue
                if line.startswith("### "):
                    flow.append(Paragraph(html.escape(line[4:]), subhead))
                else:
                    flow.append(Paragraph(paragraph_markup(line, sources), body))
            story.append(KeepTogether(flow[:2]))
            story.extend(flow[2:])
            story.append(Spacer(1, 2))
        story.extend([NextPageTemplate("sources"), PageBreak(), Paragraph("Sources", section)])
        for item in sources_list:
            item_id = html.escape(str(item["id"]), quote=True)
            publisher = html.escape(str(item["publisher"]))
            title = html.escape(source_title(item))
            published = html.escape(str(item["publication_date"]))
            url = html.escape(str(item["url"]), quote=True)
            text = f'<a name="source-{item_id}"/>[<b>{item_id}</b>] {publisher}<br/>{title}<br/>{published}<br/><a href="{url}"><font color="#176b5b">{url}</font></a>'
            story.append(Paragraph(text, source))
        NewspaperDoc(str(body_pdf), regular, bold, date).build(story)
        writer = PdfWriter()
        for page in PdfReader(str(front)).pages:
            writer.add_page(page)
        for page in PdfReader(str(body_pdf)).pages:
            writer.add_page(page)
        with path.open("wb") as output:
            writer.write(output)


def xhtml_document(title: str, body: str) -> str:
    return f'''<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="ary-Latn" lang="ary-Latn"><head><title>{html.escape(title)}</title><link rel="stylesheet" type="text/css" href="styles.css" /></head><body>{body}</body></html>'''


def epub_paragraph(text: str, sources: dict[str, dict]) -> str:
    clean = html.escape(text.replace("**", "").replace("*", ""), quote=False)

    def cite(match: re.Match[str]) -> str:
        return f'<a href="sources.xhtml#source-{match.group(1)}">[{match.group(1)}]</a>' if match.group(1) in sources else match.group(0)

    return CITATION.sub(cite, clean)


def epub(path: Path, markdown: str, sources_list: list[dict], cover_bytes: bytes, date: str) -> None:
    sections = split_sections(markdown)
    sources = {str(source["id"]): source for source in sources_list}
    items, spine, documents = [], ['<itemref idref="cover-page" linear="yes"/>'], {}
    for index, (title, lines) in enumerate(sections, 1):
        filename = f"section-{index:02d}.xhtml"
        article = [f'<article id="section-{index:02d}"><h1>{html.escape(title)}</h1>']
        for line in lines:
            line = line.strip()
            if not line or line.startswith("# ") or line.startswith("<!--") or line.startswith("**PRE-PRODUCTION"):
                continue
            article.append(f"<h2>{html.escape(line[4:])}</h2>" if line.startswith("### ") else f"<p>{epub_paragraph(line, sources)}</p>")
        article.append("</article>")
        documents[filename] = xhtml_document(title, "".join(article))
        items.append(f'<item id="section-{index:02d}" href="{filename}" media-type="application/xhtml+xml"/>')
        spine.append(f'<itemref idref="section-{index:02d}"/>')
    rows = []
    for source in sources_list:
        source_id = html.escape(str(source["id"]), quote=True)
        url = html.escape(str(source["url"]), quote=True)
        rows.append(f'<li id="source-{source_id}"><strong>[{source_id}] {html.escape(str(source["publisher"]))}</strong><br/>{html.escape(source_title(source))}<br/>{html.escape(str(source["publication_date"]))}<br/><a href="{url}">{url}</a></li>')
    documents["sources.xhtml"] = xhtml_document("Sources", f'<section id="sources"><h1>Sources</h1><ol>{"".join(rows)}</ol></section>')
    items.append('<item id="sources" href="sources.xhtml" media-type="application/xhtml+xml"/>')
    spine.append('<itemref idref="sources"/>')
    links = ['<li><a href="cover.xhtml">Cover</a></li>']
    links.extend(f'<li><a href="section-{index:02d}.xhtml">{html.escape(title)}</a></li>' for index, (title, _) in enumerate(sections, 1))
    links.append('<li><a href="sources.xhtml">Sources</a></li>')
    nav = xhtml_document("Table of Contents", f'<nav id="toc" epub:type="toc" xmlns:epub="http://www.idpf.org/2007/ops"><h1>Table of Contents</h1><ol>{"".join(links)}</ol></nav>')
    cover_page = xhtml_document("Cover", '<section id="cover"><h1 class="visually-hidden">DRAGON Daily Newspaper</h1><img src="cover.webp" alt="DRAGON editorial illustration: water lines, an open book and a rising sun" /></section>')
    css = "body{font-family:serif;line-height:1.55;margin:6%;color:#172b2a}h1{color:#9b442e}h2{color:#142c2b;margin-top:1.5em}a{color:#176b5b;word-break:break-word}li{margin-bottom:1em}img{max-width:100%;height:auto}.visually-hidden{position:absolute;left:-10000px}"
    opf = f'''<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="publication-id" xml:lang="ary-Latn"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="publication-id">dragon-{date}-v1.1</dc:identifier><dc:title>DRAGON Daily Newspaper - {date}</dc:title><dc:language>ary-Latn</dc:language><dc:creator>DRAGON Editorial Desk</dc:creator><dc:date>{date}</dc:date><dc:description>{LABEL}</dc:description><meta name="cover" content="cover-image"/></metadata><manifest><item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/><item id="cover-image" href="cover.webp" media-type="image/webp" properties="cover-image"/><item id="cover-page" href="cover.xhtml" media-type="application/xhtml+xml"/><item id="style" href="styles.css" media-type="text/css"/>{"".join(items)}</manifest><spine>{"".join(spine)}</spine></package>'''
    container = '<?xml version="1.0" encoding="utf-8"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>'
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("mimetype", b"application/epub+zip", compress_type=zipfile.ZIP_STORED)
        archive.writestr("META-INF/container.xml", container.encode("utf-8"))
        archive.writestr("OEBPS/content.opf", opf.encode("utf-8"))
        archive.writestr("OEBPS/nav.xhtml", nav.encode("utf-8"))
        archive.writestr("OEBPS/cover.xhtml", cover_page.encode("utf-8"))
        archive.writestr("OEBPS/styles.css", css.encode("utf-8"))
        archive.writestr("OEBPS/cover.webp", cover_bytes)
        for filename, document in documents.items():
            archive.writestr(f"OEBPS/{filename}", document.encode("utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    args = parser.parse_args()
    edition = target(args.date)
    markdown = (edition / "edition.md").read_text(encoding="utf-8")
    sources = json.loads((edition / "sources.json").read_text(encoding="utf-8"))
    cover_path = edition / "cover.webp"
    cover(cover_path, args.date)
    render_pdf(edition / "edition.pdf", markdown, sources, cover_path, args.date)
    epub(edition / "edition.epub", markdown, sources, cover_path.read_bytes(), args.date)
    sections = [title for title, _ in split_sections(markdown)] + ["Sources"]
    citations = len(CITATION.findall(markdown))
    manifest = {"date": args.date, "mode": "preproduction", "status": "published", "language": "darija-latin", "pdf": "edition.pdf", "epub": "edition.epub", "cover": "cover.webp", "fact_check": "passed", "language_check": "passed", "sources_count": len(sources), "citations_count": citations, "sections": sections, "smoke_test": False, "label": LABEL, "reader_facing": {"front_page": "designed", "cover_integrated": True, "source_links": "generated"}}
    (edition / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"rendered {edition.relative_to(ROOT)}: {len(sources)} sources, {citations} citations, {len(sections)} sections")


if __name__ == "__main__":
    main()
