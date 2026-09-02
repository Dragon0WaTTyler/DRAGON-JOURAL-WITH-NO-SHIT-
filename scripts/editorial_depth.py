"""Editorial-depth policy loading, Markdown section parsing, and reporting."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


ARABIC_SCRIPT = re.compile(r"[\u0600-\u06ff\u0750-\u077f\u08a0-\u08ff\ufb50-\ufdff\ufe70-\ufeff]")
CITATION = re.compile(r"\[S\d+\]")
WORD = re.compile(r"[\wÀ-ÿ]+(?:['’ʼ-][\wÀ-ÿ]+)*", re.UNICODE)
H2 = re.compile(r"^##\s+(.+?)\s*$")


@dataclass(frozen=True)
class MarkdownSection:
    heading: str
    body: str


def load_policy(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a mapping")
    return payload


def extract_sections(markdown: str) -> list[MarkdownSection]:
    """Extract H2 sections; front matter and H1 metadata are not sections."""
    sections: list[MarkdownSection] = []
    heading: str | None = None
    body: list[str] = []
    for line in markdown.splitlines():
        match = H2.match(line)
        if match:
            if heading is not None:
                sections.append(MarkdownSection(heading, "\n".join(body)))
            heading = match.group(1).strip()
            body = []
        elif heading is not None:
            body.append(line)
    if heading is not None:
        sections.append(MarkdownSection(heading, "\n".join(body)))
    return sections


def _normalise(value: str) -> str:
    value = value.casefold().replace("—", "-")
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def section_key(heading: str, aliases: dict[str, list[str]]) -> str | None:
    normalised = _normalise(heading)
    # Check longer aliases first so "adab w culture" is not confused with a
    # generic culture mention in a different heading.
    for key, values in aliases.items():
        for alias in sorted(values, key=len, reverse=True):
            alias_normalised = _normalise(alias)
            if normalised == alias_normalised or normalised.startswith(alias_normalised + " "):
                return key
    return None


def _strip_markdown(line: str) -> str:
    if "PRE-PRODUCTION" in line.upper() or "SMOKE TEST" in line.upper():
        return ""
    line = re.sub(r"!\[([^]]*)\]\([^)]*\)", r"\1", line)
    line = re.sub(r"\[([^]]+)\]\([^)]*\)", r"\1", line)
    line = CITATION.sub(" ", line)
    line = re.sub(r"`([^`]*)`", r"\1", line)
    line = re.sub(r"[*_>#|~]", " ", line)
    return line


def count_words(text: str) -> int:
    """Count narrative words, excluding citation IDs and Markdown metadata."""
    return sum(len(WORD.findall(_strip_markdown(line))) for line in text.splitlines())


def _target_range(value: Any) -> tuple[int | None, int | None]:
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return int(value[0]), int(value[1])
    if isinstance(value, str):
        match = re.fullmatch(r"\s*(\d+)\s*-\s*(\d+)\s*", value)
        if match:
            return int(match.group(1)), int(match.group(2))
    return None, None


def _is_sources_or_non_editorial(heading: str) -> bool:
    normalised = _normalise(heading)
    return normalised in {
        "sources",
        "mola7adat t ta79i9 w l logha",
        "mola7adat fact check w darija qa",
        "mola7adat t ta79i9 w darija qa",
        "fact check w darija qa",
    } or "source" == normalised


def _exception_reason(body: str, key: str, count: int, policy: dict[str, Any]) -> str | None:
    if key == "meknes" and policy.get("allow_thin_news_exception") and count < int(policy.get("hard_min_words", 0)):
        for line in body.splitlines():
            if "THIN-NEWS EXCEPTION" in line.upper():
                return _strip_markdown(line).strip()
    if key == "investigations" and policy.get("allow_dossier_update_without_publication"):
        if re.search(r"\b(RESEARCHING|NEEDS_VERIFICATION|HOLD)\b", body, re.IGNORECASE):
            return "dossier is explicitly not publication-ready"
    if key in {"history", "literature_culture"} and policy.get("allow_hold_without_publication"):
        if re.search(r"\bHOLD\b", body, re.IGNORECASE):
            return "section is explicitly held rather than published"
    return None


def evaluate(
    markdown: str,
    policy: dict[str, Any],
    *,
    edition_date: str | None = None,
    previous_topics: list[str] | None = None,
) -> dict[str, Any]:
    aliases = policy.get("section_aliases", {})
    sections = extract_sections(markdown)
    counts: dict[str, int] = {}
    bodies: dict[str, str] = {}
    headings: dict[str, str] = {}
    for section in sections:
        key = section_key(section.heading, aliases)
        if key and key not in counts:
            counts[key] = count_words(section.body)
            bodies[key] = section.body
            headings[key] = section.heading

    total = sum(count_words(section.body) for section in sections if not _is_sources_or_non_editorial(section.heading))
    # H2 headings are never counted; source and QA sections are excluded above.
    total_rule = policy.get("edition", {})
    total_min = int(total_rule.get("hard_min_words", 0))
    total_target = _target_range(total_rule.get("target_words"))
    requests: list[str] = []
    section_report: dict[str, dict[str, Any]] = {}
    exceptions: dict[str, dict[str, Any]] = {}

    for key, rule in policy.items():
        if key in {"version", "section_aliases", "edition"} or not isinstance(rule, dict):
            continue
        count = counts.get(key, 0)
        hard_min = rule.get("hard_min_words")
        publication_min = rule.get("publication_min_words")
        target_min, target_max = _target_range(rule.get("target_words"))
        exception = _exception_reason(
            headings.get(key, "") + "\n" + bodies.get(key, ""), key, count, rule
        )
        hard_pass = True
        if hard_min is not None:
            hard_pass = count >= int(hard_min) or exception is not None
        if publication_min is not None and count < int(publication_min) and exception is None:
            hard_pass = False
        if hard_min is not None and count < int(hard_min) and exception is None:
            requests.append(f"{key} section has {count} words; hard minimum is {int(hard_min)}")
        elif publication_min is not None and count < int(publication_min) and exception is None:
            requests.append(f"{key} section has {count} words; publication minimum is {int(publication_min)}")
        section_report[key] = {
            "heading": headings.get(key),
            "word_count": count,
            "hard_min_words": int(hard_min) if hard_min is not None else None,
            "publication_min_words": int(publication_min) if publication_min is not None else None,
            "target_range": [target_min, target_max] if target_min is not None else None,
            "pass": hard_pass,
        }
        exceptions[key] = {
            "allowed": bool(
                rule.get("allow_thin_news_exception")
                or rule.get("allow_dossier_update_without_publication")
                or rule.get("allow_hold_without_publication")
            ),
            "used": exception is not None,
            "reason": exception,
        }

    duplicate_headings = []
    seen: set[str] = set()
    for section in sections:
        normalised = _normalise(section.heading)
        if normalised in seen and normalised not in {"sources"}:
            duplicate_headings.append(section.heading)
        seen.add(normalised)
    repeated_topic_pass = not duplicate_headings
    if duplicate_headings:
        requests.append("repeated section headings detected: " + ", ".join(duplicate_headings))

    memory_matches: list[str] = []
    editorial_text = "\n".join(
        section.body
        for section in sections
        if not _is_sources_or_non_editorial(section.heading)
    )
    current_text = _normalise(editorial_text)
    for topic in previous_topics or []:
        topic_normalised = _normalise(topic)
        if len(topic_normalised) >= 8 and topic_normalised in current_text:
            memory_matches.append(topic)
    if memory_matches:
        requests.append("previous-topic memory match requires Chief Editor review: " + ", ".join(memory_matches))

    report = {
        "date": edition_date,
        "validation_status": "PASS" if total >= total_min and not requests else "FAIL",
        "total_word_count": total,
        "total": {
            "hard_min_words": total_min,
            "target_range": list(total_target) if total_target[0] is not None else None,
            "pass": total >= total_min,
        },
        "per_section_word_counts": section_report,
        "allowed_exceptions": exceptions,
        "repeated_topic_check": {
            "pass": repeated_topic_pass and not memory_matches,
            "duplicate_headings": duplicate_headings,
            "memory_matches": memory_matches,
            "memory_review_required": bool(memory_matches),
        },
        "chief_editor_regeneration_requests": requests,
    }
    return report


def language_has_arabic_script(markdown: str) -> bool:
    return bool(ARABIC_SCRIPT.search(markdown))
