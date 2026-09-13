"""Deterministic institutional page typing and bounded listing navigation."""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from dragon.source_intelligence import normalize_url


PAGE_TYPES = {
    "ARTICLE_DETAIL", "OFFICIAL_NOTICE", "OFFICIAL_DECISION", "PRESS_RELEASE",
    "REPORT_DETAIL", "PROCUREMENT_NOTICE", "SERVICE_NOTICE", "LISTING_PAGE",
    "SEARCH_RESULTS_PAGE", "CATEGORY_PAGE", "PORTAL_HOME", "AGGREGATOR",
    "UNKNOWN_PAGE_TYPE",
}

OUTBOUND_LINK_TYPES = {
    "CITED_PRIMARY_SOURCE", "OFFICIAL_SERVICE_DESTINATION", "OFFICIAL_DOCUMENT",
    "INSTITUTIONAL_DETAIL", "BACKGROUND_REFERENCE", "NEWSROOM_SOURCE",
    "AGGREGATOR_LINK", "SOCIAL_LINK", "UNRELATED_LINK", "LINK_RELATION_UNRESOLVED",
}

_AGGREGATOR_HOSTS = {"news.google.com", "www.google.com"}
_SOCIAL_HOSTS = {"facebook.com", "www.facebook.com", "x.com", "twitter.com", "www.twitter.com", "instagram.com", "www.instagram.com", "youtube.com", "www.youtube.com", "tiktok.com", "www.tiktok.com"}
_INSTITUTION_MARKERS = (
    "ministry", "department", "authority", "agency", "commission", "office",
    "government", "public", "institution", "university", "municipality",
    "وزارة", "مؤسسة", "هيئة", "مصلحة", "جامعة", "جماعة", "حكومي",
)
_SERVICE_MARKERS = (
    "registration", "deadline", "eligibility", "application", "procedure", "service",
    "schedule", "notice", "inscription", "candidature", "date limite", "procédure", "service public",
    "تسجيل", "التسجيل", "الترشح", "منصة", "مباراة", "آخر أجل", "أجل", "ولوج", "مسطرة", "خدمة", "إعلان",
)
_ACCOUNTABILITY_MARKERS = (
    "audit", "inspection", "oversight", "enforcement", "regulator", "court", "prosecution",
    "finding", "decision", "procurement", "tender", "contrat", "contrôle", "cour des comptes",
    "افتحاص", "رقابة", "تفتيش", "محكمة", "نيابة", "صفقة", "قرار", "مراقبة",
)
_NAVIGATION_NOISE = {
    "home", "homepage", "about", "contact", "login", "privacy", "terms", "cookies",
    "accueil", "connexion", "اتصل", "الرئيسية", "من نحن",
}

_OFFICIAL_HOST_MARKERS = (".gov", ".gov.", ".ac.", ".ma")
_CITATION_MARKERS = ("according to", "announced by", "in a circular", "in a decision", "official portal", "selon le ministère", "selon l'autorité", "وفق", "حسب", "بلاغ", "قرار", "منصة رسمية")
_DOCUMENT_MARKERS = (".pdf", "circular", "decision", "notice", "report", "directive", "communique", "بلاغ", "قرار", "تقرير", "مذكرة")


def classify_outbound_link(parent_url: str, link_url: str, *, label: str = "", context: str = "", semantic_target: str | None = None, institution_domain: str | None = None) -> dict:
    """Classify a discovered link for bounded navigation, never as evidence."""
    parent = normalize_url(str(parent_url or ""))
    link = normalize_url(str(link_url or ""))
    p_host = (urlsplit(parent).hostname or "").casefold()
    host = (urlsplit(link).hostname or "").casefold()
    path = (urlsplit(link).path or "/").casefold()
    target = str(semantic_target or "").upper()
    haystack = f"{label} {context} {link}".casefold()
    same_domain = bool(host and p_host and (host == p_host or host.endswith("." + p_host) or p_host.endswith("." + host)))
    official_domain = bool(host and (host.endswith(".gov.ma") or host.endswith(".gov") or host.endswith(".ac.ma") or (institution_domain and host == str(institution_domain).casefold())))
    service = any(marker in haystack for marker in _SERVICE_MARKERS) or any(token in path for token in ("application", "inscription", "candidature", "register", "service", "portal", "suivi"))
    document = any(marker in haystack for marker in _DOCUMENT_MARKERS)
    citation = any(marker in haystack for marker in _CITATION_MARKERS)
    if not link or urlsplit(link).scheme != "https":
        kind = "LINK_RELATION_UNRESOLVED"
        reason = "UNSUPPORTED_OR_NONPUBLIC_SCHEME"
    elif host in _AGGREGATOR_HOSTS or "news.google.com/rss" in link:
        kind, reason = "AGGREGATOR_LINK", "AGGREGATOR_HOST"
    elif host in _SOCIAL_HOSTS:
        kind, reason = "SOCIAL_LINK", "SOCIAL_HOST"
    elif path in {"", "/"} and official_domain:
        kind, reason = "INSTITUTIONAL_DETAIL", "OFFICIAL_HOMEPAGE_NAVIGATION_ONLY"
    elif official_domain and service and target == "SERVICE":
        kind, reason = "OFFICIAL_SERVICE_DESTINATION", "OFFICIAL_SERVICE_ROUTE"
    elif official_domain and (document or citation):
        kind, reason = "CITED_PRIMARY_SOURCE" if citation else "OFFICIAL_DOCUMENT", "OFFICIAL_ARTIFACT_SIGNAL"
    elif official_domain and (same_domain or institution_domain):
        kind, reason = "INSTITUTIONAL_DETAIL", "OFFICIAL_INSTITUTION_RELATION"
    elif same_domain and document:
        kind, reason = "INSTITUTIONAL_DETAIL", "SAME_DOMAIN_DOCUMENT_ROUTE"
    elif any(marker in haystack for marker in ("news", "article", "press", "صحافة", "خبر")):
        kind, reason = "NEWSROOM_SOURCE", "NEWSROOM_SIGNAL"
    elif any(marker in haystack for marker in ("facebook.com", "twitter.com", "instagram.com", "youtube.com")):
        kind, reason = "SOCIAL_LINK", "SOCIAL_SIGNAL"
    elif same_domain:
        kind, reason = "BACKGROUND_REFERENCE", "SAME_DOMAIN_NON_ARTIFACT"
    else:
        kind, reason = "UNRELATED_LINK", "NO_INSTITUTION_OR_SEMANTIC_RELATION"
    return {"url": link, "label": str(label or ""), "type": kind, "reason": reason,
            "same_domain": same_domain, "cross_domain": bool(host and p_host and not same_domain),
            "official_looking": official_domain, "service_signal": service, "document_signal": document,
            "citation_signal": citation}


def extract_outbound_link_candidates(raw: dict, *, semantic_target: str | None = None, institution_domain: str | None = None) -> list[dict]:
    """Extract links from structured fields and Markdown text with provenance."""
    parent = str(raw.get("canonical_url") or raw.get("url") or "")
    context = " ".join(str(raw.get(key) or "") for key in ("title", "text", "extracted_text"))
    items = _link_items(raw)
    result = []
    for url, label in items:
        result.append(classify_outbound_link(parent, url, label=label, context=context, semantic_target=semantic_target, institution_domain=institution_domain))
    return result


def extract_actor_attributions(raw: dict) -> dict:
    """Extract concrete institutional actors and attribution phrases as routing metadata."""
    text = " ".join(str(raw.get(key) or "") for key in ("title", "text", "extracted_text", "claim"))
    phrases = [text[m.start():m.end()].strip() for m in re.finditer(r"(?:according to|announced by|in a circular|in a decision|وفق(?:ا لـ)?|حسب|بلاغ|قرار|بناء على)[^.;\n]{0,140}", text, flags=re.I)]
    known = (
        ("Supreme Audit Council", ("Supreme Audit Council", "Cour des comptes", "المجلس الأعلى للحسابات")),
        ("General Inspectorate of Finance", ("General Inspectorate of Finance", "Inspection Générale des Finances", "المفتشية العامة للمالية")),
        ("General Directorate of National Security", ("DGSN", "Direction Générale de la Sûreté Nationale", "المديرية العامة للأمن الوطني")),
        ("Public Prosecution", ("Public Prosecution", "Parquet", "النيابة العامة")),
    )
    actors = []
    lowered = text.casefold()
    for canonical, aliases in known:
        matched = [alias for alias in aliases if alias.casefold() in lowered]
        if matched:
            actors.append({"name": canonical, "aliases": matched, "confidence": "HIGH", "provenance": "TEXT_OR_TITLE"})
    identifiers = sorted(set(re.findall(r"\b(?:[A-Z]{2,}[\-/]?\d{2,}|\d{3,})\b", text)))
    return {"actors": actors, "attribution_phrases": phrases[:8], "document_identifiers": identifiers[:8]}


def detect_official_portal_republication(raw: dict) -> dict:
    """Record an official portal's stated origin without collapsing provenance."""
    url = str(raw.get("canonical_url") or raw.get("url") or "")
    host = (urlsplit(url).hostname or "").casefold()
    metadata = raw.get("article_metadata") if isinstance(raw.get("article_metadata"), dict) else {}
    publisher = metadata.get("publisher") if isinstance(metadata.get("publisher"), dict) else {}
    text = " ".join(str(raw.get(key) or "") for key in ("title", "text", "extracted_text", "claim"))
    issuer = raw.get("issuing_institution") or raw.get("stated_issuing_institution") or metadata.get("issuing_institution")
    if not issuer:
        match = re.search(r"(?:according to|announced by|selon|وفق(?:ا لـ)?|حسب)\s+([^.;\n]{3,120})", text, flags=re.I)
        issuer = match.group(1).strip() if match else None
    official_portal = host.endswith(".gov.ma") or host.endswith(".gov") or "official portal" in text.casefold() or "portail officiel" in text.casefold()
    publisher_name = publisher.get("name") or raw.get("publisher") or host
    if official_portal and issuer and str(issuer).casefold().strip() not in str(publisher_name).casefold().strip():
        return {"article_origin_state": "OFFICIAL_PORTAL_REPUBLICATION", "portal_publisher": publisher_name, "issuing_institution": str(issuer).strip(), "origin_relationship": "PORTAL_REPUBLISHES_ISSUER"}
    return {"article_origin_state": "PRIMARY_ORIGINAL_ARTIFACT" if official_portal else "ORIGIN_UNRESOLVED", "portal_publisher": publisher_name if official_portal else None, "issuing_institution": str(issuer).strip() if issuer else None, "origin_relationship": "PORTAL_ORIGINAL" if official_portal else "UNRESOLVED"}


def _text(raw: dict) -> str:
    metadata = raw.get("article_metadata") if isinstance(raw.get("article_metadata"), dict) else {}
    signals = metadata.get("signals") if isinstance(metadata.get("signals"), dict) else {}
    return " ".join(str(raw.get(key) or "") for key in ("title", "text", "extracted_text", "publisher")) + " " + " ".join(str(value or "") for value in signals.values())


def classify_page_type(raw: dict, *, action: dict | None = None) -> str:
    """Classify material shape without assigning an evidence role."""
    action = action or {}
    host = (urlsplit(str(raw.get("canonical_url") or raw.get("url") or "")).hostname or "").casefold()
    path = (urlsplit(str(raw.get("canonical_url") or raw.get("url") or "")).path or "/").casefold()
    metadata = raw.get("article_metadata") if isinstance(raw.get("article_metadata"), dict) else {}
    types = {str(value).casefold() for value in metadata.get("jsonld_article_types", [])}
    content_type = str(raw.get("content_type") or "").casefold()
    text = _text(raw).casefold()
    title = str(raw.get("title") or "").casefold()
    if host in _AGGREGATOR_HOSTS or "news.google.com/rss" in str(raw.get("url") or "").casefold():
        return "AGGREGATOR"
    if raw.get("material_type") or content_type == "application/pdf":
        if any(marker in text for marker in _ACCOUNTABILITY_MARKERS + ("report", "rapport", "تقرير")):
            return "REPORT_DETAIL"
        return "UNKNOWN_PAGE_TYPE"
    if action.get("discovery_only") and (raw.get("links") or len(text) > 0):
        return "LISTING_PAGE"
    if any(marker in title or marker in text[:1800] for marker in ("search results", "résultats de recherche", "نتائج البحث")):
        return "SEARCH_RESULTS_PAGE"
    if any(marker in path for marker in ("/category/", "/categories/", "/tag/", "/archive/", "/rubrique/")):
        return "CATEGORY_PAGE"
    strong_event = ("deadline", "date limite", "آخر أجل", "registration closes", "enforcement decision", "قرار تنفيذي", "audit finding", "نتيجة الافتحاص")
    if path in {"", "/", "/index.html", "/index.php"} and not raw.get("published_at") and not raw.get("links") and ("portal" in text or "homepage" in title or not any(marker in text for marker in _SERVICE_MARKERS + _ACCOUNTABILITY_MARKERS)) and not any(marker in text for marker in strong_event):
        return "PORTAL_HOME"
    if any(marker in text for marker in ("official decision", "enforcement decision", "قرار رسمي", "قرار إداري")):
        return "OFFICIAL_DECISION"
    if any(marker in text for marker in ("press release", "press-release", "communiqué", "بلاغ صحفي")):
        return "PRESS_RELEASE"
    if any(marker in text for marker in ("procurement notice", "tender notice", "appel d'offres", "صفقة عمومية", "طلب عروض")):
        return "PROCUREMENT_NOTICE"
    if any(marker in text for marker in _SERVICE_MARKERS) and any(marker in text for marker in ("deadline", "date limite", "آخر أجل", "registration", "تسجيل", "notice", "إعلان")):
        return "SERVICE_NOTICE"
    if any(marker in text for marker in ("audit report", "inspection report", "rapport d'audit", "rapport", "situation du marché", "présentent", "table marocaine", "تقرير الافتحاص")):
        return "REPORT_DETAIL"
    if types & {"newsarticle", "article", "reportagenewsarticle", "analysisnewsarticle", "liveblogposting"}:
        return "ARTICLE_DETAIL"
    if raw.get("links") and not raw.get("published_at") and len(raw.get("links") or []) >= 2:
        return "LISTING_PAGE"
    if raw.get("title") and raw.get("text") and raw.get("published_at"):
        return "ARTICLE_DETAIL"
    return "UNKNOWN_PAGE_TYPE"


def _profile_type(text: str, host: str) -> str:
    value = f"{host} {text}".casefold()
    if any(marker in value for marker in ("procurement", "tender", "marchés publics", "صفقات", "طلبات العروض")):
        return "PROCUREMENT_PORTAL"
    if any(marker in value for marker in ("regulator", "régulateur", "هيئة تنظيم", "ضبط")):
        return "REGULATOR"
    if any(marker in value for marker in ("prosecution", "parquet", "public prosecutor", "النيابة العامة")):
        return "PROSECUTION_AUTHORITY"
    if any(marker in value for marker in ("audit", "cour des comptes", "افتحاص", "المجلس الأعلى للحسابات")):
        return "AUDIT_BODY"
    if any(marker in value for marker in ("court", "tribunal", "محكمة")):
        return "COURT"
    if any(marker in value for marker in ("education", "university", "التعليم", "جامعة")):
        return "EDUCATION_AUTHORITY"
    if any(marker in value for marker in ("health", "hospital", "santé", "صحة")):
        return "HEALTH_AUTHORITY"
    if any(marker in value for marker in ("transport", "rail", "airport", "نقل", "مطار")):
        return "TRANSPORT_OPERATOR"
    if any(marker in value for marker in _SERVICE_MARKERS):
        return "PUBLIC_SERVICE_OPERATOR"
    if any(marker in value for marker in _INSTITUTION_MARKERS) or host.endswith((".gov", ".gov.ma", ".ac.ma")):
        return "PUBLIC_INSTITUTION"
    return "OTHER_INSTITUTION"


def resolve_institution_identity(raw: dict, *, known_profile: dict | None = None) -> dict:
    """Resolve identity/navigation facts separately from evidence role."""
    metadata = raw.get("article_metadata") if isinstance(raw.get("article_metadata"), dict) else {}
    publisher = metadata.get("publisher") if isinstance(metadata.get("publisher"), dict) else {}
    profile = known_profile if isinstance(known_profile, dict) else (raw.get("publisher_profile") if isinstance(raw.get("publisher_profile"), dict) else {})
    host = (urlsplit(str(raw.get("canonical_url") or raw.get("url") or "")).hostname or "").casefold()
    canonical = str(profile.get("canonical_domain") or publisher.get("canonical_domain") or host).casefold()
    site_name = publisher.get("name") or profile.get("canonical_publisher_name") or (metadata.get("signals") or {}).get("og_site_name") or raw.get("publisher")
    text = _text(raw)
    public_signal = canonical.endswith((".gov", ".gov.ma", ".ac.ma")) or any(marker in f"{site_name} {text}".casefold() for marker in _INSTITUTION_MARKERS)
    known = bool(profile.get("canonical_domain") or profile.get("identity_state") == "PUBLISHER_PROFILE_RESOLVED")
    if known or public_signal:
        state = "INSTITUTION_IDENTITY_RESOLVED"
    elif host:
        state = "CANONICAL_DOMAIN_UNRESOLVED"
    else:
        state = "INSTITUTION_IDENTITY_UNRESOLVED"
    relationship = "CANONICAL_HOST"
    if host and canonical and host != canonical:
        relationship = "SUBDOMAIN_OF_CANONICAL" if host.endswith("." + canonical) else "PAGE_OWNERSHIP_UNRESOLVED"
    return {
        "state": state,
        "host": host or None,
        "canonical_institution_domain": canonical or None,
        "institution_name": str(site_name).strip() if site_name else None,
        "profile_type": _profile_type(text, canonical),
        "relationship": relationship,
        "relationship_evidence": "canonical_profile_or_first_party_metadata" if known else "domain_and_page_signals" if public_signal else None,
        "identity_confidence": "HIGH" if known else "MEDIUM" if public_signal else "LOW",
        "evidence_role": "UNRESOLVED",
    }


def _link_items(raw: dict) -> list[tuple[str, str]]:
    values = list(raw.get("links") or [])
    text = str(raw.get("text") or raw.get("extracted_text") or "")
    values.extend((url, label) for label, url in re.findall(r"\[([^\]]{2,160})\]\((https?://[^)]+)\)", text))
    values.extend((url, "") for url in re.findall(r"https?://[^\s)\]>]+", text))
    items = []
    seen = set()
    for item in values:
        if isinstance(item, dict):
            url, label = item.get("url") or item.get("href"), item.get("text") or item.get("title") or ""
        elif isinstance(item, (tuple, list)) and len(item) >= 2:
            url, label = str(item[0]), str(item[1])
        else:
            url, label = str(item), ""
        if not isinstance(url, str) or not url.startswith("https://"):
            continue
        canonical = normalize_url(url)
        if canonical in seen:
            continue
        seen.add(canonical)
        items.append((canonical, str(label).strip()))
    return items


def extract_listing_child_links(raw: dict, *, semantic_target: str | None, edition_date: str | None, maximum: int = 8) -> list[dict]:
    """Extract and rank only a bounded set of likely detail/artifact links."""
    parent = normalize_url(str(raw.get("canonical_url") or raw.get("url") or ""))
    parent_host = urlsplit(parent).hostname or ""
    target = str(semantic_target or "").upper()
    markers = _ACCOUNTABILITY_MARKERS if target == "ACCOUNTABILITY" else _SERVICE_MARKERS if target == "SERVICE" else _INSTITUTION_MARKERS
    full_text = str(raw.get("text") or raw.get("extracted_text") or "")
    candidates = []
    for url, label in _link_items(raw):
        host = urlsplit(url).hostname or ""
        path = urlsplit(url).path.casefold()
        if url == parent or label.casefold() in _NAVIGATION_NOISE or path in {"", "/"}:
            continue
        haystack = f"{label} {url} {full_text}".casefold()
        score = 0
        reasons = []
        overlap = sum(marker.casefold() in haystack for marker in markers)
        if overlap:
            score += min(6, overlap * 2); reasons.append("SEMANTIC_FUNCTION_MATCH")
        if re.search(r"\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}\s+[A-Za-zÀ-ÿ]+\s+\d{4}", label + " " + full_text):
            score += 2; reasons.append("DATE_SIGNAL")
        if edition_date and str(edition_date)[:7] in (label + " " + full_text):
            score += 2; reasons.append("EDITION_WINDOW_SIGNAL")
        if host == parent_host:
            score += 2; reasons.append("FIRST_PARTY_HOST")
        if any(token in path for token in ("notice", "decision", "report", "detail", "communique", "annonce", "a4", "pdf", "document")):
            score += 2; reasons.append("DETAIL_OR_ARTIFACT_PATH")
        if score <= 0:
            continue
        candidates.append({
            "url": url, "label": label or urlsplit(url).path.rsplit("/", 1)[-1],
            "score": score, "reasons": reasons, "host": host,
            "parent_url": parent, "navigation_depth": 2,
            "page_type": "UNKNOWN_PAGE_TYPE", "discovery_only": True,
        })
    candidates.sort(key=lambda item: (-item["score"], item["url"]))
    return candidates[:maximum]


def select_listing_child_link(raw: dict, *, semantic_target: str | None, edition_date: str | None) -> dict | None:
    return (extract_listing_child_links(raw, semantic_target=semantic_target, edition_date=edition_date, maximum=1) or [None])[0]
