from pathlib import Path

from dragon.assets import asset_record, build_asset_manifest, validate_asset_manifest


def record(tmp_path: Path, *, classification: str = "EDITORIAL_ILLUSTRATION", chart=None) -> dict:
    edition = tmp_path / "edition"
    asset = edition / "assets" / "cover.png"
    asset.parent.mkdir(parents=True, exist_ok=True)
    asset.write_bytes(b"local image bytes")
    return asset_record(
        asset,
        edition,
        asset_id="canonical-cover",
        classification=classification,
        role="CANONICAL_COVER",
        source_ids=["source-1"],
        documentary_evidence=classification in {"SOURCE_PHOTO", "ARCHIVAL_IMAGE", "DOCUMENT_EXCERPT"},
        generated_by="test-fixture",
        license_use_notes="Fixture only.",
        chart=chart,
    )


def test_local_asset_manifest_binds_bytes_and_classification(tmp_path: Path) -> None:
    edition = tmp_path / "edition"
    manifest = build_asset_manifest("2099-01-02", "synthetic", [record(tmp_path)])
    assert validate_asset_manifest(manifest, edition) == []
    (edition / "assets" / "cover.png").write_bytes(b"tampered")
    assert "ASSET_INVALID:canonical-cover:IDENTITY" in validate_asset_manifest(manifest, edition)


def test_generated_asset_cannot_masquerade_as_documentary_evidence(tmp_path: Path) -> None:
    edition = tmp_path / "edition"
    item = record(tmp_path)
    item["documentary_evidence"] = True
    manifest = build_asset_manifest("2099-01-02", "synthetic", [item])
    assert "ASSET_INVALID:canonical-cover:FALSE_DOCUMENTARY_SIGNAL" in validate_asset_manifest(manifest, edition)


def test_chart_requires_data_provenance_units_period_axis_and_arabic_labels(tmp_path: Path) -> None:
    edition = tmp_path / "edition"
    incomplete = record(tmp_path, classification="CHART", chart={"source_ids": ["source-1"]})
    manifest = build_asset_manifest("2099-01-02", "synthetic", [incomplete])
    assert "ASSET_INVALID:canonical-cover:CHART_PROVENANCE" in validate_asset_manifest(manifest, edition)
    complete = record(
        tmp_path,
        classification="CHART",
        chart={
            "source_ids": ["source-1"],
            "units": "%",
            "period": "2025-2026",
            "axis": {"x": "السنة", "y": "النسبة"},
            "arabic_labels": ["السنة", "النسبة"],
        },
    )
    assert validate_asset_manifest(
        build_asset_manifest("2099-01-02", "synthetic", [complete]), edition
    ) == []


def test_remote_asset_path_is_rejected(tmp_path: Path) -> None:
    edition = tmp_path / "edition"
    item = record(tmp_path)
    item["path"] = "https://example.org/expiring.png"
    manifest = build_asset_manifest("2099-01-02", "synthetic", [item])
    assert "ASSET_INVALID:canonical-cover:PATH" in validate_asset_manifest(manifest, edition)
