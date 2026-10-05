"""Isolate response contract faults; never qualify sources or repair role links."""

from collections import Counter
from copy import deepcopy

from dragon.provider_targeting import HARD_TARGET_SECTIONS
from dragon.providers import ProviderError, SECTION_HEADINGS


def _candidate_error(candidate, source_ids):
    required = {"id", "rank", "title", "discovery_source_ids", "verification_source_ids",
                "primary_evidence_source_ids", "independent_evidence_source_ids",
                "facts", "claims", "unknowns", "disputed_points"}
    if not isinstance(candidate, dict) or not required.issubset(candidate):
        return "CANDIDATE_STRUCTURE_INVALID", "Candidate structure is incomplete"
    evidence = ("discovery_source_ids", "verification_source_ids", "primary_evidence_source_ids", "independent_evidence_source_ids")
    content = ("facts", "claims", "unknowns", "disputed_points")
    if (not isinstance(candidate["id"], str) or not candidate["id"].strip()
        or not isinstance(candidate["rank"], int) or isinstance(candidate["rank"], bool) or candidate["rank"] < 1
        or not isinstance(candidate["title"], str) or not candidate["title"].strip()
        or any(not isinstance(candidate[field], list) for field in (*evidence, *content))
        or any(not isinstance(item, str) or len(item) > 600 for field in content for item in candidate[field])):
        return "CANDIDATE_STRUCTURE_INVALID", "Candidate types or identity are invalid"
    references = [item for field in evidence for item in candidate[field]]
    if not references or any(not isinstance(item, str) for item in references) or not set(references).issubset(source_ids):
        return "CANDIDATE_SOURCE_REFERENCE_INVALID", "Candidate cites unknown or malformed source identifiers"
    return None


def isolate_response_candidates(value, targeting, sources, validate_target, evidence_issues):
    """Mutate only the caller's private copy; return audit data on every rejection.

    Ambiguous global identities and absent top-level containers remain fatal.
    Strict target validation is reused separately for each candidate/target.
    Rejected data never remains in a candidate or recovery-candidate pool.
    """
    sections = value.get("sections")
    expected_sections = {key for key, _ in SECTION_HEADINGS}
    if (not isinstance(sections, list) or len(sections) != len(expected_sections)
        or any(not isinstance(s, dict) or not isinstance(s.get("section_id"), str) for s in sections)
        or {s["section_id"] for s in sections} != expected_sections):
        observed = [s.get("section_id") for s in sections if isinstance(s, dict) and isinstance(s.get("section_id"), str)] if isinstance(sections, list) else []
        counts = Counter(observed)
        raise ProviderError("RESEARCH_PACKET_INVALID", "research must contain one candidate decision for every section; "
            f"count={len(sections) if isinstance(sections, list) else 'not-list'}; "
            f"missing={sorted(expected_sections - set(observed))}; unknown={sorted(set(observed) - expected_sections)}; "
            f"duplicates={sorted(key for key, count in counts.items() if count > 1)}; "
            f"invalid_entries={len(sections) - len(observed) if isinstance(sections, list) else 0}")
    pools = []
    for section in sections:
        candidates = section.get("candidates")
        if not isinstance(candidates, list):
            raise ProviderError("RESEARCH_PACKET_INVALID", "section candidate registry must be a list")
        if section.get("status") == "NO_NEWS" and candidates:
            raise ProviderError("RESEARCH_PACKET_INVALID", "no-news section must have no fabricated candidates")
        if section.get("status") == "ACTIVE" and len(candidates) < 2:
            raise ProviderError("RESEARCH_PACKET_INVALID", "active section needs at least two ranked candidates")
        recovery = section.get("recovery_candidates", [])
        if not isinstance(recovery, list):
            raise ProviderError("RESEARCH_PACKET_INVALID", "recovery candidate registry must be a list")
        pools.extend((section, field, items) for field, items in (("candidates", candidates), ("recovery_candidates", recovery)))
    identities = [c["id"] for _, _, pool in pools for c in pool if isinstance(c, dict) and isinstance(c.get("id"), str)]
    if any(count > 1 for count in Counter(identities).values()):
        raise ProviderError("RESEARCH_PACKET_INVALID", "candidate ids must be globally unique")
    candidates, candidate_sections, rejected = {}, {}, []
    rejected_ids = set()
    for section, field, pool in pools:
        for index, candidate in enumerate(pool):
            candidate_id = candidate.get("id") if isinstance(candidate, dict) else None
            error = _candidate_error(candidate, set(sources))
            if error:
                rejected.append({"candidate_id": candidate_id, "section_id": section["section_id"],
                    "locator": f"{section['section_id']}/{field}/{index}",
                    "rejection_code": error[0], "rejection_reason": error[1]})
                if isinstance(candidate_id, str):
                    rejected_ids.add(candidate_id)
                continue
            candidates[candidate_id] = candidate
            candidate_sections[candidate_id] = {section["section_id"]}
    targets = [t for t in (targeting or {}).get("unresolved_targets", []) if isinstance(t, dict)
               and t.get("hard") is True and t.get("current_status") == "UNRESOLVED_PRE_DISCOVERY"
               and t.get("target_id") in {"HARD:ACCOUNTABILITY", "HARD:SERVICE"}]
    normalized, audits = [], []
    if targets:
        raw_results = value.get("hard_target_results")
        if not isinstance(raw_results, list) or any(not isinstance(r, dict) or not isinstance(r.get("target_id"), str) for r in raw_results):
            raise ProviderError("RESEARCH_PACKET_INVALID", "hard-target registry must be an identifiable list")
        expected_targets = {t["target_id"] for t in targets}
        unknown = [deepcopy(r) for r in raw_results if r["target_id"] not in expected_targets]
        for target in targets:
            target_id = target["target_id"]
            entries = [r for r in raw_results if r["target_id"] == target_id]
            record = entries[0] if len(entries) == 1 else None
            raw_matches = record.get("candidate_matches") if record else []
            matches = [match for entry in entries for match in
                (entry.get("candidate_matches") if isinstance(entry.get("candidate_matches"), list) else [])]
            accepted, failures = [], []
            single_target = {"unresolved_targets": [target]}
            target_error = None
            if record is None:
                target_error = ("HARD_TARGET_DISPOSITION_MISSING" if not entries else "HARD_TARGET_DISPOSITION_INVALID",
                                "Missing provider disposition" if not entries else "Duplicate provider dispositions")
            elif record.get("status") == "CANDIDATES_PRODUCED":
                # Validate the target envelope without inventing a candidate.
                if (not isinstance(raw_matches, list) or not raw_matches or record.get("no_qualifying_reason") is not None
                    or not str(record.get("search_intent") or "").strip()
                    or not isinstance(record.get("search_attempts"), list) or not record["search_attempts"]
                    or any(not isinstance(a, dict) or not str(a.get("query") or "").strip()
                           or not str(a.get("purpose") or "").strip() for a in record["search_attempts"])):
                    target_error = ("HARD_TARGET_DISPOSITION_INVALID", "Target lacks a consistent disposition or search attempt")
                else:
                    match_ids = [m.get("candidate_id") for m in matches if isinstance(m, dict)]
                    duplicates = {key for key, n in Counter(key for key in match_ids if isinstance(key, str)).items() if n > 1}
                    for match in matches:
                        candidate_id = match.get("candidate_id") if isinstance(match, dict) else None
                        try:
                            if not isinstance(candidate_id, str) or candidate_id in duplicates:
                                raise ProviderError("HARD_TARGET_CANDIDATE_MISMATCH", "Candidate match identity is missing or duplicated")
                            structural_failure = next((r for r in rejected if r.get("candidate_id") == candidate_id), None)
                            if structural_failure:
                                raise ProviderError(structural_failure["rejection_code"], structural_failure["rejection_reason"])
                            # Type checking here keeps a bad list/reference local,
                            # rather than leaking TypeError from set construction.
                            if any(not isinstance(match.get(field), list) or any(not isinstance(x, str) for x in match[field])
                                   for field in ("expected_source_roles", "exact_artifact_source_ids")):
                                raise ProviderError("HARD_TARGET_DISPOSITION_INVALID", "Candidate has malformed evidence-role references")
                            validate_target([{**deepcopy(record), "candidate_matches": [deepcopy(match)]}],
                                            single_target, candidate_sections, candidates, sources)
                            role_issues = evidence_issues(candidates[candidate_id], sources,
                                section_id=next(iter(candidate_sections[candidate_id])))
                            contradictions = [issue for issue in role_issues if issue not in {
                                "PRIMARY_EVIDENCE_MISSING", "INDEPENDENT_EVIDENCE_MISSING"}]
                            if contradictions:
                                raise ProviderError("INVALID_EVIDENCE_ROLE_LINKAGE", ",".join(contradictions))
                            accepted.append(deepcopy(match))
                        except ProviderError as exc:
                            code = "INVALID_EVIDENCE_ROLE_LINKAGE" if "expectation without" in exc.detail else exc.code
                            failure = {"candidate_id": candidate_id, "rejection_code": code, "rejection_reason": exc.detail}
                            failures.append(failure)
                            if (isinstance(candidate_id, str) and candidate_sections.get(candidate_id, set()).intersection(
                                HARD_TARGET_SECTIONS.get(target.get("semantic_lane"), set()))):
                                rejected_ids.add(candidate_id)
                            existing = next((r for r in rejected if candidate_id is not None and r.get("candidate_id") == candidate_id), None)
                            if existing is not None:
                                existing["target_id"] = target_id
                            else:
                                rejected.append({**failure, "target_id": target_id})
            elif record.get("status") != "NO_QUALIFYING_CANDIDATE_FOUND":
                target_error = ("HARD_TARGET_DISPOSITION_INVALID", "Target disposition is invalid")
            else:
                try:
                    normalized_record = validate_target([deepcopy(record)], single_target, candidate_sections, candidates, sources)[0]
                    normalized.append(normalized_record)
                except ProviderError as exc:
                    target_error = (exc.code, exc.detail)
            if target_error:
                # Reject this target's referenced candidates and its own desk
                # pool; no unrelated desk/target is removed.
                lane = target.get("semantic_lane")
                scoped_ids = {key for key, desks in candidate_sections.items() if desks.intersection(HARD_TARGET_SECTIONS.get(lane, set()))}
                rejected_ids.update(scoped_ids)
                for key in sorted(scoped_ids):
                    failure = {"candidate_id": key, "rejection_code": target_error[0], "rejection_reason": target_error[1]}
                    failures.append(failure)
                    rejected.append({**failure, "target_id": target_id})
                effective = "CONTRACT_VIOLATION"
            elif record["status"] == "CANDIDATES_PRODUCED":
                effective = "CANDIDATES_PRODUCED" if accepted else "CONTRACT_VIOLATION_NO_VALID_CANDIDATES"
                if accepted:
                    normalized.append({**deepcopy(record), "candidate_matches": accepted})
            else:
                effective = record["status"]
            if effective.startswith("CONTRACT_VIOLATION"):
                normalized.append({"target_id": target_id, "status": effective, "candidate_matches": [],
                    "search_intent": record.get("search_intent") if record else None,
                    "search_attempts": deepcopy(record.get("search_attempts", [])) if record else [],
                    "no_qualifying_reason": None})
            audits.append({"target_id": target_id, "raw_candidate_count": len(matches),
                "accepted_candidate_count": len(accepted), "rejected_candidate_count": len(matches) - len(accepted),
                "target_disposition_raw": record.get("status") if record else None,
                "target_disposition_effective": effective,
                "target_contract_status": "FAIL" if effective.startswith("CONTRACT_VIOLATION") else "PARTIAL" if failures else "PASS",
                "target_error": {"code": target_error[0], "reason": target_error[1]} if target_error else None,
                "rejected_candidates": failures, "raw_target_results": deepcopy(entries)})
        value["hard_target_results"] = normalized
    else:
        unknown = []
    # Retain every valid no-result record verbatim. Keep rejected originals only
    # in diagnostics, never in a downstream candidate pool.
    for section, field, original in pools:
        survivors = [c for c in original if isinstance(c, dict) and c.get("id") in candidates and c["id"] not in rejected_ids]
        section[field] = survivors
    for section in sections:
        survivors = section["candidates"]
        selected_rejected = section.get("selected_candidate_id") in rejected_ids
        if section.get("status") == "ACTIVE" and (len(survivors) < 2 or selected_rejected):
            isolation_issue = "SELECTED_CANDIDATE_REJECTED" if selected_rejected and len(survivors) >= 2 else "CANDIDATE_QUORUM_NOT_MET"
            for candidate in survivors:
                issues = evidence_issues(candidate, sources, section_id=section["section_id"])
                candidate["evidence_eligibility"] = {"status": "RESEARCH_INCOMPLETE", "issues": sorted(set(issues + [isolation_issue]))}
            section.update(status="NO_NEWS", candidates=[], recovery_candidates=survivors,
                selected_candidate_id=None, selection_reason=None,
                no_news_reason="لم يبق عدد كاف من المرشحين الصالحين بعد عزل مخالفات عقد البحث.",
                fallback_action="DOSSIER_FOLLOW_UP")
    value["provider_response_validation"] = {"schema_version": 1,
        "status": "PARTIAL" if rejected or any(a["target_contract_status"] != "PASS" for a in audits) or unknown else "PASS",
        "rejected_candidates": rejected, "hard_targets": audits, "unrecognized_target_results": unknown}
    return value
