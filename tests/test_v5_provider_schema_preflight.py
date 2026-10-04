"""Provider-free checks at the real Codex CLI invocation boundary."""
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
from jsonschema import Draft202012Validator

from dragon.archive import ArchiveError, LocalAcceptanceArchive, verify_acceptance_bundle
from dragon.acceptance_replay import replay_acceptance_bundle
from dragon.provider_research_acceptance import OneShotProviderResearch
from dragon.providers import LocalCommandEditorialProvider, ProviderError
from dragon.provider_targeting import build_research_targeting
from dragon.provider_schema import schema_preflight, serialized_json, text_hash
from scripts import codex_editorial_provider as adapter
from tests.test_v5_provider_research_acceptance import _undercovered_packet, _source, DATE

ROOT = Path(__file__).resolve().parents[1]
COMMAND = (sys.executable, str(ROOT / "scripts/codex_editorial_provider.py"))


def payload():
    targeting = build_research_targeting(DATE, {"coverage_rules": [{
        "id": "accountability_and_service", "sections": ["investigations", "service"], "minimum_active": 2,
    }]})
    return LocalCommandEditorialProvider(COMMAND).research_payload(DATE, {"research_targeting": targeting})


def response(*, candidate=False):
    value = _undercovered_packet()
    value["hard_target_results"] = [{
        "target_id": f"HARD:{lane}", "status": "NO_QUALIFYING_CANDIDATE_FOUND",
        "search_intent": "Offline fixture search", "search_attempts": [{"query": "fixture current event", "purpose": "fixture search"}],
        "candidate_matches": [], "no_qualifying_reason": "Fixture found no qualifying event.",
    } for lane in ("ACCOUNTABILITY", "SERVICE")]
    if candidate:
        value["sources"].append(_source("independent", "independent", "news.fixture"))
        section = next(s for s in value["sections"] if s["section_id"] == "investigations")
        section.update(status="ACTIVE", selected_candidate_id="audit", selection_reason="Fixture selection.", no_news_reason=None, fallback_action=None,
            candidates=[{"id": "audit", "rank": 1, "title": "Fictional current audit finding",
                "discovery_source_ids": ["provider-lead", "independent"], "verification_source_ids": ["provider-lead", "independent"],
                "primary_evidence_source_ids": ["provider-lead"], "independent_evidence_source_ids": ["independent"],
                "facts": ["Fictional oversight event."], "claims": [], "unknowns": [], "disputed_points": []}])
        alternate = deepcopy(section["candidates"][0])
        alternate.update(id="audit-alternate", rank=2)
        section["candidates"].append(alternate)
        value["hard_target_results"][0].update(status="CANDIDATES_PRODUCED", no_qualifying_reason=None,
            candidate_matches=[{"candidate_id": "audit", "semantic_match_rationale": "Fictional formal oversight action.",
                "current_event_rationale": "Fictional current dated action.", "expected_source_roles": ["PRIMARY", "INDEPENDENT"],
                "exact_artifact_source_ids": ["provider-lead", "independent"]}])
    return value


def test_exact_serializer_and_provider_free_cli_emit_identical_schema():
    value = payload()
    prepared = adapter.prepare_codex_request("research", value)
    assert prepared["status"] == "PASS", prepared["schema_preflight"]
    assert all(prepared["schema_preflight"]["keyword_counts"][key] == 0 for key in ("allOf", "oneOf", "anyOf", "$ref", "$defs", "definitions", "if", "then", "else"))
    result = subprocess.run([*COMMAND, "--operation", "schema-preflight"], input=serialized_json(value),
        capture_output=True, text=True, encoding="utf-8", check=True, timeout=30)
    assert json.loads(result.stdout) == prepared
    assert json.loads(prepared["schema_text"]) == adapter._schema("research")


@pytest.mark.parametrize("keyword", ["allOf", "oneOf", "if", "then", "else", "not", "dependentSchemas", "dependentRequired", "definitions"])
def test_unsupported_keywords_fail_recursively(keyword):
    schema = adapter._schema("research")
    schema["properties"]["hard_target_results"]["items"][keyword] = ([{"type": "object"}] if keyword in {"allOf", "oneOf"} else {})
    report = schema_preflight(serialized_json(schema))
    assert report["status"] == "FAIL"


def test_regressed_real_schema_blocks_guard_and_client_with_zero_calls(tmp_path, monkeypatch):
    real_schema = adapter._schema
    def regressed(operation):
        schema = real_schema(operation)
        schema["properties"]["hard_target_results"]["items"]["allOf"] = [{"type": "object"}]
        return schema
    monkeypatch.setattr(adapter, "_schema", regressed)
    provider = LocalCommandEditorialProvider(COMMAND, capture_directory=tmp_path / "provider")
    monkeypatch.setattr(provider.__class__, "_invoke", lambda *_: pytest.fail("provider invoked after schema failure"))
    guard = OneShotProviderResearch(provider, tmp_path / "provider", "schema-regression", "Africa/Casablanca")
    with pytest.raises(ProviderError) as caught:
        guard.research(DATE, payload()["continuity"])
    assert caught.value.code == "BLOCKED_PRE_PROVIDER"
    assert guard.calls == 0
    report = json.loads((tmp_path / "provider/research.schema-preflight.json").read_text(encoding="utf-8"))
    assert report["schema"]["keyword_counts"]["allOf"] == 1
    with pytest.raises(RuntimeError, match="PREFLIGHT_FAILED"):
        adapter._run_codex("research", payload(), binary="forbidden", runner=lambda *_args, **_kwargs: pytest.fail("network boundary reached"))


@pytest.mark.parametrize("candidate", [False, True])
def test_no_result_and_candidate_contracts_round_trip(candidate):
    raw = response(candidate=candidate)
    prepared = adapter.prepare_codex_request("research", payload())
    Draft202012Validator(json.loads(prepared["schema_text"])).validate(raw)
    normalized = LocalCommandEditorialProvider(COMMAND).normalize_research_packet(DATE, json.loads(serialized_json(raw)),
        research_targeting=payload()["continuity"]["research_targeting"])
    assert [r["target_id"] for r in normalized["hard_target_results"]] == ["HARD:ACCOUNTABILITY", "HARD:SERVICE"]
    assert normalized["hard_target_results"][1]["status"] == "NO_QUALIFYING_CANDIDATE_FOUND"
    if candidate:
        assert normalized["hard_target_results"][0]["candidate_matches"][0]["exact_artifact_source_ids"] == ["provider-lead", "independent"]


def test_only_client_boundary_is_stubbed_and_receives_prevalidated_bytes(monkeypatch):
    value = payload()
    prepared = adapter.prepare_codex_request("research", value)
    monkeypatch.setattr(adapter, "_schema", lambda *_: pytest.fail("schema regenerated after preflight"))
    calls = []
    def client(command, **kwargs):
        outgoing = Path(command[command.index("--output-schema") + 1]).read_bytes()
        assert outgoing == prepared["schema_text"].encode("utf-8")
        assert text_hash(outgoing.decode()) == prepared["schema_preflight"]["schema_sha256"]
        assert kwargs["input"] == prepared["prompt_text"]
        calls.append(command)
        Path(command[command.index("--output-last-message") + 1]).write_text(serialized_json(response()), encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "")
    assert adapter._run_codex("research", value, binary="stub-client", runner=client, prepared=prepared) == response()
    assert len(calls) == 1


def test_prepared_payload_or_schema_mutation_blocks_client():
    prepared = adapter.prepare_codex_request("research", payload())
    prepared["schema_text"] += " "
    with pytest.raises(RuntimeError, match="PREFLIGHT_FAILED"):
        adapter._run_codex("research", payload(), binary="forbidden", prepared=prepared,
            runner=lambda *_args, **_kwargs: pytest.fail("changed schema reached client"))


def test_real_protocol_subprocess_preserves_preflight_bytes_and_one_call_guard(tmp_path, monkeypatch):
    raw = serialized_json(response()) + "\n"
    response_path = tmp_path / "fixture-response.json"
    response_path.write_bytes(raw.encode("utf-8"))
    audit_path = tmp_path / "client-boundary.json"
    stub = tmp_path / "client.py"
    stub.write_text(
        "import hashlib,json,pathlib,sys\n"
        "args=sys.argv\n"
        "schema=pathlib.Path(args[args.index('--output-schema')+1]).read_bytes()\n"
        "prompt=sys.stdin.read()\n"
        f"pathlib.Path({str(audit_path)!r}).write_text(json.dumps({{'schema_sha256':hashlib.sha256(schema).hexdigest(),'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest()}}),encoding='utf-8')\n"
        f"pathlib.Path(args[args.index('--output-last-message')+1]).write_bytes(pathlib.Path({str(response_path)!r}).read_bytes())\n",
        encoding="utf-8",
    )
    if os.name == "nt":
        binary = tmp_path / "stub-client.cmd"
        binary.write_text(f'@"{sys.executable}" "{stub}" %*\n', encoding="utf-8")
    else:
        binary = stub
        stub.write_text(f"#!{sys.executable}\n" + stub.read_text(encoding="utf-8"), encoding="utf-8")
        stub.chmod(0o755)
    monkeypatch.setenv("DRAGON_CODEX_BINARY", str(binary))
    provider = LocalCommandEditorialProvider(COMMAND, capture_directory=tmp_path / "capture")
    guard = OneShotProviderResearch(provider, tmp_path / "capture", "actual-protocol-fixture", "Africa/Casablanca")
    guard.research(DATE, payload()["continuity"])
    assert guard.calls == 1
    prepared = json.loads((tmp_path / "capture/research.prepared-request.json").read_text(encoding="utf-8"))
    client = json.loads(audit_path.read_text(encoding="utf-8"))
    assert client["schema_sha256"] == prepared["schema_preflight"]["schema_sha256"]
    assert client["prompt_sha256"] == prepared["prompt_sha256"]
    assert (tmp_path / "capture/research.raw.json").read_bytes() == raw.encode("utf-8")
    with pytest.raises(ProviderError, match="exactly one"):
        guard.research(DATE, payload()["continuity"])
    assert guard.calls == 1


def test_documented_nested_union_and_local_reference_are_supported():
    schema = {"type": "object", "properties": {"value": {"anyOf": [{"$ref": "#/$defs/text"}, {"type": "null"}]}},
        "required": ["value"], "additionalProperties": False, "$defs": {"text": {"type": "string"}}}
    assert schema_preflight(serialized_json(schema))["status"] == "PASS"
    schema["properties"]["value"] = {"$ref": "https://untrusted.fixture/schema"}
    assert schema_preflight(serialized_json(schema))["status"] == "FAIL"


def test_durable_preservation_and_missing_response_have_separate_states(tmp_path):
    source = tmp_path / "run"
    source.mkdir()
    run_id = "provider-rejected-fixture"
    (source / "state.json").write_text(serialized_json({"run_id": run_id}), encoding="utf-8")
    (source / "provider-research").mkdir()
    (source / "provider-research/invocation.json").write_text(serialized_json({"run_id": run_id, "status": "FAILED",
        "failure_classification": "PROVIDER_REQUEST_SCHEMA_REJECTED_PRE_MODEL"}), encoding="utf-8")
    archive = LocalAcceptanceArchive(root=ROOT, run_dir=source, run_id=run_id, edition_date=DATE, destination=tmp_path / "archive")
    with pytest.raises(ArchiveError):
        archive.finalize(required=["state.json", "provider-research/research.raw.json"], provider_calls=1, run_result="FAILED",
            incompleteness_reason="INCOMPLETE_PROVIDER_REJECTED_REQUEST")
    manifest = verify_acceptance_bundle(archive.bundle, require_complete=False)
    assert manifest["acceptance_artifact_durability"] == "PASS"
    assert manifest["acceptance_bundle_completeness"] == "INCOMPLETE_PROVIDER_REJECTED_REQUEST"
    assert replay_acceptance_bundle(archive.bundle, code_root=ROOT)["FRESH_LIVE_REPLAY"] == "NOT_APPLICABLE_NO_PROVIDER_PACKET"
