#!/usr/bin/env python3
"""Create a clearly synthetic edition to test the cloud archive contract."""

from __future__ import annotations

import argparse
import base64
import json
import re
import struct
import zipfile
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WEBP_1X1 = base64.b64decode(
    "UklGRiIAAABXRUJQVlA4IBgAAAAwAQCdASoBAAEAAUAmJaQAA3AA/v89WAAAAA=="
)


def edition_dir(edition_date: str) -> Path:
    parsed = date.fromisoformat(edition_date)
    return ROOT / "editions" / f"{parsed:%Y}" / f"{parsed:%m}" / edition_date


def write_pdf(path: Path, title: str) -> None:
    streams = (
        "BT /F1 18 Tf 72 720 Td (DAILY NEWSPAPER - SMOKE TEST) Tj "
        "0 -32 Td /F1 12 Tf (NOT FOR PUBLICATION) Tj "
        f"0 -28 Td ({title}) Tj ET"
    ).encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(streams)).encode("ascii") + b" >>\nstream\n" + streams + b"\nendstream",
    ]
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, 1):
        offsets.append(len(output))
        output.extend(f"{index} 0 obj\n".encode("ascii"))
        output.extend(obj)
        output.extend(b"\nendobj\n")
    xref = len(output)
    output.extend(f"xref\n0 {len(objects)+1}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.extend(
        f"trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode("ascii")
    )
    path.write_bytes(output)


def write_epub(path: Path, edition_date: str, markdown_text: str) -> None:
    xhtml_text = re.sub(r"\n\n+", "</p><p>", markdown_text.strip())
    xhtml_text = xhtml_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    with zipfile.ZipFile(path, "w") as epub:
        epub.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        epub.writestr(
            "META-INF/container.xml",
            '<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>',
        )
        epub.writestr(
            "OEBPS/content.opf",
            f'''<?xml version="1.0" encoding="utf-8"?><package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="pub-id"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="pub-id">daily-newspaper-{edition_date}</dc:identifier><dc:title>Daily Newspaper Smoke Test</dc:title><dc:language>darija-Latn</dc:language></metadata><manifest><item id="edition" href="edition.xhtml" media-type="application/xhtml+xml"/><item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/><item id="cover" href="cover.webp" media-type="image/webp"/></manifest><spine><itemref idref="edition"/></spine></package>''',
        )
        epub.writestr(
            "OEBPS/nav.xhtml",
            '<!doctype html><html xmlns="http://www.w3.org/1999/xhtml"><body><nav epub:type="toc" xmlns:epub="http://www.idpf.org/2007/ops"><ol><li><a href="edition.xhtml">Edition</a></li></ol></nav></body></html>',
        )
        epub.writestr(
            "OEBPS/edition.xhtml",
            f'<!doctype html><html xmlns="http://www.w3.org/1999/xhtml"><head><title>Smoke Test</title></head><body><h1>Daily Newspaper — Smoke Test</h1><p>{xhtml_text}</p></body></html>',
        )
        epub.writestr("OEBPS/cover.webp", WEBP_1X1)


def update_readme(edition_date: str) -> None:
    readme = ROOT / "README.md"
    text = readme.read_text(encoding="utf-8")
    marker = "## Latest archived fixture\n"
    start = text.index(marker) + len(marker)
    next_heading = re.search(r"\n## ", text[start:])
    end = start + next_heading.start() if next_heading else len(text)
    replacement = f"{edition_date}\n\n- [Markdown](editions/{edition_date[:4]}/{edition_date[5:7]}/{edition_date}/edition.md)\n- [PDF](editions/{edition_date[:4]}/{edition_date[5:7]}/{edition_date}/edition.pdf)\n- [EPUB](editions/{edition_date[:4]}/{edition_date[5:7]}/{edition_date}/edition.epub)\n"
    readme.write_text(text[:start] + replacement + text[end:], encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True, help="Edition date in YYYY-MM-DD format")
    args = parser.parse_args()
    parsed = date.fromisoformat(args.date)
    target = edition_dir(args.date)
    target.mkdir(parents=True, exist_ok=True)
    edition_text = (
        "# DAILY NEWSPAPER — SMOKE TEST\n\n"
        "**SMOKE TEST — NOT FOR PUBLICATION**\n\n"
        f"Had l-edition ghir fixture bach ntestiw cloud archive pipeline dyal {parsed:%d/%m/%Y}. "
        "Ma fiha la khbar 7a9i9i la claim journalism."
    )
    (target / "edition.md").write_text(edition_text, encoding="utf-8")
    (target / "sources.json").write_text(
        json.dumps([{"id": "synthetic-fixture", "type": "test-fixture"}], indent=2) + "\n",
        encoding="utf-8",
    )
    write_pdf(target / "edition.pdf", args.date)
    write_epub(target / "edition.epub", args.date, edition_text)
    (target / "cover.webp").write_bytes(WEBP_1X1)
    manifest = {
        "date": args.date,
        "status": "published",
        "language": "darija-latin",
        "pdf": "edition.pdf",
        "epub": "edition.epub",
        "cover": "cover.webp",
        "fact_check": "passed",
        "language_check": "passed",
        "sources_count": 1,
        "smoke_test": True,
    }
    (target / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    update_readme(args.date)
    print(f"created smoke edition: {target.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
