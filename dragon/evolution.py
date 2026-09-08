"""Controlled daily self-evaluation; production resources never self-mutate."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import yaml

from dragon.state import atomic_write_json


DIMENSIONS = (
    "presentation",
    "analysis",
    "evidence",
    "citation_support",
    "journalism_quality",
    "arabic_editorial_quality",
    "visual_quality",
)


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _completed_mode_editions(root: Path, mode: str) -> int:
    count = 0
    for path in root.glob("editions/*/*/*/final-qa.json"):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if value.get("status") == "PASS" and value.get("mode") == mode:
            count += 1
    return count


def build_evolution_report(
    root: Path,
    edition_date: str,
    mode: str,
    *,
    articles: list[dict],
    source_intelligence: dict,
    claim_graph: dict,
    science_report: dict,
    layout_plan: dict,
    pdf_report: dict,
    epub_report: dict,
) -> dict:
    config_path = root / "config" / "evolution.yaml"
    config = (
        yaml.safe_load(config_path.read_text(encoding="utf-8"))
        if config_path.exists()
        else {"evaluation_interval_complete_editions": 7, "resource_versions": {}}
    )
    complete_count = _completed_mode_editions(root, mode) + 1
    interval = int(config["evaluation_interval_complete_editions"])
    due = complete_count % interval == 0
    sources = source_intelligence.get("source_records", [])
    events = source_intelligence.get("event_clusters", [])
    claims = claim_graph.get("claims", [])
    assessments = [claim.get("assessment") for claim in claims]
    passports = science_report.get("passports", [])
    roles = [page.get("page_role") for page in layout_plan.get("pages", [])]
    metrics = {
        "source_count": len(sources),
        "primary_source_rate": _rate(sum(item.get("primary_evidence") is True for item in sources), len(sources)),
        "independent_origin_rate": _rate(sum(item.get("independent_origin_count", 0) >= 2 for item in events), len(events)),
        "wire_duplication_rate": _rate(sum(item.get("wire_origin") is not None for item in sources), len(sources)),
        "duplicate_source_rate": _rate(sum(bool(item.get("duplicate_group_ids")) for item in sources), len(sources)),
        "unsupported_claim_rate": _rate(sum(item in {"UNAVAILABLE", "CONTRADICTED"} for item in assessments), len(assessments)),
        "citation_support_rate": _rate(sum(item == "SUPPORTED" for item in assessments), len(assessments)),
        "science_fulltext_rate": _rate(sum(item.get("full_text_status") == "FULL_TEXT_VERIFIED" for item in passports), len(passports)),
        "section_depth_words": round(sum(len(" ".join(item.get("body", [])).split()) for item in articles) / max(1, len(articles)), 2),
        "page_grammar_variety": len(set(roles)),
        "layout_repetition_rate": _rate(len(roles) - len(set(roles)), len(roles)),
        "layout_defect_rate": _rate(len(pdf_report.get("issues", [])), max(1, pdf_report.get("pages", 0))),
        "pdf_failure_rate": 0.0 if pdf_report.get("status") == "PASS" else 1.0,
        "epub_failure_rate": 0.0 if epub_report.get("status") == "PASS" else 1.0,
    }
    return {
        "schema_version": 1,
        "status": "PASS" if due else "NOT_DUE",
        "mode": mode,
        "edition_date": edition_date,
        "complete_edition_ordinal": complete_count,
        "threshold": interval,
        "evaluation_due": due,
        "metrics": metrics,
        "dragon_eval_dimensions": list(DIMENSIONS),
        "resource_versions": config.get("resource_versions", {}),
        "control_plane": {
            "sequence": [
                "OBSERVE", "DETECT_WEAKNESS", "PROPOSE_CHANGE", "CREATE_CANDIDATE",
                "RUN_FIXED_BENCHMARK", "COMPARE", "REGRESSION_CHECK", "PROMOTE_OR_REJECT",
            ],
            "automatic_production_mutation": False,
            "separate_schedule": False,
        },
    }


def compare_candidate(
    resource: str,
    old_version: str,
    candidate_version: str,
    baseline: dict[str, float],
    candidate: dict[str, float],
    reason: str,
) -> dict:
    missing = set(DIMENSIONS) - set(baseline) | (set(DIMENSIONS) - set(candidate))
    if missing:
        raise ValueError("missing DRAGON-EVAL dimensions: " + ", ".join(sorted(missing)))
    regressions = [name for name in DIMENSIONS if candidate[name] < baseline[name]]
    before = sum(baseline[name] for name in DIMENSIONS) / len(DIMENSIONS)
    after = sum(candidate[name] for name in DIMENSIONS) / len(DIMENSIONS)
    decision = "PROMOTION_ELIGIBLE" if after > before and not regressions else "REJECT"
    return {
        "schema_version": 1,
        "resource": resource,
        "old_version": old_version,
        "candidate_version": candidate_version,
        "reason": reason,
        "metrics_before": baseline,
        "metrics_after": candidate,
        "regressions": regressions,
        "decision": decision,
        "automatic_promotion": False,
        "rollback_pointer": old_version,
    }


def record_feedback(root: Path, text: str, *, received_at: str | None = None) -> Path:
    timestamp = received_at or datetime.now(timezone.utc).isoformat()
    identifier = "FB-" + hashlib.sha256(f"{timestamp}\n{text}".encode("utf-8")).hexdigest()[:12].upper()
    path = root / "evolution" / "feedback" / f"{identifier}.json"
    atomic_write_json(
        path,
        {
            "schema_version": 1,
            "feedback_id": identifier,
            "received_at": timestamp,
            "text": text,
            "status": "QUEUED_FOR_BENCHMARK",
            "production_mutated": False,
        },
    )
    return path
