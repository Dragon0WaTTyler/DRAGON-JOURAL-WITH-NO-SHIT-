"""Local asset provenance records and publication safety validation."""

from __future__ import annotations

from pathlib import Path

from dragon.state import sha256_file


ASSET_CLASSES = {
    "SOURCE_PHOTO",
    "ARCHIVAL_IMAGE",
    "EDITORIAL_ILLUSTRATION",
    "AI_EDITORIAL_ART",
    "CHART",
    "DOCUMENT_EXCERPT",
    "DECORATIVE",
}

DOCUMENTARY_CLASSES = {"SOURCE_PHOTO", "ARCHIVAL_IMAGE", "DOCUMENT_EXCERPT"}


def asset_record(
    path: Path,
    edition_dir: Path,
    *,
    asset_id: str,
    classification: str,
    role: str,
    source_ids: list[str],
    documentary_evidence: bool,
    generated_by: str,
    license_use_notes: str,
    ai_generated: bool = False,
    chart: dict | None = None,
) -> dict:
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(edition_dir.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError("ASSET_PATH_OUTSIDE_EDITION") from exc
    if not resolved.is_file() or resolved.stat().st_size == 0:
        raise ValueError("ASSET_FILE_MISSING_OR_EMPTY")
    return {
        "asset_id": asset_id,
        "path": relative,
        "classification": classification,
        "role": role,
        "source_ids": source_ids,
        "documentary_evidence": documentary_evidence,
        "ai_generated": ai_generated,
        "generated_by": generated_by,
        "license_use_notes": license_use_notes,
        "local_persisted": True,
        "sha256": sha256_file(resolved),
        "bytes": resolved.stat().st_size,
        "chart": chart,
    }


def build_asset_manifest(edition_date: str, mode: str, assets: list[dict]) -> dict:
    return {
        "schema_version": 1,
        "edition_date": edition_date,
        "mode": mode,
        "status": "PASS",
        "remote_assets_allowed": False,
        "assets": assets,
    }


def validate_asset_manifest(value: dict, edition_dir: Path) -> list[str]:
    issues = []
    if (
        value.get("schema_version") != 1
        or value.get("remote_assets_allowed") is not False
        or not isinstance(value.get("assets"), list)
    ):
        return ["ASSET_MANIFEST_ROOT_INVALID"]
    identifiers = []
    for asset in value["assets"]:
        asset_id = asset.get("asset_id")
        identifiers.append(asset_id)
        prefix = f"ASSET_INVALID:{asset_id}"
        classification = asset.get("classification")
        if classification not in ASSET_CLASSES:
            issues.append(f"{prefix}:CLASSIFICATION")
        relative = asset.get("path")
        if not isinstance(relative, str) or "://" in relative or Path(relative).is_absolute():
            issues.append(f"{prefix}:PATH")
            continue
        path = (edition_dir / relative).resolve()
        try:
            path.relative_to(edition_dir.resolve())
        except ValueError:
            issues.append(f"{prefix}:PATH_ESCAPE")
            continue
        if not path.is_file() or asset.get("local_persisted") is not True:
            issues.append(f"{prefix}:NOT_LOCAL")
            continue
        if asset.get("sha256") != sha256_file(path) or asset.get("bytes") != path.stat().st_size:
            issues.append(f"{prefix}:IDENTITY")
        source_ids = asset.get("source_ids")
        if not isinstance(source_ids, list):
            issues.append(f"{prefix}:SOURCE_IDS")
            source_ids = []
        if classification in DOCUMENTARY_CLASSES:
            if not source_ids or asset.get("documentary_evidence") is not True:
                issues.append(f"{prefix}:DOCUMENTARY_PROVENANCE")
        elif asset.get("documentary_evidence") is not False:
            issues.append(f"{prefix}:FALSE_DOCUMENTARY_SIGNAL")
        if classification == "AI_EDITORIAL_ART" and asset.get("ai_generated") is not True:
            issues.append(f"{prefix}:AI_CLASSIFICATION")
        if classification != "AI_EDITORIAL_ART" and asset.get("ai_generated") is not False:
            issues.append(f"{prefix}:AI_FLAG")
        if not asset.get("generated_by") or not asset.get("license_use_notes"):
            issues.append(f"{prefix}:USAGE_NOTES")
        if classification == "CHART":
            chart = asset.get("chart")
            required = {"source_ids", "units", "period", "axis", "arabic_labels"}
            if not isinstance(chart, dict) or not required <= chart.keys():
                issues.append(f"{prefix}:CHART_PROVENANCE")
            elif (
                not chart["source_ids"]
                or not chart["units"]
                or not chart["period"]
                or not chart["axis"]
                or not chart["arabic_labels"]
            ):
                issues.append(f"{prefix}:CHART_PROVENANCE")
    if len(identifiers) != len(set(identifiers)):
        issues.append("ASSET_IDS_NOT_UNIQUE")
    if not any(item.get("role") == "CANONICAL_COVER" for item in value["assets"]):
        issues.append("ASSET_CANONICAL_COVER_MISSING")
    return issues
