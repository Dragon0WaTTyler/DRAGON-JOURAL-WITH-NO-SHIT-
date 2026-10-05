from pathlib import Path
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

from dragon.publication import build_cover_png, build_epub, validate_epub
from dragon.state import sha256_file


DATE = "2099-01-02"


def _article() -> dict:
    return {
        "id": "article-1", "section": "العلوم", "headline": "عنوان عربي موثق",
        "standfirst": "مقدمة عربية واضحة للقارئ", "byline": "تحرير: DRAGON",
        "body": ["متن عربي موثق يختبر القراءة وإعادة التدفق واتجاه النص من اليمين إلى اليسار. " * 8],
        "source_urls": ["https://example.org/exact-source"],
    }


def _fixture(tmp_path: Path) -> tuple[Path, Path]:
    cover = build_cover_png(
        tmp_path / "cover.png", DATE, "عنوان عربي موثق", "مقدمة عربية واضحة للقارئ"
    )
    epub = build_epub(tmp_path / "edition.epub", DATE, [_article()], cover)
    return epub, cover


def _rewrite(source: Path, destination: Path, member: str, transform, *, omit: str | None = None) -> Path:
    with ZipFile(source) as incoming, ZipFile(destination, "w") as outgoing:
        for info in incoming.infolist():
            if info.filename == omit:
                continue
            payload = incoming.read(info.filename)
            if info.filename == member:
                payload = transform(payload)
            outgoing.writestr(
                info.filename,
                payload,
                compress_type=ZIP_STORED if info.filename == "mimetype" else ZIP_DEFLATED,
            )
    return destination


def test_epub_is_deterministic_valid_reflowable_arabic(tmp_path: Path) -> None:
    epub, cover = _fixture(tmp_path)
    repeated = build_epub(tmp_path / "repeated.epub", DATE, [_article()], cover)
    report = validate_epub(
        epub,
        canonical_cover=cover,
        expected_article_ids=("article-1",),
        expected_source_urls=("https://example.org/exact-source",),
    )
    assert report["status"] == "PASS"
    assert report["language"]["status"] == "PASS"
    assert sha256_file(epub) == sha256_file(repeated)


def test_epub_reports_malformed_opf_nav_and_xhtml_separately(tmp_path: Path) -> None:
    epub, cover = _fixture(tmp_path)
    cases = {
        "OEBPS/content.opf": "EPUB_OPF_XML_INVALID",
        "OEBPS/nav.xhtml": "EPUB_NAV_XML_INVALID",
        "OEBPS/edition.xhtml": "EPUB_XHTML_XML_INVALID",
    }
    for index, (member, expected) in enumerate(cases.items()):
        broken = _rewrite(epub, tmp_path / f"broken-{index}.epub", member, lambda _value: b"<")
        assert expected in validate_epub(broken, canonical_cover=cover)["issues"]


def test_epub_blocks_remote_or_missing_assets_and_bad_navigation(tmp_path: Path) -> None:
    epub, cover = _fixture(tmp_path)
    remote = _rewrite(
        epub, tmp_path / "remote.epub", "OEBPS/content.opf",
        lambda value: value.replace(b'href="style.css"', b'href="https://example.org/style.css"'),
    )
    assert any(issue.startswith("EPUB_REMOTE_MANIFEST_ASSET") for issue in validate_epub(remote)["issues"])

    missing = _rewrite(epub, tmp_path / "missing.epub", "unused", lambda value: value, omit="OEBPS/cover.png")
    missing_issues = validate_epub(missing, canonical_cover=cover)["issues"]
    assert any(issue.startswith("EPUB_MEMBERS_MISSING") for issue in missing_issues)
    assert any(issue.startswith("EPUB_MANIFEST_ASSET_MISSING") for issue in missing_issues)

    bad_nav = _rewrite(
        epub, tmp_path / "bad-nav.epub", "OEBPS/nav.xhtml",
        lambda value: value.replace(b'href="edition.xhtml"', b'href="missing.xhtml"'),
    )
    assert "EPUB_NAV_TARGET_MISSING:missing.xhtml" in validate_epub(bad_nav)["issues"]


def test_epub_rejects_wrong_direction_missing_cover_metadata_and_corrupt_zip(tmp_path: Path) -> None:
    epub, _cover = _fixture(tmp_path)
    wrong_direction = _rewrite(
        epub, tmp_path / "ltr.epub", "OEBPS/content.opf",
        lambda value: value.replace(b'page-progression-direction="rtl"', b'page-progression-direction="ltr"'),
    )
    assert "EPUB_RTL_METADATA_INVALID" in validate_epub(wrong_direction)["issues"]

    no_cover_metadata = _rewrite(
        epub, tmp_path / "no-cover-meta.epub", "OEBPS/content.opf",
        lambda value: value.replace(b' properties="cover-image"', b''),
    )
    assert "EPUB_COVER_METADATA_INVALID" in validate_epub(no_cover_metadata)["issues"]

    corrupt = tmp_path / "corrupt.epub"
    corrupt.write_bytes(b"not a zip")
    assert validate_epub(corrupt)["issues"][0].startswith("EPUB_OPEN_FAILED")
