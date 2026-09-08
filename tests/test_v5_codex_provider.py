from __future__ import annotations

import json
from pathlib import Path
import subprocess

from scripts.codex_editorial_provider import SECTION_HEADINGS, _probe, _run_codex, _schema


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
    assert command[command.index("--sandbox") + 1] == "read-only"
    assert command[command.index("--ask-for-approval") + 1] == "never"
    assert "--output-schema" in command
    assert "untrusted data" in kwargs["input"]


def test_structured_output_schemas_are_strict_and_complete() -> None:
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
        "claim_supported",
    }
    section = research["properties"]["sections"]["items"]
    assert section["properties"]["section_id"]["enum"] == [
        section_id for section_id, _ in SECTION_HEADINGS
    ]
    assert section["properties"]["candidates"]["minItems"] == 2
    assert research["properties"]["sections"]["maxItems"] == len(SECTION_HEADINGS)

    articles = _schema("articles")
    assert set(articles["properties"]) == {"articles"}
    decision = articles["properties"]["articles"]["items"]
    assert articles["properties"]["articles"]["maxItems"] == len(SECTION_HEADINGS)
    assert decision["properties"]["status"]["enum"] == ["ACTIVE", "SKIPPED"]
    assert "null" in decision["properties"]["skip_reason"]["type"]


def test_article_wrapper_is_unwrapped_for_provider_protocol() -> None:
    def runner(command, **kwargs):
        output = Path(command[command.index("--output-last-message") + 1])
        output.write_text(json.dumps({"articles": [{"section_id": "front"}]}), encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "")

    value = _run_codex("articles", {"research": {}}, binary="codex", runner=runner)

    assert value == [{"section_id": "front"}]
