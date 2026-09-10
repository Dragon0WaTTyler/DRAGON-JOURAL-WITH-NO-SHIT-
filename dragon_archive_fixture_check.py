#!/usr/bin/env python3
"""Verify real Git archive/read-back with clearly labelled cutover fixtures.

This command never creates a newspaper edition.  It clones the configured
remote branch into a temporary directory, archives a disposable fixture only
under ``acceptance/cutover-fixtures/``, and persists a local machine receipt.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from uuid import uuid4
from zoneinfo import ZoneInfo
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

from PIL import Image
from pypdf import PdfWriter

from dragon.archive import GitArchiveProvider
from dragon.config import load_local_config
from dragon.state import atomic_write_json, runtime_fingerprint, sha256_file, source_revision


ROOT = Path(__file__).resolve().parent


def _run(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, encoding="utf-8", timeout=120
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "git command failed")
    return result.stdout.strip()


def _write_fixture(directory: Path, fixture_id: str) -> dict[str, str]:
    """Create valid, non-editorial representative artifacts and their manifest."""
    directory.mkdir(parents=True)
    text = directory / "fixture-readme.md"
    text.write_bytes(
        b"# DRAGON cutover archive fixture\n\n"
        b"This is deterministic archive verification material, not a newspaper edition.\n"
    )
    status = directory / "fixture-status.json"
    status.write_bytes(
        (json.dumps(
            {"schema_version": 5, "fixture": True, "fixture_id": fixture_id, "publication": "NOT_A_NEWSPAPER"},
            ensure_ascii=False,
            indent=2,
        ) + "\n").encode("utf-8")
    )
    pdf = directory / "fixture.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=144, height=144)
    writer.add_metadata({"/Title": "DRAGON Cutover Archive Fixture", "/Subject": "NOT A NEWSPAPER"})
    with pdf.open("wb") as stream:
        writer.write(stream)
    epub = directory / "fixture.epub"
    with ZipFile(epub, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip", compress_type=ZIP_STORED)
        archive.writestr(
            "META-INF/container.xml",
            "<?xml version='1.0'?><container version='1.0' "
            "xmlns='urn:oasis:names:tc:opendocument:xmlns:container'><rootfiles>"
            "<rootfile full-path='OEBPS/content.opf' media-type='application/oebps-package+xml'/>"
            "</rootfiles></container>",
            compress_type=ZIP_DEFLATED,
        )
        archive.writestr(
            "OEBPS/content.opf",
            "<?xml version='1.0' encoding='UTF-8'?><package version='3.0' "
            "xmlns='http://www.idpf.org/2007/opf' unique-identifier='book'><metadata "
            "xmlns:dc='http://purl.org/dc/elements/1.1/'><dc:identifier id='book'>"
            f"{fixture_id}</dc:identifier><dc:title>DRAGON archive fixture — NOT A NEWSPAPER"
            "</dc:title><dc:language>en</dc:language></metadata><manifest/></package>",
            compress_type=ZIP_DEFLATED,
        )
    cover = directory / "assets" / "canonical-cover.png"
    cover.parent.mkdir()
    Image.new("RGB", (16, 16), color=(31, 41, 55)).save(cover, "PNG")
    artifacts = {str(path.relative_to(directory)).replace("\\", "/"): sha256_file(path) for path in sorted(directory.rglob("*")) if path.is_file()}
    manifest = directory / "fixture-manifest.json"
    manifest.write_bytes(
        (json.dumps(
            {
                "schema_version": 5,
                "fixture": True,
                "fixture_id": fixture_id,
                "classification": "CUTOVER_ARCHIVE_FIXTURE_NOT_A_NEWSPAPER",
                "artifacts": artifacts,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ) + "\n").encode("utf-8")
    )
    artifacts["fixture-manifest.json"] = sha256_file(manifest)
    return artifacts


def run_check(root: Path = ROOT) -> dict:
    root = root.resolve()
    config = load_local_config(root)
    archive = config["providers"]["github_archive"]
    if archive.get("type") != "git-cli":
        raise RuntimeError("GITHUB_ARCHIVE_PROVIDER_TYPE_UNSUPPORTED")
    remote = str(archive.get("remote", "origin"))
    branch = str(archive.get("branch", "main"))
    remote_url = _run(root, "remote", "get-url", remote)
    if not remote_url.startswith("https://github.com/"):
        raise RuntimeError("CUTOVER_FIXTURE_REQUIRES_CONFIGURED_GITHUB_REMOTE")
    now = datetime.now(ZoneInfo(str(config["timezone"])))
    fixture_id = f"{now.strftime('%Y%m%dT%H%M%S%z')}-{uuid4().hex[:12]}"
    fixture_relative = f"acceptance/cutover-fixtures/{now.date().isoformat()}/{fixture_id}"
    with tempfile.TemporaryDirectory(prefix="dragon-github-fixture-") as temporary:
        clone = Path(temporary) / "repository"
        subprocess.run(
            ["git", "clone", "--branch", branch, "--single-branch", remote_url, str(clone)],
            check=True, capture_output=True, text=True, encoding="utf-8", timeout=120,
        )
        _run(clone, "config", "user.name", _run(root, "config", "user.name"))
        _run(clone, "config", "user.email", _run(root, "config", "user.email"))
        fixture = clone / fixture_relative
        expected = _write_fixture(fixture, fixture_id)
        first = GitArchiveProvider(remote=remote, branch=branch).archive(
            clone, fixture, fixture_id, fixture=True
        )
        second = GitArchiveProvider(remote=remote, branch=branch).archive(
            clone, fixture, fixture_id, fixture=True
        )
        remote_ref = f"refs/remotes/{remote}/{branch}"
        remote_hashes = {}
        for relative, expected_hash in expected.items():
            remote_path = f"{fixture_relative}/{relative}"
            bytes_result = subprocess.run(
                ["git", "show", f"{remote_ref}:{remote_path}"], cwd=clone, capture_output=True, timeout=120
            )
            if bytes_result.returncode:
                raise RuntimeError(f"REMOTE_FIXTURE_READBACK_MISSING:{remote_path}")
            actual_hash = hashlib.sha256(bytes_result.stdout).hexdigest()
            if actual_hash != expected_hash:
                raise RuntimeError(f"REMOTE_FIXTURE_READBACK_MISMATCH:{remote_path}")
            remote_hashes[remote_path] = actual_hash
    receipt = {
        "schema_version": 5,
        "status": "PASS",
        "fixture": True,
        "classification": "CUTOVER_ARCHIVE_FIXTURE_NOT_A_NEWSPAPER",
        "created_at": now.isoformat(),
        "runtime_fingerprint": runtime_fingerprint(root),
        "source_git_revision": source_revision(root),
        "remote": remote,
        "branch": branch,
        "fixture_path": fixture_relative,
        "first_archive": first,
        "idempotent_retry": second,
        "expected_artifact_hashes": expected,
        "remote_artifact_hashes": remote_hashes,
    }
    output = root / "acceptance" / "machine" / "github-archive-fixture" / fixture_id / "receipt.json"
    atomic_write_json(output, receipt)
    return {**receipt, "receipt_path": str(output.relative_to(root)).replace("\\", "/")}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    print(json.dumps(run_check(args.root), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
