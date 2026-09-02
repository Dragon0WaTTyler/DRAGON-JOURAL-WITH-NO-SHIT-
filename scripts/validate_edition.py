#!/usr/bin/env python3
"""Validate a smoke or real-edition archive contract.

This validator intentionally checks content metadata and container signatures,
not just whether expected filenames happen to exist.
"""

from __future__ import annotations

import argparse
import json
import re
import zipfile
from datetime import date
from pathlib import Path
from urllib.parse import urlparse
from xml.etree import ElementTree


ROOT = Path(__file__).resolve().parents[1]
REQUIRED = ("edition.md", "edition.pdf", "edition.epub", "cover.webp", "sources.json", "manifest.json")
ARABIC_SCRIPT = re.compile(r"[\u0600-\u06ff\u0750-\u077f\u08a0-\u08ff\ufb50-\ufdff\ufe70-\ufeff]")
CITATION = re.compile(r"\[(S\d+)\]")
SOURCE_FIELDS = ("id", "url", "publisher", "publication_date", "accessed_at", "source_type", "claim_supported")


def edition_dir(edition_date: str) -> Path:
    parsed = date.fromisoformat(edition_date)
    return ROOT / "editions" / f"{parsed:%Y}" / f"{parsed:%m}" / edition_date


def validate_pdf(path: Path, errors: list[str]) -> None:
    data = path.read_bytes()
    if not data.startswith(b"%PDF-"):
        errors.append("edition.pdf is not a PDF")
    if b"%%EOF" not in data[-128:]:
        errors.append("edition.pdf has no final EOF marker")
    if b"/Type /Page" not in data:
        errors.append("edition.pdf contains no page object")
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        if not reader.pages:
            errors.append("edition.pdf has no readable pages")
    except ImportError:
        errors.append("pypdf is required for PDF validation")
    except Exception as exc:  # pypdf exposes different parse exceptions by version
        errors.append(f"edition.pdf cannot be parsed by pypdf: {exc}")


def validate_epub(path: Path, errors: list[str]) -> None:
    try:
        with zipfile.ZipFile(path) as epub:
            names = epub.namelist()
            if epub.testzip() is not None:
                errors.append("EPUB contains a corrupt member")
            if not names or names[0] != "mimetype":
                errors.append("EPUB mimetype is not first")
            if epub.read("mimetype") != b"application/epub+zip":
                errors.append("EPUB mimetype is incorrect")
            for required in ("META-INF/container.xml", "OEBPS/content.opf", "OEBPS/nav.xhtml"):
                if required not in names:
                    errors.append(f"EPUB missing {required}")
            container = ElementTree.fromstring(epub.read("META-INF/container.xml"))
            rootfile = next(iter(container.iter("{urn:oasis:names:tc:opendocument:xmlns:container}rootfile")), None)
            if rootfile is None or rootfile.attrib.get("full-path") != "OEBPS/content.opf":
                errors.append("EPUB container does not point to OEBPS/content.opf")
            opf = epub.read("OEBPS/content.opf").decode("utf-8")
            if "darija" not in opf.lower() and "latn" not in opf.lower():
                errors.append("EPUB metadata does not identify Darija Latin language")
            nav = epub.read("OEBPS/nav.xhtml").decode("utf-8").lower()
            if "toc" not in nav or "href=" not in nav:
                errors.append("EPUB navigation has no usable table of contents")
            for name in names:
                if name.startswith("OEBPS/") and name.endswith((".xhtml", ".html")):
                    text = epub.read(name).decode("utf-8")
                    if ARABIC_SCRIPT.search(text):
                        errors.append(f"EPUB {name} contains Arabic-script characters")
    except (zipfile.BadZipFile, KeyError, UnicodeDecodeError, ElementTree.ParseError) as exc:
        errors.append(f"invalid EPUB: {exc}")


def validate_smoke(target: Path, manifest: dict, sources: list, edition_text: str, errors: list[str]) -> None:
    expected = {
        "date": target.name,
        "status": "published",
        "language": "darija-latin",
        "fact_check": "passed",
        "language_check": "passed",
        "smoke_test": True,
    }
    for key, value in expected.items():
        if manifest.get(key) != value:
            errors.append(f"manifest {key} != {value!r}")
    if not edition_text.startswith("# DAILY NEWSPAPER"):
        errors.append("smoke edition.md has unexpected heading")
    if "SMOKE TEST" not in edition_text or "NOT FOR PUBLICATION" not in edition_text:
        errors.append("smoke edition is not clearly labeled")


def validate_real(target: Path, manifest: dict, sources: list, edition_text: str, errors: list[str]) -> None:
    expected = {
        "date": target.name,
        "mode": "preproduction",
        "status": "pre-production",
        "language": "darija-latin",
        "fact_check": "passed",
        "language_check": "passed",
        "smoke_test": False,
        "label": "PRE-PRODUCTION — NOT YET DAILY PRODUCTION",
    }
    for key, value in expected.items():
        if manifest.get(key) != value:
            errors.append(f"manifest {key} != {value!r}")
    if "PRE-PRODUCTION" not in edition_text or "NOT YET DAILY PRODUCTION" not in edition_text:
        errors.append("pre-production edition is not clearly labeled")
    if ARABIC_SCRIPT.search(edition_text):
        errors.append("edition.md contains Arabic-script characters")
    if not sources:
        errors.append("pre-production edition has no source records")
    source_ids: list[str] = []
    for index, source in enumerate(sources):
        if not isinstance(source, dict):
            errors.append(f"source {index} is not an object")
            continue
        for key in SOURCE_FIELDS:
            if not source.get(key):
                errors.append(f"source {index} missing {key}")
        source_id = source.get("id")
        if isinstance(source_id, str):
            source_ids.append(source_id)
        parsed_url = urlparse(str(source.get("url", "")))
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            errors.append(f"source {index} has an invalid HTTP(S) URL")
    if len(source_ids) != len(set(source_ids)):
        errors.append("sources.json contains duplicate source IDs")
    if not isinstance(manifest.get("sources_count"), int) or manifest["sources_count"] != len(sources):
        errors.append("manifest sources_count does not match sources.json")
    if not isinstance(manifest.get("sections"), list) or len(manifest["sections"]) < 5:
        errors.append("pre-production manifest needs at least five named sections")
    if not isinstance(manifest.get("citations_count"), int) or manifest["citations_count"] < 1:
        errors.append("pre-production manifest needs a positive citations_count")
    cited_ids = CITATION.findall(edition_text)
    unknown_ids = sorted(set(cited_ids) - set(source_ids))
    uncited_ids = sorted(set(source_ids) - set(cited_ids))
    if unknown_ids:
        errors.append(f"edition cites unknown source IDs: {', '.join(unknown_ids)}")
    if uncited_ids:
        errors.append(f"sources.json contains uncited source IDs: {', '.join(uncited_ids)}")
    if isinstance(manifest.get("citations_count"), int) and manifest["citations_count"] != len(cited_ids):
        errors.append("manifest citations_count does not match edition citations")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True, help="Edition date in YYYY-MM-DD format")
    parser.add_argument("--mode", choices=("smoke", "preproduction"), default="smoke")
    args = parser.parse_args()
    parsed = date.fromisoformat(args.date)
    target = edition_dir(args.date)
    errors: list[str] = []
    for name in REQUIRED:
        path = target / name
        if not path.is_file() or path.stat().st_size == 0:
            errors.append(f"missing or empty: {name}")
    if errors:
        print("VALIDATION FAIL")
        print("\n".join(errors))
        return 1

    try:
        manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
        sources = json.loads((target / "sources.json").read_text(encoding="utf-8"))
        edition_text = (target / "edition.md").read_text(encoding="utf-8")
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        errors.append(f"invalid JSON or Markdown encoding: {exc}")
        manifest, sources, edition_text = {}, [], ""

    if not isinstance(manifest, dict):
        errors.append("manifest.json must contain an object")
        manifest = {}
    if not isinstance(sources, list):
        errors.append("sources.json must contain an array")
        sources = []

    if args.mode == "smoke":
        validate_smoke(target, manifest, sources, edition_text, errors)
    else:
        validate_real(target, manifest, sources, edition_text, errors)

    validate_pdf(target / "edition.pdf", errors)
    cover = (target / "cover.webp").read_bytes()
    if not (cover.startswith(b"RIFF") and cover[8:12] == b"WEBP"):
        errors.append("cover.webp is not a WebP container")
    if args.mode == "preproduction":
        try:
            from PIL import Image

            with Image.open(target / "cover.webp") as image:
                if image.format != "WEBP":
                    errors.append("cover.webp does not decode as WebP")
                if image.size != (1200, 1600):
                    errors.append(f"cover.webp must be 1200x1600, got {image.size[0]}x{image.size[1]}")
        except ImportError:
            errors.append("Pillow is required for pre-production cover validation")
        except Exception as exc:
            errors.append(f"cover.webp cannot be decoded: {exc}")
    validate_epub(target / "edition.epub", errors)

    if errors:
        print(f"VALIDATION FAIL ({args.mode})")
        print("\n".join(errors))
        return 1
    print(f"VALIDATION PASS ({args.mode}): {target.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
