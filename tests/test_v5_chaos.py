from __future__ import annotations

from pathlib import Path

import pytest

from dragon.orchestrator import Orchestrator
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
