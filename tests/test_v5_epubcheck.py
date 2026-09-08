import json
from pathlib import Path
import subprocess

from dragon.epubcheck import epubcheck_version, run_epubcheck


def test_epubcheck_adapter_requires_exact_version_and_parses_json(tmp_path: Path) -> None:
    jar = tmp_path / "epubcheck.jar"
    jar.write_bytes(b"jar")
    epub = tmp_path / "edition.epub"
    epub.write_bytes(b"epub")
    calls = []

    def runner(command, **kwargs):
        calls.append(command)
        if "--version" in command:
            return subprocess.CompletedProcess(command, 0, "EPUBCheck v5.3.0\n", "")
        report_path = Path(command[command.index("--json") + 1])
        report_path.write_text(
            json.dumps({
                "messages": [],
                "checker": {"nFatal": 0, "nError": 0, "nWarning": 0},
            }),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0, "EPUBCheck completed", "")

    environment = {"DRAGON_EPUBCHECK_JAR": str(jar)}
    assert epubcheck_version(tmp_path, runner=runner, environ=environment) == "5.3.0"
    report = run_epubcheck(
        tmp_path,
        epub,
        tmp_path / "report.json",
        runner=runner,
        environ=environment,
    )
    assert report["status"] == "PASS"
    assert report["validator"] == "W3C_EPUBCHECK"
    assert report["jar_sha256"]
    assert len(calls) == 3
