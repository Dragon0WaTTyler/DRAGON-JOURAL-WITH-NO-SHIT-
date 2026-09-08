import json
from pathlib import Path

from pypdf import PdfReader

from dragon.publication import (
    build_pdf_contact_sheet,
    build_cover_png,
    build_html,
    render_pdf,
    validate_pdf,
    validate_pdf_visuals,
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
    report = validate_pdf(
        pdf,
        canonical_cover=edition / "assets" / "cover.png",
        expected_source_urls=tuple(article["source_urls"]),
        minimum_content_fill=0.55,
    )

    assert len(PdfReader(str(pdf)).pages) >= 4
    assert report["status"] == "PASS"
    assert report["populated_pages"] == report["pages"]
    assert report["cover_visual_rms"] < 8
    assert report["source_links"] == 1
    annotations = [
        annotation.get_object()
        for page in PdfReader(str(pdf)).pages
        for annotation in page.get("/Annots", [])
    ]
    assert any(
        str((annotation.get("/A") or {}).get("/URI")) == article["source_urls"][0]
        for annotation in annotations
    )


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


def test_publication_source_binds_functional_layout_grammar(tmp_path: Path) -> None:
    article = {
        "id": "science-1", "section": "العلوم", "headline": "دراسة جديدة",
        "standfirst": "مقدمة", "byline": "تحرير: DRAGON", "body": ["متن عربي"],
        "source_urls": ["https://example.org/paper"],
    }
    layout = {"pages": [{"article_id": "science-1", "page_role": "SCIENCE"}]}
    html = build_html(tmp_path, "2099-01-02", [article], layout_plan=layout)
    document = html.read_text(encoding="utf-8")
    assert 'data-page-grammar="SCIENCE"' in document
    assert validate_publication_source(document, [article], layout) == []


def test_pdf_visual_qa_persists_contact_sheet_and_reports_human_review(tmp_path: Path) -> None:
    edition = tmp_path / "edition"
    edition.mkdir()
    build_cover_png(
        edition / "assets" / "cover.png", "2099-01-02", "عنوان عربي", "مقدمة عربية"
    )
    article = {
        "id": "a", "section": "الواجهة", "status": "ACTIVE",
        "headline": "عنوان عربي", "standfirst": "مقدمة عربية",
        "byline": "تحرير: DRAGON", "body": ["متن عربي موثق " * 400],
        "source_urls": ["https://example.org/source"],
    }
    (edition / "articles.json").write_text(
        json.dumps({"mode": "synthetic", "articles": [article]}, ensure_ascii=False),
        encoding="utf-8",
    )
    (edition / "layout-plan.json").write_text(
        json.dumps({"pages": [{"article_id": "a", "page_role": "LEAD", "columns": 2}]}),
        encoding="utf-8",
    )
    html = edition / "edition.html"
    html.write_text("x", encoding="utf-8")
    pdf = render_pdf(html, edition / "edition.pdf")
    structural = validate_pdf(pdf, minimum_content_fill=0.55)
    contact = build_pdf_contact_sheet(pdf, tmp_path / "qa" / "contact.png")
    visual = validate_pdf_visuals(
        structural,
        contact,
        {"pages": [
            {"page_role": "LEAD"}, {"page_role": "SCIENCE"},
            {"page_role": "DATA"}, {"page_role": "INVESTIGATION_DOSSIER"},
        ]},
        minimum_content_fill=0.55,
    )
    assert contact.stat().st_size > 10_000
    assert visual["status"] == "PASS"
    assert visual["human_review_status"] == "NOT_RUN"
