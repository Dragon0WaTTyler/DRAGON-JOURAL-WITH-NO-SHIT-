"""Idempotent Git archive provider with exact remote byte read-back."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import subprocess

from dragon.state import sha256_file


class ArchiveError(RuntimeError):
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


def _git(root: Path, *args: str, binary: bool = False) -> bytes | str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=root,
            capture_output=True,
            text=not binary,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ArchiveError("GIT_PUSH_FAILED", str(exc)) from exc
    if result.returncode:
        stderr = result.stderr if isinstance(result.stderr, str) else result.stderr.decode("utf-8", "replace")
        raise ArchiveError("GIT_PUSH_FAILED", stderr.strip() or "git command failed")
    return result.stdout


@dataclass(frozen=True)
class DisabledGitArchiveProvider:
    reason: str = "PROVIDER_DISABLED_OR_UNCONFIGURED"
    enabled: bool = False

    def archive(self, root: Path, edition_dir: Path, edition_date: str) -> dict:
        return {"status": "DEGRADED", "reason": self.reason, "verified": False}


@dataclass(frozen=True)
class GitArchiveProvider:
    remote: str = "origin"
    branch: str = "main"
    enabled: bool = True

    def archive(self, root: Path, edition_dir: Path, edition_date: str) -> dict:
        root = root.resolve()
        edition_dir = edition_dir.resolve()
        try:
            edition_dir.relative_to(root)
        except ValueError as exc:
            raise ArchiveError("GIT_PUSH_FAILED", "edition directory escapes repository") from exc
        files = sorted(path for path in edition_dir.rglob("*") if path.is_file())
        if not files:
            raise ArchiveError("GIT_PUSH_FAILED", "edition has no files to archive")
        relative_files = [str(path.relative_to(root)).replace("\\", "/") for path in files]
        _git(root, "add", "--", *relative_files)
        staged = subprocess.run(
            ["git", "diff", "--cached", "--quiet", "--", *relative_files],
            cwd=root,
            timeout=30,
        ).returncode
        action = "ALREADY_COMMITTED"
        if staged == 1:
            _git(root, "commit", "-m", f"archive: DRAGON edition {edition_date}", "--", *relative_files)
            action = "COMMITTED"
        elif staged != 0:
            raise ArchiveError("GIT_PUSH_FAILED", "could not inspect staged archive changes")
        commit = str(_git(root, "rev-parse", "HEAD")).strip()
        try:
            _git(root, "push", self.remote, f"HEAD:{self.branch}")
            _git(root, "fetch", self.remote, self.branch)
        except ArchiveError as exc:
            raise ArchiveError("GIT_PUSH_FAILED", exc.detail) from exc
        remote_ref = f"refs/remotes/{self.remote}/{self.branch}"
        remote_commit = str(_git(root, "rev-parse", remote_ref)).strip()
        if remote_commit != commit:
            raise ArchiveError(
                "GITHUB_READBACK_MISMATCH",
                f"remote commit {remote_commit} differs from local {commit}",
            )
        artifacts = []
        for path, relative in zip(files, relative_files):
            remote_bytes = _git(root, "show", f"{remote_ref}:{relative}", binary=True)
            assert isinstance(remote_bytes, bytes)
            remote_hash = hashlib.sha256(remote_bytes).hexdigest()
            local_hash = sha256_file(path)
            if remote_hash != local_hash:
                raise ArchiveError(
                    "GITHUB_READBACK_MISMATCH",
                    f"remote bytes differ for {relative}",
                )
            artifacts.append({"path": relative, "sha256": local_hash})
        return {
            "status": "COMPLETE",
            "action": action,
            "verified": True,
            "remote": self.remote,
            "branch": self.branch,
            "commit": commit,
            "remote_commit": remote_commit,
            "artifacts": artifacts,
        }


def archive_provider_from_config(config: dict) -> DisabledGitArchiveProvider | GitArchiveProvider:
    value = config.get("providers", {}).get("github_archive", {})
    if not value.get("enabled"):
        return DisabledGitArchiveProvider()
    if value.get("type") != "git-cli":
        return DisabledGitArchiveProvider("PROVIDER_TYPE_UNSUPPORTED")
    return GitArchiveProvider(
        remote=str(value.get("remote", "origin")),
        branch=str(value.get("branch", config.get("preflight", {}).get("expected_branch", "main"))),
    )
