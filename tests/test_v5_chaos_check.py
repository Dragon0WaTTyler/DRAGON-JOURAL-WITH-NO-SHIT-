from __future__ import annotations

import subprocess

import dragon_chaos_check


def test_chaos_check_persists_hash_bound_machine_evidence(tmp_path, monkeypatch) -> None:
    config = tmp_path / "config" / "local-automation.yaml"
    config.parent.mkdir(parents=True)
    config.write_text(
        "version: 5\ntimezone: Africa/Casablanca\norchestrator:\n  stages: [preflight]\n",
        encoding="utf-8",
    )

    def runner(command, **kwargs):
        target = next(item.split("=", 1)[1] for item in command if item.startswith("--junitxml="))
        cases = "".join(
            f'<testcase classname="chaos" name="{marker}" />'
            for marker in dragon_chaos_check.SCENARIO_MARKERS.values()
        )
        from pathlib import Path

        Path(target).write_text(f'<testsuite tests="8">{cases}</testsuite>', encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "8 passed", "")

    monkeypatch.setattr(dragon_chaos_check, "source_revision", lambda root: "abc123")
    receipt = dragon_chaos_check.run_check(tmp_path, runner)

    assert receipt["status"] == "PASS"
    assert receipt["human_review_status"] == "NOT_REVIEWED"
    assert all(value == "PASS" for value in receipt["scenarios"].values())
    assert (tmp_path / receipt["junit"]["path"]).is_file()
    assert (tmp_path / "acceptance" / "machine" / "failure-injection" / "receipt.json").is_file()
