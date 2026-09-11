from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess
from unittest.mock import patch

import pytest

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
    git(root, "config", "core.autocrlf", "true")
    (root / "README.md").write_text("seed\n", encoding="utf-8")
    (root / ".gitattributes").write_text("* text=auto eol=lf\neditions/** -text\n", encoding="utf-8")
    git(root, "add", "README.md", ".gitattributes")
    git(root, "commit", "-m", "seed")
    git(root, "push", "origin", "main")
    edition = root / "editions" / "2099" / "01" / "2099-01-02"
    edition.mkdir(parents=True)
    artifact = edition / "edition.md"
    artifact.write_text("# نسخة عربية\n", encoding="utf-8")
    cover = edition / "assets" / "cover.png"
    cover.parent.mkdir()
    cover.write_bytes(b"canonical cover fixture\x00\xff")

    receipt = GitArchiveProvider().archive(root, edition, "2099-01-02")

    assert receipt["status"] == "COMPLETE"
    assert receipt["verified"] is True
    assert receipt["commit"] == receipt["remote_commit"]
    remote_bytes = subprocess.run(
        ["git", "--git-dir", str(remote), "show", "main:editions/2099/01/2099-01-02/edition.md"],
        capture_output=True,
        check=True,
    ).stdout
    receipt_artifacts = {item["path"]: item["sha256"] for item in receipt["artifacts"]}
    assert hashlib.sha256(remote_bytes).hexdigest() == receipt_artifacts[
        "editions/2099/01/2099-01-02/edition.md"
    ]
    remote_cover = subprocess.run(
        ["git", "--git-dir", str(remote), "show", "main:editions/2099/01/2099-01-02/assets/cover.png"],
        capture_output=True, check=True,
    ).stdout
    assert remote_cover == cover.read_bytes()
    assert hashlib.sha256(remote_cover).hexdigest() == receipt_artifacts[
        "editions/2099/01/2099-01-02/assets/cover.png"
    ]

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


def test_archive_rejects_wrong_canonical_path_and_zero_byte_artifact(tmp_path: Path) -> None:
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", "--initial-branch=main", str(remote)], check=True, capture_output=True)
    root = tmp_path / "work"
    subprocess.run(["git", "clone", str(remote), str(root)], check=True, capture_output=True)
    git(root, "config", "user.name", "DRAGON Test")
    git(root, "config", "user.email", "dragon@example.invalid")
    (root / "README.md").write_text("seed\n", encoding="utf-8")
    git(root, "add", "README.md")
    git(root, "commit", "-m", "seed")
    git(root, "push", "origin", "main")
    wrong = root / "editions" / "2099" / "01" / "2099-01-03"
    wrong.mkdir(parents=True)
    (wrong / "edition.md").write_text("fixture\n", encoding="utf-8")
    with pytest.raises(ArchiveError, match="canonical dated edition"):
        GitArchiveProvider().archive(root, wrong, "2099-01-02")
    canonical = root / "editions" / "2099" / "01" / "2099-01-02"
    canonical.mkdir(parents=True)
    (canonical / "edition.md").write_bytes(b"")
    with pytest.raises(ArchiveError, match="zero-byte"):
        GitArchiveProvider().archive(root, canonical, "2099-01-02")


def test_archive_rejects_immutable_remote_bytes_after_finality(tmp_path: Path) -> None:
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", "--initial-branch=main", str(remote)], check=True, capture_output=True)
    root = tmp_path / "work"
    subprocess.run(["git", "clone", str(remote), str(root)], check=True, capture_output=True)
    git(root, "config", "user.name", "DRAGON Test")
    git(root, "config", "user.email", "dragon@example.invalid")
    (root / "README.md").write_text("seed\n", encoding="utf-8")
    git(root, "add", "README.md")
    git(root, "commit", "-m", "seed")
    git(root, "push", "origin", "main")
    edition = root / "editions" / "2099" / "01" / "2099-01-02"
    edition.mkdir(parents=True)
    artifact = edition / "edition.md"
    artifact.write_bytes(b"first bytes")
    GitArchiveProvider().archive(root, edition, "2099-01-02")
    artifact.write_bytes(b"attempted historical mutation")
    with pytest.raises(ArchiveError, match="immutable archive directory"):
        GitArchiveProvider().archive(root, edition, "2099-01-02")


def test_archive_fails_closed_when_remote_readback_bytes_are_corrupt(tmp_path: Path) -> None:
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", "--initial-branch=main", str(remote)], check=True, capture_output=True)
    root = tmp_path / "work"
    subprocess.run(["git", "clone", str(remote), str(root)], check=True, capture_output=True)
    git(root, "config", "user.name", "DRAGON Test")
    git(root, "config", "user.email", "dragon@example.invalid")
    (root / "README.md").write_text("seed\n", encoding="utf-8")
    git(root, "add", "README.md")
    git(root, "commit", "-m", "seed")
    git(root, "push", "origin", "main")
    edition = root / "editions" / "2099" / "01" / "2099-01-02"
    edition.mkdir(parents=True)
    (edition / "edition.md").write_bytes(b"archive subject")
    from dragon import archive as archive_module

    original = archive_module._git

    def corrupt_show(*args, **kwargs):
        if kwargs.get("binary") and args[1] == "show":
            return b"corrupt remote blob"
        return original(*args, **kwargs)

    with patch("dragon.archive._git", side_effect=corrupt_show), pytest.raises(
        ArchiveError, match="remote bytes differ"
    ) as caught:
        GitArchiveProvider().archive(root, edition, "2099-01-02")
    assert caught.value.code == "GITHUB_READBACK_MISMATCH"


def test_archive_refuses_stale_checkout_without_overwriting_remote_change(tmp_path: Path) -> None:
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", "--initial-branch=main", str(remote)], check=True, capture_output=True)
    root = tmp_path / "work"
    peer = tmp_path / "peer"
    subprocess.run(["git", "clone", str(remote), str(root)], check=True, capture_output=True)
    git(root, "config", "user.name", "DRAGON Test")
    git(root, "config", "user.email", "dragon@example.invalid")
    git(root, "config", "core.autocrlf", "true")
    (root / "README.md").write_text("seed\n", encoding="utf-8")
    (root / ".gitattributes").write_text("* text=auto eol=lf\neditions/** -text\n", encoding="utf-8")
    git(root, "add", "README.md", ".gitattributes")
    git(root, "commit", "-m", "seed")
    git(root, "push", "origin", "main")
    subprocess.run(["git", "clone", str(remote), str(peer)], check=True, capture_output=True)
    git(peer, "config", "user.name", "Peer")
    git(peer, "config", "user.email", "peer@example.invalid")
    git(peer, "config", "core.autocrlf", "true")
    (peer / "remote-note.txt").write_text("remote change\n", encoding="utf-8")
    git(peer, "add", "remote-note.txt")
    git(peer, "commit", "-m", "remote change")
    git(peer, "push", "origin", "main")
    edition = root / "editions" / "2099" / "01" / "2099-01-02"
    edition.mkdir(parents=True)
    (edition / "edition.md").write_text("# نسخة محلية\n", encoding="utf-8")

    with pytest.raises(ArchiveError) as caught:
        GitArchiveProvider().archive(root, edition, "2099-01-02")

    assert caught.value.code == "GIT_PUSH_FAILED"
    assert "stale checkout" in caught.value.detail
    remote_note = subprocess.run(
        ["git", "--git-dir", str(remote), "show", "main:remote-note.txt"],
        capture_output=True, check=True, text=True,
    ).stdout
    assert remote_note == "remote change\n"
    assert git(root, "status", "--short", "--", "editions") == "?? editions/"


def test_archive_resumes_after_crash_between_local_commit_and_push(tmp_path: Path) -> None:
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", "--initial-branch=main", str(remote)], check=True, capture_output=True)
    root = tmp_path / "work"
    subprocess.run(["git", "clone", str(remote), str(root)], check=True, capture_output=True)
    git(root, "config", "user.name", "DRAGON Test")
    git(root, "config", "user.email", "dragon@example.invalid")
    git(root, "config", "core.autocrlf", "true")
    (root / "README.md").write_text("seed\n", encoding="utf-8")
    (root / ".gitattributes").write_text("* text=auto eol=lf\neditions/** -text\n", encoding="utf-8")
    git(root, "add", "README.md", ".gitattributes")
    git(root, "commit", "-m", "seed")
    git(root, "push", "origin", "main")
    edition = root / "editions" / "2099" / "01" / "2099-01-02"
    edition.mkdir(parents=True)
    artifact = edition / "edition.md"
    artifact.write_text("# نسخة ملتزمة محليا\n", encoding="utf-8")
    git(root, "add", "--", "editions/2099/01/2099-01-02/edition.md")
    git(root, "commit", "-m", "simulated crash after binary commit")

    receipt = GitArchiveProvider().archive(root, edition, "2099-01-02")

    assert receipt["status"] == "COMPLETE"
    assert receipt["action"] == "ALREADY_COMMITTED"
    assert receipt["commit"] == receipt["remote_commit"]
