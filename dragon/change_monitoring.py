"""Git-backed source watchlist and deterministic cross-run change detection."""

from __future__ import annotations

from datetime import datetime, timezone
from html.parser import HTMLParser
import hashlib
import json
from pathlib import Path
import re
from typing import Callable

from jsonschema import Draft202012Validator
import yaml

from dragon.discovery import DiscoveryError, FetchResponse, default_transport


class ChangeMonitoringError(RuntimeError):
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


class _VisibleText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() in {"script", "style", "noscript", "svg"}:
            self.hidden_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() in {"script", "style", "noscript", "svg"} and self.hidden_depth:
            self.hidden_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self.hidden_depth:
            self.parts.append(data)


Transport = Callable[[str, int, int], FetchResponse]


def load_change_watchlist(path: Path, schema_path: Path | None = None) -> dict:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
        schema = json.loads(
            (schema_path or path.with_name("change-watchlist-schema.json")).read_text(
                encoding="utf-8"
            )
        )
    except (OSError, UnicodeError, yaml.YAMLError, json.JSONDecodeError) as exc:
        raise ChangeMonitoringError("CHANGE_WATCHLIST_INVALID", str(exc)) from exc
    errors = sorted(
        Draft202012Validator(schema).iter_errors(value), key=lambda item: list(item.path)
    )
    if errors:
        detail = "; ".join(
            f"{'/'.join(str(part) for part in error.path) or '$'}: {error.message}"
            for error in errors
        )
        raise ChangeMonitoringError("CHANGE_WATCHLIST_INVALID", detail)
    identifiers = [item["target_id"] for item in value["targets"]]
    if len(identifiers) != len(set(identifiers)):
        raise ChangeMonitoringError(
            "CHANGE_WATCHLIST_INVALID", "target_id values must be unique"
        )
    return value


def find_previous_monitor_report(root: Path, edition_date: str) -> Path | None:
    run_root = root / "daily-runs"
    if not run_root.is_dir():
        return None
    candidates = []
    for directory in run_root.iterdir():
        if not directory.is_dir() or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", directory.name):
            continue
        if directory.name >= edition_date:
            continue
        report = directory / "source-monitoring" / "report.json"
        if report.is_file():
            candidates.append(report)
    return max(candidates, key=lambda path: path.parents[1].name) if candidates else None


def _fingerprint(response: FetchResponse, strategy: str) -> tuple[str, int]:
    if strategy == "bytes":
        payload = response.body
    elif strategy == "json-canonical":
        try:
            value = json.loads(response.body.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise ChangeMonitoringError("CHANGE_CONTENT_INVALID", str(exc)) from exc
        payload = json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    elif strategy == "html-visible-text":
        try:
            parser = _VisibleText()
            parser.feed(response.body.decode("utf-8", errors="strict"))
        except (UnicodeError, ValueError) as exc:
            raise ChangeMonitoringError("CHANGE_CONTENT_INVALID", str(exc)) from exc
        normalized = " ".join(" ".join(parser.parts).split()).casefold()
        if len(normalized) < 40:
            raise ChangeMonitoringError(
                "CHANGE_CONTENT_INSUFFICIENT", f"only {len(normalized)} visible characters"
            )
        payload = normalized.encode("utf-8")
    else:  # schema makes this unreachable; retain fail-closed behavior for direct callers.
        raise ChangeMonitoringError("CHANGE_STRATEGY_UNSUPPORTED", strategy)
    return hashlib.sha256(payload).hexdigest(), len(payload)


def monitor_watchlist(
    watchlist: dict,
    previous: dict | None = None,
    *,
    transport: Transport = default_transport,
    observed_at: str | None = None,
    execute: bool = True,
) -> dict:
    timestamp = observed_at or datetime.now(timezone.utc).isoformat()
    previous_by_id = {
        item.get("target_id"): item
        for item in (previous or {}).get("targets", [])
        if item.get("target_id")
    }
    targets = []
    required_failures = []
    optional_failures = []
    for target in watchlist["targets"]:
        common = {
            "target_id": target["target_id"],
            "label": target["label"],
            "url": target["url"],
            "material_type": target["material_type"],
            "required": target["required"],
            "verification_status": "DISCOVERY_ONLY",
        }
        if not target["enabled"]:
            targets.append({**common, "status": "DISABLED", "content_hash": None})
            continue
        if not execute:
            targets.append(
                {**common, "status": "NOT_FETCHED_FIXTURE_MODE", "content_hash": None}
            )
            continue
        try:
            response = transport(
                target["url"], target["timeout_seconds"], target["maximum_bytes"]
            )
            if not 200 <= response.status < 300:
                raise ChangeMonitoringError("CHANGE_FETCH_FAILED", f"HTTP {response.status}")
            expected = target["expected_content_types"]
            if response.content_type not in expected:
                raise ChangeMonitoringError(
                    "CHANGE_CONTENT_TYPE_MISMATCH",
                    f"{response.content_type} not in {expected}",
                )
            digest, normalized_bytes = _fingerprint(response, target["strategy"])
            prior = previous_by_id.get(target["target_id"], {})
            prior_hash = prior.get("content_hash")
            status = "INITIAL_BASELINE" if not prior_hash else "UNCHANGED" if prior_hash == digest else "CHANGED"
            targets.append(
                {
                    **common,
                    "status": status,
                    "observed_at": timestamp,
                    "http_status": response.status,
                    "content_type": response.content_type,
                    "strategy": target["strategy"],
                    "normalized_bytes": normalized_bytes,
                    "previous_content_hash": prior_hash,
                    "content_hash": digest,
                    "changed": status == "CHANGED",
                }
            )
        except (ChangeMonitoringError, DiscoveryError, OSError) as exc:
            code = getattr(exc, "code", "CHANGE_FETCH_FAILED")
            failed = {**common, "status": "FAILED", "content_hash": None, "error_code": code, "error_detail": str(exc)}
            targets.append(failed)
            (required_failures if target["required"] else optional_failures).append(
                target["target_id"]
            )
    enabled = [item for item in watchlist["targets"] if item["enabled"]]
    changed = [item for item in targets if item.get("status") == "CHANGED"]
    if required_failures:
        status = "FAIL"
    elif optional_failures:
        status = "DEGRADED"
    elif not enabled:
        status = "NOT_CONFIGURED"
    elif not execute:
        status = "NOT_APPLICABLE"
    else:
        status = "PASS"
    return {
        "schema_version": 1,
        "status": status,
        "observed_at": timestamp,
        "reference_architecture": "internal Git-backed watchlist; no monitoring daemon",
        "targets": targets,
        "discovery_candidates": [
            {
                "target_id": item["target_id"],
                "label": item["label"],
                "url": item["url"],
                "change_status": item["status"],
                "verification_status": "DISCOVERY_ONLY",
            }
            for item in targets
            if item["status"] in {"INITIAL_BASELINE", "CHANGED"}
        ],
        "summary": {
            "configured": len(watchlist["targets"]),
            "enabled": len(enabled),
            "changed": len(changed),
            "required_failures": required_failures,
            "optional_failures": optional_failures,
        },
    }
