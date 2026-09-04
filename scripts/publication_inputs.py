"""Fail-closed checks for the dated, immutable inputs to binary publication."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit, unquote
from xml.etree import ElementTree as ET

from scripts.reader_facing_qa import lint_markdown, ARABIC_SCRIPT, MOJIBAKE


def canonical_date(value: str) -> str:
    if date.fromisoformat(value).isoformat() != value:
        raise ValueError("date must be exactly YYYY-MM-DD")
    return value


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def safe_asset(root: Path, edition: Path, declared: str) -> Path:
    if not isinstance(declared, str) or not declared or "\\" in declared:
        raise ValueError("cover_asset_path must be a repository-relative POSIX path")
    if urlsplit(declared).scheme or Path(declared).is_absolute() or ".." in Path(declared).parts:
        raise ValueError("unsafe cover_asset_path")
    result = (root / declared).resolve()
    if not result.is_relative_to(edition.resolve()) or not result.is_file() or not result.stat().st_size:
        raise ValueError("canonical cover must exist inside this edition; no filename fallback")
    return result


class VisibleHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.links, self.resources, self.ids = [], [], [], []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in {"head", "script", "style", "nav"}:
            self.hidden += 1
        if tag in {"script", "iframe", "object", "embed", "base"}:
            raise ValueError(f"active/embedded publication content forbidden: {tag}")
        if any(k.startswith("on") for k in attrs):
            raise ValueError("event handlers forbidden in publication content")
        if "id" in attrs:
            self.ids.append(attrs["id"])
        if tag == "a":
            self.links.append(attrs.get("href", ""))
        if "src" in attrs:
            self.resources.append(attrs["src"])
        if tag == "link" and attrs.get("rel") == "stylesheet":
            self.resources.append(attrs.get("href", ""))

    def handle_endtag(self, tag):
        if tag in {"head", "script", "style", "nav"}:
            self.hidden -= 1

    def handle_data(self, data):
        if self.hidden == 0:
            self.parts.append(data)


def visible(text: str) -> VisibleHTML:
    parser = VisibleHTML()
    parser.feed(text)
    if len(parser.ids) != len(set(parser.ids)):
        raise ValueError("duplicate HTML IDs")
    return parser


def tokens(text: str) -> list[str]:
    return re.findall(r"\w+", text.casefold())


def source_records(value):
    records = value.get("sources") if isinstance(value, dict) else value
    if not isinstance(records, list) or not records:
        raise ValueError("sources.json must contain non-empty sources")
    result = {}
    for item in records:
        key, url = item.get("source_id", item.get("id")), item.get("exact_url", item.get("url"))
        if not key or key in result or not isinstance(url, str) or urlsplit(url).scheme not in {"http", "https"} or not urlsplit(url).netloc:
            raise ValueError("duplicate source ID or invalid source URL")
        result[key] = url
    return result


def validate_inputs(root: Path, value: str) -> tuple[Path, Path, dict[str, str]]:
    value = canonical_date(value)
    edition = root / "editions" / value[:4] / value[5:7] / value
    run = root / "daily-runs" / value
    paths = [edition / n for n in ("edition.md", "sources.json", "edition.html", "print.css", "epub-content.xhtml")]
    paths += [run / n for n in ("editorial-report.json", "cover-brief.json", "current-news.json", "deep-features.json")]
    payload = {}
    for path in paths + [edition / "manifest.json", run / "status.json", run / "publishing-report.json"]:
        text = path.read_text(encoding="utf-8")
        if not text.strip():
            raise ValueError(f"empty input: {path.name}")
        if path.suffix == ".json":
            payload[path.name] = json.loads(text)
            if isinstance(payload[path.name], dict) and payload[path.name].get("date") != value:
                raise ValueError(f"wrong or missing date: {path.name}")
    status = payload["status.json"]
    for field in ("current_research", "deep_research", "editorial", "cover", "publishing"):
        if status.get(field) != "COMPLETE":
            raise ValueError(f"prerequisite {field} is not COMPLETE")
    manifest, brief, report = (payload[n] for n in ("manifest.json", "cover-brief.json", "editorial-report.json"))
    if manifest.get("publication_source_package") != "COMPLETE" or status.get("publication_source_package") != "COMPLETE":
        raise ValueError("publication source package is not COMPLETE")
    if report.get("fact_check_status") != "PASS" or report.get("darija_status") != "PASS" or report.get("arabic_script_count") != 0:
        raise ValueError("editorial evidence gates have not passed")
    cover = safe_asset(root, edition, brief.get("cover_asset_path"))
    for key in ("cover_asset_type", "cover_asset_path"):
        if manifest.get(key) != brief.get(key) or status.get(key) != brief.get(key):
            raise ValueError(f"cover metadata mismatch: {key}")
    if brief.get("visual_qa_status") != "PASS" or status.get("visual_qa_status") != "PASS":
        raise ValueError("cover visual QA has not passed")
    kind = brief.get("cover_asset_type")
    if kind == "SVG_FALLBACK":
        svg = ET.fromstring(cover.read_bytes())
        if svg.tag != "{http://www.w3.org/2000/svg}svg" or cover.suffix != ".svg":
            raise ValueError("invalid canonical SVG")
        box = [float(x) for x in svg.attrib.get("viewBox", "").replace(",", " ").split()]
        if len(box) != 4 or box[2] <= 0 or box[3] <= 0 or abs(box[2] / box[3] - .75) > .01:
            raise ValueError("cover SVG must have a usable 3:4 viewBox")
        text = " ".join(svg.itertext())
        for element in svg.iter():
            if element.tag.rsplit("}", 1)[-1] in {"script", "foreignObject", "image", "use"}:
                raise ValueError("SVG must be self-contained vector artwork")
            if any(key.lower().startswith("on") or key.endswith("href") for key in element.attrib):
                raise ValueError("active or external SVG references forbidden")
        if "url(" in cover.read_text(encoding="utf-8").lower():
            raise ValueError("SVG resource URLs are not supported; use solid fills")
        if ARABIC_SCRIPT.search(text) or MOJIBAKE.search(text) or value not in text or "DRAGON" not in text:
            raise ValueError("invalid SVG text/date/masthead")
    elif kind == "AI_GENERATED":
        if brief.get("image_generation_status") != "PASS":
            raise ValueError("generated cover lacks generation PASS")
        from PIL import Image
        with Image.open(cover) as image:
            if abs(image.width / image.height - .75) > .04:
                raise ValueError("generated cover must be 3:4")
            image.verify()
    else:
        raise ValueError("unsupported canonical cover type")
    markdown = (edition / "edition.md").read_text(encoding="utf-8")
    issues = lint_markdown(markdown)
    if issues:
        raise ValueError("; ".join(issues))
    if ARABIC_SCRIPT.search(markdown):
        raise ValueError("canonical edition contains Arabic-script characters")
    from scripts.editorial_depth import evaluate, load_policy
    depth = evaluate(markdown, load_policy(root / "config/editorial-depth.yaml"), edition_date=value)
    if depth["validation_status"] != "PASS":
        raise ValueError("editorial depth failed: " + "; ".join(depth["chief_editor_regeneration_requests"]))
    from markdown_it import MarkdownIt
    canonical = tokens(" ".join(visible(MarkdownIt().render(markdown)).parts))
    sources = source_records(payload["sources.json"])
    if set(re.findall(r"\[(S\d+)\]", markdown)) - sources.keys():
        raise ValueError("unresolved Markdown source IDs")
    for name in ("edition.html", "epub-content.xhtml"):
        text = (edition / name).read_text(encoding="utf-8")
        doc = visible(text)
        if name.endswith("xhtml"):
            if ET.fromstring(text).tag != "{http://www.w3.org/1999/xhtml}html":
                raise ValueError("EPUB source is not XHTML")
        if ARABIC_SCRIPT.search(" ".join(doc.parts)) or MOJIBAKE.search(" ".join(doc.parts)):
            raise ValueError(f"reader text encoding/language failure: {name}")
        # Exact normalized prose equality: markup may differ; omissions/reordering may not.
        if tokens(" ".join(doc.parts)) != canonical:
            raise ValueError(f"STALE_PUBLICATION_SOURCE: {name} must preserve all canonical prose in order (keep extra navigation inside nav)")
        if set(sources.values()) - set(doc.links):
            raise ValueError(f"missing clickable source URLs: {name}")
        for link in doc.links:
            if link.startswith("#") and unquote(link[1:]) not in doc.ids:
                raise ValueError(f"unresolved internal link: {link}")
        for resource in doc.resources:
            if urlsplit(resource).scheme or resource.startswith("//"):
                raise ValueError("publication resources must be archived locally")
            resource_path = (edition / unquote(resource.split("#")[0])).resolve()
            if not resource_path.is_relative_to(edition.resolve()) or not resource_path.is_file():
                raise ValueError(f"missing/unsafe publication resource: {resource}")
            paths.append(resource_path)
    paths.append(cover)
    paths.append(root / "config/editorial-depth.yaml")
    return edition, cover, {str(p.relative_to(root)).replace("\\", "/"): digest(p) for p in paths}
