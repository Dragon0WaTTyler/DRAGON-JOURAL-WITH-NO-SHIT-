from pathlib import Path

import json

from dragon.acceptance import (
    _archive_receipt_valid,
    _checkpointed_receipt,
    _consecutive,
    _delivery_receipt_valid,
    _provider_trial_evidence,
    _publication_evidence_issues,
    _review_file_evidence,
    _state_valid,
    audit_cutover,
)
from dragon.assets import asset_record, build_asset_manifest
from dragon.state import runtime_fingerprint, sha256_file


def test_consecutive_trial_dates_require_an_unbroken_sequence() -> None:
    assert _consecutive(["2099-01-01", "2099-01-02", "2099-01-04"], 3) == []
    assert _consecutive(["2099-01-04", "2099-01-02", "2099-01-03"], 3) == [
        "2099-01-02",
        "2099-01-03",
        "2099-01-04",
    ]


def test_repository_cutover_audit_is_fail_closed() -> None:
    result = audit_cutover(Path(__file__).resolve().parents[1])
    assert result["status"] == "BLOCKED"
    assert result["checks"]["editorial_provider_proven"] is False
    assert result["completion_checks"]["local_scheduler_enabled"] is False


def test_configured_pass_without_provider_trial_evidence_is_not_proven(
    tmp_path: Path, monkeypatch
) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "cutover-acceptance.yaml").write_text(
        "version: 5\nrequired_consecutive_unattended_runs: 1\nrequired_review_evidence: []\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "dragon.acceptance.load_local_config",
        lambda root: {
            "providers": {
                "ai": {"type": "local-command", "integration_test_status": "PASS"}
            },
            "scheduler": {"enabled": False},
            "cutover": {},
        },
    )

    result = audit_cutover(tmp_path)

    assert result["checks"]["editorial_provider_proven"] is False
    assert result["evidence"]["provider_trials"] == []


def test_external_receipt_must_match_its_complete_checkpoint(tmp_path: Path) -> None:
    receipt = tmp_path / "daily-runs" / "2099-01-02" / "archive-receipt.json"
    receipt.parent.mkdir(parents=True)
    receipt.write_text(json.dumps({"status": "COMPLETE"}), encoding="utf-8")
    relative = "daily-runs/2099-01-02/archive-receipt.json"
    state = {
        "date": "2099-01-02",
        "stages": {
            "github_archive": {
                "status": "COMPLETE",
                "artifact_hashes": {relative: sha256_file(receipt)},
            }
        },
    }

    assert _checkpointed_receipt(
        tmp_path, state, "github_archive", "archive-receipt.json"
    ) == {"status": "COMPLETE"}

    receipt.write_text(json.dumps({"status": "COMPLETE", "tampered": True}), encoding="utf-8")
    assert _checkpointed_receipt(
        tmp_path, state, "github_archive", "archive-receipt.json"
    ) is None


def test_archive_receipt_binds_runtime_manifest_and_remote_artifacts(tmp_path: Path) -> None:
    day = "2099-01-02"
    edition = tmp_path / "editions" / "2099" / "01" / day
    edition.mkdir(parents=True)
    article = edition / "edition.md"
    article.write_text("نسخة", encoding="utf-8")
    article_relative = f"editions/2099/01/{day}/edition.md"
    manifest = edition / "manifest.json"
    manifest.write_text(
        json.dumps({"artifacts": [{"path": article_relative, "sha256": sha256_file(article)}]}),
        encoding="utf-8",
    )
    manifest_relative = f"editions/2099/01/{day}/manifest.json"
    manifest_hash = sha256_file(manifest)
    state = {
        "date": day,
        "runtime_fingerprint": "runtime-1",
        "archive_status": "COMPLETE",
        "stages": {"github_archive": {"input_hashes": {manifest_relative: manifest_hash}}},
    }
    receipt = {
        "schema_version": 5,
        "stage": "github_archive",
        "mode": "production",
        "edition_date": day,
        "runtime_fingerprint": "runtime-1",
        "publication_status": "COMPLETE",
        "status": "COMPLETE",
        "verified": True,
        "commit": "abc",
        "remote_commit": "abc",
        "manifest_sha256": manifest_hash,
        "artifacts": [
            {"path": article_relative, "sha256": sha256_file(article)},
            {"path": manifest_relative, "sha256": manifest_hash},
        ],
    }
    assert _archive_receipt_valid(tmp_path, state, receipt) is True
    receipt["manifest_sha256"] = "tampered"
    assert _archive_receipt_valid(tmp_path, state, receipt) is False


def test_delivery_receipt_binds_runtime_pdf_and_recipient_acceptance(tmp_path: Path) -> None:
    day = "2099-01-02"
    pdf = tmp_path / "editions" / "2099" / "01" / day / f"DRAGON-{day}.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"%PDF-1.7\nfixture")
    relative = f"editions/2099/01/{day}/DRAGON-{day}.pdf"
    pdf_hash = sha256_file(pdf)
    state = {
        "date": day,
        "runtime_fingerprint": "runtime-1",
        "delivery_status": "COMPLETE",
        "stages": {"whatsapp_delivery": {"input_hashes": {relative: pdf_hash}}},
    }
    receipt = {
        "schema_version": 5,
        "stage": "whatsapp_delivery",
        "mode": "production",
        "edition_date": day,
        "runtime_fingerprint": "runtime-1",
        "publication_status": "COMPLETE",
        "status": "COMPLETE",
        "accepted": True,
        "pdf_sha256": pdf_hash,
        "delivery_fingerprint": "a" * 64,
        "recipients": [
            {
                "status": "ACCEPTED_BY_PROVIDER",
                "recipient_hash": "recipient-1",
                "message_id": "message-1",
            }
        ],
    }
    assert _delivery_receipt_valid(tmp_path, state, receipt) is True
    receipt["recipients"][0]["status"] = "UNKNOWN"
    assert _delivery_receipt_valid(tmp_path, state, receipt) is False


def test_acceptance_rejects_missing_or_stale_runtime_fingerprint(tmp_path: Path) -> None:
    state = {
        "schema_version": 5,
        "date": "2099-01-02",
        "run_id": "run-1",
        "publication_status": "COMPLETE",
        "stages": {},
        "report_paths": [],
    }
    _, missing = _state_valid(tmp_path, state)
    assert "RUNTIME_FINGERPRINT_MISSING" in missing

    state["runtime_fingerprint"] = runtime_fingerprint(tmp_path)
    runtime_file = tmp_path / "dragon" / "pipeline.py"
    runtime_file.parent.mkdir(parents=True)
    runtime_file.write_text("changed = True\n", encoding="utf-8")
    _, stale = _state_valid(tmp_path, state)
    assert "RUNTIME_FINGERPRINT_MISMATCH" in stale


def test_publication_evidence_is_semantically_revalidated(tmp_path: Path) -> None:
    day = "2099-01-02"
    edition = tmp_path / "editions" / "2099" / "01" / day
    run = tmp_path / "daily-runs" / day
    (edition / "assets").mkdir(parents=True)
    (run / "qa").mkdir(parents=True)
    cover = edition / "assets" / "cover.png"
    cover.write_bytes(b"cover-bytes")
    asset = asset_record(
        cover,
        edition,
        asset_id="canonical-cover",
        classification="EDITORIAL_ILLUSTRATION",
        role="CANONICAL_COVER",
        source_ids=["source-1"],
        documentary_evidence=False,
        generated_by="fixture",
        license_use_notes="Fixture only.",
    )
    asset_manifest = edition / "assets-manifest.json"
    asset_manifest.write_text(
        json.dumps(build_asset_manifest(day, "synthetic", [asset])), encoding="utf-8"
    )
    final = {
        "status": "PASS", "issues": [],
        "editorial_status": "PASS", "factcheck_status": "PASS",
        "arabic_status": "PASS", "pdf_status": "PASS",
        "pdf_visual_status": "PASS", "epub_status": "PASS",
        "epubcheck_status": "PASS", "layout_status": "PASS",
    }
    (edition / "final-qa.json").write_text(json.dumps(final), encoding="utf-8")
    (run / "qa" / "epubcheck.json").write_text(
        json.dumps({
            "status": "PASS", "validator": "W3C_EPUBCHECK", "version": "5.3.0",
            "fatal_count": 0, "error_count": 0,
        }),
        encoding="utf-8",
    )
    manifest_entries = []
    for path in (cover, asset_manifest, edition / "final-qa.json", run / "qa" / "epubcheck.json"):
        manifest_entries.append({
            "path": path.relative_to(tmp_path).as_posix(), "sha256": sha256_file(path)
        })
    (edition / "manifest.json").write_text(
        json.dumps({"artifacts": manifest_entries}), encoding="utf-8"
    )
    evolution = tmp_path / "evolution" / "reports" / f"{day}.json"
    evolution.parent.mkdir(parents=True)
    evolution.write_text(
        json.dumps({
            "status": "NOT_DUE",
            "dragon_eval_dimensions": [
                "presentation", "analysis", "evidence", "citation_support",
                "journalism_quality", "arabic_editorial_quality", "visual_quality",
            ],
            "control_plane": {"automatic_production_mutation": False, "separate_schedule": False},
        }),
        encoding="utf-8",
    )
    state = {"date": day}
    assert _publication_evidence_issues(tmp_path, state) == []
    cover.write_bytes(b"tampered")
    issues = _publication_evidence_issues(tmp_path, state)
    assert "ASSET_INVALID:canonical-cover:IDENTITY" in issues
    assert any(item.startswith("PUBLICATION_MANIFEST_HASH_INVALID") for item in issues)


def test_provider_trial_requires_hash_bound_human_review(tmp_path: Path) -> None:
    trial = tmp_path / "acceptance" / "provider-trials" / "2099-01-02"
    trial.mkdir(parents=True)
    research = trial / "research.json"
    articles = trial / "articles.json"
    research.write_text('{"sources":[]}', encoding="utf-8")
    articles.write_text('{"articles":[]}', encoding="utf-8")
    fingerprint = runtime_fingerprint(tmp_path)
    receipt = {
        "schema_version": 5,
        "status": "VALIDATED_AWAITING_HUMAN_REVIEW",
        "edition_date": "2099-01-02",
        "created_at": "2099-01-02T11:00:00+01:00",
        "editorial_generation_tested": True,
        "runtime_fingerprint": fingerprint,
        "source_git_revision": "abc123",
        "provider": {"status": "PASS", "unattended": True},
        "artifacts": {
            "acceptance/provider-trials/2099-01-02/research.json": sha256_file(research),
            "acceptance/provider-trials/2099-01-02/articles.json": sha256_file(articles),
        },
    }
    receipt_path = trial / "receipt.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    valid, evidence = _provider_trial_evidence(tmp_path, fingerprint)
    assert valid is False
    assert "HUMAN_REVIEW_MISSING_OR_INVALID" in evidence[0]["issues"]

    review = {
        "schema_version": 5,
        "status": "PASS",
        "reviewed_by": "Human Editor",
        "reviewed_at": "2099-01-02T12:00:00+01:00",
        "receipt_sha256": sha256_file(receipt_path),
        "checks": {
            "sources": "PASS",
            "factual_accuracy": "PASS",
            "arabic_quality": "PASS",
            "article_depth": "PASS",
            "section_decisions": "PASS",
        },
    }
    (trial / "review.json").write_text(json.dumps(review), encoding="utf-8")
    valid, evidence = _provider_trial_evidence(tmp_path, fingerprint)
    assert valid is True
    assert evidence[0]["status"] == "PASS"

    articles.write_text('{"articles":[{"tampered":true}]}', encoding="utf-8")
    valid, evidence = _provider_trial_evidence(tmp_path, fingerprint)
    assert valid is False
    assert any(issue.startswith("TRIAL_ARTIFACT_HASH_INVALID") for issue in evidence[0]["issues"])


def test_cutover_review_requires_current_runtime_checks_and_hashed_evidence(
    tmp_path: Path,
) -> None:
    proof = tmp_path / "daily-runs" / "2099-01-02" / "proof.json"
    proof.parent.mkdir(parents=True)
    proof.write_text('{"observed":true}', encoding="utf-8")
    fingerprint = runtime_fingerprint(tmp_path)
    review_dir = tmp_path / "acceptance" / "evidence"
    review_dir.mkdir(parents=True)
    review = {
        "schema_version": 5,
        "status": "PASS",
        "reviewed_by": "Human Operator",
        "reviewed_at": "2099-01-02T12:00:00+01:00",
        "runtime_fingerprint": fingerprint,
        "checks": {"resume": "PASS", "state_integrity": "PASS"},
        "evidence": {
            "daily-runs/2099-01-02/proof.json": sha256_file(proof),
        },
    }
    review_path = review_dir / "failure-injection.json"
    review_path.write_text(json.dumps(review), encoding="utf-8")

    accepted = _review_file_evidence(
        tmp_path,
        "failure-injection.json",
        ["resume", "state_integrity"],
        fingerprint,
    )
    assert accepted["status"] == "PASS"

    proof.write_text('{"observed":false}', encoding="utf-8")
    rejected = _review_file_evidence(
        tmp_path,
        "failure-injection.json",
        ["resume", "state_integrity"],
        fingerprint,
    )
    assert rejected["status"] == "MISSING_OR_INVALID"
    assert any(issue.startswith("REVIEW_EVIDENCE_HASH_INVALID") for issue in rejected["issues"])
