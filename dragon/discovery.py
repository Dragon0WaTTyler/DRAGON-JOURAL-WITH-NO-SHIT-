"""Source-provider registry plus bounded RSS and HTML extraction adapters."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from ipaddress import ip_address
import json
from pathlib import Path
import socket
from typing import Callable
from urllib.parse import urljoin, urlparse
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


Transport = Callable[[str, int, int], FetchResponse]
# A deferred browser extractor (for example Crawl4AI) is injected explicitly.
# It is never imported, installed, or selected as the ordinary extraction path.
ExtractionFallback = Callable[[FetchResponse, str], dict | None]


def _validate_source_url(
    url: str, *, error_code: str = "SOURCE_URL_UNSAFE", resolve_dns: bool = False
) -> None:
    parsed = urlparse(url)
    hostname = parsed.hostname
    if parsed.scheme.casefold() != "https" or not hostname or not parsed.netloc:
        raise DiscoveryError(error_code, "only absolute HTTPS source URLs are permitted")
    try:
        port = parsed.port
    except ValueError as exc:
        raise DiscoveryError(error_code, "source URL port is invalid") from exc
    if parsed.username is not None or parsed.password is not None:
        raise DiscoveryError(error_code, "source URLs must not contain credentials")
    normalized = hostname.rstrip(".").casefold()
    if normalized == "localhost" or normalized.endswith((".localhost", ".local", ".internal")):
        raise DiscoveryError(error_code, "local source hosts are not permitted")
    try:
        literal = ip_address(normalized)
    except ValueError:
        literal = None
    if literal is not None and not literal.is_global:
        raise DiscoveryError(error_code, "non-public source addresses are not permitted")
    if not resolve_dns or literal is not None:
        return
    try:
        addresses = {
            item[4][0]
            for item in socket.getaddrinfo(
                hostname, port or 443, type=socket.SOCK_STREAM
            )
        }
    except OSError as exc:
        raise DiscoveryError("SOURCE_FETCH_FAILED", f"source host resolution failed: {hostname}") from exc
    if not addresses:
        raise DiscoveryError("SOURCE_FETCH_FAILED", f"source host has no addresses: {hostname}")
    if any(not ip_address(address.split("%", 1)[0]).is_global for address in addresses):
        raise DiscoveryError(error_code, "source host resolves to a non-public address")


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
    try:
        response = transport(url, timeout_seconds, maximum_bytes)
    except DiscoveryError:
        raise
    except TimeoutError as exc:
        raise DiscoveryError("SOURCE_TIMEOUT", str(exc) or url) from exc
    except OSError as exc:
        raise DiscoveryError("SOURCE_FETCH_FAILED", str(exc) or url) from exc
    _validate_source_url(response.url, error_code="SOURCE_REDIRECT_UNSAFE")
    if len(response.body) > maximum_bytes:
        raise DiscoveryError("SOURCE_RESPONSE_TOO_LARGE", f"response exceeds {maximum_bytes} bytes")
    if response.status in {401, 403}:
        raise DiscoveryError("SOURCE_BLOCKED", f"HTTP {response.status}")
    if response.status < 200 or response.status >= 300:
        raise DiscoveryError("SOURCE_HTTP_FAILED", f"HTTP {response.status}")
    if not response.body.strip():
        raise DiscoveryError("SOURCE_CONTENT_EMPTY", response.url)
    return response


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
        candidates.append(
            {
                "provider_id": provider_id,
                "title": title.strip(),
                "discovered_url": url,
                "verification_status": "DISCOVERY_ONLY",
            }
        )
    return candidates


def default_transport(url: str, timeout_seconds: int, maximum_bytes: int) -> FetchResponse:
    _validate_source_url(url, resolve_dns=True)
    request = Request(url, headers={"User-Agent": "DRAGON/5 source-research (+local newsroom)"})
    opener = build_opener(_SafeRedirectHandler())
    with opener.open(request, timeout=timeout_seconds) as response:  # noqa: S310 - URL and DNS checked above
        final_url = response.geturl()
        _validate_source_url(
            final_url, error_code="SOURCE_REDIRECT_UNSAFE", resolve_dns=True
        )
        body = response.read(maximum_bytes + 1)
        if len(body) > maximum_bytes:
            raise DiscoveryError("SOURCE_RESPONSE_TOO_LARGE", f"response exceeds {maximum_bytes} bytes")
        return FetchResponse(
            final_url,
            int(response.status),
            response.headers.get_content_type(),
            body,
        )


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
    published_at, metadata_warnings = _published_at(extracted.get("date"))
    author = extracted.get("author")
    if not author:
        metadata_warnings.append("AUTHOR_MISSING")
    return {
        "canonical_url": str(extracted.get("url") or response.url),
        "discovered_url": url,
        "title": extracted.get("title"),
        "author": author,
        "publisher": extracted.get("sitename") or extracted.get("hostname") or urlparse(response.url).hostname,
        "published_at": published_at,
        "retrieved_at": timestamp,
        "fetch_status": "FETCHED",
        "http_status": response.status,
        "content_type": response.content_type,
        "extraction_method": "trafilatura-bare-extraction",
        "extraction_quality": quality,
        "quality_score": min(1.0, round(len(text) / 1_000, 3)),
        "content_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "language": extracted.get("language"),
        "text": text,
        "links": extracted.get("links") or [],
        "metadata_warnings": sorted(metadata_warnings),
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
        "author": author,
        "publisher": extracted.get("publisher") or urlparse(response.url).hostname,
        "published_at": published_at,
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
