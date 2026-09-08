"""Persistent, evidence-bound investigation dossiers."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from dragon.state import atomic_write_json


class InvestigationError(RuntimeError):
    pass


def _case_id(story_key: str) -> str:
    return "CASE-" + hashlib.sha256(story_key.encode("utf-8")).hexdigest()[:12].upper()


def _load_dossier(path: Path, case_id: str, story_key: str, edition_date: str) -> dict:
    if not path.exists():
        return {
            "schema_version": 1,
            "case_id": case_id,
            "story_key": story_key,
            "first_observed": edition_date,
            "dates_observed": [],
            "claims": [],
            "evidence_index": [],
            "contradictions": [],
            "unanswered_questions": [],
            "publication_state": {"publication_ready": False, "last_evaluated": edition_date},
        }
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InvestigationError(f"existing dossier is unreadable: {path}") from exc
    if (
        value.get("schema_version") != 1
        or value.get("case_id") != case_id
        or value.get("story_key") != story_key
        or not isinstance(value.get("claims"), list)
        or not isinstance(value.get("evidence_index"), list)
    ):
        raise InvestigationError(f"existing dossier identity/schema mismatch: {path}")
    return value


def update_investigation_dossiers(
    root: Path,
    edition_date: str,
    articles: list[dict],
    claim_graph: dict,
    intelligence: dict,
    *,
    synthetic: bool = False,
) -> tuple[dict, tuple[Path, ...]]:
    graph_by_article = {}
    for claim in claim_graph.get("claims", []):
        graph_by_article.setdefault(claim["article_id"], []).append(claim)
    source_records = {item["source_id"]: item for item in intelligence.get("source_records", [])}
    reports = []
    paths = []
    for article in articles:
        if article.get("status") != "ACTIVE" or article.get("section_id") != "investigations":
            continue
        story_key = str(article.get("story_key") or "")
        if not story_key:
            raise InvestigationError("active investigation has no stable story_key")
        case_id = _case_id(story_key)
        path = root / "investigations" / case_id / "dossier.json"
        dossier = _load_dossier(path, case_id, story_key, edition_date)
        claims = graph_by_article.get(article["id"], [])
        claim_map = {item["claim_id"]: item for item in dossier["claims"]}
        evidence_map = {
            (item["claim_id"], item["source_id"]): item
            for item in dossier["evidence_index"]
        }
        for claim in claims:
            claim_map[claim["claim_id"]] = {
                "claim_id": claim["claim_id"],
                "text": claim.get("text"),
                "classification": claim.get("classification"),
                "assessment": claim.get("assessment"),
                "disputed": bool(claim.get("disputed")),
                "last_observed": edition_date,
            }
            for evidence in claim.get("evidence", []):
                evidence_map[(claim["claim_id"], evidence["source_id"])] = {
                    "claim_id": claim["claim_id"],
                    "source_id": evidence["source_id"],
                    "url": evidence.get("url"),
                    "alignment": evidence.get("alignment"),
                    "observed_at": edition_date,
                }
        checks = article.get("investigation_checks") or {}
        primary = any(
            evidence.get("source_type") in {"primary", "official"} and evidence.get("supports")
            for claim in claims for evidence in claim.get("evidence", [])
        )
        origins = {
            evidence.get("independent_origin_group")
            for claim in claims for evidence in claim.get("evidence", [])
            if evidence.get("independent_origin_group")
        }
        unsupported = any(claim.get("assessment") != "SUPPORTED" for claim in claims)
        serious = bool(checks.get("serious_accountability_claim"))
        fairness = (
            not serious
            or (
                checks.get("counter_evidence_checked") is True
                and checks.get("response_status") in {"SOUGHT", "RECEIVED", "DECLINED", "NO_RESPONSE"}
            )
        )
        ready = bool(
            checks.get("publication_ready")
            and claims
            and (synthetic or (primary and len(origins) >= 2))
            and not unsupported
            and fairness
        )
        dossier["dates_observed"] = sorted(set(dossier["dates_observed"]) | {edition_date})
        dossier["claims"] = sorted(claim_map.values(), key=lambda item: item["claim_id"])
        dossier["evidence_index"] = sorted(
            evidence_map.values(), key=lambda item: (item["claim_id"], item["source_id"])
        )
        dossier["contradictions"] = sorted(
            {claim["claim_id"] for claim in claims if claim.get("disputed")}
        )
        dossier["unanswered_questions"] = sorted(
            set(dossier.get("unanswered_questions", []))
            | ({"يلزم استكمال الدليل المستقل أو الموقف المقابل."} if not ready else set())
        )
        dossier["publication_state"] = {
            "publication_ready": ready,
            "last_evaluated": edition_date,
            "primary_evidence_present": primary,
            "independent_origin_count": len(origins),
            "counter_evidence_checked": bool(checks.get("counter_evidence_checked")),
            "response_status": checks.get("response_status"),
            "serious_accountability_claim": serious,
            "unsupported_claim_present": unsupported,
        }
        atomic_write_json(path, dossier)
        paths.append(path)
        reports.append({
            "article_id": article["id"], "case_id": case_id,
            "publication_ready": ready, "dossier": path.relative_to(root).as_posix(),
        })
    failures = [item["article_id"] for item in reports if not item["publication_ready"]]
    return ({
        "schema_version": 1,
        "status": "PASS" if not failures else "FAIL",
        "investigations": reports,
        "not_ready_article_ids": failures,
        "no_active_investigation": not reports,
        "mode": "synthetic" if synthetic else "production",
    }, tuple(paths))
