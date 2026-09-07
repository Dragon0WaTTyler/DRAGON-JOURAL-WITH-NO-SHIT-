from __future__ import annotations

import json
from pathlib import Path
from zipfile import ZIP_STORED, ZipFile

from pypdf import PdfReader

from dragon.orchestrator import Orchestrator
from dragon.pipeline import build_stage_definitions
from dragon.providers import SyntheticEditorialProvider, UnconfiguredEditorialProvider


DATE = "2099-01-02"


def test_synthetic_pipeline_creates_real_arabic_publications(tmp_path: Path) -> None:
    stages = build_stage_definitions(SyntheticEditorialProvider(), synthetic=True)
    orchestrator = Orchestrator(root=tmp_path, edition_date=DATE, timezone="Africa/Casablanca", stages=stages, use_lock=False)
    state = orchestrator.run()
    edition = tmp_path / "editions" / "2099" / "01" / DATE
    pdf = edition / f"DRAGON-{DATE}.pdf"
    epub = edition / f"DRAGON-{DATE}.epub"
    assert state["publication_status"] == "COMPLETE"
    assert state["archive_status"] == "DEGRADED"
    assert state["delivery_status"] == "DEGRADED"
    assert state["stages"]["github_archive"]["prerequisites"] == ["final_qa"]
    assert state["stages"]["whatsapp_delivery"]["prerequisites"] == ["final_qa"]
    assert len(PdfReader(str(pdf)).pages) == 24
    with ZipFile(epub) as archive:
        assert archive.namelist()[0] == "mimetype"
        assert archive.getinfo("mimetype").compress_type == ZIP_STORED
        assert b"<dc:language>ar</dc:language>" in archive.read("OEBPS/content.opf")
        xhtml = archive.read("OEBPS/edition.xhtml").decode("utf-8")
        assert 'lang="ar"' in xhtml and 'dir="rtl"' in xhtml
    report = json.loads((edition / "final-qa.json").read_text(encoding="utf-8"))
    assert report["status"] == "PASS"
    assert report["mode"] == "synthetic"
    assert report["active_sections"] == 23


def test_synthetic_resume_reuses_hash_bound_checkpoints(tmp_path: Path) -> None:
    stages = build_stage_definitions(SyntheticEditorialProvider(), synthetic=True)
    orchestrator = Orchestrator(root=tmp_path, edition_date=DATE, timezone="Africa/Casablanca", stages=stages, use_lock=False)
    first = orchestrator.run()
    attempts = {name: record["attempt_count"] for name, record in first["stages"].items()}
    second = orchestrator.run(resume=True)
    assert {name: record["attempt_count"] for name, record in second["stages"].items()} == attempts


def test_unconfigured_production_provider_never_generates_fixture_news() -> None:
    provider = UnconfiguredEditorialProvider()
    try:
        provider.research(DATE)
    except RuntimeError as exc:
        assert str(exc) == "AI_PROVIDER_UNCONFIGURED"
    else:
        raise AssertionError("production provider unexpectedly returned content")
