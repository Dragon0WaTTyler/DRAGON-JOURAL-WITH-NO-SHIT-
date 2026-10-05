"""Candidate/target faults remain explicit; global identity failures stay fatal."""

from copy import deepcopy
from pathlib import Path
import socket
from urllib import request

import pytest

from dragon.providers import LocalCommandEditorialProvider, ProviderError
from dragon.deep_research import build_deep_research_state, load_deep_research_config
from dragon.deep_research_executor import plan_research_actions, schedule_research_actions
from dragon.contract_replay import replay_contract_isolation, preserve_contract_comparison
from dragon.config import load_local_config
from dragon.source_intelligence import build_source_intelligence
from dragon.research_planning import build_research_plan, load_research_budget_config
from dragon.research_recovery import build_recovery_plan
from dragon.source_coverage import load_source_coverage
from dragon.providers import SECTION_HEADINGS
from tests.test_v5_provider_schema_preflight import response, payload, DATE

ROOT = Path(__file__).resolve().parents[1]


def packet():
    value = response(candidate=True)
    match = deepcopy(value["hard_target_results"][0]["candidate_matches"][0])
    match["candidate_id"] = "audit-alternate"
    value["hard_target_results"][0]["candidate_matches"].append(match)
    return value


def normalize(value):
    return LocalCommandEditorialProvider(("forbidden-provider",)).normalize_research_packet(
        DATE, value, research_targeting=payload()["continuity"]["research_targeting"],
        retrieved_at=f"{DATE}T07:00:00+00:00")


def pool(value):
    return [c for s in value["sections"] for key in ("candidates", "recovery_candidates") for c in s.get(key, [])]


def alternate(value):
    return next(c for c in pool(value) if c["id"] == "audit-alternate")


def test_candidate_failure_preserves_sibling_and_service_without_repair():
    raw = packet()
    alternate(raw)["independent_evidence_source_ids"] = []
    before = deepcopy(raw)
    value = normalize(raw)
    assert raw == before
    assert [c["id"] for c in pool(value)] == ["audit"]
    assert value["hard_target_results"][0]["status"] == "CANDIDATES_PRODUCED"
    assert value["hard_target_results"][1] == raw["hard_target_results"][1]
    validation = value["provider_response_validation"]
    audit = validation["hard_targets"][0]
    assert (audit["raw_candidate_count"], audit["accepted_candidate_count"], audit["rejected_candidate_count"]) == (2, 1, 1)
    assert audit["rejected_candidates"][0]["rejection_code"] == "INVALID_EVIDENCE_ROLE_LINKAGE"
    assert alternate(raw)["independent_evidence_source_ids"] == []
    desk = next(s for s in value["sections"] if s["section_id"] == "investigations")
    assert desk["status"] == "NO_NEWS"  # two-candidate publication floor survives
    assert desk["recovery_candidates"][0]["evidence_eligibility"]["status"] == "RESEARCH_INCOMPLETE"
    assert not value["evidence_normalization"]["link_repairs"]


@pytest.mark.parametrize("target", [0, 1])
def test_target_failure_preserves_unrelated_target(target):
    raw = packet()
    raw["hard_target_results"][target]["search_attempts"] = []
    value = normalize(raw)
    assert value["hard_target_results"][target]["status"] == "CONTRACT_VIOLATION"
    assert value["hard_target_results"][1-target] == raw["hard_target_results"][1-target]
    assert value["provider_response_validation"]["hard_targets"][target]["target_contract_status"] == "FAIL"
    if target == 1:
        assert {c["id"] for c in pool(value)} == {"audit", "audit-alternate"}


def test_missing_target_is_failure_not_an_invented_unsuccessful_search():
    raw = packet()
    raw["hard_target_results"].pop()
    value = normalize(raw)
    assert value["hard_target_results"][0]["status"] == "CANDIDATES_PRODUCED"
    service = value["hard_target_results"][1]
    assert service["status"] == "CONTRACT_VIOLATION"
    assert service["no_qualifying_reason"] is None
    assert value["provider_response_validation"]["hard_targets"][1]["target_error"]["code"] == "HARD_TARGET_DISPOSITION_MISSING"


def test_all_bad_candidates_are_contract_failure_not_no_result():
    raw = packet()
    for candidate in pool(raw):
        candidate["independent_evidence_source_ids"] = []
    value = normalize(raw)
    assert value["hard_target_results"][0]["status"] == "CONTRACT_VIOLATION_NO_VALID_CANDIDATES"
    assert value["hard_target_results"][0]["no_qualifying_reason"] is None
    assert not pool(value)
    audit = value["provider_response_validation"]["hard_targets"][0]
    assert (audit["raw_candidate_count"], audit["accepted_candidate_count"], audit["rejected_candidate_count"]) == (2, 0, 2)
    assert value["hard_target_results"][1] == raw["hard_target_results"][1]


@pytest.mark.parametrize("fault", ["primary_missing", "independent_type", "source_overlap", "origin_overlap", "unknown_exact", "malformed_ids", "content"])
def test_equivalent_evidence_or_candidate_contradictions_are_local(fault):
    raw = packet()
    bad = alternate(raw)
    if fault == "primary_missing": bad["primary_evidence_source_ids"] = []
    elif fault == "independent_type": bad["independent_evidence_source_ids"] = ["provider-lead"]
    elif fault == "source_overlap": bad["primary_evidence_source_ids"] = ["independent"]
    elif fault == "origin_overlap":
        source = deepcopy(next(s for s in raw["sources"] if s["id"] == "independent"))
        source.update(id="same-origin", origin=raw["sources"][0]["origin"])
        raw["sources"].append(source)
        bad["independent_evidence_source_ids"] = ["same-origin"]
    elif fault == "unknown_exact": raw["hard_target_results"][0]["candidate_matches"][1]["exact_artifact_source_ids"] = ["missing"]
    elif fault == "malformed_ids": bad["verification_source_ids"] = [{}]
    else: bad["facts"] = [{}]
    value = normalize(raw)
    assert [c["id"] for c in pool(value)] == ["audit"]
    assert value["provider_response_validation"]["hard_targets"][0]["rejected_candidate_count"] == 1


@pytest.mark.parametrize("fault", ["sources", "sections", "duplicate_source", "duplicate_candidate", "version", "target_registry"])
def test_global_corruption_still_rejects_packet(fault):
    raw = packet()
    if fault in {"sources", "sections"}: raw.pop(fault)
    elif fault == "duplicate_source": raw["sources"].append(deepcopy(raw["sources"][0]))
    elif fault == "duplicate_candidate": alternate(raw)["id"] = "audit"
    elif fault == "version": raw["schema_version"] = 999
    else: raw["hard_target_results"] = "corrupted"
    with pytest.raises(ProviderError) as caught: normalize(raw)
    assert caught.value.code == "RESEARCH_PACKET_INVALID"


def test_duplicate_target_does_not_erase_valid_service():
    raw = packet()
    raw["hard_target_results"].append(deepcopy(raw["hard_target_results"][0]))
    value = normalize(raw)
    assert value["hard_target_results"][0]["status"] == "CONTRACT_VIOLATION"
    assert value["hard_target_results"][1] == raw["hard_target_results"][1]
    audit = value["provider_response_validation"]["hard_targets"][0]
    assert audit["raw_candidate_count"] == audit["rejected_candidate_count"] == 4


@pytest.mark.parametrize("malformed", [[], {}, None, 17])
def test_malformed_target_status_is_local(malformed):
    raw = packet()
    raw["hard_target_results"][0]["status"] = malformed
    value = normalize(raw)
    assert value["hard_target_results"][0]["status"] == "CONTRACT_VIOLATION"
    assert value["hard_target_results"][1] == raw["hard_target_results"][1]


def test_wrong_lane_reference_cannot_erase_the_valid_owner_target():
    raw = packet()
    raw["hard_target_results"][1].update(status="CANDIDATES_PRODUCED", no_qualifying_reason=None,
        candidate_matches=deepcopy(raw["hard_target_results"][0]["candidate_matches"]))
    value = normalize(raw)
    assert value["hard_target_results"][0] == raw["hard_target_results"][0]
    assert value["hard_target_results"][1]["status"] == "CONTRACT_VIOLATION_NO_VALID_CANDIDATES"
    assert {c["id"] for c in pool(value)} == {"audit", "audit-alternate"}


def test_rejected_selected_lead_does_not_choose_a_replacement_for_publication():
    raw = packet()
    section = next(s for s in raw["sections"] if s["section_id"] == "investigations")
    third = deepcopy(section["candidates"][1])
    third.update(id="audit-third", rank=3)
    section["candidates"].append(third)
    match = deepcopy(raw["hard_target_results"][0]["candidate_matches"][1])
    match["candidate_id"] = "audit-third"
    raw["hard_target_results"][0]["candidate_matches"].append(match)
    section["candidates"][0]["independent_evidence_source_ids"] = []
    value = normalize(raw)
    desk = next(s for s in value["sections"] if s["section_id"] == "investigations")
    assert desk["status"] == "NO_NEWS" and desk["selected_candidate_id"] is None
    assert {c["id"] for c in pool(value)} == {"audit-alternate", "audit-third"}
    assert all("SELECTED_CANDIDATE_REJECTED" in c["evidence_eligibility"]["issues"] for c in pool(value))


def test_fixture_materialization_reserves_surviving_pair_and_defers_only_empty_initial_lane():
    raw = packet()
    alternate(raw)["independent_evidence_source_ids"] = []
    value = normalize(raw)
    for source in value["sources"]:
        source.update(verification_status="PROVIDER_REPORTED", evidence_relation=None, directness=None, provenance=None)
    config = load_deep_research_config(ROOT / "config/deep-research.yaml", ROOT / "config/deep-research-schema.json")
    readiness = load_local_config(ROOT)["editorial_readiness"]
    intelligence = build_source_intelligence(value)
    plan = build_research_plan(value, intelligence, load_research_budget_config(ROOT / "config/research-budget.yaml"), readiness)
    coverage = load_source_coverage(ROOT / "config/source-coverage.yaml", {s[0] for s in SECTION_HEADINGS})
    recovery = build_recovery_plan(value, intelligence, coverage, readiness)
    initial = build_deep_research_state(value, intelligence, plan, recovery, config, run_scope_id="offline-isolation")
    actions = [a for j in initial["jobs"] for a in plan_research_actions(j, config)]
    assert not any(a.get("target_editorial_function") == "SERVICE" for a in actions)
    schedule = schedule_research_actions(initial["jobs"], config)
    assert schedule["budget_allocation"]["round_cap"] == 8
    assert len(schedule["actions"]) <= 8
    assert not schedule["budget_allocation"]["budget_increased"]
    reservation = schedule["budget_allocation"]["hard_lane_reservation"]
    assert reservation["hard_lane_reserved_capacity"] == 2
    assert reservation["remaining_general_capacity"] == 6
    assert reservation["hard_lane_actions_selected"]["SERVICE"] == []
    pair = [a for a in schedule["actions"] if a.get("provider_candidate_id") == "investigations:audit"]
    assert {a["provider_source_role"] for a in pair} == {"PRIMARY", "INDEPENDENT"}
    assert any(a.get("provider_candidate_id") != "investigations:audit" for a in schedule["actions"])
    later = build_deep_research_state(value, intelligence, plan, recovery, config,
        run_scope_id="offline-isolation", recovery_epoch=1, recovery_only=True)
    assert any(a.get("target_editorial_function") == "SERVICE" for j in later["jobs"] for a in plan_research_actions(j, config))


def test_real_bundle_replays_deterministically_without_network_and_keeps_cap(tmp_path):
    # Optional primary evidence supplied by the task, not a substitute packet.
    import subprocess
    common = Path(subprocess.check_output(["git", "rev-parse", "--git-common-dir"], cwd=ROOT, text=True).strip()).resolve()
    bundle = common / "dragon/research-acceptance/provider-research-acceptance-f1bd0998-d792-4d28-851c-b1c60bfa1f99"
    if not bundle.is_dir(): pytest.skip("task's exact immutable live bundle is not present on this checkout")
    with pytest.MonkeyPatch.context() as patch:
        def forbidden(*args, **kwargs): pytest.fail("offline comparison attempted provider/network execution")
        patch.setattr(LocalCommandEditorialProvider, "_invoke", forbidden)
        patch.setattr(socket.socket, "connect", forbidden)
        patch.setattr(socket.socket, "connect_ex", forbidden)
        patch.setattr(request, "urlopen", forbidden)
        first = replay_contract_isolation(bundle, code_root=ROOT)
        second = replay_contract_isolation(bundle, code_root=ROOT)
        receipt = preserve_contract_comparison(bundle, code_root=ROOT, destination=tmp_path)
        assert preserve_contract_comparison(bundle, code_root=ROOT, destination=tmp_path) == receipt
        preserved = Path(receipt["receipt"]).parent
        (preserved / "comparison.json").write_text("tampered", encoding="utf-8")
        with pytest.raises(ValueError, match="changed; refusing overwrite"):
            preserve_contract_comparison(bundle, code_root=ROOT, destination=tmp_path)
        assert (preserved / "comparison.json").read_text(encoding="utf-8") == "tampered"
    assert first == second
    assert first["input_manifest_sha256"] == "ba2899253f187da1d77acac28210f6d738635b5272945eb8382098fa27497ae8"
    assert first["provider_calls"] == first["network_calls"] == first["actions_executed"] == 0
    assert {c["id"] for c in pool(first["normalized_packet"])}.isdisjoint({"inv-rotork"})
    assert "inv-itrane" in {c["id"] for c in pool(first["normalized_packet"])}
    actions = first["materialized_actions"]
    assert not [a for a in actions if a.get("target_editorial_function") == "SERVICE"]
    schedule = first["scheduler_allocation"]
    assert len(schedule["actions"]) == schedule["budget_allocation"]["round_cap"] == 8
    assert schedule["budget_allocation"]["budget_increased"] is False
    reservation = schedule["budget_allocation"]["hard_lane_reservation"]
    assert reservation["hard_lane_actions_selected"]["SERVICE"] == []
    assert reservation["hard_lane_reserved_capacity"] == 2
    pair = [a for a in schedule["actions"] if a.get("provider_candidate_id") == "investigations:inv-itrane"]
    assert {a["provider_source_role"] for a in pair} == {"PRIMARY", "INDEPENDENT"}
    assert all(a["action_type"] == "FETCH_URL" for a in pair)
    assert reservation["remaining_general_capacity"] == 6
    assert schedule["budget_allocation"]["hard_breadth_reserved_slots"] == 1
    # The empty lane's acquisition is deferred, never disabled or treated closed.
    frozen = bundle / "configuration"
    config = load_deep_research_config(frozen / "config/deep-research.yaml", frozen / "config/deep-research-schema.json")
    packet_value = first["normalized_packet"]
    epoch1 = build_deep_research_state(packet_value, first["source_intelligence"], first["research_plan"],
        first["recovery_plan"], config, run_scope_id=first["input_run_id"], recovery_epoch=1, recovery_only=True)
    recovery_actions = [a for j in epoch1["jobs"] for a in plan_research_actions(j, config)]
    assert any(a.get("target_editorial_function") == "SERVICE" for a in recovery_actions)
