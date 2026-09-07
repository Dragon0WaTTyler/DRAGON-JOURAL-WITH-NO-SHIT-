import json
from pathlib import Path

from pypdf import PdfReader

from dragon.publication import (
    build_cover_png,
    render_pdf,
    validate_pdf,
    validate_publication_source,
)


def test_long_arabic_article_expands_pages_instead_of_clipping(tmp_path: Path) -> None:
    edition = tmp_path / "editions" / "2099" / "01" / "2099-01-02"
    edition.mkdir(parents=True)
    build_cover_png(
        edition / "assets" / "cover.png",
        "2099-01-02",
        "عنوان عربي طويل للاختبار",
        "مقدمة توضح أن الصفحة يجب أن تتوسع قبل قطع المادة الموثقة.",
    )
    words = "هذه مادة عربية موثقة تختبر استمرار الفقرات عبر صفحات متعددة من دون حذف أو قص "
    article = {
        "id": "long-article",
        "section_id": "front",
        "section": "الواجهة",
        "status": "ACTIVE",
        "headline": "اختبار التمدد الآمن للمقال العربي الطويل",
        "standfirst": "يجب أن يضيف المحرك صفحات جديدة ويحافظ على اتجاه القراءة.",
        "byline": "تحرير: DRAGON",
        "body": [words * 120],
        "source_urls": ["https://example.org/a/very/long/exact/source/page/for/the/article"],
    }
    (edition / "articles.json").write_text(
        json.dumps({"mode": "production", "articles": [article]}, ensure_ascii=False),
        encoding="utf-8",
    )
    html = edition / "edition.html"
    html.write_text('<html lang="ar" dir="rtl"></html>', encoding="utf-8")

    pdf = render_pdf(html, edition / "DRAGON-2099-01-02.pdf")
    report = validate_pdf(pdf, canonical_cover=edition / "assets" / "cover.png")

    assert len(PdfReader(str(pdf)).pages) >= 4
    assert report["status"] == "PASS"
    assert report["populated_pages"] == report["pages"]
    assert report["cover_visual_rms"] < 8


def test_pdf_validator_rejects_a_different_first_page_cover(tmp_path: Path) -> None:
    edition = tmp_path / "edition"
    edition.mkdir()
    canonical = build_cover_png(
        edition / "assets" / "cover.png",
        "2099-01-02",
        "العنوان الأصلي",
        "المقدمة الأصلية",
    )
    (edition / "articles.json").write_text(
        json.dumps(
            {
                "mode": "production",
                "articles": [
                    {
                        "id": "a",
                        "section": "الواجهة",
                        "status": "ACTIVE",
                        "headline": "العنوان الأصلي",
                        "standfirst": "المقدمة الأصلية",
                        "byline": "تحرير: DRAGON",
                        "body": ["متن عربي للاختبار"],
                        "source_urls": [],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    html = edition / "edition.html"
    html.write_text("x", encoding="utf-8")
    pdf = render_pdf(html, edition / "edition.pdf")
    other = build_cover_png(
        edition / "other.png",
        "2099-01-03",
        "عنوان مختلف تماما",
        "مقدمة مختلفة تماما",
    )
    assert validate_pdf(pdf, canonical_cover=other)["status"] == "FAIL"
    assert validate_pdf(pdf, canonical_cover=canonical)["status"] == "PASS"


def test_publication_source_requires_exact_article_sources() -> None:
    article = {
        "id": "a1",
        "source_urls": ["https://example.org/exact?a=1&b=2"],
    }
    valid = '<html lang="ar" dir="rtl"><body><img src="assets/cover.png"><article id="a1"><a href="https://example.org/exact?a=1&amp;b=2">مصدر</a></article></body></html>'
    assert validate_publication_source(valid, [article]) == []
    issues = validate_publication_source(
        valid.replace("/exact?", "/wrong?"), [article]
    )
    assert any(issue.startswith("HTML_SOURCE_LINK_MISSING") for issue in issues)
