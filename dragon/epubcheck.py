"""Hard EPUBCheck 5.3 integration for production publication."""

from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path
import subprocess
from typing import Callable


EXPECTED_VERSION = "5.3.0"
Runner = Callable[..., subprocess.CompletedProcess[str]]


class EPUBCheckError(RuntimeError):
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


def resolve_epubcheck_jar(root: Path, environ: dict[str, str] | None = None) -> Path:
    environment = environ if environ is not None else os.environ
    configured = str(environment.get("DRAGON_EPUBCHECK_JAR", "")).strip()
    return Path(configured) if configured else root / "tools" / "epubcheck-5.3.0" / "epubcheck.jar"


def epubcheck_version(
    root: Path,
    *,
    runner: Runner = subprocess.run,
    environ: dict[str, str] | None = None,
) -> str:
    jar = resolve_epubcheck_jar(root, environ)
    if not jar.is_file():
        raise EPUBCheckError("EPUBCHECK_UNAVAILABLE", f"missing EPUBCheck JAR: {jar}")
    try:
        result = runner(
            ["java", "-jar", str(jar), "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise EPUBCheckError("EPUBCHECK_UNAVAILABLE", str(exc)) from exc
    output = (result.stdout + "\n" + result.stderr).strip()
    if result.returncode or f"EPUBCheck v{EXPECTED_VERSION}" not in output:
        raise EPUBCheckError("EPUBCHECK_VERSION_MISMATCH", output or "no version output")
    return EXPECTED_VERSION


def run_epubcheck(
    root: Path,
    epub_path: Path,
    raw_report_path: Path,
    *,
    runner: Runner = subprocess.run,
    environ: dict[str, str] | None = None,
) -> dict:
    version = epubcheck_version(root, runner=runner, environ=environ)
    jar = resolve_epubcheck_jar(root, environ)
    raw_report_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = runner(
            ["java", "-jar", str(jar), "--json", str(raw_report_path), str(epub_path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=180,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise EPUBCheckError("EPUBCHECK_EXECUTION_FAILED", str(exc)) from exc
    try:
        raw = json.loads(raw_report_path.read_text(encoding="utf-8"))
        checker = raw["checker"]
        fatal = int(checker["nFatal"])
        errors = int(checker["nError"])
        warnings = int(checker["nWarning"])
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise EPUBCheckError("EPUBCHECK_REPORT_INVALID", str(exc)) from exc
    passed = result.returncode == 0 and fatal == 0 and errors == 0
    return {
        "status": "PASS" if passed else "FAIL",
        "validator": "W3C_EPUBCHECK",
        "version": version,
        "jar_sha256": hashlib.sha256(jar.read_bytes()).hexdigest(),
        "exit_code": result.returncode,
        "fatal_count": fatal,
        "error_count": errors,
        "warning_count": warnings,
        "message_ids": [item.get("ID") for item in raw.get("messages", [])],
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
        "raw_report": raw_report_path.name,
    }
