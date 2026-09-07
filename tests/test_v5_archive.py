from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess

from dragon.archive import ArchiveError, GitArchiveProvider, archive_provider_from_config


def git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True)
    return result.stdout.strip()


def test_disabled_archive_provider_is_truthfully_degraded(tmp_path: Path) -> None:
    provider = archive_provider_from_config({"providers": {"github_archive": {"type": "git-cli", "enabled": False}}})
    assert provider.archive(tmp_path, tmp_path / "missing", "2099-01-02")["status"] == "DEGRADED"


def test_git_archive_pushes_and_reads_back_exact_bytes(tmp_path: Path) -> None:
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", "--initial-branch=main", str(remote)], check=True, capture_output=True)
    root = tmp_path / "work"
    subprocess.run(["git", "clone", str(remote), str(root)], check=True, capture_output=True)
    git(root, "config", "user.name", "DRAGON Test")
    git(root, "config", "user.email", "dragon@example.invalid")
    git(root, "config", "core.autocrlf", "false")
    (root / "README.md").write_text("seed\n", encoding="utf-8")
    git(root, "add", "README.md")
    git(root, "commit", "-m", "seed")
    git(root, "push", "origin", "main")
    edition = root / "editions" / "2099" / "01" / "2099-01-02"
    edition.mkdir(parents=True)
    artifact = edition / "edition.md"
    artifact.write_text("# نسخة عربية\n", encoding="utf-8")

    receipt = GitArchiveProvider().archive(root, edition, "2099-01-02")

    assert receipt["status"] == "COMPLETE"
    assert receipt["verified"] is True
    assert receipt["commit"] == receipt["remote_commit"]
    remote_bytes = subprocess.run(
        ["git", "--git-dir", str(remote), "show", "main:editions/2099/01/2099-01-02/edition.md"],
        capture_output=True,
        check=True,
    ).stdout
    assert hashlib.sha256(remote_bytes).hexdigest() == receipt["artifacts"][0]["sha256"]

    again = GitArchiveProvider().archive(root, edition, "2099-01-02")
    assert again["status"] == "COMPLETE"
    assert again["action"] == "ALREADY_COMMITTED"
    assert again["commit"] == receipt["commit"]


def test_archive_rejects_an_edition_outside_repository(tmp_path: Path) -> None:
    root = tmp_path / "work"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        GitArchiveProvider().archive(root, outside, "2099-01-02")
    except ArchiveError as exc:
        assert exc.code == "GIT_PUSH_FAILED"
    else:
        raise AssertionError("out-of-repository archive was accepted")
