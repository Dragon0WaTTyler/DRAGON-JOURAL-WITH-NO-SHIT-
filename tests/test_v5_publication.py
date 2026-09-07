import json
from pathlib import Path

from pypdf import PdfReader

from dragon.publication import build_cover_png, render_pdf, validate_pdf


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
    report = validate_pdf(pdf)

    assert len(PdfReader(str(pdf)).pages) >= 4
    assert report["status"] == "PASS"
    assert report["populated_pages"] == report["pages"]
