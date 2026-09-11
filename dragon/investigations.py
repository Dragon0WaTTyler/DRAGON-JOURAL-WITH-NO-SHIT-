"""Persistent, evidence-bound investigation dossiers."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from dragon.investigation_scope import evaluate_super_investigation_scope
from dragon.state import atomic_write_json, sha256_file


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
            "question": None,
            "entities": [],
            "relationships": [],
            "contracts": [],
            "timeline": [],
            "archive_references": [],
            "leads": [],
            "material_uncertainties": [],
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
    for field in (
        "entities", "relationships", "contracts", "timeline", "archive_references",
        "leads", "material_uncertainties", "contradictions", "unanswered_questions",
        "dates_observed",
    ):
        value.setdefault(field, [])
    value.setdefault("question", None)
    return value


def _merge_records(
    existing: list[dict], incoming: list[dict], key_fields: tuple[str, ...], *, identity_fields: tuple[str, ...] = ()
) -> list[dict]:
    merged = {tuple(item.get(field) for field in key_fields): item for item in existing}
    for item in incoming:
        key = tuple(item.get(field) for field in key_fields)
        prior = merged.get(key)
        if prior is not None and any(prior.get(field) != item.get(field) for field in identity_fields):
            raise InvestigationError(f"investigation identity conflict for {key}")
        merged[key] = item
    return [merged[key] for key in sorted(merged, key=lambda item: tuple(str(value) for value in item))]


def _write_case_artifacts(case_root: Path, dossier: dict) -> tuple[Path, ...]:
    case_root.mkdir(parents=True, exist_ok=True)
    (case_root / "evidence").mkdir(exist_ok=True)
    (case_root / "archive").mkdir(exist_ok=True)
    payloads = {
        "entities.json": {
            "schema_version": 1, "case_id": dossier["case_id"],
            "entities": dossier["entities"], "relationships": dossier["relationships"],
            "contracts": dossier["contracts"],
        },
        "timeline.json": {
            "schema_version": 1, "case_id": dossier["case_id"], "events": dossier["timeline"],
        },
        "claims.json": {
            "schema_version": 1, "case_id": dossier["case_id"], "claims": dossier["claims"],
        },
        "evidence-index.json": {
            "schema_version": 1, "case_id": dossier["case_id"],
            "evidence": dossier["evidence_index"], "archive_references": dossier["archive_references"],
        },
        "contradictions.json": {
            "schema_version": 1, "case_id": dossier["case_id"],
            "claim_ids": dossier["contradictions"],
        },
        "unanswered-questions.json": {
            "schema_version": 1, "case_id": dossier["case_id"],
            "questions": dossier["unanswered_questions"],
            "material_uncertainties": dossier["material_uncertainties"],
        },
        "publication-state.json": {"schema_version": 1, "case_id": dossier["case_id"], **dossier["publication_state"]},
    }
    paths = []
    for filename, payload in payloads.items():
        path = case_root / filename
        atomic_write_json(path, payload)
        paths.append(path)
    dossier["modular_artifacts"] = {
        path.name: sha256_file(path) for path in paths
    }
    dossier_path = case_root / "dossier.json"
    atomic_write_json(dossier_path, dossier)
    return (dossier_path, *paths)


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
        if article.get("investigation_mode") == "SUPER_INVESTIGATION":
            scope = evaluate_super_investigation_scope(
                article.get("super_investigation_scope") or {}
            )
            if scope["status"] != "ELIGIBLE":
                raise InvestigationError(
                    "SUPER_INVESTIGATION_SCOPE_REJECTED: MOROCCO + MEKNES ONLY"
                )
        story_key = str(article.get("story_key") or "")
        if not story_key:
            raise InvestigationError("active investigation has no stable story_key")
        case_id = _case_id(story_key)
        path = root / "investigations" / case_id / "dossier.json"
        dossier = _load_dossier(path, case_id, story_key, edition_date)
        investigation_data = article.get("investigation_data") or {
            "question": article.get("headline", ""), "entities": [], "relationships": [],
            "contracts": [], "timeline": [], "archive_references": [], "leads": [],
            "material_uncertainties": [],
        }
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
        material_uncertainties = sorted(
            set(dossier.get("material_uncertainties", []))
            | set(investigation_data.get("material_uncertainties", []))
        )
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
            and not material_uncertainties
        )
        dossier["question"] = investigation_data.get("question") or dossier.get("question")
        dossier["entities"] = _merge_records(
            dossier["entities"], investigation_data.get("entities", []), ("entity_id",),
            identity_fields=("entity_type", "name"),
        )
        dossier["relationships"] = _merge_records(
            dossier["relationships"], investigation_data.get("relationships", []),
            ("from_entity_id", "to_entity_id", "relationship_type"),
        )
        dossier["contracts"] = _merge_records(
            dossier["contracts"], investigation_data.get("contracts", []), ("contract_id",),
            identity_fields=("buyer_entity_id", "supplier_entity_id", "currency"),
        )
        dossier["timeline"] = _merge_records(
            dossier["timeline"], investigation_data.get("timeline", []), ("event_id",),
        )
        archive_references = list(investigation_data.get("archive_references", []))
        for source_id in sorted({evidence["source_id"] for claim in claims for evidence in claim.get("evidence", [])}):
            source = source_records.get(source_id, {})
            if source.get("archive_reference") and source.get("content_hash"):
                archive_references.append({
                    "source_id": source_id,
                    "canonical_url": source.get("canonical_url"),
                    "retrieved_at": source.get("retrieved_at"),
                    "sha256": source.get("content_hash"),
                    "archive_locator": source.get("archive_reference"),
                })
        dossier["archive_references"] = _merge_records(
            dossier["archive_references"], archive_references, ("source_id", "sha256"),
        )
        dossier["leads"] = _merge_records(
            dossier["leads"], investigation_data.get("leads", []), ("description",),
        )
        dossier["material_uncertainties"] = material_uncertainties
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
            "evidence_quality": "HIGH" if primary and len(origins) >= 2 else "MEDIUM" if primary else "LOW",
            "material_uncertainties": material_uncertainties,
            "source_independence": len(origins),
        }
        case_paths = _write_case_artifacts(path.parent, dossier)
        paths.extend(case_paths)
        reports.append({
            "article_id": article["id"], "case_id": case_id,
            "publication_ready": ready, "dossier": path.relative_to(root).as_posix(),
            "artifacts": [item.relative_to(root).as_posix() for item in case_paths],
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
