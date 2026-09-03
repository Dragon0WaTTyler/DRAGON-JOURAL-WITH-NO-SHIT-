#!/usr/bin/env python3
"""Validate a smoke or real-edition archive contract.

This validator intentionally checks content metadata and container signatures,
not just whether expected filenames happen to exist.
"""

from __future__ import annotations

import argparse
import json
import posixpath
import re
import zipfile
from datetime import date
from pathlib import Path
from urllib.parse import urlparse
from xml.etree import ElementTree

import yaml

try:
    from editorial_depth import evaluate, language_has_arabic_script, load_policy
    from reader_facing_qa import lint_markdown, lint_text, report_payload, require_reader_manifest
except ImportError:  # imports also work when tests load scripts as a package
    from scripts.editorial_depth import evaluate, language_has_arabic_script, load_policy
    from scripts.reader_facing_qa import lint_markdown, lint_text, report_payload, require_reader_manifest


ROOT = Path(__file__).resolve().parents[1]
REQUIRED = ("edition.md", "edition.pdf", "edition.epub", "cover.webp", "sources.json", "manifest.json")
ARABIC_SCRIPT = re.compile(r"[\u0600-\u06ff\u0750-\u077f\u08a0-\u08ff\ufb50-\ufdff\ufe70-\ufeff]")
CITATION = re.compile(r"\[(S\d+)\]")
SOURCE_FIELDS = ("id", "url", "publisher", "publication_date", "accessed_at", "source_type", "claim_supported")


def edition_dir(edition_date: str) -> Path:
    parsed = date.fromisoformat(edition_date)
    return ROOT / "editions" / f"{parsed:%Y}" / f"{parsed:%m}" / edition_date


def validate_pdf(path: Path, errors: list[str]) -> tuple[str, int]:
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
            return "", 0
        return "\n".join(page.extract_text() or "" for page in reader.pages), len(reader.pages)
    except ImportError:
        errors.append("pypdf is required for PDF validation")
    except Exception as exc:  # pypdf exposes different parse exceptions by version
        errors.append(f"edition.pdf cannot be parsed by pypdf: {exc}")
    return "", 0


def validate_epub(path: Path, errors: list[str]) -> tuple[str, int]:
    """Strict EPUB 3 validation without extracting untrusted archive members."""
    epub_text = ""
    document_count = 0
    try:
        with zipfile.ZipFile(path) as epub:
            names = epub.namelist()
            if epub.testzip() is not None:
                errors.append("EPUB contains a corrupt member")
            if any(name.startswith("/") or ".." in Path(name).parts for name in names):
                errors.append("EPUB contains an unsafe member path")
            if not names or names[0] != "mimetype":
                errors.append("EPUB mimetype is not first")
            if epub.read("mimetype") != b"application/epub+zip":
                errors.append("EPUB mimetype is incorrect")
            elif epub.getinfo("mimetype").compress_type != zipfile.ZIP_STORED:
                errors.append("EPUB mimetype must be stored without compression")
            required = ("META-INF/container.xml", "OEBPS/content.opf", "OEBPS/nav.xhtml")
            if any(member not in names for member in required):
                errors.extend(f"EPUB missing {member}" for member in required if member not in names)
                return epub_text, document_count

            xml, decoded = {}, {}
            for name in names:
                if name.endswith((".xml", ".opf", ".xhtml", ".html")):
                    try:
                        decoded[name] = epub.read(name).decode("utf-8", errors="strict")
                        xml[name] = ElementTree.fromstring(decoded[name])
                    except UnicodeDecodeError as exc:
                        errors.append(f"EPUB {name} is not valid UTF-8: {exc}")
                    except ElementTree.ParseError as exc:
                        errors.append(f"EPUB {name} is malformed XML/XHTML: {exc}")
            if errors:
                return epub_text, document_count

            container = xml["META-INF/container.xml"]
            rootfile = next(iter(container.iter("{urn:oasis:names:tc:opendocument:xmlns:container}rootfile")), None)
            if rootfile is None or rootfile.attrib.get("full-path") != "OEBPS/content.opf":
                errors.append("EPUB container does not point to OEBPS/content.opf")
            if "latn" not in decoded["OEBPS/content.opf"].lower():
                errors.append("EPUB metadata does not identify Darija Latin language")
            if re.search(r'\bdir\s*=\s*["\']rtl["\']|direction\s*:\s*rtl\b', decoded["OEBPS/content.opf"], re.IGNORECASE):
                errors.append("EPUB OPF contains RTL direction metadata")

            opf_ns = "{http://www.idpf.org/2007/opf}"
            opf = xml["OEBPS/content.opf"]
            manifest = {item.attrib.get("id", ""): item.attrib.get("href", "") for item in opf.findall(f"{opf_ns}manifest/{opf_ns}item")}
            if not manifest:
                errors.append("EPUB OPF has no manifest items")
            for itemref in opf.findall(f"{opf_ns}spine/{opf_ns}itemref"):
                if itemref.attrib.get("idref") not in manifest:
                    errors.append("EPUB spine references a missing manifest item")
            spine_element = opf.find(f"{opf_ns}spine")
            if spine_element is None or spine_element.attrib.get("page-progression-direction") != "ltr":
                errors.append("EPUB spine page progression is not explicitly LTR")

            for name in names:
                if name.endswith(".css"):
                    try:
                        css = epub.read(name).decode("utf-8", errors="strict")
                    except UnicodeDecodeError as exc:
                        errors.append(f"EPUB {name} is not valid UTF-8: {exc}")
                    else:
                        if re.search(r"direction\s*:\s*rtl\b", css, re.IGNORECASE):
                            errors.append(f"EPUB {name} contains an RTL rule")

            xhtml_names = [name for name in names if name.startswith("OEBPS/") and name.endswith((".xhtml", ".html"))]
            identifiers: dict[str, set[str]] = {}
            html_ns = "{http://www.w3.org/1999/xhtml}"
            for name in xhtml_names:
                root = xml[name]
                if root.tag != f"{html_ns}html":
                    errors.append(f"EPUB {name} is not an XHTML html document")
                if root.attrib.get("dir", "").lower() != "ltr":
                    errors.append(f"EPUB {name} html root direction is not LTR")
                body = next((element for element in root.iter() if element.tag == f"{html_ns}body"), None)
                if body is None or body.attrib.get("dir", "").lower() != "ltr":
                    errors.append(f"EPUB {name} body direction is not LTR")
                if re.search(r'\bdir\s*=\s*["\']rtl["\']', decoded[name], re.IGNORECASE):
                    errors.append(f"EPUB {name} contains RTL direction metadata")
                ids = [element.attrib["id"] for element in root.iter() if "id" in element.attrib]
                if len(ids) != len(set(ids)):
                    errors.append(f"EPUB {name} has duplicate IDs")
                identifiers[name] = set(ids)
                if ARABIC_SCRIPT.search(decoded[name]):
                    errors.append(f"EPUB {name} contains Arabic-script characters")
                if name.endswith("cover.xhtml"):
                    if not any(element.tag == f"{html_ns}img" for element in root.iter()):
                        errors.append("EPUB cover page is missing its image")
                elif name.endswith("nav.xhtml"):
                    if not any(element.tag == f"{html_ns}nav" for element in root.iter()):
                        errors.append("EPUB navigation has no semantic nav element")
                else:
                    if not any(element.tag == f"{html_ns}h1" for element in root.iter()):
                        errors.append(f"EPUB {name} is missing an h1")
                epub_text += decoded[name] + "\n"
                document_count += 1

            def resolve(base: str, href: str) -> tuple[str, str]:
                target, _, fragment = href.partition("#")
                return (base if not target else posixpath.normpath(posixpath.join(posixpath.dirname(base), target))), fragment

            nav_links = 0
            for name in xhtml_names:
                for anchor in xml[name].iter(f"{html_ns}a"):
                    href = anchor.attrib.get("href", "")
                    if not href:
                        errors.append(f"EPUB {name} has an anchor without href")
                        continue
                    parsed = urlparse(href)
                    if parsed.scheme or href.startswith("//"):
                        continue
                    destination, fragment = resolve(name, href)
                    if destination not in names:
                        errors.append(f"EPUB {name} has an unresolved link: {href}")
                    elif fragment and fragment not in identifiers.get(destination, set()):
                        errors.append(f"EPUB {name} has an unresolved fragment: {href}")
                    if name == "OEBPS/nav.xhtml":
                        nav_links += 1
            if nav_links == 0:
                errors.append("EPUB navigation has no usable table of contents")
            if "OEBPS/sources.xhtml" not in xhtml_names:
                errors.append("EPUB is missing a Sources document")
    except (zipfile.BadZipFile, KeyError, UnicodeDecodeError, ElementTree.ParseError) as exc:
        errors.append(f"invalid EPUB: {exc}")
    return epub_text, document_count


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
        "status": "published",
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
    if language_has_arabic_script(edition_text):
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


def validate_editorial_depth(edition_date: str, edition_text: str, errors: list[str], report_path: Path) -> None:
    try:
        policy = load_policy(ROOT / "config/editorial-depth.yaml")
        previous_topics: list[str] = []
        for memory_name in ("covered-stories.json", "history-used.json", "literature-used.json"):
            memory_path = ROOT / "memory" / memory_name
            if not memory_path.is_file():
                continue
            memory = json.loads(memory_path.read_text(encoding="utf-8"))
            if isinstance(memory, list):
                for item in memory:
                    if isinstance(item, dict) and isinstance(item.get("topic"), str):
                        previous_topics.append(item["topic"])
                    if isinstance(item, dict) and isinstance(item.get("topics"), list):
                        previous_topics.extend(topic for topic in item["topics"] if isinstance(topic, str))
        report = evaluate(
            edition_text,
            policy,
            edition_date=edition_date,
            previous_topics=previous_topics,
        )
        language_pass = not language_has_arabic_script(edition_text)
        report["language"] = {
            "arabic_script_characters": 0 if language_pass else 1,
            "pass": language_pass,
        }
        if not language_pass:
            report["validation_status"] = "FAIL"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    except (OSError, ValueError, TypeError, yaml.YAMLError) as exc:
        errors.append(f"editorial-depth policy/report failed: {exc}")
        return
    if report["total"]["pass"] is False:
        errors.append(
            f"edition has {report['total_word_count']} words; hard minimum is {report['total']['hard_min_words']}"
        )
    errors.extend(report["chief_editor_regeneration_requests"])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True, help="Edition date in YYYY-MM-DD format")
    parser.add_argument("--mode", choices=("smoke", "preproduction"), default="smoke")
    parser.add_argument(
        "--quality-report-path",
        type=Path,
        help="override the default research/YYYY-MM-DD/editorial-quality-report.json path",
    )
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
        report_path = args.quality_report_path or ROOT / "research" / args.date / "editorial-quality-report.json"
        validate_editorial_depth(args.date, edition_text, errors, report_path)

    pdf_text, pdf_pages = validate_pdf(target / "edition.pdf", errors)
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
    epub_text, epub_documents = validate_epub(target / "edition.epub", errors)
    if args.mode == "preproduction":
        reader_issues = []
        reader_issues.extend(lint_markdown(edition_text))
        reader_issues.extend(lint_text(pdf_text, "PDF-extracted text"))
        reader_issues.extend(lint_text(re.sub(r"<[^>]+>", "\n", epub_text), "EPUB text"))
        reader_issues.extend(require_reader_manifest(manifest))
        try:
            from pypdf import PdfReader

            reader = PdfReader(str(target / "edition.pdf"))
            uri_links = 0
            for page in reader.pages:
                for annotation in page.get("/Annots", []):
                    action = annotation.get_object().get("/A")
                    if action and action.get("/URI"):
                        uri_links += 1
            if uri_links < len(sources):
                reader_issues.append("PDF has fewer clickable source URLs than source records")
        except Exception as exc:
            reader_issues.append(f"PDF source-link inspection failed: {exc}")
        errors.extend(reader_issues)
        qa_path = ROOT / "research" / args.date / "reader-facing-qa-report.json"
        qa_path.write_text(json.dumps(report_payload(reader_issues, pdf_pages=pdf_pages, epub_documents=epub_documents), indent=2) + "\n", encoding="utf-8")

    if errors:
        print(f"VALIDATION FAIL ({args.mode})")
        print("\n".join(errors))
        return 1
    print(f"VALIDATION PASS ({args.mode}): {target.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
