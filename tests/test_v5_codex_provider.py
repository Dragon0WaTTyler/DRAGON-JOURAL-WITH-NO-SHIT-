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
            }
        },
    )
    assert "minimum_active_article_words" in prompt
    assert "minimum_edition_words" in prompt
    assert "تحرير: اسم القلم" in prompt
    assert "تحرير: DRAGON" not in prompt
    assert "original Arabic synthesis" in prompt
    assert "never reproduce a full copyrighted article" in prompt


def test_structured_output_schemas_are_strict_and_complete() -> None:
    assert SECTION_HEADINGS == RUNTIME_SECTION_HEADINGS
    for operation in ("research", "articles"):
        schema = _schema(operation)
        assert schema["type"] == "object"
        for object_schema in _object_schemas(schema):
            assert object_schema["additionalProperties"] is False
            assert set(object_schema["required"]) == set(object_schema["properties"])

    research = _schema("research")
    source = research["properties"]["sources"]["items"]
    assert set(source["properties"]) == {
        "id", "url", "publisher", "publication_date", "accessed_at", "source_type",
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
    assert {"FACT_CHECK", "DOCUMENT_PUBLIC_RECORD", "SECTION_OPENER"}.issubset(
        set(decision["properties"]["story_type"]["enum"])
    )


def test_article_wrapper_is_unwrapped_for_provider_protocol() -> None:
    def runner(command, **kwargs):
        output = Path(command[command.index("--output-last-message") + 1])
        output.write_text(json.dumps({"articles": [{"section_id": "front"}]}), encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "")

    value = _run_codex("articles", {"research": {}}, binary="codex", runner=runner)

    assert value == [{"section_id": "front"}]
