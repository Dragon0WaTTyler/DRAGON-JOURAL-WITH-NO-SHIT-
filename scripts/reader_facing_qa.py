"""Reader-facing publishing checks kept separate from factual/editorial-depth QA."""
from __future__ import annotations

import re
from pathlib import Path

ARABIC_SCRIPT = re.compile(r"[\u0600-\u06ff\u0750-\u077f\u08a0-\u08ff\ufb50-\ufdff\ufe70-\ufeff]")
MOJIBAKE = re.compile(r"(?:\ufffd|Ã.|Â.|â€|â€™|â€œ|â€\x9d|grA\s+ve|communiquA\b|mostaAfa\b|franAais\b|kaykabbETMr)")
ENGINEERING = re.compile(r"\b(?:codex\s+cloud|execution\s+test|api\s+key|github\s+actions|origin/main|git\s+(?:commit|push)|remote\s+sha|pipeline\s+stages?|validators?|manifest(?:\.json)?|research\s+packets?|artifact-generation|scheduler\s+internals?|self-hosted\s+runner)\b", re.IGNORECASE)
RAW_MARKDOWN = re.compile(r"(?:^|\n)\s*(?:#{1,6}\s|[-*]\s|\*\*[^*]+\*\*)")


def reader_body(markdown: str) -> str:
    parts = re.split(r"^## Sources\s*$", markdown, maxsplit=1, flags=re.MULTILINE)
    return re.sub(r"<!--.*?-->", "", parts[0], flags=re.DOTALL)


def lint_text(text: str, label: str, *, allow_markdown: bool = False) -> list[str]:
    issues: list[str] = []
    if ARABIC_SCRIPT.search(text):
        issues.append(f"{label} contains Arabic-script characters")
    if MOJIBAKE.search(text):
        issues.append(f"{label} contains suspicious mojibake")
    if ENGINEERING.search(text):
        issues.append(f"{label} leaks internal engineering terminology")
    if not allow_markdown and RAW_MARKDOWN.search(text):
        issues.append(f"{label} contains raw Markdown artifacts")
    long_lines = [line for line in text.splitlines() if len(line.split()) > 190]
    if long_lines:
        issues.append(f"{label} contains an excessively long unbroken paragraph")
    return issues


def lint_markdown(markdown: str) -> list[str]:
    return lint_text(reader_body(markdown), "reader-facing Markdown", allow_markdown=True)


def require_reader_manifest(manifest: dict) -> list[str]:
    reader = manifest.get("reader_facing")
    if not isinstance(reader, dict):
        return ["manifest is missing reader-facing publishing metadata"]
    issues = []
    if reader.get("front_page") != "designed":
        issues.append("manifest does not confirm a designed front page")
    if reader.get("cover_integrated") is not True:
        issues.append("manifest does not confirm cover integration")
    if reader.get("source_links") != "generated":
        issues.append("manifest does not confirm generated source links")
    return issues


def report_payload(issues: list[str], *, pdf_pages: int, epub_documents: int) -> dict:
    return {
        "status": "PASS" if not issues else "FAIL",
        "checks": {
            "engineering_text": "PASS" if not any("engineering" in item for item in issues) else "FAIL",
            "mojibake": "PASS" if not any("mojibake" in item for item in issues) else "FAIL",
            "raw_markdown": "PASS" if not any("Markdown" in item for item in issues) else "FAIL",
            "front_page": "PASS" if not any("front page" in item for item in issues) else "FAIL",
            "cover_integration": "PASS" if not any("cover" in item for item in issues) else "FAIL",
        },
        "pdf_pages": pdf_pages,
        "epub_documents": epub_documents,
        "issues": issues,
    }
