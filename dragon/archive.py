"""Idempotent Git archive provider with exact remote byte read-back."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from uuid import uuid4

from dragon.state import atomic_write_json, sha256_file


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

    def archive(self, root: Path, edition_dir: Path, edition_date: str, *, fixture: bool = False) -> dict:
        return {"status": "DEGRADED", "reason": self.reason, "verified": False}


@dataclass(frozen=True)
class GitArchiveProvider:
    remote: str = "origin"
    branch: str = "main"
    enabled: bool = True

    def archive(self, root: Path, edition_dir: Path, edition_date: str, *, fixture: bool = False) -> dict:
        root = root.resolve()
        edition_dir = edition_dir.resolve()
        try:
            edition_dir.relative_to(root)
        except ValueError as exc:
            raise ArchiveError("GIT_PUSH_FAILED", "edition directory escapes repository") from exc
        expected = root / "editions" / edition_date[:4] / edition_date[5:7] / edition_date
        fixture_root = root / "acceptance" / "cutover-fixtures"
        if fixture:
            try:
                edition_dir.relative_to(fixture_root)
            except ValueError as exc:
                raise ArchiveError(
                    "GIT_PUSH_FAILED", "archive fixture must stay below acceptance/cutover-fixtures"
                ) from exc
        elif edition_dir != expected:
            raise ArchiveError(
                "GIT_PUSH_FAILED", "archive path must match the canonical dated edition directory"
            )
        files = sorted(path for path in edition_dir.rglob("*") if path.is_file())
        if not files:
            raise ArchiveError("GIT_PUSH_FAILED", "edition has no files to archive")
        if any(path.stat().st_size == 0 for path in files):
            raise ArchiveError("GIT_PUSH_FAILED", "zero-byte archive artifact is not publishable")
        relative_files = [str(path.relative_to(root)).replace("\\", "/") for path in files]
        remote_ref = f"refs/remotes/{self.remote}/{self.branch}"
        # Refresh the remote identity before touching the index.  A stale or
        # diverged checkout must be reconciled explicitly; archive publication
        # never force-pushes or silently rebases unrelated user work.
        _git(root, "fetch", self.remote, self.branch)
        ancestry = subprocess.run(
            ["git", "merge-base", "--is-ancestor", remote_ref, "HEAD"],
            cwd=root,
            capture_output=True,
            timeout=30,
        )
        if ancestry.returncode == 1:
            raise ArchiveError(
                "GIT_PUSH_FAILED",
                f"remote {self.remote}/{self.branch} changed; reconcile the stale checkout before archive retry",
            )
        if ancestry.returncode != 0:
            raise ArchiveError("GIT_PUSH_FAILED", "could not compare local and remote archive history")
        existing_under_directory = str(
            _git(root, "ls-tree", "-r", "--name-only", remote_ref, "--", str(edition_dir.relative_to(root)))
        ).splitlines()
        if existing_under_directory:
            if set(existing_under_directory) != set(relative_files):
                raise ArchiveError("GIT_PUSH_FAILED", "immutable archive directory already has a different file set")
            for path, relative in zip(files, relative_files):
                remote_bytes = _git(root, "show", f"{remote_ref}:{relative}", binary=True)
                assert isinstance(remote_bytes, bytes)
                if hashlib.sha256(remote_bytes).hexdigest() != sha256_file(path):
                    raise ArchiveError("GIT_PUSH_FAILED", "immutable archive directory already has different bytes")
        _git(root, "add", "--", *relative_files)
        staged = subprocess.run(
            ["git", "diff", "--cached", "--quiet", "--", *relative_files],
            cwd=root,
            timeout=30,
        ).returncode
        action = "ALREADY_COMMITTED"
        if staged == 1:
            label = f"cutover fixture {edition_date}" if fixture else f"edition {edition_date}"
            _git(root, "commit", "-m", f"archive: DRAGON {label}", "--", *relative_files)
            action = "COMMITTED"
        elif staged != 0:
            raise ArchiveError("GIT_PUSH_FAILED", "could not inspect staged archive changes")
        commit = str(_git(root, "rev-parse", "HEAD")).strip()
        try:
            _git(root, "push", self.remote, f"HEAD:{self.branch}")
            _git(root, "fetch", self.remote, self.branch)
        except ArchiveError as exc:
            raise ArchiveError("GIT_PUSH_FAILED", exc.detail) from exc
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
            "fixture": fixture,
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


def acceptance_archive_root(root: Path, configured: Path | None = None) -> Path:
    """Keep local research evidence in shared Git storage, outside a worktree."""
    override = configured or os.environ.get("DRAGON_ACCEPTANCE_ARCHIVE_ROOT")
    if override:
        destination = Path(override).expanduser().resolve()
    else:
        common = Path(str(_git(root, "rev-parse", "--git-common-dir")).strip())
        destination = (common if common.is_absolute() else root / common).resolve() / "dragon" / "research-acceptance"
    if destination.is_relative_to(root.resolve()):
        raise ArchiveError("ACCEPTANCE_ARCHIVE_NOT_DURABLE", "acceptance archive must be outside the disposable worktree")
    return destination


def _bundle_path(bundle: Path, relative: str) -> Path:
    path = (bundle / relative).resolve()
    if not relative or Path(relative).is_absolute() or not path.is_relative_to(bundle.resolve()):
        raise ArchiveError("ACCEPTANCE_MANIFEST_INVALID", "artifact path escapes the bundle")
    return path


def verify_acceptance_bundle(bundle: Path, *, require_complete: bool = True) -> dict:
    """Verify identities and every preserved byte before any replay reads them."""
    bundle = bundle.resolve()
    try:
        manifest_path = bundle / "manifest.json"
        expected = (bundle / "manifest.sha256").read_text(encoding="ascii").strip()
        if sha256_file(manifest_path) != expected:
            raise ArchiveError("ACCEPTANCE_HASH_MISMATCH", "manifest hash differs")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("schema_version") != 1 or manifest.get("run_id") != bundle.name:
            raise ArchiveError("ACCEPTANCE_MANIFEST_INVALID", "bundle identity differs from manifest")
        if require_complete and manifest.get("completion_state") != "COMPLETE":
            raise ArchiveError("ACCEPTANCE_BUNDLE_INCOMPLETE", str(manifest.get("completion_state")))
        artifacts = manifest.get("artifacts")
        if not isinstance(artifacts, dict) or not artifacts:
            raise ArchiveError("ACCEPTANCE_MANIFEST_INVALID", "artifact inventory is empty")
        for relative, identity in artifacts.items():
            path = _bundle_path(bundle, relative)
            if not path.is_file() or path.is_symlink() or path.stat().st_size != identity["bytes"] or sha256_file(path) != identity["sha256"]:
                raise ArchiveError("ACCEPTANCE_HASH_MISMATCH", relative)
        actual = {path.relative_to(bundle).as_posix() for prefix in ("artifacts", "configuration")
                  for path in (bundle / prefix).rglob("*") if path.is_file()}
        if actual != set(artifacts):
            raise ArchiveError("ACCEPTANCE_MANIFEST_INVALID", "file inventory differs")
        missing = set(manifest.get("required_artifacts", [])) - set(artifacts)
        if missing and require_complete:
            raise ArchiveError("ACCEPTANCE_BUNDLE_INCOMPLETE", ", ".join(sorted(missing)))
        for relative in ("state.json", "provider-research-acceptance-report.json", "provider-research/invocation.json"):
            path = bundle / "artifacts" / relative
            if path.is_file():
                value = json.loads(path.read_text(encoding="utf-8"))
                if value.get("run_id") != manifest["run_id"]:
                    raise ArchiveError("ACCEPTANCE_MANIFEST_INVALID", f"run identity differs in {relative}")
        for relative, digest in manifest.get("configuration_hashes", {}).items():
            if artifacts.get("configuration/" + relative, {}).get("sha256") != digest:
                raise ArchiveError("ACCEPTANCE_MANIFEST_INVALID", f"configuration identity differs: {relative}")
        return manifest
    except ArchiveError:
        raise
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ArchiveError("ACCEPTANCE_MANIFEST_INVALID", str(exc)) from exc


class LocalAcceptanceArchive:
    """One exclusively created local bundle; completed bundles are immutable."""

    def __init__(self, *, root: Path, run_dir: Path, run_id: str, edition_date: str,
                 destination: Path | None = None, synthetic: bool = False):
        if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,150}", run_id) is None:
            raise ArchiveError("ACCEPTANCE_RUN_ID_INVALID", run_id)
        self.root, self.run_dir = root.resolve(), run_dir.resolve()
        self.destination = acceptance_archive_root(self.root, destination)
        self.bundle = self.destination / run_id
        self.destination.mkdir(parents=True, exist_ok=True)
        try:
            self.bundle.mkdir()
        except FileExistsError as exc:
            raise ArchiveError("ACCEPTANCE_BUNDLE_EXISTS", str(self.bundle)) from exc
        self.manifest = {
            "schema_version": 1, "run_id": run_id, "edition_date": edition_date,
            "created_at": datetime.now(timezone.utc).isoformat(), "finalized_at": None,
            "source_git_revision": str(_git(self.root, "rev-parse", "HEAD")).strip(),
            "source_worktree": str(self.root), "source_run_directory": str(self.run_dir),
            "synthetic": synthetic, "provider_call_limit": 1, "provider_calls": 0,
            "completion_state": "INITIALIZED", "run_result": "NOT_STARTED",
            "required_artifacts": [], "artifacts": {}, "configuration_hashes": {},
            "implementation_hashes": {},
            "SEP27_EXACT_REPLAY": "UNAVAILABLE_MISSING_PRIMARY_ARTIFACTS",
        }
        for relative in str(_git(self.root, "ls-files", "--", "config")).splitlines():
            source = self.root / relative
            if source.suffix not in {".yaml", ".yml", ".json"}:
                continue
            target = self.bundle / "configuration" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            self.manifest["configuration_hashes"][relative] = sha256_file(target)
        for relative in str(_git(self.root, "ls-files", "--", "dragon", "scripts/codex_editorial_provider.py")).splitlines():
            if relative.endswith(".py"):
                self.manifest["implementation_hashes"][relative] = sha256_file(self.root / relative)
        for relative in ("dragon/acceptance_replay.py", "dragon_acceptance_bundle.py", "dragon_provider_research_acceptance.py"):
            if (self.root / relative).is_file():
                self.manifest["implementation_hashes"][relative] = sha256_file(self.root / relative)
        self._write_manifest()

    def _write_manifest(self) -> None:
        inventory = {}
        for prefix in ("artifacts", "configuration"):
            for path in sorted((self.bundle / prefix).rglob("*")):
                if path.is_file():
                    inventory[path.relative_to(self.bundle).as_posix()] = {"sha256": sha256_file(path), "bytes": path.stat().st_size}
        self.manifest["artifacts"] = inventory
        atomic_write_json(self.bundle / "manifest.json", self.manifest)
        digest = sha256_file(self.bundle / "manifest.json")
        temporary = self.bundle / ".manifest.sha256.tmp"
        temporary.write_text(digest + "\n", encoding="ascii")
        os.replace(temporary, self.bundle / "manifest.sha256")

    def snapshot(self) -> None:
        if self.manifest["completion_state"] == "COMPLETE":
            raise ArchiveError("ACCEPTANCE_BUNDLE_IMMUTABLE", str(self.bundle))
        for source in sorted(self.run_dir.rglob("*")):
            if not source.is_file() or source.name.endswith((".tmp", ".lock")):
                continue
            if source.is_symlink():
                raise ArchiveError("ACCEPTANCE_ARCHIVE_UNSAFE", str(source))
            target = self.bundle / "artifacts" / source.relative_to(self.run_dir)
            target.parent.mkdir(parents=True, exist_ok=True)
            before = sha256_file(source)
            temporary = target.with_name("." + target.name + ".tmp")
            shutil.copyfile(source, temporary)
            if before != sha256_file(source) or before != sha256_file(temporary):
                raise ArchiveError("ACCEPTANCE_SOURCE_CHANGED", str(source))
            os.replace(temporary, target)
        self.manifest["completion_state"] = "IN_PROGRESS"
        self._write_manifest()
        verify_acceptance_bundle(self.bundle, require_complete=False)

    def finalize(self, *, required: list[str], provider_calls: int, run_result: str) -> dict:
        self.snapshot()
        self.manifest.update({
            "required_artifacts": sorted("artifacts/" + relative for relative in required),
            "provider_calls": provider_calls, "run_result": run_result,
            "finalized_at": datetime.now(timezone.utc).isoformat(),
        })
        missing = [name for name in self.manifest["required_artifacts"] if name not in self.manifest["artifacts"]]
        self.manifest["completion_state"] = "INCOMPLETE" if missing else "VERIFYING"
        self.manifest["missing_required_artifacts"] = missing
        self._write_manifest()
        if missing:
            raise ArchiveError("ACCEPTANCE_BUNDLE_INCOMPLETE", ", ".join(missing))
        try:
            verify_acceptance_bundle(self.bundle, require_complete=False)
            self.manifest["completion_state"] = "COMPLETE"
            self._write_manifest()
            return verify_acceptance_bundle(self.bundle)
        except ArchiveError as exc:
            self.manifest["completion_state"] = "INCOMPLETE"
            self.manifest["verification_error"] = exc.code
            self._write_manifest()
            raise


def discover_acceptance_bundles(destination: Path) -> list[Path]:
    return sorted(path.parent for path in destination.glob("*/manifest.json"))


def prove_acceptance_archive(root: Path, destination: Path | None = None) -> dict:
    """Exercise the real storage path, without contacting an AI provider."""
    with tempfile.TemporaryDirectory(prefix="dragon-archive-proof-") as directory:
        source = Path(directory) / "run"
        source.mkdir()
        run_id = f"archive-proof-{uuid4()}"
        atomic_write_json(source / "state.json", {"run_id": run_id, "synthetic": True})
        archive = LocalAcceptanceArchive(root=root, run_dir=source, run_id=run_id,
            edition_date=datetime.now(timezone.utc).date().isoformat(), destination=destination, synthetic=True)
        archive.finalize(required=["state.json"], provider_calls=0, run_result="SYNTHETIC_ARCHIVE_PROOF")
        artifact = archive.bundle / "artifacts" / "state.json"
        original = artifact.read_bytes()
        artifact.write_bytes(original + b"tamper")
        try:
            verify_acceptance_bundle(archive.bundle)
            raise AssertionError("tampered artifact was accepted")
        except ArchiveError as exc:
            tamper = exc.code
        artifact.write_bytes(original)
        try:
            LocalAcceptanceArchive(root=root, run_dir=source, run_id=run_id, edition_date="2099-01-01", destination=archive.destination)
            raise AssertionError("existing bundle was overwritten")
        except ArchiveError as exc:
            overwrite = exc.code
        incomplete = LocalAcceptanceArchive(root=root, run_dir=source, run_id=f"archive-incomplete-{uuid4()}",
            edition_date="2099-01-01", destination=archive.destination, synthetic=True)
        # Use a native artifact with its own identity for the missing-file case.
        atomic_write_json(source / "state.json", {"run_id": incomplete.manifest["run_id"], "synthetic": True})
        try:
            incomplete.finalize(required=["state.json", "missing.json"], provider_calls=0, run_result="SYNTHETIC_INCOMPLETE")
            raise AssertionError("incomplete bundle was accepted")
        except ArchiveError as exc:
            missing = exc.code
    # The source temp directory has now been removed; only durable bytes remain.
    verified = verify_acceptance_bundle(archive.bundle)
    result = {"status": "PASS", "provider_calls": 0, "bundle": str(archive.bundle),
        "source_removed": not source.exists(), "hash_verification": "PASS",
        "tamper": tamper, "overwrite": overwrite, "missing_required": missing,
        "discovery": archive.bundle in discover_acceptance_bundles(archive.destination),
        "manifest_sha256": sha256_file(archive.bundle / "manifest.json"),
        "source_git_revision": verified["source_git_revision"]}
    atomic_write_json(archive.destination / "provider-free-durability-proof.json", result)
    return result
