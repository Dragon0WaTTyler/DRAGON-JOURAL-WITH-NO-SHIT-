from pathlib import Path

from dragon.continuity import build_snapshot, prior_context
from dragon.state import atomic_write_json, sha256_file


def accepted_snapshot(root: Path, edition_date: str, mode: str = "production") -> Path:
    parsed = edition_date.split("-")
    edition = root / "editions" / parsed[0] / parsed[1] / edition_date
    continuity = edition / "continuity.json"
    atomic_write_json(
        continuity,
        {
            "schema_version": 5,
            "date": edition_date,
            "mode": mode,
            "covered_stories": [],
        },
    )
    report = edition / "final-qa.json"
    atomic_write_json(
        report,
        {
            "status": "PASS",
            "mode": mode,
            "artifacts": [
                {
                    "path": str(continuity.relative_to(root)).replace("\\", "/"),
                    "sha256": sha256_file(continuity),
                }
            ],
        },
    )
    state = root / "daily-runs" / edition_date / "state.json"
    atomic_write_json(
        state,
        {
            "schema_version": 5,
            "date": edition_date,
            "publication_status": "COMPLETE",
            "stages": {
                "final_qa": {
                    "status": "COMPLETE",
                    "artifact_hashes": {
                        str(report.relative_to(root)).replace("\\", "/"): sha256_file(report)
                    },
                }
            },
        },
    )
    return continuity


def test_prior_context_uses_only_earlier_production_snapshots(tmp_path: Path) -> None:
    accepted_snapshot(tmp_path, "2099-01-01")
    accepted_snapshot(tmp_path, "2099-01-02", mode="synthetic")
    accepted_snapshot(tmp_path, "2099-01-04")

    value = prior_context(tmp_path, "2099-01-03")

    assert value["edition_count"] == 1
    assert value["editions"][0]["date"] == "2099-01-01"


def test_prior_context_rejects_unaccepted_or_tampered_continuity(tmp_path: Path) -> None:
    unaccepted = tmp_path / "editions" / "2099" / "01" / "2099-01-01" / "continuity.json"
    atomic_write_json(
        unaccepted,
        {"schema_version": 5, "date": "2099-01-01", "mode": "production"},
    )
    tampered = accepted_snapshot(tmp_path, "2099-01-02")
    tampered.write_text("{}", encoding="utf-8")

    value = prior_context(tmp_path, "2099-01-03")

    assert value["edition_count"] == 0


def test_snapshot_records_coverage_skips_and_next_steps() -> None:
    decisions = [
        {
            "id": "a1",
            "section_id": "front",
            "status": "ACTIVE",
            "headline": "عنوان",
            "story_key": "event-018",
            "story_type": "FACT_CHECK",
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
    assert value["covered_stories"][0]["story_key"] == "event-018"
    assert value["covered_stories"][0]["story_type"] == "FACT_CHECK"
    assert value["skipped_sections"][0]["section_id"] == "science"
    assert value["watch_items"][0]["description"] == "موعد القرار المقبل"
