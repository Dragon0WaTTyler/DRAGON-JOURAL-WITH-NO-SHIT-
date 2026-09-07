#!/usr/bin/env python3
"""Build reader-facing V4 HTML and XHTML directly from the canonical edition."""
from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CITATION = re.compile(r"\[(S\d+)\]")
FORMAT_CLASS = {
    "lead_article": "article--lead",
    "standard_article": "article--standard",
    "long_form": "article--long-form",
    "analysis": "article--analysis",
    "explainer": "article--explainer",
    "fact_check": "article--fact-check",
    "data_story": "sidebar",
    "opinion": "article--opinion",
    "interview_qa": "article--interview",
    "brief": "brief",
    "timeline": "sidebar",
}


def normalise(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold().replace("—", "-")).strip()


def edition_dir(day: str) -> Path:
    return ROOT / "editions" / day[:4] / day[5:7] / day


def source_urls(value: object) -> dict[str, str]:
    records = value.get("sources", value) if isinstance(value, dict) else value
    if not isinstance(records, list):
        raise ValueError("sources.json must contain a source list")
    result: dict[str, str] = {}
    for item in records:
        if not isinstance(item, dict):
            continue
        key = str(item.get("source_id", item.get("id", "")))
        url = str(item.get("exact_url", item.get("url", "")))
        if key and url.startswith(("https://", "http://")):
            result[key] = url
    if not result:
        raise ValueError("sources.json has no usable URLs")
    return result


def prose(text: str, urls: dict[str, str]) -> str:
    escaped = html.escape(text.strip(), quote=False)
    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        url = urls.get(key)
        return f'<a href="{html.escape(url, quote=True)}">[{key}]</a>' if url else match.group(0)
    return CITATION.sub(replace, escaped)


def plan_index(plan: dict) -> dict[str, dict[str, str]]:
    index: dict[str, dict[str, str]] = {}
    for section in plan.get("sections", []):
        if not isinstance(section, dict) or section.get("status") != "ACTIVE":
            continue
        section_id = str(section.get("section_id", ""))
        for article in section.get("articles", []):
            if isinstance(article, dict):
                index[normalise(str(article.get("headline", "")))] = {
                    "story_id": str(article.get("story_id", "")),
                    "section_id": section_id,
                    "format": str(article.get("format", "")),
                }
    return index


def blocks(markdown: str, index: dict[str, dict[str, str]], urls: dict[str, str]) -> str:
    lines = markdown.splitlines()
    body: list[str] = []
    current_section: str | None = None
    current_article: dict[str, str] | None = None
    paragraph: list[str] = []

    def flush_paragraph() -> None:
        nonlocal paragraph
        if not paragraph:
            return
        raw = " ".join(line.strip() for line in paragraph).strip()
        paragraph = []
        if not raw:
            return
        if raw.startswith("*") and raw.endswith("*"):
            body.append(f'<p class="standfirst">{prose(raw[1:-1], urls)}</p>')
        elif raw.casefold().startswith("tahrir:"):
            body.append(f'<p class="byline">{prose(raw, urls)}</p>')
        else:
            body.append(f"<p>{prose(raw, urls)}</p>")

    def close_article() -> None:
        nonlocal current_article
        flush_paragraph()
        if current_article is not None:
            body.append("</article>")
            current_article = None

    def close_section() -> None:
        nonlocal current_section
        close_article()
        if current_section is not None:
            body.append("</section>")
            current_section = None

    def open_article(headline: str) -> None:
        nonlocal current_article
        close_article()
        meta = index.get(normalise(headline))
        if meta is None:
            raise ValueError(f"headline absent from active edition plan: {headline}")
        css_class = FORMAT_CLASS.get(meta["format"])
        if not meta["story_id"] or not css_class:
            raise ValueError(f"invalid V4 plan metadata for: {headline}")
        current_article = meta
        body.append(
            '<article class="article ' + css_class + '" id="story-' + html.escape(meta["story_id"], quote=True)
            + '" data-story-id="' + html.escape(meta["story_id"], quote=True)
            + '" data-section-id="' + html.escape(meta["section_id"], quote=True)
            + '" data-format="' + html.escape(meta["format"], quote=True) + '"><h3>' + prose(headline, urls) + "</h3>"
        )

    masthead_seen = False
    for line in lines:
        if line.startswith("# "):
            body.append('<header class="paper-header"><h1>' + prose(line[2:], urls) + "</h1>")
            masthead_seen = True
            continue
        if masthead_seen and line.strip() and line[:1] not in {"#"} and current_section is None:
            body.append('<p class="date">' + prose(line, urls) + "</p></header>")
            masthead_seen = False
            continue
        if line.startswith("## "):
            close_section()
            heading = line[3:].strip()
            section_slug = re.sub(r"[^a-z0-9]+", "-", heading.casefold()).strip("-")
            current_section = section_slug or "section"
            body.append(f'<section class="edition-section" id="section-{html.escape(current_section, quote=True)}"><header class="section-header"><h2>{prose(heading, urls)}</h2></header>')
            continue
        if line.startswith("### "):
            headline = line[4:].strip()
            if normalise(headline) == "briefs":
                close_article()
                body.append('<h3 class="brief-cluster-heading">Briefs</h3>')
            else:
                open_article(headline)
            continue
        if line.startswith("#### "):
            open_article(line[5:].strip())
            continue
        if not line.strip():
            flush_paragraph()
        elif current_article is not None:
            paragraph.append(line)
    close_section()
    return "\n".join(body)


def build(day: str) -> None:
    edition = edition_dir(day)
    run = ROOT / "daily-runs" / day
    markdown = (edition / "edition.md").read_text(encoding="utf-8")
    plan = json.loads((run / "edition-plan.json").read_text(encoding="utf-8"))
    urls = source_urls(json.loads((edition / "sources.json").read_text(encoding="utf-8")))
    content = blocks(markdown, plan_index(plan), urls)
    links = "".join(f'<a href="{html.escape(url, quote=True)}"></a>' for url in urls.values())
    common_head = f'<meta charset="utf-8"><meta name="date" content="{day}"><meta name="timezone" content="Africa/Casablanca"><title>DRAGON — {day}</title><link rel="stylesheet" href="print.css">'
    document = '<!doctype html><html lang="ary-Latn" dir="ltr"><head>' + common_head + '</head><body dir="ltr"><nav aria-label="Sources">' + links + '</nav><main>' + content + '</main></body></html>\n'
    xhtml = '<?xml version="1.0" encoding="utf-8"?>\n<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="ary-Latn" lang="ary-Latn" dir="ltr"><head>' + common_head.replace('<meta charset="utf-8">', '<meta charset="utf-8" />').replace('<meta name="date" content="' + day + '">', '<meta name="date" content="' + day + '" />').replace('<meta name="timezone" content="Africa/Casablanca">', '<meta name="timezone" content="Africa/Casablanca" />').replace('<link rel="stylesheet" href="print.css">', '<link rel="stylesheet" href="print.css" />') + '</head><body dir="ltr"><nav aria-label="Sources">' + links + '</nav><main>' + content + '</main></body></html>\n'
    (edition / "edition.html").write_text(document, encoding="utf-8")
    (edition / "epub-content.xhtml").write_text(xhtml, encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    args = parser.parse_args()
    build(args.date)
