import json
from pathlib import Path

from jsonschema import Draft202012Validator

from dragon.source_intelligence import build_source_intelligence, normalize_url


ROOT = Path(__file__).resolve().parents[1]


def _source(identifier: str, url: str, publisher: str) -> dict:
    return {
        "id": identifier,
        "url": url,
        "publisher": publisher,
        "publication_date": "2099-01-02",
        "accessed_at": "2099-01-02T07:00:00+01:00",
        "source_type": "independent",
        "claim_supported": "خبر موثق",
    }


def test_url_normalization_removes_tracking_without_losing_query_identity() -> None:
    assert normalize_url("HTTPS://Example.ORG:443/a//b?utm_source=x&id=7#part") == (
        "https://example.org/a/b?id=7"
    )


def test_source_intelligence_preserves_lineage_and_detects_wire_duplicates() -> None:
    packet = {
        "sources": [
            _source("s1", "https://example.org/story?id=7&utm_source=x", "Reuters"),
            _source("s2", "https://example.org/story?utm_medium=y&id=7", "رويترز"),
            _source("s3", "https://official.example/report", "وزارة الاختبار"),
        ],
        "sections": [
            {
                "section_id": "front",
                "candidates": [
                    {
                        "id": "lead",
                        "title": "تقرير رسمي جديد عن الاختبار",
                        "discovery_source_ids": ["s1"],
                        "verification_source_ids": ["s2", "s3"],
                        "primary_evidence_source_ids": ["s3"],
                        "independent_evidence_source_ids": ["s1"],
                    }
                ],
            },
            {
                "section_id": "world",
                "candidates": [
                    {
                        "id": "same-event",
                        "title": "تقرير رسمي جديد عن الاختبار",
                        "discovery_source_ids": ["s2"],
                        "verification_source_ids": ["s3"],
                        "primary_evidence_source_ids": [],
                        "independent_evidence_source_ids": ["s2"],
                    }
                ],
            },
        ],
    }

    first = build_source_intelligence(packet)
    second = build_source_intelligence(packet)
    schema = json.loads(
        (ROOT / "config" / "source-intelligence-schema.json").read_text(encoding="utf-8")
    )
    Draft202012Validator(schema).validate(first)
    assert first == second
    assert first["summary"] == {
        "source_count": 3,
        "canonical_source_count": 2,
        "duplicate_group_count": 1,
        "event_count": 1,
        "wire_source_count": 2,
    }
    assert first["duplicate_groups"][0]["source_ids"] == ["s1", "s2"]
    assert first["event_clusters"][0]["independent_origin_count"] == 2
    records = {item["source_id"]: item for item in first["source_records"]}
    assert records["s1"]["discovered_url"].endswith("utm_source=x")
    assert records["s1"]["canonical_url"] == records["s2"]["canonical_url"]
    assert records["s1"]["wire_origin"] == records["s2"]["wire_origin"] == "REUTERS"
    assert records["s3"]["fetch_status"] == "PROVIDER_REPORTED"
    assert "FETCH_NOT_INDEPENDENTLY_VERIFIED" in records["s3"]["uncertainty"]
