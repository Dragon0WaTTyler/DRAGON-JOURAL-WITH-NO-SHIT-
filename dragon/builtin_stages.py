"""Built-in deterministic V5 stage definitions."""

from __future__ import annotations

from dragon.preflight import run_preflight
from dragon.stages import StageContext, StageDefinition, StageFailure, StageResult
from dragon.state import atomic_write_json


def preflight_stage() -> StageDefinition:
    def run(context: StageContext) -> StageResult:
        report = run_preflight(context.root, context.edition_date)
        path = context.run_dir / "preflight.json"
        atomic_write_json(path, report)
        if report["status"] != "PASS":
            names = [item["name"] for item in report["blocking_failures"]]
            raise StageFailure(
                "PREFLIGHT_FAILED",
                "blocking checks failed: " + ", ".join(names),
                outputs=(path,),
            )
        return StageResult(outputs=(path,))

    return StageDefinition(name="preflight", prerequisites=(), runner=run)
