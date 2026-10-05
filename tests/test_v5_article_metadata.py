"""Deterministic article-metadata cascade tests; no network access."""

from __future__ import annotations

from dragon.discovery import extract_article_metadata


def _metadata(head: str, body: str = "") -> dict:
    return extract_article_metadata(
        f"<html><head>{head}</head><body>{body}</body></html>".encode(),
        canonical_url="https://news.example/report",
    )


def test_jsonld_newsarticle_wins_title_date_publisher_and_author() -> None:
    value = _metadata(
        """<title>Document title</title><script type="application/ld+json">
        {"@context":"https://schema.org","@type":"NewsArticle","headline":"JSON-LD headline",
        "datePublished":"2026-09-09T08:30:00Z","dateModified":"2026-09-09T09:00:00Z",
        "publisher":{"@type":"Organization","name":"Example News"},"author":{"@type":"Person","name":"A. Reporter"}}
        </script>""",
        "<h1>HTML heading</h1>",
    )
    assert value["title"] == "JSON-LD headline"
    assert value["title_source"] == "JSON_LD_HEADLINE"
    assert value["publication_date"] == {
        "raw": "2026-09-09T08:30:00Z", "normalized": "2026-09-09T08:30:00+00:00",
        "source": "JSON_LD_DATE_PUBLISHED", "kind": "PUBLICATION", "precision": "TIMESTAMP",
    }
    assert value["publisher"]["name"] == "Example News"
    assert value["publisher"]["state"] == "PUBLISHER_RESOLVED_ARTICLE_ROLE_PENDING"
    assert value["attribution"]["author_byline"] == "A. Reporter"


def test_jsonld_graph_and_nested_author_are_supported() -> None:
    value = _metadata(
        """<script type="application/ld+json">{"@graph":[
        {"@type":"Organization","name":"Graph News"},
        {"@type":["NewsArticle","ReportageNewsArticle"],"headline":"Graph headline",
        "datePublished":"2026-09-10","publisher":{"name":"Graph News"},"author":[{"name":"One"},{"name":"Two"}]}
        ]}</script>"""
    )
    assert value["title"] == "Graph headline"
    assert value["publication_date"]["normalized"] == "2026-09-10"
    assert value["attribution"]["author_byline"] == "One; Two"
    assert "NewsArticle" in value["jsonld_article_types"]


def test_open_graph_then_h1_then_document_title_fallbacks_are_ordered() -> None:
    og = _metadata("<title>Document title</title><meta property='og:title' content='OpenGraph title'><meta property='og:site_name' content='OG Publisher'>", "<h1>Heading title</h1>")
    h1 = _metadata("<title>Document title</title>", "<h1>Heading title</h1>")
    document = _metadata("<title>Document title</title>")
    assert (og["title"], og["title_source"], og["publisher"]["name"]) == ("OpenGraph title", "OPEN_GRAPH_TITLE", "OG Publisher")
    assert (h1["title"], h1["title_source"]) == ("Heading title", "HTML_H1")
    assert (document["title"], document["title_source"]) == ("Document title", "DOCUMENT_TITLE")


def test_meta_and_time_date_cascade_never_uses_crawl_time() -> None:
    meta = _metadata("<meta property='article:published_time' content='2026-09-11T10:00:00+01:00'>")
    time = _metadata("", "<time datetime='2026-09-12T12:00:00Z'>today</time>")
    missing = _metadata("<meta property='og:title' content='Title only'>")
    assert meta["publication_date"]["source"] == "META_PUBLICATION_DATE"
    assert time["publication_date"]["source"] == "HTML_TIME"
    assert missing["publication_date"]["raw"] is None
    assert missing["publication_date"]["normalized"] is None


def test_attribution_preserves_wire_and_partner_hints_without_trust() -> None:
    value = _metadata(
        "<meta name='author' content='Named author'>",
        "<article><p>Reporting by Reuters in partnership with the local newsroom.</p></article>",
    )
    assert value["attribution"]["author_byline"] == "Named author"
    assert value["attribution"]["wire_credit"] == "REUTERS"
    assert value["attribution"]["article_origin_state"] == "WIRE_REPUBLICATION"


def test_metadata_is_available_even_without_article_body_and_missing_title_is_explicit() -> None:
    value = _metadata("<meta property='og:site_name' content='Metadata Desk'>")
    missing = _metadata("")
    assert value["publisher"]["state"] == "PUBLISHER_RESOLVED_ARTICLE_ROLE_PENDING"
    assert missing["title"] is None
    assert missing["title_state"] == "TITLE_UNRESOLVED"


def test_news_un_representative_fixture_resolves_not_placeholder() -> None:
    value = _metadata(
        """<title>Security Council LIVE: Rising tensions in Gaza, West Bank | UN News</title>
        <meta property='og:title' content='Security Council LIVE: Rising tensions in Gaza, West Bank'>
        <meta property='article:published_time' content='2026-08-26T09:50:47-04:00'>
        <script type='application/ld+json'>{"@type":"NewsArticle","headline":"Security Council LIVE: Rising tensions in Gaza, West Bank","datePublished":"2026-08-26T09:50:47-04:00","publisher":{"name":"UN News"},"author":{"name":"UN News"}}</script>""",
        "<h1>Security Council LIVE: Rising tensions in Gaza, West Bank</h1>",
    )
    assert value["title"] == "Security Council LIVE: Rising tensions in Gaza, West Bank"
    assert value["publication_date"]["raw"] == "2026-08-26T09:50:47-04:00"
    assert value["publisher"]["name"] == "UN News"
