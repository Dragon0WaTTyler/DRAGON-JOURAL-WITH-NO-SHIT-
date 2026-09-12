"""Provenance-bound publisher identity profiles, separate from article evidence."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import re
from urllib.parse import urlsplit

from dragon.source_intelligence import normalize_url


PROFILE_PATHS = ("/about", "/about-us", "/editorial-team", "/policies", "/terms", "/legal")


def publisher_profile_from_pages(domain: str, pages: list[dict]) -> dict:
    """Build a deterministic first-party profile without assigning article trust."""
    canonical_domain = (urlsplit(domain).hostname or domain).casefold().strip("/")
    usable = [page for page in pages if page.get("canonical_url") and page.get("text")]
    evidence_urls = sorted({normalize_url(str(page["canonical_url"])) for page in usable})
    text = " ".join(str(page.get("text") or "") for page in usable)
    title = next((str(page.get("publisher") or page.get("title") or "").strip() for page in usable if str(page.get("publisher") or page.get("title") or "").strip()), None)
    parent_match = re.search(r"(?:part of|owned by|a service of|member of)\s+([A-Z][\w .,&-]{2,80})", text, re.I)
    parent = parent_match.group(1).strip(" .") if parent_match else None
    profile = {
        "schema_version": 1,
        "canonical_publisher_name": title,
        "canonical_domain": canonical_domain,
        "alternate_domains": [],
        "parent_company": parent,
        "newsroom_family_id": f"PARENT:{parent.casefold()}" if parent else f"DOMAIN:{canonical_domain}",
        "languages": sorted({str(page.get("language")) for page in usable if page.get("language")} ),
        "country_or_region": None,
        "publication_type": "NEWSROOM_CANDIDATE" if any("news" in str(page.get("title") or "").casefold() for page in usable) else "PUBLISHER_UNCLASSIFIED",
        "official_about_urls": [url for url in evidence_urls if any(path in urlsplit(url).path.casefold() for path in ("about", "editorial", "team"))],
        "official_policy_urls": [url for url in evidence_urls if any(path in urlsplit(url).path.casefold() for path in ("policy", "terms", "legal"))],
        "known_sister_publications": [],
        "identity_state": "PUBLISHER_PROFILE_RESOLVED" if usable else "PUBLISHER_PROFILE_UNRESOLVED",
        "identity_confidence": "FIRST_PARTY_METADATA" if usable else "NONE",
        "discovered_at": datetime.now(timezone.utc).isoformat(),
        "evidence_urls": evidence_urls,
        "article_evidence_role": "UNRESOLVED",
    }
    profile["profile_hash"] = hashlib.sha256(repr(sorted(profile.items())).encode("utf-8")).hexdigest()
    return profile


class PublisherProfileCache:
    """Run-scoped, refreshable cache; it never stores article evidence."""

    def __init__(self) -> None:
        self._profiles: dict[str, dict] = {}

    def get(self, domain: str) -> dict | None:
        value = self._profiles.get((urlsplit(domain).hostname or domain).casefold().strip("/"))
        return deepcopy(value) if value else None

    def put(self, profile: dict) -> dict:
        domain = str(profile["canonical_domain"]).casefold()
        self._profiles[domain] = deepcopy(profile)
        return deepcopy(profile)


def article_origin_evaluation(article_attribution: dict, *, publisher_profile: dict | None, existing_origin_ids: set[str]) -> dict:
    """Evaluate lineage relationally; identity alone never supplies independence."""
    state = str(article_attribution.get("article_origin_state") or "SYNDICATION_UNRESOLVED")
    family = (publisher_profile or {}).get("newsroom_family_id")
    if state in {"WIRE_REPUBLICATION", "PARTNER_REPUBLICATION", "SYNDICATION_UNRESOLVED"}:
        return {"article_origin_state": state, "evidence_role": "UNRESOLVED", "reason": "ARTICLE_LINEAGE_NOT_INDEPENDENTLY_ESTABLISHED"}
    if not family or family in existing_origin_ids:
        return {"article_origin_state": state, "evidence_role": "UNRESOLVED", "reason": "PUBLISHER_FAMILY_OVERLAPS_EXISTING_EVIDENCE"}
    return {"article_origin_state": state, "evidence_role": "UNRESOLVED", "reason": "ARTICLE_REPORTING_ORIGINALITY_STILL_REQUIRES_DIRECT_EVIDENCE"}
