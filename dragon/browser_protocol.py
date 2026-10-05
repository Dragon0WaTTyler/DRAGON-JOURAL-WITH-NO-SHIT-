"""Strict protocol/policy shared by the host and isolated browser worker."""
from __future__ import annotations
import hashlib
from ipaddress import ip_address
import json
import os
from pathlib import Path
import re
import socket
from urllib.parse import urlsplit

BACKEND_VERSION = "0.9.4"
PLAYWRIGHT_VERSION = "1.63.0"
FORBIDDEN_FLAGS = ("--no-sandbox", "--disable-setuid-sandbox", "--ignore-certificate-errors",
                   "--ignore-certificate-errors-spki-list", "--allow-insecure-localhost",
                   "--disable-web-security", "--disable-site-isolation-trials",
                   "--single-process", "--no-zygote", "--unsafely-treat-insecure-origin-as-secure")
LIMITS = {"wall_seconds": 30, "navigation_ms": 15000, "output_bytes": 2_000_000,
          "stderr_bytes": 65_536, "content_bytes": 750_000, "temp_bytes": 64_000_000,
          "memory_bytes": 2_147_483_648, "processes": 32, "cpu_percent": 50,
          "concurrency": 1, "retries": 0, "dynamic_calls_per_action": 1}


class BrowserFailure(RuntimeError):
    def __init__(self, code, detail):
        super().__init__(detail)
        self.code, self.detail = code, detail


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest()


def write_json_atomic(path,value):
    path=Path(path); temporary=path.with_suffix(path.suffix+".tmp")
    temporary.write_text(json.dumps(value,ensure_ascii=False),encoding="utf-8")
    os.replace(temporary,path)


def assert_launch_policy(options):
    if options.get("chromium_sandbox") is not True:
        raise BrowserFailure("DYNAMIC_POLICY_REJECTED", "Chromium sandbox must be explicitly enabled")
    if options.get("ignore_https_errors") is True:
        raise BrowserFailure("DYNAMIC_POLICY_REJECTED", "HTTPS errors must never be ignored")
    flags = options.get("args", [])
    if any(any(flag == bad or flag.startswith(bad + "=") for bad in FORBIDDEN_FLAGS) for flag in flags):
        raise BrowserFailure("DYNAMIC_POLICY_REJECTED", "Forbidden browser launch argument")


def safe_url(url, *, resolve=False):
    try:
        p = urlsplit(url)
        host = (p.hostname or "").casefold().rstrip(".")
        if p.scheme != "https" or not host or p.username is not None or p.password is not None or p.port not in (None,443):
            raise ValueError("Only public HTTPS on port 443 is supported")
        if host == "localhost" or host.endswith((".localhost",".local",".internal")) or not re.fullmatch(r"[a-z0-9.:-]{1,253}",host):
            raise ValueError("Local/internal or malformed hostname")
        try:
            literal = ip_address(host)
        except ValueError:
            literal = None
        if literal and not literal.is_global:
            raise ValueError("Private/reserved address")
        addresses = [str(literal)] if literal else []
        if resolve and not literal:
            addresses = sorted({item[4][0] for item in socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)})
        if resolve and (not addresses or any(not ip_address(ip).is_global for ip in addresses)):
            raise ValueError("DNS resolves to a private/reserved address")
        return {"host":host,"origin":f"https://{host}","addresses":addresses}
    except (ValueError,OSError) as exc:
        raise BrowserFailure("DYNAMIC_POLICY_REJECTED",str(exc)) from exc


def classify_error(detail, *, phase="navigation"):
    text = str(detail).upper()
    if any(x in text for x in ("ERR_CERT_", "CERTIFICATE_VERIFY_FAILED", "SSL_ERROR", "ERR_SSL_")):
        return "DYNAMIC_TLS_FAILURE"
    if "TIMEOUT" in text or "TIMED OUT" in text:
        return "DYNAMIC_NAVIGATION_TIMEOUT"
    if phase == "launch":
        return "DYNAMIC_LAUNCH_FAILURE"
    if any(x in text for x in ("TARGET CLOSED", "BROWSER HAS BEEN CLOSED", "CRASH", "TARGETCLOSED")):
        return "DYNAMIC_BROWSER_CRASH"
    return "DYNAMIC_PAGE_RETRIEVAL_FAILURE"
