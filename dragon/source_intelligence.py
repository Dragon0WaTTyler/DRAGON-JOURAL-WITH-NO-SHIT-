"""Deterministic source normalization, origin analysis, and event clustering."""

from __future__ import annotations

from collections import defaultdict
from difflib import SequenceMatcher
import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


TRACKING_KEYS = {"fbclid", "gclid", "mc_cid", "mc_eid", "ref_src"}
WIRE_MARKERS = {
    "reuters": "REUTERS",
    "رويترز": "REUTERS",
    "associated press": "AP",
    "أسوشيتد برس": "AP",
    "agence france-presse": "AFP",
    "فرانس برس": "AFP",
    "maghreb arabe presse": "MAP",
    "وكالة المغرب العربي للأنباء": "MAP",
}


def normalize_url(value: str) -> str:
    """Canonicalize identity-safe URL parts while retaining meaningful query data."""
    parts = urlsplit(value.strip())
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").encode("idna").decode("ascii").lower()
    port = parts.port
    netloc = host
    if port and not ((scheme == "https" and port == 443) or (scheme == "http" and port == 80)):
        netloc = f"{host}:{port}"
    query = [
        (key, item)
        for key, item in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in TRACKING_KEYS
    ]
    path = re.sub(r"/{2,}", "/", parts.path or "/")
    return urlunsplit((scheme, netloc, path, urlencode(sorted(query)), ""))


def _tokens(value: str) -> set[str]:
    return {token for token in re.findall(r"[\w\u0600-\u06ff]+", value.casefold()) if len(token) > 1}


def _similarity(left: str, right: str) -> float:
    a, b = _tokens(left), _tokens(right)
    return len(a & b) / len(a | b) if a and b else 0.0


def _normalized_text(value: str) -> str:
    return " ".join(re.findall(r"[\w\u0600-\u06ff]+", value.casefold()))


def _edit_similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, _normalized_text(left), _normalized_text(right)).ratio()


def _wire_origin(source: dict) -> str | None:
    text = " ".join(str(source.get(key) or "") for key in ("publisher", "title", "claim_supported")).casefold()
    return next((wire for marker, wire in WIRE_MARKERS.items() if marker in text), None)


def _stable_event_id(keys: list[str]) -> str:
    digest = hashlib.sha256("\n".join(sorted(keys)).encode("utf-8")).hexdigest()[:12]
    return f"EVT-{digest.upper()}"


def build_source_intelligence(packet: dict) -> dict:
    """Build an honest normalized registry and stable clusters from provider evidence."""
    records = []
    source_by_id: dict[str, dict] = {}
    canonical_groups: dict[str, list[str]] = defaultdict(list)
    for source in packet.get("sources", []):
        canonical = normalize_url(source["url"])
        wire = _wire_origin(source)
        host = urlsplit(canonical).hostname or "unknown"
        evidence_text = " ".join(
            str(source.get(key) or "")
            for key in ("title", "extracted_text", "content", "claim_supported")
        ).strip()
        normalized = _normalized_text(evidence_text)
        record = {
            "source_id": source["id"],
            "canonical_url": canonical,
            "discovered_url": source["url"],
            "publisher": source.get("publisher"),
            "author": source.get("author"),
            "title": source.get("title"),
            "source_type": source.get("source_type"),
            "retrieved_at": source.get("accessed_at"),
            "published_at": source.get("publication_date"),
            "fetch_status": "PROVIDER_REPORTED",
            "http_status": None,
            "extraction_method": "provider-structured-output",
            "extraction_quality": "UNVERIFIED",
            "content_hash": source.get("content_hash"),
            "normalized_text_hash": (
                hashlib.sha256(normalized.encode("utf-8")).hexdigest()
                if len(normalized) >= 80 else None
            ),
            "language": source.get("language"),
            "primary_or_secondary": source.get("source_type"),
            "authority_level": "PRIMARY" if source.get("source_type") in {"primary", "official"} else "SECONDARY",
            "independent_origin_group": f"WIRE:{wire}" if wire else f"DOMAIN:{host}",
            "wire_origin": wire,
            "syndication_status": "WIRE_REPORTED" if wire else "UNKNOWN",
            "citation_chain": [],
            "first_observed": source.get("publication_date") or source.get("accessed_at"),
            "likely_original": source.get("source_type") in {"primary", "official"} and not wire,
            "primary_evidence": source.get("source_type") in {"primary", "official"},
            "archive_reference": source.get("archive_reference"),
            "license_use_notes": source.get("license_use_notes"),
            "doi": source.get("doi"),
            "publication_status": source.get("publication_status"),
            "full_text_status": source.get("full_text_status"),
            "methods_read": bool(source.get("methods_read")),
            "limitations_read": bool(source.get("limitations_read")),
            "science_metadata": source.get("science_metadata"),
            "verification_status": source.get("verification_status", "PROVIDER_REPORTED"),
            "evidence_relation": source.get("evidence_relation"),
            "directness": source.get("directness"),
            "provenance": source.get("provenance"),
            # Provider provenance is append-only routing telemetry.  It does
            # not alter source role, independent-origin, or evidence status.
            "provider_lead_id": source.get("provider_lead_id"),
            "provider_supplied_url": source.get("provider_supplied_url"),
            "lead_origin": source.get("lead_origin") or "DETERMINISTIC_DISCOVERY",
            "provider_candidate_ids": [],
            "uncertainty": (
                [] if source.get("verification_status") == "VALIDATED_EVIDENCE"
                else ["FULL_TEXT_NOT_CAPTURED", "FETCH_NOT_INDEPENDENTLY_VERIFIED"]
            ),
            "event_ids": [],
            "claims_supported": [source.get("claim_supported")],
            "duplicate_group_ids": [],
        }
        record["_comparison_text"] = evidence_text
        records.append(record)
        source_by_id[record["source_id"]] = record
        canonical_groups[canonical].append(record["source_id"])

    candidates = []
    for section in packet.get("sections", []):
        # Recovery candidates are preserved leads from a NO_NEWS decision.
        # They inform bounded corroboration planning only and never count as
        # selected editorial placements.
        for candidate in [*section.get("candidates", []), *section.get("recovery_candidates", [])]:
            source_ids = sorted(set().union(*(
                set(candidate.get(field, []))
                for field in (
                    "discovery_source_ids", "verification_source_ids",
                    "primary_evidence_source_ids", "independent_evidence_source_ids",
                )
            )))
            candidates.append({
                "key": f"{section['section_id']}:{candidate['id']}",
                "section_id": section["section_id"],
                "candidate_id": candidate["id"],
                "title": candidate.get("title", ""),
                "source_ids": source_ids,
            })
            candidate_key = f"{section['section_id']}:{candidate['id']}"
            for source_id in source_ids:
                record = source_by_id.get(source_id)
                if record and record.get("provider_lead_id"):
                    record["provider_candidate_ids"].append(candidate_key)

    parent = list(range(len(candidates)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        a, b = find(left), find(right)
        if a != b:
            parent[max(a, b)] = min(a, b)

    for left in range(len(candidates)):
        for right in range(left + 1, len(candidates)):
            shared = set(candidates[left]["source_ids"]) & set(candidates[right]["source_ids"])
            if shared or _similarity(candidates[left]["title"], candidates[right]["title"]) >= 0.6:
                union(left, right)

    clustered: dict[int, list[dict]] = defaultdict(list)
    for index, candidate in enumerate(candidates):
        clustered[find(index)].append(candidate)
    events = []
    for members in clustered.values():
        event_id = _stable_event_id([item["key"] for item in members])
        source_ids = sorted({source for item in members for source in item["source_ids"]})
        origins = sorted({source_by_id[item]["independent_origin_group"] for item in source_ids if item in source_by_id})
        for source_id in source_ids:
            if source_id in source_by_id:
                source_by_id[source_id]["event_ids"].append(event_id)
        events.append({
            "event_id": event_id,
            "candidate_keys": sorted(item["key"] for item in members),
            "source_ids": source_ids,
            "publisher_count": len({source_by_id[item]["publisher"] for item in source_ids if item in source_by_id}),
            "independent_origin_count": len(origins),
            "independent_origin_groups": origins,
            "wire_origins": sorted({source_by_id[item]["wire_origin"] for item in source_ids if item in source_by_id and source_by_id[item]["wire_origin"]}),
        })
    events.sort(key=lambda item: item["event_id"])
    duplicate_parent = list(range(len(records)))
    duplicate_signals: dict[tuple[int, int], list[dict]] = defaultdict(list)

    def duplicate_find(index: int) -> int:
        while duplicate_parent[index] != index:
            duplicate_parent[index] = duplicate_parent[duplicate_parent[index]]
            index = duplicate_parent[index]
        return index

    def duplicate_union(left: int, right: int) -> None:
        a, b = duplicate_find(left), duplicate_find(right)
        if a != b:
            duplicate_parent[max(a, b)] = min(a, b)

    for left in range(len(records)):
        for right in range(left + 1, len(records)):
            a, b = records[left], records[right]
            signals = duplicate_signals[(left, right)]
            if a["canonical_url"] == b["canonical_url"]:
                signals.append({"kind": "EXACT_CANONICAL_URL", "score": 1.0})
            if a.get("content_hash") and a["content_hash"] == b.get("content_hash"):
                signals.append({"kind": "EXACT_CONTENT_HASH", "score": 1.0})
            if a.get("normalized_text_hash") and a["normalized_text_hash"] == b.get("normalized_text_hash"):
                signals.append({"kind": "NORMALIZED_TEXT_HASH", "score": 1.0})
            comparison_a, comparison_b = a["_comparison_text"], b["_comparison_text"]
            if min(len(_normalized_text(comparison_a)), len(_normalized_text(comparison_b))) >= 80:
                token_score = _similarity(comparison_a, comparison_b)
                edit_score = _edit_similarity(comparison_a, comparison_b)
                if token_score >= 0.82:
                    signals.append({"kind": "TOKEN_SIMILARITY", "score": round(token_score, 4)})
                if edit_score >= 0.88:
                    signals.append({"kind": "EDIT_SIMILARITY", "score": round(edit_score, 4)})
            title_a, title_b = str(a.get("title") or ""), str(b.get("title") or "")
            if min(len(title_a), len(title_b)) >= 20:
                headline_score = _similarity(title_a, title_b)
                if headline_score >= 0.82:
                    signals.append({"kind": "HEADLINE_SIMILARITY", "score": round(headline_score, 4)})
            if signals:
                duplicate_union(left, right)

    duplicate_components: dict[int, list[int]] = defaultdict(list)
    for index in range(len(records)):
        duplicate_components[duplicate_find(index)].append(index)
    signal_order = (
        "EXACT_CANONICAL_URL", "EXACT_CONTENT_HASH", "NORMALIZED_TEXT_HASH",
        "TOKEN_SIMILARITY", "EDIT_SIMILARITY", "HEADLINE_SIMILARITY",
    )
    duplicates = []
    for component in duplicate_components.values():
        if len(component) < 2:
            continue
        component_signals = [
            signal
            for (left, right), signals in duplicate_signals.items()
            if left in component and right in component
            for signal in signals
        ]
        kinds = {item["kind"] for item in component_signals}
        kind = next(value for value in signal_order if value in kinds)
        source_ids = sorted(records[index]["source_id"] for index in component)
        group_id = "DUP-" + hashlib.sha256("\n".join(source_ids).encode("utf-8")).hexdigest()[:12].upper()
        urls = {records[index]["canonical_url"] for index in component}
        group = {
            "duplicate_group_id": group_id,
            "kind": kind,
            "canonical_url": next(iter(urls)) if len(urls) == 1 else None,
            "source_ids": source_ids,
            "signals": sorted(
                component_signals, key=lambda item: (signal_order.index(item["kind"]), -item["score"])
            ),
        }
        duplicates.append(group)
        for index in component:
            records[index]["duplicate_group_ids"].append(group_id)
    duplicates.sort(key=lambda item: item["duplicate_group_id"])
    for record in records:
        record["provider_candidate_ids"] = list(dict.fromkeys(record["provider_candidate_ids"]))
        record.pop("_comparison_text", None)
    return {
        "schema_version": 1,
        "status": "PASS",
        "source_records": records,
        "duplicate_groups": duplicates,
        "event_clusters": events,
        "summary": {
            "source_count": len(records),
            "canonical_source_count": len(canonical_groups),
            "duplicate_group_count": len(duplicates),
            "event_count": len(events),
            "wire_source_count": sum(record["wire_origin"] is not None for record in records),
        },
    }
