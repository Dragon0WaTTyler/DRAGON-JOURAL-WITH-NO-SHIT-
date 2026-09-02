#!/usr/bin/env python3
"""Validate the machine-checkable archive contract for one edition."""

from __future__ import annotations

import argparse
import json
import zipfile
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REQUIRED = ("edition.md", "edition.pdf", "edition.epub", "cover.webp", "sources.json", "manifest.json")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    args = parser.parse_args()
    parsed = date.fromisoformat(args.date)
    target = ROOT / "editions" / f"{parsed:%Y}" / f"{parsed:%m}" / args.date
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
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        errors.append(f"invalid JSON: {exc}")
        manifest, sources = {}, []
    expected = {
        "date": args.date,
        "status": "published",
        "language": "darija-latin",
        "fact_check": "passed",
        "language_check": "passed",
        "smoke_test": True,
    }
    for key, value in expected.items():
        if manifest.get(key) != value:
            errors.append(f"manifest {key} != {value!r}")
    if manifest.get("sources_count") != len(sources):
        errors.append("manifest sources_count does not match sources.json")
    if not (target / "edition.md").read_text(encoding="utf-8").startswith("# DAILY NEWSPAPER"):
        errors.append("edition.md has unexpected heading")
    if not (target / "edition.pdf").read_bytes().startswith(b"%PDF-"):
        errors.append("edition.pdf is not a PDF")
    cover = (target / "cover.webp").read_bytes()
    if not (cover.startswith(b"RIFF") and cover[8:12] == b"WEBP"):
        errors.append("cover.webp is not a WebP container")
    try:
        with zipfile.ZipFile(target / "edition.epub") as epub:
            names = epub.namelist()
            if not names or names[0] != "mimetype":
                errors.append("EPUB mimetype is not first")
            if epub.read("mimetype") != b"application/epub+zip":
                errors.append("EPUB mimetype is incorrect")
            for required in ("META-INF/container.xml", "OEBPS/content.opf", "OEBPS/nav.xhtml"):
                if required not in names:
                    errors.append(f"EPUB missing {required}")
    except (zipfile.BadZipFile, KeyError) as exc:
        errors.append(f"invalid EPUB: {exc}")
    if errors:
        print("VALIDATION FAIL")
        print("\n".join(errors))
        return 1
    print(f"VALIDATION PASS: {target.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
