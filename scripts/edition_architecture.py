"""Validate DRAGON's version-4 newspaper inventory and article plan."""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

from scripts.editorial_depth import count_words

H2 = re.compile(r"^##\s+(.+?)\s*$")
H3_OR_DEEPER = re.compile(r"^(#{3,6})\s+(.+?)\s*$")


def load_architecture(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("version") != 4:
        raise ValueError("edition architecture must be a version-4 mapping")
    return value


def normalise(value: str) -> str:
    value = re.sub(r"\[S\d+\]", "", value).casefold().replace("—", "-")
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def markdown_outline(markdown: str) -> tuple[set[str], dict[str, str]]:
    """Return H2 sections and body text keyed by each H3-or-deeper headline."""
    sections: set[str] = set()
    articles: dict[str, str] = {}
    heading: str | None = None
    body: list[str] = []
    for line in markdown.splitlines():
        h2 = H2.match(line)
        h3 = H3_OR_DEEPER.match(line)
        if h2:
            if heading is not None:
                articles.setdefault(normalise(heading), "\n".join(body))
            sections.add(normalise(h2.group(1)))
            heading, body = None, []
        elif h3:
            if heading is not None:
                articles.setdefault(normalise(heading), "\n".join(body))
            heading, body = h3.group(2), []
        elif heading is not None:
            body.append(line)
    if heading is not None:
        articles.setdefault(normalise(heading), "\n".join(body))
    return sections, articles


def _range(rule: dict[str, Any], key: str) -> tuple[int, int]:
    values = rule.get(key)
    if not isinstance(values, list) or len(values) != 2:
        raise ValueError(f"architecture {key} must be a two-value list")
    return int(values[0]), int(values[1])


def validate_plan(
    plan: dict[str, Any], architecture: dict[str, Any], markdown: str, *, edition_date: str
) -> dict[str, Any]:
    """Return deterministic gate data; callers turn non-empty errors into failure."""
    errors: list[str] = []
    if plan.get("date") != edition_date:
        errors.append("edition plan date does not match edition")
    if plan.get("timezone") != "Africa/Casablanca":
        errors.append("edition plan timezone must be Africa/Casablanca")
    if plan.get("edition_architecture_version") != 4:
        errors.append("edition plan must declare edition_architecture_version 4")

    expected = {item["id"]: item for item in architecture["section_inventory"]}
    entries = plan.get("sections")
    if not isinstance(entries, list):
        return {"validation_status": "FAIL", "errors": errors + ["edition plan sections must be a list"]}
    ids = [entry.get("section_id") for entry in entries if isinstance(entry, dict)]
    if len(ids) != len(entries) or len(ids) != len(set(ids)):
        errors.append("edition plan has missing or duplicate section IDs")
    if set(ids) != set(expected):
        errors.append("edition plan must contain each inventory section exactly once")

    headings, articles_in_markdown = markdown_outline(markdown)
    formats = architecture["formats"]
    format_count: Counter[str] = Counter()
    active: set[str] = set()
    planned_words = 0
    story_ids: set[str] = set()

    for entry in entries:
        if not isinstance(entry, dict):
            errors.append("edition plan section entry must be an object")
            continue
        section_id = entry.get("section_id")
        if section_id not in expected:
            continue
        status = entry.get("status")
        if status not in {"ACTIVE", "SKIPPED"}:
            errors.append(f"{section_id} must be ACTIVE or SKIPPED")
            continue
        expected_heading = normalise(expected[section_id]["reader_heading"])
        if status == "SKIPPED":
            if not isinstance(entry.get("skip_reason"), str) or len(entry["skip_reason"].strip()) < 16:
                errors.append(f"{section_id} skipped without a specific reason")
            continue
        active.add(section_id)
        if expected_heading not in headings:
            errors.append(f"{section_id} ACTIVE but its reader-facing H2 is missing")
        listed = entry.get("articles")
        if not isinstance(listed, list) or not listed:
            errors.append(f"{section_id} ACTIVE without planned articles")
            continue
        for article in listed:
            if not isinstance(article, dict):
                errors.append(f"{section_id} has a non-object article")
                continue
            story_id, headline, fmt = article.get("story_id"), article.get("headline"), article.get("format")
            if not isinstance(story_id, str) or not story_id or story_id in story_ids:
                errors.append(f"{section_id} has missing or duplicate story_id")
            else:
                story_ids.add(story_id)
            if fmt not in formats:
                errors.append(f"{section_id} uses an unknown format")
                continue
            format_count[fmt] += 1
            if not isinstance(headline, str) or normalise(headline) not in articles_in_markdown:
                errors.append(f"{section_id} planned headline is missing from Markdown")
                continue
            budget = article.get("word_budget")
            low, high = _range(formats[fmt], "words")
            if not isinstance(budget, int) or not low <= budget <= high:
                errors.append(f"{section_id} {fmt} word_budget is outside {low}-{high}")
            else:
                planned_words += budget
            body = articles_in_markdown[normalise(headline)]
            actual_words = count_words(body)
            if actual_words < low:
                errors.append(f"{section_id} {fmt} is only {actual_words} words; minimum is {low}")
            requirements = formats[fmt].get("requires", [])
            if "byline" in requirements and "tahrir:" not in body.casefold():
                errors.append(f"{section_id} {fmt} has no Tahrir byline")
            if "standfirst" in requirements and not any(line.strip().startswith("*") for line in body.splitlines()):
                errors.append(f"{section_id} {fmt} has no standfirst")
            if "citations" in requirements and not re.search(r"\[S\d+\]", body):
                errors.append(f"{section_id} {fmt} has no source citation")

    for rule in architecture["coverage_rules"]:
        active_count = len(active.intersection(rule["sections"]))
        if active_count < int(rule["minimum_active"]):
            errors.append(f"coverage rule {rule['id']} needs {rule['minimum_active']} active sections, has {active_count}")

    edition_rule = architecture["edition"]
    for label, count in (("lead_article", format_count["lead_article"]), ("brief", format_count["brief"]), ("long_form", format_count["long_form"])):
        config_key = {"lead_article": "lead_articles", "brief": "briefs", "long_form": "long_form_features"}[label]
        low, high = _range(edition_rule, config_key)
        if not low <= count <= high:
            errors.append(f"edition needs {low}-{high} {label} items, has {count}")
    secondary = sum(format_count[name] for name in ("standard_article", "analysis", "explainer", "fact_check", "data_story", "opinion", "interview_qa", "timeline"))
    low, high = _range(edition_rule, "secondary_articles")
    if not low <= secondary <= high:
        errors.append(f"edition needs {low}-{high} secondary articles, has {secondary}")

    total_words = count_words(markdown)
    if total_words < int(edition_rule["hard_min_words"]):
        errors.append(f"edition has {total_words} words; architecture minimum is {edition_rule['hard_min_words']}")
    budget = plan.get("edition_word_budget")
    minimum, maximum = _range({"target": edition_rule["target_words"].split("-")}, "target")
    if not isinstance(budget, int) or not minimum <= budget <= maximum:
        errors.append(f"edition_word_budget must be {minimum}-{maximum}")
    if planned_words < int(edition_rule["hard_min_words"]):
        errors.append("planned article word budgets do not reach the edition minimum")

    return {
        "validation_status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "active_sections": sorted(active),
        "skipped_sections": sorted(set(expected) - active),
        "format_counts": dict(format_count),
        "planned_word_count": planned_words,
        "actual_word_count": total_words,
    }


def validate_daily_architecture(root: Path, edition_date: str, markdown: str, editorial_report: dict[str, Any]) -> dict[str, Any]:
    """Apply v4 only when the editor explicitly declares it; keep archives valid."""
    if editorial_report.get("edition_architecture_version") != 4:
        return {"validation_status": "LEGACY_NOT_REQUIRED", "errors": []}
    plan_path = root / "daily-runs" / edition_date / "edition-plan.json"
    if not plan_path.is_file():
        raise ValueError("version-4 editorial report requires edition-plan.json")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    architecture = load_architecture(root / "config" / "edition-architecture.yaml")
    return validate_plan(plan, architecture, markdown, edition_date=edition_date)
