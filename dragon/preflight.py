"""Local-machine preflight checks for DRAGON V5."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
import importlib
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
from typing import Any, Callable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dragon.config import load_local_config, load_mapping


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
                _git(root, "status", "--porcelain"),
                (
                    f"daily-runs/{edition_date}/",
                    f"editions/{parsed_date:%Y}/{parsed_date:%m}/{edition_date}/",
                ),
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
    checks.append(
        Check(
            "ai_provider",
            "PASS" if ai_type != "unconfigured" and ai_test == "PASS" else "FAIL",
            bool(policy.get("require_ai_provider", True)),
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


def _require_contains(value: str, expected: str) -> str:
    if expected not in value:
        raise RuntimeError(f"unexpected repository remote: {value}")
    return value


def _require_equal(value: str, expected: str, label: str) -> str:
    if value != expected:
        raise RuntimeError(f"unexpected {label}: {value!r}; expected {expected!r}")
    return value


def _clean_worktree(value: str, allowed_prefixes: tuple[str, ...]) -> str:
    unrelated: list[str] = []
    for line in value.splitlines():
        path = line[3:].replace("\\", "/") if len(line) > 3 else line
        if not any(path.startswith(prefix) for prefix in allowed_prefixes):
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

    image = Image.new("RGB", (20, 20), "white")
    draw = ImageDraw.Draw(image)
    shaped = get_display(arabic_reshaper.reshape("اختبار عربي"))
    draw.text((1, 1), shaped, fill="black")
    return "Pillow PDF with Arabic reshaping and bidi support"


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
