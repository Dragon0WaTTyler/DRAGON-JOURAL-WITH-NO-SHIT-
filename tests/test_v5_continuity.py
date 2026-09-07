from pathlib import Path

from dragon.continuity import build_snapshot, prior_context
from dragon.state import atomic_write_json


def test_prior_context_uses_only_earlier_production_snapshots(tmp_path: Path) -> None:
    production = tmp_path / "editions" / "2099" / "01" / "2099-01-01" / "continuity.json"
    synthetic = tmp_path / "editions" / "2099" / "01" / "2099-01-02" / "continuity.json"
    future = tmp_path / "editions" / "2099" / "01" / "2099-01-04" / "continuity.json"
    atomic_write_json(production, {"schema_version": 5, "date": "2099-01-01", "mode": "production", "covered_stories": []})
    atomic_write_json(synthetic, {"schema_version": 5, "date": "2099-01-02", "mode": "synthetic", "covered_stories": []})
    atomic_write_json(future, {"schema_version": 5, "date": "2099-01-04", "mode": "production", "covered_stories": []})

    value = prior_context(tmp_path, "2099-01-03")

    assert value["edition_count"] == 1
    assert value["editions"][0]["date"] == "2099-01-01"


def test_snapshot_records_coverage_skips_and_next_steps() -> None:
    decisions = [
        {
            "id": "a1",
            "section_id": "front",
            "status": "ACTIVE",
            "headline": "عنوان",
            "source_urls": ["https://example.org/story"],
            "editorial_elements": {"next_steps": ["موعد القرار المقبل"]},
        },
        {
            "section_id": "science",
            "status": "SKIPPED",
            "skip_reason": "لم تتوفر دراسة أصلية قابلة للتحقق",
        },
    ]
    value = build_snapshot("2099-01-02", "production", decisions)
    assert value["covered_stories"][0]["article_id"] == "a1"
    assert value["skipped_sections"][0]["section_id"] == "science"
    assert value["watch_items"][0]["description"] == "موعد القرار المقبل"
