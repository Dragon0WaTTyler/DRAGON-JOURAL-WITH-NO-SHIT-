from __future__ import annotations

from pathlib import Path
import json

import pytest

from dragon.orchestrator import Orchestrator
from dragon.pipeline import build_stage_definitions
from dragon.providers import SyntheticEditorialProvider
from dragon.state import sha256_file
from dragon.stages import StageDefinition, StageFailure, StageResult


NAMES = (
    "preflight",
    "research",
    "article_generation",
    "chief_editor",
    "factcheck",
    "arabic_language_qa",
    "cover",
    "publication_source",
    "pdf",
    "epub",
    "final_qa",
    "github_archive",
    "whatsapp_delivery",
)


@pytest.mark.parametrize("injected_stage", NAMES)
def test_failure_at_every_stage_boundary_is_resumable_without_upstream_rework(
    tmp_path: Path, injected_stage: str
) -> None:
    failures = {injected_stage: True}
    calls: list[str] = []

    def stage(name: str, prerequisites: tuple[str, ...]) -> StageDefinition:
        def run(context):
            calls.append(name)
            if failures.get(name):
                raise StageFailure("INJECTED_FAILURE", f"fault at {name}")
            path = context.run_dir / name / "accepted.txt"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"{name}:{context.attempt}", encoding="utf-8")
            updates = {}
            if name == "final_qa":
                updates["publication_status"] = "COMPLETE"
            elif name == "github_archive":
                updates["archive_status"] = "COMPLETE"
            elif name == "whatsapp_delivery":
                updates["delivery_status"] = "COMPLETE"
            return StageResult((path,), metadata={"state_updates": updates})

        return StageDefinition(name, prerequisites, run)

    definitions = []
    for index, name in enumerate(NAMES):
        if name == "epub":
            prerequisites = ("publication_source",)
        elif name in {"github_archive", "whatsapp_delivery"}:
            prerequisites = ("final_qa",)
        elif name == "final_qa":
            prerequisites = ("pdf", "epub")
        else:
            prerequisites = NAMES[index - 1 : index]
        definitions.append(stage(name, tuple(prerequisites)))
    orchestrator = Orchestrator(
        root=tmp_path,
        edition_date="2099-02-01",
        timezone="Africa/Casablanca",
        stages=definitions,
        use_lock=False,
    )
    failed = orchestrator.run()
    assert failed["stages"][injected_stage]["status"] == "FAILED"
    attempts_before = {
        name: record["attempt_count"] for name, record in failed["stages"].items()
    }
    failures[injected_stage] = False
    calls.clear()

    recovered = orchestrator.run(retry_stage=injected_stage)

    assert all(record["status"] == "COMPLETE" for record in recovered["stages"].values())
    injected_index = NAMES.index(injected_stage)
    for name in NAMES[:injected_index]:
        if name not in calls:
            assert recovered["stages"][name]["attempt_count"] == attempts_before[name]


def test_abrupt_process_interrupt_leaves_running_state_and_resume_reuses_upstream(
    tmp_path: Path,
) -> None:
    interrupt = {"enabled": True}

    def accepted(context):
        path = context.run_dir / "first.txt"
        path.write_text("accepted", encoding="utf-8")
        return StageResult((path,))

    def interrupted(context):
        if interrupt["enabled"]:
            raise KeyboardInterrupt("simulated process termination")
        path = context.run_dir / "second.txt"
        path.write_text("resumed", encoding="utf-8")
        return StageResult((path,))

    orchestrator = Orchestrator(
        root=tmp_path,
        edition_date="2099-02-02",
        timezone="Africa/Casablanca",
        stages=[
            StageDefinition("first", (), accepted),
            StageDefinition("second", ("first",), interrupted),
        ],
        use_lock=False,
    )
    with pytest.raises(KeyboardInterrupt):
        orchestrator.run()
    crashed = json.loads(orchestrator.store.path.read_text(encoding="utf-8"))
    assert crashed["stages"]["first"]["status"] == "COMPLETE"
    assert crashed["stages"]["second"]["status"] == "RUNNING"
    first_hash = crashed["stages"]["first"]["artifact_hashes"]

    interrupt["enabled"] = False
    resumed = orchestrator.run(resume=True)

    assert resumed["stages"]["first"]["attempt_count"] == 1
    assert resumed["stages"]["first"]["artifact_hashes"] == first_hash
    assert resumed["stages"]["second"]["attempt_count"] == 2
    assert resumed["stages"]["second"]["status"] == "COMPLETE"
    assert resumed["stages"]["second"]["recovery_history"][0]["action"] == "resume_interrupted_attempt"


def test_corrupt_epub_is_rebuilt_without_touching_valid_pdf_or_editorial(
    tmp_path: Path,
) -> None:
    date_value = "2099-02-03"
    orchestrator = Orchestrator(
        root=tmp_path,
        edition_date=date_value,
        timezone="Africa/Casablanca",
        stages=build_stage_definitions(SyntheticEditorialProvider(), synthetic=True),
        use_lock=False,
    )
    first = orchestrator.run()
    edition = tmp_path / "editions" / "2099" / "02" / date_value
    pdf = edition / f"DRAGON-{date_value}.pdf"
    epub = edition / f"DRAGON-{date_value}.epub"
    pdf_hash = sha256_file(pdf)
    chief_attempts = first["stages"]["chief_editor"]["attempt_count"]
    pdf_attempts = first["stages"]["pdf"]["attempt_count"]
    epub.write_bytes(b"corrupt EPUB fixture")

    recovered = orchestrator.run(retry_stage="epub")

    assert recovered["publication_status"] == "COMPLETE"
    assert recovered["stages"]["chief_editor"]["attempt_count"] == chief_attempts
    assert recovered["stages"]["pdf"]["attempt_count"] == pdf_attempts
    assert recovered["stages"]["epub"]["attempt_count"] == 2
    assert sha256_file(pdf) == pdf_hash
    assert epub.read_bytes().startswith(b"PK")
