"""Local-machine preflight checks for DRAGON V5."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from io import BytesIO
import importlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
from typing import Any, Callable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dragon.acceptance import _provider_trial_evidence
from dragon.config import load_local_config, load_mapping
from dragon.discovery import load_provider_registry, registry_report
from dragon.epubcheck import epubcheck_version
from dragon.providers import SECTION_HEADINGS, editorial_provider_from_config
from dragon.source_coverage import load_source_coverage
from dragon.state import runtime_fingerprint


@dataclass(frozen=True)
class Check:
    name: str
    status: str
    blocking: bool
    detail: str


def _check(name: str, blocking: bool, operation: Callable[[], str]) -> Check:
    try:
        return Check(name, "PASS", blocking, operation())
    except Exception as exc:
        return Check(name, "FAIL", blocking, str(exc))


def _writable(path: Path) -> str:
    path.mkdir(parents=True, exist_ok=True)
    probe = path / ".dragon-write-probe"
    try:
        with probe.open("x", encoding="utf-8") as stream:
            stream.write("ok")
    finally:
        probe.unlink(missing_ok=True)
    return str(path)


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, timeout=15
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "git command failed")
    return result.stdout.strip()


def _font_available(families: list[str]) -> str:
    roots = [
        Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts",
        Path.home() / "AppData" / "Local" / "Microsoft" / "Windows" / "Fonts",
        Path("/usr/share/fonts"),
        Path.home() / ".local" / "share" / "fonts",
    ]
    normalized = ["".join(character for character in name.casefold() if character.isalnum()) for name in families]
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if path.suffix.casefold() not in {".ttf", ".otf", ".ttc"}:
                continue
            stem = "".join(character for character in path.stem.casefold() if character.isalnum())
            if any(name in stem or stem in name for name in normalized):
                return str(path)
    raise RuntimeError("PREFLIGHT_ARABIC_FONT_MISSING: no configured Arabic font found")


def _network(host: str, port: int, timeout: float) -> str:
    with socket.create_connection((host, port), timeout=timeout):
        return f"{host}:{port} reachable"


def run_preflight(root: Path, edition_date: str) -> dict[str, Any]:
    root = root.resolve()
    parsed_date = date.fromisoformat(edition_date)
    config = load_local_config(root)
    policy = config.get("preflight", {})
    arabic = load_mapping(root / "config" / "arabic-publishing.yaml")
    checks: list[Check] = []
    checks.append(_check("repository", True, lambda: _git(root, "rev-parse", "--show-toplevel")))

    expected_remote = str(policy.get("expected_remote_contains", "DRAGON-JOURAL-WITH-NO-SHIT-"))
    checks.append(
        _check(
            "repository_identity",
            True,
            lambda: _require_contains(_git(root, "remote", "get-url", "origin"), expected_remote),
        )
    )
    expected_branch = str(policy.get("expected_branch", "main"))
    checks.append(
        _check(
            "git_branch",
            True,
            lambda: _require_equal(
                _git(root, "branch", "--show-current"), expected_branch, "branch"
            ),
        )
    )
    checks.append(
        _check(
            "git_worktree",
            bool(policy.get("require_clean_worktree", True)),
            lambda: _clean_worktree(
                _git(root, "status", "--porcelain", "--untracked-files=all"),
                (
                    f"daily-runs/{edition_date}/",
                    f"editions/{parsed_date:%Y}/{parsed_date:%m}/{edition_date}/",
                ),
                _v5_generated_prefixes(root, exclude_date=edition_date),
            ),
        )
    )
    checks.append(_check("git_executable", True, lambda: shutil.which("git") or _raise("git not found")))
    checks.append(_check("run_directory_writable", True, lambda: _writable(root / "daily-runs" / edition_date)))
    checks.append(_check("edition_directory_writable", True, lambda: _writable(root / "editions")))
    minimum_python = tuple(policy.get("minimum_python", [3, 12]))
    checks.append(
        _check(
            "python_runtime",
            True,
            lambda: _python_version(minimum_python),
        )
    )
    for module in policy.get("required_modules", []):
        checks.append(_check(f"python_module:{module}", True, lambda module=module: _import(module)))
    checks.append(_check("timezone", True, lambda: _timezone(config["timezone"])))
    checks.append(
        _check(
            "storage",
            True,
            lambda: _storage(root, int(policy.get("minimum_free_bytes", 536_870_912))),
        )
    )
    font_families = arabic.get("fonts", {}).get("preferred_families", []) + arabic.get("fonts", {}).get("local_fallback_families", [])
    checks.append(_check("arabic_font", True, lambda: _font_available(font_families)))
    checks.append(_check("pdf_runtime", True, _pdf_runtime))
    checks.append(_check("epub_runtime", True, lambda: _import("zipfile")))
    epubcheck_config = config.get("providers", {}).get("epubcheck", {})
    if epubcheck_config.get("enabled"):
        checks.append(
            _check(
                "epubcheck",
                True,
                lambda: f"W3C EPUBCheck {epubcheck_version(root)}",
            )
        )
    checks.append(
        _check(
            "source_provider_registry",
            bool(policy.get("require_source_provider_registry", False)),
            lambda: _provider_registry(root),
        )
    )
    checks.append(
        _check(
            "source_coverage",
            bool(policy.get("require_source_coverage", False)),
            lambda: _source_coverage(root),
        )
    )
    network = policy.get("network_probe", {})
    if network.get("enabled", True):
        checks.append(
            _check(
                "network",
                True,
                lambda: _network(
                    str(network.get("host", "github.com")),
                    int(network.get("port", 443)),
                    float(network.get("timeout_seconds", 5)),
                ),
            )
        )
    ai_type = config.get("providers", {}).get("ai", {}).get("type", "unconfigured")
    ai_test = config.get("providers", {}).get("ai", {}).get("integration_test_status")
    editorial_provider = editorial_provider_from_config(config)
    provider_blocking = bool(policy.get("require_ai_provider", True))
    if editorial_provider.available:
        checks.append(
            _check(
                "ai_provider",
                provider_blocking,
                lambda: _provider_health(editorial_provider, ai_type, ai_test),
            )
        )
        checks.append(
            _check(
                "ai_provider_evidence",
                provider_blocking,
                lambda: _provider_evidence(root),
            )
        )
    else:
        checks.append(
            Check(
                "ai_provider",
                "FAIL",
                provider_blocking,
                f"configured type: {ai_type}; integration test: {ai_test or 'NOT_RUN'}",
            )
        )
    for provider in ("github_archive", "whatsapp"):
        provider_config = config.get("providers", {}).get(provider, {})
        enabled = bool(provider_config.get("enabled"))
        configured = provider_config.get("type") not in {None, "unconfigured"}
        if provider == "whatsapp" and enabled:
            configured = configured and provider_config.get("integration_test_status") == "PASS"
            configured = configured and bool(provider_config.get("graph_version"))
            environment_names = (
                provider_config.get("access_token_env", "META_WHATSAPP_ACCESS_TOKEN"),
                provider_config.get("phone_number_id_env", "META_WHATSAPP_PHONE_NUMBER_ID"),
                provider_config.get("recipients_env", "DRAGON_WHATSAPP_RECIPIENTS"),
            )
            configured = configured and all(os.environ.get(str(name)) for name in environment_names)
        if provider == "github_archive" and enabled and configured:
            checks.append(
                _check(
                    "optional_provider:github_archive",
                    False,
                    lambda: _github_archive_capability(root, provider_config),
                )
            )
        else:
            checks.append(
                Check(
                    f"optional_provider:{provider}",
                    "PASS" if (not enabled or configured) else "FAIL",
                    False,
                    "disabled" if not enabled else f"configured type: {provider_config.get('type')}",
                )
            )
    blocking_failures = [asdict(item) for item in checks if item.blocking and item.status == "FAIL"]
    warnings = [asdict(item) for item in checks if not item.blocking and item.status == "FAIL"]
    return {
        "version": 5,
        "date": edition_date,
        "timezone": config["timezone"],
        "status": "PASS" if not blocking_failures else "FAIL",
        "checks": [asdict(item) for item in checks],
        "blocking_failures": blocking_failures,
        "warnings": warnings,
    }


def _raise(detail: str):
    raise RuntimeError(detail)


def _provider_health(provider, provider_type: object, integration_status: object) -> str:
    result = provider.healthcheck()
    if result.get("status") != "PASS" or result.get("unattended") is not True:
        raise RuntimeError("PREFLIGHT_AI_PROVIDER_HEALTHCHECK_FAILED")
    identity = result.get("provider", "unknown")
    return (
        f"configured type: {provider_type}; integration test: {integration_status}; "
        f"live unattended health: PASS ({identity})"
    )


def _provider_evidence(root: Path) -> str:
    valid, trials = _provider_trial_evidence(root, runtime_fingerprint(root))
    if not valid:
        rejected = ", ".join(
            f"{item['date']}:{'/'.join(item['issues'])}" for item in trials
        ) or "no trial receipt"
        raise RuntimeError(f"PREFLIGHT_AI_PROVIDER_EVIDENCE_INVALID: {rejected}")
    accepted = [item["date"] for item in trials if item["status"] == "PASS"]
    return f"reviewed current-runtime provider trial: {accepted[-1]}"


def _provider_registry(root: Path) -> str:
    report = registry_report(load_provider_registry(root / "config" / "provider-registry.yaml"))
    if report["status"] != "PASS":
        raise RuntimeError(
            "required providers unavailable: "
            + ", ".join(report["summary"]["unavailable_required"])
        )
    return (
        f"{report['summary']['available']} adapters proven; "
        f"{report['summary']['enabled']} enabled; optional outages do not block"
    )


def _source_coverage(root: Path) -> str:
    value = load_source_coverage(
        root / "config" / "source-coverage.yaml",
        {section_id for section_id, _ in SECTION_HEADINGS},
    )
    gaps = [item["section_id"] for item in value["desks"] if item["coverage_status"] == "GAP"]
    return f"{len(value['desks'])} desk coverage entries; explicit gaps={','.join(gaps) or 'none'}"


def _require_contains(value: str, expected: str) -> str:
    if expected not in value:
        raise RuntimeError(f"unexpected repository remote: {value}")
    return value


def _require_equal(value: str, expected: str, label: str) -> str:
    if value != expected:
        raise RuntimeError(f"unexpected {label}: {value!r}; expected {expected!r}")
    return value


def _github_archive_capability(root: Path, provider_config: dict[str, Any]) -> str:
    remote = str(provider_config.get("remote", "origin"))
    branch = str(provider_config.get("branch", "main"))
    name = _git(root, "config", "user.name")
    email = _git(root, "config", "user.email")
    if not name or not email:
        raise RuntimeError("archive commit identity is incomplete")
    value = _git(root, "ls-remote", "--exit-code", remote, f"refs/heads/{branch}")
    if not value:
        raise RuntimeError(f"archive branch is not readable: {remote}/{branch}")
    return f"commit identity configured; remote branch readable: {remote}/{branch}"


def _v5_generated_prefixes(root: Path, *, exclude_date: str) -> tuple[str, ...]:
    prefixes: list[str] = [
        "acceptance/machine/",
        "acceptance/provider-trials/",
        "acceptance/evidence/",
    ]
    for state_path in (root / "daily-runs").glob("????-??-??/state.json"):
        day = state_path.parent.name
        if day == exclude_date:
            continue
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
            parsed = date.fromisoformat(day)
        except (OSError, json.JSONDecodeError, ValueError):
            continue
        if state.get("schema_version") != 5 or state.get("date") != day:
            continue
        prefixes.extend(
            (
                f"daily-runs/{day}/",
                f"editions/{parsed:%Y}/{parsed:%m}/{day}/",
            )
        )
    return tuple(prefixes)


def _clean_worktree(
    value: str,
    allowed_prefixes: tuple[str, ...],
    allowed_untracked_prefixes: tuple[str, ...] = (),
) -> str:
    unrelated: list[str] = []
    for line in value.splitlines():
        status = line[:2]
        path = line[3:].replace("\\", "/") if len(line) > 3 else line
        current_run = any(path.startswith(prefix) for prefix in allowed_prefixes)
        prior_untracked = status == "??" and any(
            path.startswith(prefix) for prefix in allowed_untracked_prefixes
        )
        if not current_run and not prior_untracked:
            unrelated.append(path)
    if unrelated:
        raise RuntimeError("working tree has unrelated changes: " + ", ".join(unrelated))
    return "clean"


def _python_version(minimum: tuple[int, ...]) -> str:
    if sys.version_info[: len(minimum)] < minimum:
        raise RuntimeError(f"Python {minimum} or newer required")
    return sys.version.split()[0]


def _import(name: str) -> str:
    importlib.import_module(name)
    return f"{name} importable"


def _pdf_runtime() -> str:
    from PIL import Image, ImageDraw
    import arabic_reshaper
    from bidi.algorithm import get_display
    from pypdf import PdfReader

    image = Image.new("RGB", (20, 20), "white")
    draw = ImageDraw.Draw(image)
    shaped = get_display(arabic_reshaper.reshape("اختبار عربي"))
    draw.text((1, 1), shaped, fill="black")
    payload = BytesIO()
    image.save(payload, format="PDF")
    payload.seek(0)
    if len(PdfReader(payload).pages) != 1:
        raise RuntimeError("PREFLIGHT_PDF_RUNTIME_INVALID")
    return "Pillow PDF encode/readback with Arabic reshaping and bidi support"


def _timezone(name: str) -> str:
    try:
        ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise RuntimeError(f"timezone unavailable: {name}") from exc
    return name


def _storage(path: Path, minimum: int) -> str:
    free = shutil.disk_usage(path).free
    if free < minimum:
        raise RuntimeError(f"only {free} bytes free; require {minimum}")
    return f"{free} bytes free"
