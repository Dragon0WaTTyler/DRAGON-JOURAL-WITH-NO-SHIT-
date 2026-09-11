#!/usr/bin/env python3
"""Run the configured local editorial provider's unattended health check."""

from __future__ import annotations

import argparse
from dataclasses import is_dataclass, replace
from datetime import datetime
import json
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from dragon.config import load_local_config
from dragon.providers import LocalCommandEditorialProvider, ProviderError, editorial_provider_from_config
from dragon.provider_acceptance import build_provider_seed_orchestrator
from dragon.redaction import redact_text
from dragon.state import atomic_write_json, runtime_fingerprint, sha256_file, source_revision


ROOT = Path(__file__).resolve().parent


def _emit_json(value: object) -> None:
    """Keep unattended Windows diagnostics printable even on cp1252 consoles."""
    print(json.dumps(value, ensure_ascii=True, indent=2))


def _trial_directory(root: Path, edition_date: str, *, full: bool) -> Path:
    """Never overwrite prior raw/provider evidence for the same edition date."""
    base = root / "acceptance" / "provider-trials" / edition_date
    terminal_evidence = (
        "receipt.json",
        "failure.json",
        "research.raw.json",
        "articles.raw.json",
        "research.json",
        "articles.json",
    )
    if not full or not any((base / name).exists() for name in terminal_evidence):
        return base
    return base / "attempts" / f"attempt-{uuid4().hex}"


def _failed_stage(state: dict) -> dict | None:
    """Return the first V5 stage that truthfully stopped an acceptance run."""
    if state.get("run_result") == "BLOCKED" and state.get("error_code"):
        return {
            "stage": None,
            "error_code": state["error_code"],
            "error_detail": state.get("error_detail") or "acceptance run blocked",
        }
    for name, record in state.get("stages", {}).items():
        if record.get("status") in {"FAILED", "BLOCKED"}:
            return {"stage": name, **record}
    return None


def _research_counts(packet: dict, post_recovery_packet: dict | None = None) -> dict:
    """Expose provider choice separately from locally derived eligibility."""
    def candidates(value: dict) -> list[dict]:
        return [
            candidate
            for section in value.get("sections", [])
            if isinstance(section, dict)
            for candidate in section.get("candidates", [])
            if isinstance(candidate, dict)
        ]

    initial = candidates(packet)
    final = candidates(post_recovery_packet or packet)
    return {
        "provider_selected_sections": sum(
            1
            for section in packet.get("sections", [])
            if isinstance(section, dict) and section.get("selected_candidate_id")
        ),
        "pre_recovery_candidate_count": len(initial),
        "pre_recovery_evidence_eligible_candidates": sum(
            candidate.get("evidence_eligibility", {}).get("status") == "ELIGIBLE"
            for candidate in initial
        ),
        "post_recovery_candidate_count": len(final),
        "post_recovery_evidence_eligible_candidates": sum(
            candidate.get("evidence_eligibility", {}).get("status") == "ELIGIBLE"
            for candidate in final
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--full",
        action="store_true",
        help="consume provider usage and validate a live research/articles trial",
    )
    parser.add_argument("--date", help="edition date for --full (defaults to local today)")
    args = parser.parse_args()
    config = load_local_config(ROOT)
    provider = editorial_provider_from_config(
        config, require_proven=False
    )
    if not isinstance(provider, LocalCommandEditorialProvider):
        _emit_json({"status": "FAIL", "error_code": provider.reason})
        return 1
    edition_date = args.date or datetime.now(
        ZoneInfo(str(config["timezone"]))
    ).date().isoformat()
    trial_dir = _trial_directory(ROOT, edition_date, full=args.full)
    if args.full and is_dataclass(provider) and hasattr(provider, "capture_directory"):
        provider = replace(provider, capture_directory=trial_dir)
    health = None
    orchestrator = None
    try:
        health = provider.healthcheck()
        if not args.full:
            _emit_json({"status": "PASS", "provider": health})
            return 0
        research = provider.research(
            edition_date,
            {"edition_count": 0, "editions": [], "trial": True},
        )
        initial_research_path = trial_dir / "initial-research-packet.json"
        atomic_write_json(initial_research_path, research)
        raw_research_path = trial_dir / "research.raw.json"
        if not raw_research_path.is_file():
            raise ProviderError(
                "PROVIDER_RAW_EVIDENCE_MISSING",
                "provider research returned without the required immutable raw capture",
            )
        orchestrator = build_provider_seed_orchestrator(
            root=ROOT,
            edition_date=edition_date,
            provider=provider,
            normalized_packet=research,
            raw_packet_path=raw_research_path,
            raw_packet_sha256=sha256_file(raw_research_path),
            mode="PROVIDER_BACKED_ACCEPTANCE_TRIAL",
            source_attempt_id=trial_dir.name,
        )
        state = orchestrator.run()
        stopped = _failed_stage(state)
        if stopped:
            raise ProviderError(
                str(stopped.get("error_code") or "V5_PIPELINE_FAILED"),
                str(stopped.get("error_detail") or "provider-seed V5 pipeline stopped"),
                diagnostics={
                    "stage": stopped.get("stage"),
                    "run_state": str((orchestrator.store.path).relative_to(ROOT)).replace("\\", "/"),
                    "run_id": state.get("run_id"),
                },
            )
    except ProviderError as exc:
        failure = {
            "schema_version": 5,
            "status": "FAIL",
            "edition_date": edition_date,
            "created_at": datetime.now(ZoneInfo(str(config["timezone"]))).isoformat(),
            "error_code": exc.code,
            "detail": redact_text(exc.detail),
            "provider": health,
            "runtime_fingerprint": runtime_fingerprint(ROOT),
            "source_git_revision": source_revision(ROOT),
            "integration_test_status_changed": False,
        }
        raw_files = sorted(trial_dir.glob("*.raw.json")) if args.full else []
        if raw_files:
            failure["raw_evidence"] = {
                str(path.relative_to(ROOT)).replace("\\", "/"): sha256_file(path)
                for path in raw_files
            }
        if args.full:
            initial_path = trial_dir / "initial-research-packet.json"
            state_path = orchestrator.store.path if orchestrator is not None else None
            pipeline_evidence = {}
            if initial_path.is_file():
                pipeline_evidence[str(initial_path.relative_to(ROOT)).replace("\\", "/")] = sha256_file(initial_path)
            if state_path is not None and state_path.is_file():
                pipeline_evidence[str(state_path.relative_to(ROOT)).replace("\\", "/")] = sha256_file(state_path)
            if pipeline_evidence:
                failure["pipeline_evidence"] = pipeline_evidence
            if exc.diagnostics:
                failure["pipeline_diagnostics"] = exc.diagnostics
        if args.full:
            trial_dir.mkdir(parents=True, exist_ok=True)
            failure_path = trial_dir / "failure.json"
            atomic_write_json(failure_path, failure)
            failure["failure_evidence"] = str(failure_path.relative_to(ROOT)).replace(
                "\\", "/"
            )
        _emit_json(failure)
        return 1
    research_path = trial_dir / "research.json"
    articles_path = trial_dir / "articles.json"
    atomic_write_json(research_path, research)
    daily_articles = orchestrator.store.run_dir / "articles" / "articles.json"
    articles_value = json.loads(daily_articles.read_text(encoding="utf-8"))["articles"]
    atomic_write_json(articles_path, {"articles": articles_value})
    active = [item for item in articles_value if item.get("status") == "ACTIVE"]
    receipt = {
        "schema_version": 5,
        "status": "VALIDATED_AWAITING_HUMAN_REVIEW",
        "edition_date": edition_date,
        "created_at": datetime.now(ZoneInfo(str(config["timezone"]))).isoformat(),
        "provider": health,
        "editorial_generation_tested": True,
        "runtime_fingerprint": runtime_fingerprint(ROOT),
        "source_git_revision": source_revision(ROOT),
        "active_sections": len(active),
        "skipped_sections": len(articles_value) - len(active),
        "edition_words": sum(
            len(" ".join(item.get("body", [])).split()) for item in active
        ),
        "artifacts": {
            str(research_path.relative_to(ROOT)).replace("\\", "/"): sha256_file(research_path),
            str(articles_path.relative_to(ROOT)).replace("\\", "/"): sha256_file(articles_path),
        },
        "research_counts": _research_counts(research),
        "integration_test_status_changed": False,
        "next_action": "Human-review facts, sources, Arabic, depth, and skips before setting PASS.",
    }
    receipt_path = trial_dir / "receipt.json"
    atomic_write_json(receipt_path, receipt)
    _emit_json(receipt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
