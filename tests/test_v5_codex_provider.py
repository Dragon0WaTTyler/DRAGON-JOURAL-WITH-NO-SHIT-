from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from dragon.providers import SECTION_HEADINGS as RUNTIME_SECTION_HEADINGS
from scripts.codex_editorial_provider import SECTION_HEADINGS, _probe, _run_codex, _schema


def test_adapter_supports_direct_script_execution() -> None:
    script = Path(__file__).resolve().parents[1] / "scripts" / "codex_editorial_provider.py"
    result = subprocess.run(
        [sys.executable, str(script), "--help"],
        cwd=Path(__file__).parent,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    assert result.returncode == 0, result.stderr


def _object_schemas(value):
    if isinstance(value, dict):
        if value.get("type") == "object" or (
            isinstance(value.get("type"), list) and "object" in value["type"]
        ):
            yield value
        for child in value.values():
            yield from _object_schemas(child)
    elif isinstance(value, list):
        for child in value:
            yield from _object_schemas(child)


def test_health_probe_is_explicitly_cli_only() -> None:
    def runner(command, **kwargs):
        output = "codex-cli 0.test" if "--version" in command else "Logged in using ChatGPT"
        return subprocess.CompletedProcess(command, 0, output, "")

    value = _probe("codex", runner)
    assert value["status"] == "PASS"
    assert value["unattended"] is True
    assert value["capability_probe"] == "CLI_AUTH_ONLY"
    assert value["editorial_generation_tested"] is False


def test_editorial_exec_is_ephemeral_read_only_and_structured() -> None:
    calls = []

    def runner(command, **kwargs):
        calls.append((command, kwargs))
        output = Path(command[command.index("--output-last-message") + 1])
        output.write_text(
            json.dumps({"edition_date": "2099-01-02", "sources": [], "sections": []}),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0, "", "")

    value = _run_codex(
        "research",
        {"edition_date": "2099-01-02"},
        binary="codex",
        runner=runner,
    )

    command, kwargs = calls[0]
    assert value["edition_date"] == "2099-01-02"
    assert "--ephemeral" in command and "--search" in command
    assert "--ignore-user-config" in command
    assert command[command.index("--sandbox") + 1] == "read-only"
    assert command[command.index("--ask-for-approval") + 1] == "never"
    assert "--output-schema" in command
    assert "untrusted data" in kwargs["input"]


def test_editorial_exec_reports_redacted_stderr_on_failure() -> None:
    def runner(command, **kwargs):
        return subprocess.CompletedProcess(
            command,
            1,
            "",
            "permission denied; DRAGON_API_KEY=do-not-log",
        )

    try:
        _run_codex("research", {"edition_date": "2099-01-02"}, binary="codex", runner=runner)
    except RuntimeError as exc:
        detail = str(exc)
    else:
        raise AssertionError("failed Codex execution was accepted")

    assert "permission denied" in detail
    assert "DRAGON_API_KEY=[REDACTED]" in detail
    assert "do-not-log" not in detail


def test_article_prompt_explains_runtime_word_constraints() -> None:
    from scripts.codex_editorial_provider import _prompt

    prompt = _prompt(
        "articles",
        {
            "editorial_identity": {"expected_byline": "تحرير: اسم القلم"},
            "quality_constraints": {
                "minimum_active_article_words": 350,
                "minimum_edition_words": 4000,
            },
            "article_budget_contract": {
                "generation_target_words": 6000,
                "articles": [{"section_id": "front", "minimum_words": 350, "target_words": 600, "evidence_ids": ["s1"]}],
            },
        },
    )
    assert "minimum_active_article_words" in prompt
    assert "minimum_edition_words" in prompt
    assert "generation_target_words" in prompt
    assert "6000" in prompt
    assert "combined edition words" in prompt
    assert "zero ACTIVE articles" in prompt
    assert "تحرير: اسم القلم" in prompt
    assert "تحرير: DRAGON" not in prompt
    assert "original Arabic synthesis" in prompt
    assert "never reproduce a full copyrighted article" in prompt
    assert "repair_skip_reason_code" in prompt
    assert "SOURCE_INVALIDATED" in prompt


def test_research_prompt_explains_inherited_edition_readiness() -> None:
    from scripts.codex_editorial_provider import _prompt

    prompt = _prompt(
        "research",
        {
            "edition_readiness": {
                "minimum_active_sections": 10,
                "coverage_rules": [{"id": "morocco_breadth", "minimum_active": 3}],
                "minimum_edition_words": 4000,
            },
        },
    )

    assert "Edition readiness" in prompt
    assert "minimum_active_sections" in prompt
    assert "morocco_breadth" in prompt


def test_research_prompt_explains_hard_deficit_targeting_and_unverified_status() -> None:
    from dragon.provider_targeting import build_research_targeting
    from scripts.codex_editorial_provider import _prompt

    prompt = _prompt(
        "research",
        {
            "continuity": {
                "research_targeting": build_research_targeting(
                    "2099-01-02",
                    {"coverage_rules": [
                        {"id": "morocco_breadth", "sections": ["siyasa_dawla"], "minimum_active": 3},
                        {"id": "accountability_and_service", "sections": ["investigations", "service"], "minimum_active": 2},
                    ]},
                ),
            },
        },
    )

    for required in (
        "HARD:ACCOUNTABILITY",
        "HARD:SERVICE",
        "BREADTH:morocco_breadth",
        "formal audit or inspection action or finding",
        "institutional participation without a concrete accountability action",
        "future-only announcement when current operation is required",
        "DISCOVERY_INTELLIGENCE_ONLY",
        "claim_supported",
        "event or effective date",
        "does not create a scheduler",
        "executor actions",
    ):
        assert required in prompt


def test_structured_output_schemas_are_strict_and_complete() -> None:
    assert SECTION_HEADINGS == RUNTIME_SECTION_HEADINGS
    for operation in ("research", "articles"):
        schema = _schema(operation)
        assert schema["type"] == "object"
        for object_schema in _object_schemas(schema):
            assert object_schema["additionalProperties"] is False
            assert set(object_schema["required"]) == set(object_schema["properties"])

    research = _schema("research")
    assert "hard_target_results" in research["required"]
    assert research["properties"]["hard_target_results"]["minItems"] == 2
    assert research["properties"]["hard_target_results"]["maxItems"] == 2
    hard_result = research["properties"]["hard_target_results"]["items"]
    assert set(hard_result["properties"]["target_id"]["enum"]) == {"HARD:ACCOUNTABILITY", "HARD:SERVICE"}
    source = research["properties"]["sources"]["items"]
    assert set(source["properties"]) == {
            "id", "url", "publisher", "publication_date", "accessed_at", "source_type", "origin",
        "claim_supported", "doi", "publication_status", "full_text_status",
        "methods_read", "limitations_read",
        "science_metadata",
    }
    assert source["properties"]["claim_supported"]["maxLength"] == 600
    assert source["properties"]["publication_date"]["pattern"] == r"^\d{4}-\d{2}-\d{2}$"
    assert source["properties"]["accessed_at"]["minLength"] == 1
    science = source["properties"]["science_metadata"]
    assert {"sample_size", "locators", "doi_verified", "metadata_matches", "claim_alignment", "correlation_only"}.issubset(
        set(science["properties"])
    )
    section = research["properties"]["sections"]["items"]
    assert section["properties"]["section_id"]["enum"] == [
        section_id for section_id, _ in SECTION_HEADINGS
    ]
    assert section["properties"]["status"]["enum"] == ["ACTIVE", "NO_NEWS"]
    assert "minItems" not in section["properties"]["candidates"]
    candidate = section["properties"]["candidates"]["items"]
    for field in ("facts", "claims", "unknowns", "disputed_points"):
        assert candidate["properties"][field]["items"]["maxLength"] == 600
    assert "null" in section["properties"]["selected_candidate_id"]["type"]
    assert section["properties"]["fallback_action"]["enum"] == [
        "RADAR", "DOSSIER_FOLLOW_UP", "PUBLIC_DATA_ANALYSIS", "SKIP", None,
    ]
    assert research["properties"]["sections"]["maxItems"] == len(SECTION_HEADINGS)

    articles = _schema("articles")
    assert set(articles["properties"]) == {"articles"}
    decision = articles["properties"]["articles"]["items"]
    assert articles["properties"]["articles"]["maxItems"] == len(SECTION_HEADINGS)
    assert decision["properties"]["status"]["enum"] == ["ACTIVE", "SKIPPED"]
    assert "null" in decision["properties"]["skip_reason"]["type"]
    assert set(decision["properties"]["repair_skip_reason_code"]["enum"]) == {
        "EVIDENCE_RETRACTED", "CANDIDATE_REMOVED", "SOURCE_INVALIDATED", None,
    }
    assert {"FACT_CHECK", "DOCUMENT_PUBLIC_RECORD", "SECTION_OPENER"}.issubset(
        set(decision["properties"]["story_type"]["enum"])
    )
    leads = decision["properties"]["investigation_data"]["properties"]["leads"]["items"]
    assert leads["properties"]["not_proof_of_wrongdoing"] == {
        "type": "boolean", "const": True
    }


def test_research_schema_avoids_composition_rejected_by_live_codex_api() -> None:
    def check(value):
        if isinstance(value, dict):
            assert "allOf" not in value
            for child in value.values():
                check(child)
        elif isinstance(value, list):
            for child in value:
                check(child)
    check(_schema("research"))
    from dragon.provider_targeting import build_research_targeting
    from dragon.providers import LocalCommandEditorialProvider, ProviderError
    targeting = build_research_targeting("2099-01-02", {"coverage_rules": [{
        "id": "accountability_and_service", "sections": ["investigations", "service"], "minimum_active": 2,
    }]})
    results = [{"target_id": f"HARD:{lane}", "status": "NO_QUALIFYING_CANDIDATE_FOUND",
        "search_intent": "Fixture search", "search_attempts": [{"query": "fixture", "purpose": "fixture search"}],
        "candidate_matches": [], "no_qualifying_reason": "Fixture search found no qualifying candidate."}
        for lane in ("ACCOUNTABILITY", "SERVICE")]
    for invalid_status, invalid_matches, invalid_reason in (
        ("CANDIDATES_PRODUCED", [], None),
        ("NO_QUALIFYING_CANDIDATE_FOUND", [{"candidate_id": "generic"}], "No qualifying candidate."),
        ("NO_QUALIFYING_CANDIDATE_FOUND", [], None),
    ):
        import copy
        invalid = copy.deepcopy(results)
        invalid[1].update(status=invalid_status, candidate_matches=invalid_matches, no_qualifying_reason=invalid_reason)
        try:
            LocalCommandEditorialProvider._validate_hard_target_results(invalid, targeting, {}, {}, {})
        except ProviderError as exc:
            assert exc.code == "HARD_TARGET_DISPOSITION_INVALID"
        else:
            raise AssertionError("unsupported schema composition removal weakened runtime disposition validation")


def test_article_wrapper_is_unwrapped_for_provider_protocol() -> None:
    def runner(command, **kwargs):
        output = Path(command[command.index("--output-last-message") + 1])
        output.write_text(json.dumps({"articles": [{"section_id": "front"}]}), encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "")

    value = _run_codex("articles", {"research": {}}, binary="codex", runner=runner)

    assert value == [{"section_id": "front"}]
