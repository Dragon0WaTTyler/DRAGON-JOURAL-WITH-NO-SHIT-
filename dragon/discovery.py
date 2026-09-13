"""Source-provider registry plus bounded RSS and HTML extraction adapters."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
import hashlib
from ipaddress import ip_address
import json
from pathlib import Path
import socket
import time
import re
from typing import Callable
from urllib.parse import urljoin, urlparse, urlunsplit
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener
from xml.etree import ElementTree

from jsonschema import Draft202012Validator
import yaml


SUPPORTED_ADAPTERS = {"seed-list", "rss", "html-trafilatura", "structured-document"}


class DiscoveryError(RuntimeError):
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class FetchResponse:
    url: str
    status: int
    content_type: str
    body: bytes
    redirect_count: int = 0
    elapsed_ms: int | None = None


Transport = Callable[[str, int, int], FetchResponse]
# A deferred browser extractor (for example Crawl4AI) is injected explicitly.
# It is never imported, installed, or selected as the ordinary extraction path.
ExtractionFallback = Callable[[FetchResponse, str], dict | None]


def assess_source_url(url: str, *, resolve_dns: bool = False) -> dict:
    """Return URL network-safety facts independently of source ownership."""
    parsed = urlparse(url)
    hostname = parsed.hostname
    details = {"url": url, "scheme": parsed.scheme.casefold(), "hostname": hostname.casefold() if hostname else None,
               "port": None, "path": parsed.path, "query": parsed.query, "fragment": parsed.fragment,
               "state": "URL_SAFE_SOURCE_UNKNOWN", "reason": None}
    if parsed.scheme.casefold() != "https" or not hostname or not parsed.netloc:
        details.update(state="URL_UNSAFE", reason="UNSUPPORTED_SCHEME_OR_MALFORMED_HOST")
        return details
    try:
        port = parsed.port
    except ValueError as exc:
        details.update(state="URL_UNSAFE", reason="MALFORMED_PORT")
        return details
    details["port"] = port or 443
    if parsed.username is not None or parsed.password is not None:
        details.update(state="URL_UNSAFE", reason="EMBEDDED_CREDENTIALS")
        return details
    normalized = hostname.rstrip(".").casefold()
    if normalized == "localhost" or normalized.endswith((".localhost", ".local", ".internal")):
        details.update(state="URL_UNSAFE", reason="LOCAL_HOSTNAME")
        return details
    try:
        literal = ip_address(normalized)
    except ValueError:
        literal = None
    if literal is not None and not literal.is_global:
        details.update(state="URL_UNSAFE", reason="PRIVATE_OR_RESERVED_ADDRESS")
        return details
    if port not in (None, 443):
        details.update(state="URL_UNSAFE", reason="UNSAFE_PORT")
        return details
    if not resolve_dns or literal is not None:
        return details
    try:
        addresses = {
            item[4][0]
            for item in socket.getaddrinfo(
                hostname, port or 443, type=socket.SOCK_STREAM
            )
        }
    except OSError as exc:
        details.update(state="URL_UNSAFE", reason="DNS_RESOLUTION_FAILED")
        return details
    if not addresses:
        details.update(state="URL_UNSAFE", reason="DNS_NO_ADDRESSES")
        return details
    if any(not ip_address(address.split("%", 1)[0]).is_global for address in addresses):
        details.update(state="URL_UNSAFE", reason="DNS_RESOLVES_PRIVATE_OR_RESERVED")
        return details
    details["state"] = "URL_SAFE_SOURCE_UNKNOWN"
    return details


def _validate_source_url(
    url: str, *, error_code: str = "SOURCE_URL_UNSAFE", resolve_dns: bool = False
) -> None:
    details = assess_source_url(url, resolve_dns=resolve_dns)
    if details["state"] == "URL_UNSAFE":
        reason = details.get("reason") or "URL_UNSAFE"
        code = "SOURCE_FETCH_FAILED" if reason == "DNS_RESOLUTION_FAILED" or reason == "DNS_NO_ADDRESSES" else error_code
        raise DiscoveryError(code, reason)


class _SafeRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        _validate_source_url(
            new_url, error_code="SOURCE_REDIRECT_UNSAFE", resolve_dns=True
        )
        return super().redirect_request(
            request, file_pointer, code, message, headers, new_url
        )


def _fetch(
    url: str, transport: Transport, timeout_seconds: int, maximum_bytes: int
) -> FetchResponse:
    _validate_source_url(url)
    started = time.monotonic()
    try:
        response = transport(url, timeout_seconds, maximum_bytes)
    except DiscoveryError:
        raise
    except TimeoutError as exc:
        raise DiscoveryError("TIMEOUT", str(exc) or url) from exc
    except OSError as exc:
        detail = str(exc) or url
        lowered = detail.casefold()
        code = "TLS_FAILED" if "ssl" in lowered or "tls" in lowered or "certificate" in lowered else "DNS_FAILED" if "name or service" in lowered or "resolve" in lowered else "CONNECTION_FAILED"
        raise DiscoveryError(code, detail) from exc
    _validate_source_url(response.url, error_code="SOURCE_REDIRECT_UNSAFE")
    if len(response.body) > maximum_bytes:
        raise DiscoveryError("SOURCE_RESPONSE_TOO_LARGE", f"response exceeds {maximum_bytes} bytes")
    if response.status in {401, 403, 404, 429}:
        raise DiscoveryError(f"HTTP_{response.status}", f"HTTP {response.status}")
    if 500 <= response.status <= 599:
        raise DiscoveryError("HTTP_5XX", f"HTTP {response.status}")
    if response.status < 200 or response.status >= 300:
        raise DiscoveryError("SOURCE_HTTP_FAILED", f"HTTP {response.status}")
    if not response.body.strip():
        raise DiscoveryError("EMPTY_RESPONSE", response.url)
    return FetchResponse(response.url, response.status, response.content_type, response.body, response.redirect_count, response.elapsed_ms or round((time.monotonic() - started) * 1000))


def _article_attribution(html: bytes) -> dict:
    """Extract deterministic article-lineage hints; none confer evidence trust."""
    text = html.decode("utf-8", errors="replace")
    def meta(*names: str) -> str | None:
        for name in names:
            match = re.search(rf"<meta[^>]+(?:name|property)=[\"']{re.escape(name)}[\"'][^>]+content=[\"']([^\"']+)", text, re.I)
            if match:
                return match.group(1).strip()
        return None
    author = meta("author", "article:author")
    body = re.sub(r"<[^>]+>", " ", text)
    lowered = body.casefold()
    wire = next((name for marker, name in (("reuters", "REUTERS"), ("associated press", "AP"), ("agence france-presse", "AFP"), ("afp", "AFP")) if marker in lowered), None)
    partner = next((marker for marker in ("in partnership with", "partner content", "republished from", "courtesy of") if marker in lowered), None)
    if wire:
        state = "WIRE_REPUBLICATION"
    elif partner:
        state = "PARTNER_REPUBLICATION"
    elif author:
        state = "ORIGINAL_UNKNOWN"
    else:
        state = "SYNDICATION_UNRESOLVED"
    return {"author_byline": author, "wire_credit": wire, "partner_credit": partner, "article_origin_state": state}


class _ArticleMetadataParser(HTMLParser):
    """Small tolerant HTML collector for article metadata, not article text.

    Trafilatura remains the body extractor.  This collector only preserves the
    publisher-provided metadata that many news pages expose outside the body.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self.title_parts: list[str] = []
        self.h1_parts: list[str] = []
        self.times: list[str] = []
        self.jsonld: list[str] = []
        self._capture: str | None = None
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {str(key).casefold(): value for key, value in attrs}
        if tag == "meta":
            key = str(values.get("property") or values.get("name") or values.get("itemprop") or "").casefold()
            value = values.get("content")
            if key and value and key not in self.meta:
                self.meta[key] = str(value).strip()
        elif tag == "time":
            value = values.get("datetime")
            if value:
                self.times.append(str(value).strip())
        if tag == "title":
            self._capture, self._parts = "title", []
        elif tag == "h1" and not self.h1_parts:
            self._capture, self._parts = "h1", []
        elif tag == "script" and "ld+json" in str(values.get("type") or "").casefold():
            self._capture, self._parts = "jsonld", []

    def handle_data(self, data: str) -> None:
        if self._capture:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        expected = {"title": "title", "h1": "h1", "script": "jsonld"}.get(tag)
        if expected != self._capture:
            return
        value = " ".join("".join(self._parts).split()).strip()
        if value:
            if self._capture == "title":
                self.title_parts.append(value)
            elif self._capture == "h1":
                self.h1_parts.append(value)
            else:
                self.jsonld.append(value)
        self._capture, self._parts = None, []


def _jsonld_nodes(value: object) -> list[dict]:
    """Flatten JSON-LD objects, arrays and @graph containers safely."""
    nodes: list[dict] = []
    if isinstance(value, list):
        for item in value:
            nodes.extend(_jsonld_nodes(item))
    elif isinstance(value, dict):
        nodes.append(value)
        graph = value.get("@graph")
        if graph is not None:
            nodes.extend(_jsonld_nodes(graph))
    return nodes


def _jsonld_article_nodes(payloads: list[str]) -> list[dict]:
    nodes: list[dict] = []
    for payload in payloads:
        try:
            parsed = json.loads(payload)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        for item in _jsonld_nodes(parsed):
            types = item.get("@type", [])
            types = [types] if isinstance(types, str) else types if isinstance(types, list) else []
            lowered = {str(value).casefold() for value in types}
            if lowered & {"newsarticle", "article", "reportagenewsarticle", "analysisnewsarticle", "liveblogposting"}:
                nodes.append(item)
    return nodes


def _first_nonempty(*values: object) -> str | None:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _named_jsonld(value: object) -> str | None:
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, dict):
        return _first_nonempty(value.get("name"), value.get("@id"), value.get("url"))
    if isinstance(value, list):
        names = [_named_jsonld(item) for item in value]
        return "; ".join(item for item in names if item) or None
    return None


def _normalized_article_date(value: object) -> tuple[str | None, str | None, str | None]:
    """Return raw, normalized value and precision without using crawl time."""
    raw = str(value or "").strip()
    if not raw:
        return None, None, None
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
            datetime.fromisoformat(raw)
            return raw, raw, "DATE"
        normalized = datetime.fromisoformat(raw.replace("Z", "+00:00")).isoformat()
        return raw, normalized, "TIMESTAMP"
    except ValueError:
        return raw, None, "UNPARSEABLE"


def extract_article_metadata(
    html: bytes,
    *,
    canonical_url: str,
    trafilatura_title: object = None,
    trafilatura_date: object = None,
    trafilatura_author: object = None,
) -> dict:
    """Extract deterministic article metadata independently from body text.

    Structured metadata identifies a publisher or an article but never assigns
    an evidence role.  Missing values are explicit states rather than fake
    titles or crawl-time publication dates.
    """
    parser = _ArticleMetadataParser()
    parser.feed(html.decode("utf-8", errors="replace"))
    articles = _jsonld_article_nodes(parser.jsonld)
    article = next((item for item in articles if item.get("headline") or item.get("datePublished") or item.get("publisher")), {})
    meta = parser.meta
    title, title_source = None, "TITLE_UNRESOLVED"
    title_candidates = (
        (_first_nonempty(article.get("headline")), "JSON_LD_HEADLINE"),
        (_first_nonempty(meta.get("og:title")), "OPEN_GRAPH_TITLE"),
        (_first_nonempty(meta.get("article:title"), meta.get("twitter:title"), meta.get("title")), "META_TITLE"),
        (_first_nonempty(parser.h1_parts[0] if parser.h1_parts else None), "HTML_H1"),
        (_first_nonempty(parser.title_parts[0] if parser.title_parts else None), "DOCUMENT_TITLE"),
        (_first_nonempty(trafilatura_title), "TRAFILATURA_TITLE"),
    )
    for candidate, source in title_candidates:
        if candidate:
            title, title_source = candidate, source
            break
    published_candidates = (
        (_first_nonempty(article.get("datePublished")), "JSON_LD_DATE_PUBLISHED", "PUBLICATION"),
        (_first_nonempty(meta.get("article:published_time"), meta.get("published-time"), meta.get("publishdate"), meta.get("publication_date"), meta.get("date"), meta.get("cxenseparse:publishtime")), "META_PUBLICATION_DATE", "PUBLICATION"),
        (_first_nonempty(parser.times[0] if parser.times else None), "HTML_TIME", "PUBLICATION"),
        (_first_nonempty(trafilatura_date), "TRAFILATURA_DATE", "PUBLICATION"),
        (_first_nonempty(article.get("dateModified"), meta.get("article:modified_time"), meta.get("modified-time"), meta.get("og:updated_time")), "MODIFIED_DATE_ONLY", "MODIFIED"),
    )
    raw_date = normalized_date = precision = date_source = date_kind = None
    for candidate, source, kind in published_candidates:
        raw_date, normalized_date, precision = _normalized_article_date(candidate)
        if raw_date:
            date_source, date_kind = source, kind
            break
    publisher = _named_jsonld(article.get("publisher"))
    publisher_source = "JSON_LD_PUBLISHER" if publisher else None
    if not publisher:
        publisher = _first_nonempty(meta.get("og:site_name"), meta.get("application-name"), meta.get("publisher"))
        publisher_source = "OPEN_GRAPH_SITE_NAME" if publisher else None
    author = _first_nonempty(_named_jsonld(article.get("author")), meta.get("author"), meta.get("article:author"), trafilatura_author)
    author_source = "JSON_LD_AUTHOR" if _named_jsonld(article.get("author")) else "META_OR_TRAFILAURA_AUTHOR" if author else None
    attribution = _article_attribution(html)
    if author and not attribution.get("author_byline"):
        attribution["author_byline"] = author
    attribution["author_source"] = author_source
    article_types = sorted({str(item) for node in articles for item in (node.get("@type") if isinstance(node.get("@type"), list) else [node.get("@type")]) if item})
    publisher_state = "PUBLISHER_RESOLVED_ARTICLE_ROLE_PENDING" if publisher else "PUBLISHER_UNRESOLVED"
    return {
        "metadata_extraction_status": "ARTICLE_METADATA_RESOLVED" if title or raw_date or publisher else "ARTICLE_METADATA_INSUFFICIENT",
        "title": title,
        "title_state": "TITLE_RESOLVED" if title else "TITLE_UNRESOLVED",
        "title_source": title_source,
        "publication_date": {"raw": raw_date, "normalized": normalized_date, "source": date_source, "kind": date_kind, "precision": precision},
        "publisher": {"name": publisher, "source": publisher_source, "state": publisher_state, "canonical_domain": urlparse(canonical_url).hostname},
        "attribution": attribution,
        "jsonld_article_types": article_types,
        "signals": {
            "html_title": _first_nonempty(parser.title_parts[0] if parser.title_parts else None),
            "h1": _first_nonempty(parser.h1_parts[0] if parser.h1_parts else None),
            "open_graph_title": _first_nonempty(meta.get("og:title")),
            "jsonld_headline": _first_nonempty(article.get("headline")),
        },
    }


def _published_at(value: object) -> tuple[str | None, list[str]]:
    if value is None or not str(value).strip():
        return None, ["PUBLISHED_AT_MISSING"]
    candidate = str(value).strip()
    try:
        datetime.fromisoformat(candidate.replace("Z", "+00:00"))
    except ValueError:
        return None, ["PUBLISHED_AT_INVALID"]
    return candidate, []


def load_provider_registry(path: Path, schema_path: Path | None = None) -> dict:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    schema_file = schema_path or path.with_name("provider-registry-schema.json")
    schema = json.loads(schema_file.read_text(encoding="utf-8"))
    errors = sorted(Draft202012Validator(schema).iter_errors(value), key=lambda item: list(item.path))
    if errors:
        detail = "; ".join(
            f"{'/'.join(str(part) for part in error.path) or '$'}: {error.message}"
            for error in errors
        )
        raise DiscoveryError("PROVIDER_REGISTRY_INVALID", detail)
    identifiers = [item["provider_id"] for item in value["providers"]]
    if len(identifiers) != len(set(identifiers)):
        raise DiscoveryError("PROVIDER_REGISTRY_INVALID", "provider_id values must be unique")
    return value


def load_extraction_adapter_config(path: Path) -> dict:
    """Load the optional-extractor contract without loading an extractor.

    This makes deferred browser tooling inspectable by preflight/tests while
    keeping Trafilatura as the only normal runtime dependency.
    """
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise DiscoveryError("EXTRACTION_ADAPTER_CONFIG_INVALID", str(exc)) from exc
    if set(value or {}) != {"version", "default_adapter", "fallbacks"} or value.get("version") != 1:
        raise DiscoveryError("EXTRACTION_ADAPTER_CONFIG_INVALID", "root fields or version are invalid")
    if value["default_adapter"] != "trafilatura" or not isinstance(value["fallbacks"], list):
        raise DiscoveryError("EXTRACTION_ADAPTER_CONFIG_INVALID", "Trafilatura must remain default")
    identifiers = set()
    required = {"adapter_id", "enabled", "trigger", "timeout_seconds", "cache_required", "integration_test_status", "classification", "provenance_behavior"}
    for adapter in value["fallbacks"]:
        if (
            not isinstance(adapter, dict) or set(adapter) != required
            or not isinstance(adapter["adapter_id"], str) or not adapter["adapter_id"]
            or adapter["adapter_id"] in identifiers or not isinstance(adapter["enabled"], bool)
            or adapter["trigger"] != "SOURCE_DYNAMIC_ROUTE_REQUIRED"
            or not isinstance(adapter["timeout_seconds"], int) or adapter["timeout_seconds"] < 1
            or not isinstance(adapter["cache_required"], bool)
            or adapter["integration_test_status"] not in {"PASS", "NOT_RUN", "FAIL"}
            or adapter["classification"] != "extraction-only"
        ):
            raise DiscoveryError("EXTRACTION_ADAPTER_CONFIG_INVALID", "fallback definition is invalid")
        if adapter["enabled"] and adapter["integration_test_status"] != "PASS":
            raise DiscoveryError("EXTRACTION_ADAPTER_CONFIG_INVALID", "enabled fallback is not proven")
        identifiers.add(adapter["adapter_id"])
    return value


def registry_report(registry: dict) -> dict:
    providers = []
    for item in registry["providers"]:
        adapter = item["adapter"]
        if not item["enabled"]:
            state = "DISABLED"
        elif adapter not in SUPPORTED_ADAPTERS:
            state = "UNAVAILABLE_ADAPTER"
        elif item.get("integration_test_status") == "PASS":
            state = "AVAILABLE"
        else:
            state = "CONFIGURED_NOT_PROVEN"
        providers.append(
            {
                "provider_id": item["provider_id"],
                "role": item["role"],
                "adapter": adapter,
                "required": item["required"],
                "authority_level": item["authority_level"],
                "health_state": state,
                "fallbacks": item["fallbacks"],
                "endpoints": item["endpoints"],
                "source_classification": item["source_classification"],
                "provenance_behavior": item["provenance_behavior"],
            }
        )
    unavailable_required = [
        item["provider_id"]
        for item in providers
        if item["required"] and item["health_state"] != "AVAILABLE"
    ]
    return {
        "schema_version": 1,
        "status": "FAIL" if unavailable_required else "PASS",
        "availability_semantics": "AVAILABLE requires a passing adapter integration test",
        "providers": providers,
        "summary": {
            "total": len(providers),
            "enabled": sum(item["health_state"] != "DISABLED" for item in providers),
            "available": sum(item["health_state"] == "AVAILABLE" for item in providers),
            "unavailable_required": unavailable_required,
        },
    }


def provider_prompt_context(registry: dict) -> dict:
    """Return bounded discovery hints; endpoints remain discovery-only evidence."""
    return {
        "priority_order": registry["priority_order"],
        "providers": [
            {
                "provider_id": item["provider_id"],
                "role": item["role"],
                "authority_level": item["authority_level"],
                "endpoints": item["endpoints"],
                "source_classification": item["source_classification"],
                "provenance_behavior": item["provenance_behavior"],
            }
            for item in registry["providers"]
            if item["enabled"]
        ],
        "warning": "Discovery endpoints are not verification; follow candidates to exact primary or independent evidence.",
        "open_discovery": {
            "allowed": True,
            "mode": "READ_ONLY_RESEARCH",
            "configured_sources_are": "PREFERRED_SEEDS_NOT_WHITELIST",
            "unknown_sources_begin_as": "LEAD",
            "untrusted_content_may_change_policy": False,
        },
        "material_routing": {
            "readable_html": "html-trafilatura",
            "pdf_office_table_json": "structured-document",
            "js_heavy": "approved-browser-fallback-only",
        },
    }


def discover_rss(xml: bytes, *, provider_id: str, endpoint: str) -> list[dict]:
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError as exc:
        raise DiscoveryError("DISCOVERY_FEED_INVALID", str(exc)) from exc
    candidates = []
    nodes = list(root.findall(".//item")) + list(root.findall(".//{http://www.w3.org/2005/Atom}entry"))
    for node in nodes:
        title = node.findtext("title") or node.findtext("{http://www.w3.org/2005/Atom}title") or ""
        link = node.findtext("link")
        if not link:
            atom_link = node.find("{http://www.w3.org/2005/Atom}link")
            link = atom_link.get("href") if atom_link is not None else None
        url = urljoin(endpoint, link or "")
        if urlparse(url).scheme != "https" or not urlparse(url).netloc:
            continue
        candidate = {
            "provider_id": provider_id,
            "title": title.strip(),
            "discovered_url": url,
            "verification_status": "DISCOVERY_ONLY",
        }
        # RSS/Atom feeds frequently expose the publisher separately from the
        # aggregator wrapper in ``<source url=...>``.  Preserve that hint as
        # discovery metadata only.  It is never treated as the fetched page,
        # ownership proof, or evidence; malformed/non-public hints are
        # discarded rather than weakening URL safety.
        source = node.find("source")
        if source is None:
            source = node.find("{http://www.w3.org/2005/Atom}source")
        if source is not None:
            source_url = str(source.get("url") or "").strip()
            parsed_source = urlparse(urljoin(endpoint, source_url)) if source_url else None
            hint = parsed_source.geturl() if parsed_source else ""
            hint_safety = assess_source_url(hint) if hint else {"state": "URL_UNSAFE"}
            if parsed_source and hint_safety.get("state") != "URL_UNSAFE":
                candidate["publisher_hint_url"] = urlunsplit((
                    parsed_source.scheme.casefold(),
                    parsed_source.netloc.casefold(),
                    parsed_source.path or "/",
                    parsed_source.query,
                    "",
                ))
            source_name = (source.text or "").strip()
            if source_name:
                candidate["publisher_hint_name"] = source_name
        description = node.findtext("description") or node.findtext("{http://www.w3.org/2005/Atom}summary")
        if description and str(description).strip():
            candidate["discovery_description"] = str(description).strip()
        candidates.append(candidate)
    return candidates


def default_transport(url: str, timeout_seconds: int, maximum_bytes: int) -> FetchResponse:
    _validate_source_url(url, resolve_dns=True)
    request = Request(url, headers={"User-Agent": "DRAGON/5 source-research (+local newsroom)"})
    opener = build_opener(_SafeRedirectHandler())
    try:
        with opener.open(request, timeout=timeout_seconds) as response:  # noqa: S310 - URL and DNS checked above
            final_url = response.geturl()
            _validate_source_url(final_url, error_code="SOURCE_REDIRECT_UNSAFE", resolve_dns=True)
            body = response.read(maximum_bytes + 1)
            if len(body) > maximum_bytes:
                raise DiscoveryError("SOURCE_RESPONSE_TOO_LARGE", f"response exceeds {maximum_bytes} bytes")
            return FetchResponse(final_url, int(response.status), response.headers.get_content_type(), body)
    except HTTPError as exc:
        final_url = exc.geturl()
        _validate_source_url(final_url, error_code="SOURCE_REDIRECT_UNSAFE", resolve_dns=True)
        body = exc.read(maximum_bytes + 1)
        if len(body) > maximum_bytes:
            raise DiscoveryError("SOURCE_RESPONSE_TOO_LARGE", f"response exceeds {maximum_bytes} bytes") from exc
        return FetchResponse(final_url, int(exc.code), exc.headers.get_content_type(), body)


def fetch_and_extract_html(
    url: str,
    *,
    transport: Transport = default_transport,
    timeout_seconds: int = 15,
    maximum_bytes: int = 5_000_000,
    retrieved_at: str | None = None,
    fallback_extractor: ExtractionFallback | None = None,
) -> dict:
    response = _fetch(url, transport, timeout_seconds, maximum_bytes)
    if response.content_type not in {"text/html", "application/xhtml+xml"}:
        raise DiscoveryError("SOURCE_MATERIAL_ROUTE_REQUIRED", response.content_type)
    try:
        from trafilatura import bare_extraction
    except ImportError as exc:
        raise DiscoveryError("EXTRACTION_ADAPTER_UNAVAILABLE", "trafilatura is not installed") from exc
    document = bare_extraction(
        response.body,
        url=response.url,
        include_comments=False,
        include_links=True,
        include_tables=True,
        favor_precision=True,
    )
    method = "trafilatura-bare-extraction"
    text = "" if document is None else str(document.as_dict().get("text") or "").strip()
    # A one-time, extraction-only retry is allowed after a successful HTML
    # fetch. It does not refetch, relax source policy, or invoke a browser.
    if document is None or len(text) < 200:
        retry = bare_extraction(
            response.body, url=response.url, include_comments=False,
            include_links=True, include_tables=True, favor_precision=False,
            favor_recall=True, fast=False,
        )
        retry_text = "" if retry is None else str(retry.as_dict().get("text") or "").strip()
        if retry is not None and len(retry_text) >= 200:
            document, text, method = retry, retry_text, "trafilatura-full-retry"
    if document is None:
        if b"<script" in response.body.lower():
            return _fallback_or_dynamic_route(response, url, retrieved_at, fallback_extractor, "static extraction returned no content")
        raise DiscoveryError("SOURCE_EXTRACTION_FAILED", response.url)
    extracted = document.as_dict()
    text = str(extracted.get("text") or "").strip()
    if len(text) < 200:
        if b"<script" in response.body.lower():
            return _fallback_or_dynamic_route(response, url, retrieved_at, fallback_extractor, "insufficient static text")
        raise DiscoveryError("SOURCE_EXTRACTION_LOW_QUALITY", f"only {len(text)} characters")
    quality = "HIGH" if len(text) >= 1_000 else "MEDIUM"
    timestamp = retrieved_at or datetime.now(timezone.utc).isoformat()
    article_metadata = extract_article_metadata(
        response.body, canonical_url=str(extracted.get("url") or response.url),
        trafilatura_title=extracted.get("title"), trafilatura_date=extracted.get("date"),
        trafilatura_author=extracted.get("author"),
    )
    date_info = article_metadata["publication_date"]
    published_at = date_info["normalized"]
    metadata_warnings = []
    if article_metadata["title_state"] == "TITLE_UNRESOLVED":
        metadata_warnings.append("TITLE_UNRESOLVED")
    if not date_info["raw"]:
        metadata_warnings.extend(["NO_PUBLICATION_DATE", "PUBLISHED_AT_MISSING"])
    elif not date_info["normalized"]:
        metadata_warnings.extend(["PUBLICATION_DATE_UNPARSEABLE", "PUBLISHED_AT_INVALID"])
    author = article_metadata["attribution"].get("author_byline")
    if not author:
        metadata_warnings.append("AUTHOR_MISSING")
    return {
        "canonical_url": str(extracted.get("url") or response.url),
        "discovered_url": url,
        "title": article_metadata["title"],
        "title_state": article_metadata["title_state"],
        "title_source": article_metadata["title_source"],
        "author": author,
        "publisher": article_metadata["publisher"].get("name") or extracted.get("sitename") or extracted.get("hostname") or urlparse(response.url).hostname,
        "published_at": published_at,
        "publication_date": date_info,
        "article_metadata": article_metadata,
        "retrieved_at": timestamp,
        "fetch_status": "FETCHED",
        "http_status": response.status,
        "content_type": response.content_type,
        "extraction_method": method,
        "extraction_quality": quality,
        "quality_score": min(1.0, round(len(text) / 1_000, 3)),
        "content_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "language": extracted.get("language"),
        "text": text,
        "links": extracted.get("links") or [],
        "metadata_warnings": sorted(metadata_warnings),
        "transport": {
            "requested_url": url, "final_url": response.url,
            "redirect_count": response.redirect_count, "http_status": response.status,
            "content_type": response.content_type, "response_bytes": len(response.body),
            "elapsed_ms": response.elapsed_ms, "fetch_backend": "safe-http",
            "extraction_backend": method,
        },
        "article_attribution": article_metadata["attribution"],
        "verification_status": "EXTRACTED_NOT_VERIFIED",
    }


def _fallback_or_dynamic_route(
    response: FetchResponse,
    discovered_url: str,
    retrieved_at: str | None,
    fallback_extractor: ExtractionFallback | None,
    reason: str,
) -> dict:
    """Run an explicitly supplied exceptional extractor, or fail closed.

    The returned material remains ``EXTRACTED_NOT_VERIFIED``.  A browser
    fallback is therefore only an extraction aid; it cannot turn discovery
    into evidence or bypass exact-page verification.
    """
    if fallback_extractor is None:
        raise DiscoveryError("SOURCE_DYNAMIC_ROUTE_REQUIRED", f"{reason} on a script-driven page")
    try:
        extracted = fallback_extractor(response, reason)
    except DiscoveryError:
        raise
    except Exception as exc:  # adapter errors must have a bounded diagnostic
        raise DiscoveryError("SOURCE_EXTRACTION_FALLBACK_FAILED", str(exc)) from exc
    if not isinstance(extracted, dict):
        raise DiscoveryError("SOURCE_EXTRACTION_FALLBACK_INVALID", "fallback returned no structured extraction")
    text = str(extracted.get("text") or "").strip()
    method = str(extracted.get("extraction_method") or "").strip()
    if len(text) < 200 or not method:
        raise DiscoveryError("SOURCE_EXTRACTION_FALLBACK_INVALID", "fallback text or method is insufficient")
    timestamp = retrieved_at or datetime.now(timezone.utc).isoformat()
    published_at, metadata_warnings = _published_at(extracted.get("date"))
    author = extracted.get("author")
    if not author:
        metadata_warnings.append("AUTHOR_MISSING")
    return {
        "canonical_url": str(extracted.get("url") or response.url),
        "discovered_url": discovered_url,
        "title": extracted.get("title"),
        "title_state": "TITLE_RESOLVED" if extracted.get("title") else "TITLE_UNRESOLVED",
        "title_source": "FALLBACK_EXTRACTOR" if extracted.get("title") else "TITLE_UNRESOLVED",
        "author": author,
        "publisher": extracted.get("publisher") or urlparse(response.url).hostname,
        "published_at": published_at,
        "publication_date": {"raw": extracted.get("date"), "normalized": published_at, "source": "FALLBACK_EXTRACTOR", "kind": "PUBLICATION", "precision": None},
        "article_metadata": {"metadata_extraction_status": "ARTICLE_METADATA_UNAVAILABLE", "title_state": "TITLE_RESOLVED" if extracted.get("title") else "TITLE_UNRESOLVED"},
        "retrieved_at": timestamp,
        "fetch_status": "FETCHED",
        "http_status": response.status,
        "content_type": response.content_type,
        "extraction_method": method,
        "extraction_quality": "HIGH" if len(text) >= 1_000 else "MEDIUM",
        "quality_score": min(1.0, round(len(text) / 1_000, 3)),
        "content_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "language": extracted.get("language"),
        "text": text,
        "links": extracted.get("links") or [],
        "metadata_warnings": sorted(metadata_warnings),
        "verification_status": "EXTRACTED_NOT_VERIFIED",
    }


def fetch_and_extract_source(
    url: str,
    *,
    transport: Transport = default_transport,
    timeout_seconds: int = 15,
    maximum_bytes: int = 10_000_000,
    retrieved_at: str | None = None,
) -> dict:
    """Fetch once, then route by the returned material type."""
    response = _fetch(url, transport, timeout_seconds, maximum_bytes)
    if response.content_type in {"text/html", "application/xhtml+xml"}:
        return fetch_and_extract_html(
            url,
            transport=lambda *_: response,
            timeout_seconds=timeout_seconds,
            maximum_bytes=maximum_bytes,
            retrieved_at=retrieved_at,
        )
    from dragon.structured_extraction import DocumentExtractionError, extract_structured_document

    try:
        value = extract_structured_document(
            response.body,
            content_type=response.content_type,
            source_url=response.url,
            retrieved_at=retrieved_at,
        )
    except DocumentExtractionError as exc:
        raise DiscoveryError(exc.code, exc.detail) from exc
    value["discovered_url"] = url
    value["http_status"] = response.status
    return value
