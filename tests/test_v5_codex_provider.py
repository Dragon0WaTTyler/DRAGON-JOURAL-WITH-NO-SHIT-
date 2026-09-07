from __future__ import annotations

import json
from pathlib import Path
import subprocess

from scripts.codex_editorial_provider import _probe, _run_codex


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
