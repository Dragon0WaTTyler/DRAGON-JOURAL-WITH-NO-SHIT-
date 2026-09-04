"""Render canonical sources; report local validation separately from publication."""
from __future__ import annotations
import base64
import html
import json
import mimetypes
import posixpath
import re
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree as ET
from pypdf import PdfReader, PdfWriter
from scripts.publication_inputs import digest, validate_inputs

X = "{http://www.w3.org/1999/xhtml}"
O = "{http://www.idpf.org/2007/opf}"
EPUB_CSS = "body{font-family:serif;line-height:1.5;max-width:42em;margin:auto;padding:1em}img,svg{max-width:100%;height:auto}table{max-width:100%}pre{white-space:pre-wrap}a{overflow-wrap:anywhere}"

def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))

def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def restricted_fetcher(edition: Path, failures: list[str]):
    def fetch(url, *args, **kwargs):
        parsed = urlsplit(url)
        if parsed.scheme == "data":
            header, encoded = url.split(",", 1)
            if not header.startswith("data:image/") or ";base64" not in header:
                failures.append(url[:40])
                raise ValueError("only embedded image data allowed")
            return {"string": base64.b64decode(encoded, validate=True), "mime_type": header[5:].split(";")[0]}
        path_text = unquote(parsed.path)
        if sys.platform == "win32" and re.match(r"^/[A-Za-z]:", path_text):
            path_text = path_text[1:]
        path = Path(path_text).resolve()
        if parsed.scheme != "file" or parsed.netloc or not path.is_relative_to(edition.resolve()) or not path.is_file():
            failures.append(url[:200])
            raise ValueError("renderer resource outside canonical edition")
        return {"string": path.read_bytes(), "mime_type": mimetypes.guess_type(path.name)[0] or "application/octet-stream"}
    return fetch

def cover_html(cover: Path) -> str:
    media = mimetypes.guess_type(cover.name)[0]
    data = base64.b64encode(cover.read_bytes()).decode("ascii")
    return f'''<!doctype html><html><head><meta charset="utf-8"/><style>
@page{{size:210mm 280mm;margin:0}}html,body{{margin:0;padding:0}}
img{{display:block;width:210mm;height:280mm;object-fit:contain}}
</style></head><body><img alt="DRAGON cover" src="data:{media};base64,{data}"/></body></html>'''

def render_pdf(edition: Path, cover: Path, output: Path) -> int:
    from weasyprint import HTML, CSS
    failures = []
    fetcher = restricted_fetcher(edition, failures)
    with tempfile.TemporaryDirectory(prefix="dragon-pdf-") as temp:
        cover_pdf, body_pdf = Path(temp) / "cover.pdf", Path(temp) / "body.pdf"
        HTML(string=cover_html(cover), base_url=edition.as_uri(), url_fetcher=fetcher).write_pdf(cover_pdf)
        document = HTML(filename=str(edition / "edition.html"), base_url=edition.as_uri() + "/", url_fetcher=fetcher)
        document.write_pdf(body_pdf, stylesheets=[CSS(filename=str(edition / "print.css"), url_fetcher=fetcher)])
        if failures:
            raise ValueError("unavailable/unsafe PDF resources: " + ", ".join(failures))
        front, body = PdfReader(cover_pdf), PdfReader(body_pdf)
        if len(front.pages) != 1 or not body.pages:
            raise ValueError("PDF needs exactly one cover page and a non-empty interior")
        if any(not (page.extract_text() or "").strip() for page in body.pages):
            raise ValueError("blank/textless PDF interior page")
        writer = PdfWriter()
        writer.add_page(front.pages[0])
        for page in body.pages:
            writer.add_page(page)
        writer.write(output)
    return len(PdfReader(output).pages)

def build_epub(edition: Path, cover: Path, output: Path, edition_date: str) -> None:
    ET.register_namespace("", X[1:-1])
    source = ET.fromstring((edition / "epub-content.xhtml").read_bytes())
    for key in ("lang", "{http://www.w3.org/XML/1998/namespace}lang"):
        source.set(key, "ary-Latn")
    source.set("dir", "ltr")
    body, head = source.find(X + "body"), source.find(X + "head")
    if body is None or head is None:
        raise ValueError("XHTML needs head and body")
    body.set("dir", "ltr")
    for child in list(head):
        if child.tag in {X + "style", X + "link"}:
            head.remove(child)
    ET.SubElement(head, X + "link", {"rel": "stylesheet", "href": "epub.css", "type": "text/css"})
    resources = {}
    for element in source.iter():
        if "src" not in element.attrib:
            continue
        relative = unquote(element.attrib["src"])
        path = (edition / relative).resolve()
        if urlsplit(relative).scheme or not path.is_relative_to(edition.resolve()) or not path.is_file():
            raise ValueError("EPUB resources must exist within edition")
        resources[relative] = path
    title = html.escape(f"DRAGON - {edition_date}")
    cover_name = "canonical-cover" + cover.suffix.lower()
    cover_media = mimetypes.guess_type(cover.name)[0]
    def page(content):
        return f'<html xmlns="{X[1:-1]}" xmlns:epub="http://www.idpf.org/2007/ops" lang="ary-Latn" dir="ltr"><head><title>{title}</title></head><body dir="ltr">{content}</body></html>'
    nav = page('<nav epub:type="toc"><h1>Contents</h1><ol><li><a href="cover.xhtml">Cover</a></li><li><a href="edition.xhtml">Edition</a></li></ol></nav>')
    modified = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    extra = "".join(f'<item id="resource-{i}" href="{html.escape(name, quote=True)}" media-type="{mimetypes.guess_type(name)[0] or "application/octet-stream"}"/>' for i, name in enumerate(resources))
    opf = f'''<package xmlns="{O[1:-1]}" version="3.0" unique-identifier="pub-id"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="pub-id">dragon-{edition_date}</dc:identifier><dc:title>{title}</dc:title><dc:language>ary-Latn</dc:language><meta property="dcterms:modified">{modified}</meta></metadata><manifest><item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/><item id="cover" href="cover.xhtml" media-type="application/xhtml+xml"/><item id="cover-image" href="{cover_name}" media-type="{cover_media}" properties="cover-image"/><item id="edition" href="edition.xhtml" media-type="application/xhtml+xml"/><item id="css" href="epub.css" media-type="text/css"/>{extra}</manifest><spine page-progression-direction="ltr"><itemref idref="cover"/><itemref idref="edition"/></spine></package>'''
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        archive.writestr("META-INF/container.xml", '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0"><rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>')
        archive.writestr("OEBPS/content.opf", opf)
        archive.writestr("OEBPS/nav.xhtml", nav)
        archive.writestr("OEBPS/cover.xhtml", page(f'<img style="max-width:100%;height:auto" src="{cover_name}" alt="DRAGON cover"/>'))
        archive.writestr("OEBPS/edition.xhtml", ET.tostring(source, encoding="utf-8", xml_declaration=True))
        archive.writestr("OEBPS/epub.css", EPUB_CSS)
        archive.writestr("OEBPS/" + cover_name, cover.read_bytes())
        for name, path in resources.items():
            archive.writestr("OEBPS/" + name, path.read_bytes())

def validate_epub(path: Path) -> None:
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or archive.testzip():
            raise ValueError("duplicate/corrupt EPUB members")
        if names[0] != "mimetype" or archive.getinfo("mimetype").compress_type != zipfile.ZIP_STORED or archive.read("mimetype") != b"application/epub+zip":
            raise ValueError("invalid EPUB mimetype")
        opf = ET.fromstring(archive.read("OEBPS/content.opf"))
        modified = opf.findall(f'{O}metadata/{O}meta[@property="dcterms:modified"]')
        if len(modified) != 1 or not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", modified[0].text or ""):
            raise ValueError("EPUB requires one UTC dcterms:modified timestamp")
        items = opf.findall(f"{O}manifest/{O}item")
        mapping = {item.get("id"): item.get("href") for item in items}
        if len(mapping) != len(items) or not any(item.get("properties") == "cover-image" for item in items):
            raise ValueError("invalid EPUB manifest/cover metadata")
        for item in items:
            if "OEBPS/" + item.get("href", "") not in names:
                raise ValueError("EPUB manifest references missing resource")
        for ref in opf.findall(f"{O}spine/{O}itemref"):
            if ref.get("idref") not in mapping:
                raise ValueError("unknown EPUB spine item")
        documents = {}
        for name in names:
            if name.endswith((".xml", ".opf", ".xhtml", ".svg")):
                element = ET.fromstring(archive.read(name))
                if name.endswith(".xhtml"):
                    if element.tag != X + "html":
                        raise ValueError("invalid XHTML namespace")
                    documents[name] = element
        for name, element in documents.items():
            ids = [node.get("id") for node in element.iter() if node.get("id")]
            if len(ids) != len(set(ids)):
                raise ValueError("duplicate XHTML IDs")
            for node in element.iter():
                link = node.get("href", node.get("src"))
                if not link or urlsplit(link).scheme:
                    continue
                target, _, fragment = link.partition("#")
                target = posixpath.normpath(posixpath.join(posixpath.dirname(name), unquote(target))) if target else name
                if target not in names:
                    raise ValueError(f"unresolved EPUB resource/link: {link}")
                if fragment and (target not in documents or not any(n.get("id") == unquote(fragment) for n in documents[target].iter())):
                    raise ValueError(f"unresolved EPUB fragment: {link}")

def render(root: Path, edition_date: str) -> dict:
    edition, cover, hashes = validate_inputs(root, edition_date)
    pdf, epub = edition / f"dragon-{edition_date}.pdf", edition / f"dragon-{edition_date}.epub"
    with tempfile.TemporaryDirectory(prefix="dragon-binaries-") as temp:
        temp_pdf, temp_epub = Path(temp) / "edition.pdf", Path(temp) / "edition.epub"
        pages = render_pdf(edition, cover, temp_pdf)
        build_epub(edition, cover, temp_epub, edition_date)
        validate_epub(temp_epub)
        pdf.write_bytes(temp_pdf.read_bytes())
        epub.write_bytes(temp_epub.read_bytes())
    receipt = {"date": edition_date, "input_sha256": hashes, "binary_sha256": {str(p.relative_to(root)).replace("\\", "/"): digest(p) for p in (pdf, epub)}, "pdf_pages": pages, "structural_validation": "PASS", "visual_review": "NOT_PERFORMED_BY_RENDERER", "github_binary_read_back": "PENDING", "final_publication_status": "PENDING"}
    write_json(root / "daily-runs" / edition_date / "binary-render-report.json", receipt)
    return receipt
