"""Source-provider registry plus bounded RSS and HTML extraction adapters."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Callable
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
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
    if urlparse(url).scheme != "https":
        raise DiscoveryError("SOURCE_URL_UNSAFE", "only HTTPS source URLs are permitted")
    request = Request(url, headers={"User-Agent": "DRAGON/5 source-research (+local newsroom)"})
    with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310 - HTTPS checked above
        final_url = response.geturl()
        if urlparse(final_url).scheme != "https":
            raise DiscoveryError("SOURCE_REDIRECT_UNSAFE", final_url)
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
) -> dict:
    response = transport(url, timeout_seconds, maximum_bytes)
    if response.status < 200 or response.status >= 300:
        raise DiscoveryError("SOURCE_HTTP_FAILED", f"HTTP {response.status}")
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
            raise DiscoveryError(
                "SOURCE_DYNAMIC_ROUTE_REQUIRED", "static extraction returned no content for a script-driven page"
            )
        raise DiscoveryError("SOURCE_EXTRACTION_FAILED", response.url)
    extracted = document.as_dict()
    text = str(extracted.get("text") or "").strip()
    if len(text) < 200:
        if b"<script" in response.body.lower():
            raise DiscoveryError(
                "SOURCE_DYNAMIC_ROUTE_REQUIRED", "insufficient static text on a script-driven page"
            )
        raise DiscoveryError("SOURCE_EXTRACTION_LOW_QUALITY", f"only {len(text)} characters")
    quality = "HIGH" if len(text) >= 1_000 else "MEDIUM"
    timestamp = retrieved_at or datetime.now(timezone.utc).isoformat()
    return {
        "canonical_url": str(extracted.get("url") or response.url),
        "discovered_url": url,
        "title": extracted.get("title"),
        "author": extracted.get("author"),
        "published_at": extracted.get("date"),
        "retrieved_at": timestamp,
        "fetch_status": "FETCHED",
        "http_status": response.status,
        "content_type": response.content_type,
        "extraction_method": "trafilatura-bare-extraction",
        "extraction_quality": quality,
        "content_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "language": extracted.get("language"),
        "text": text,
        "links": extracted.get("links") or [],
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
    response = transport(url, timeout_seconds, maximum_bytes)
    if response.status < 200 or response.status >= 300:
        raise DiscoveryError("SOURCE_HTTP_FAILED", f"HTTP {response.status}")
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
