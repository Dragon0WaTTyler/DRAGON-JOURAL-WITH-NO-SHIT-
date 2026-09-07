"""Single-owner, checkpoint-aware DRAGON V5 orchestrator."""

from __future__ import annotations

from datetime import date
from pathlib import Path
import traceback
from typing import Iterable

from dragon.runlog import StageLogger
from dragon.stages import StageContext, StageDefinition, StageFailure, StageResult
from dragon.state import StateStore, now_iso, sha256_file


class Orchestrator:
    def __init__(
        self,
        *,
        root: Path,
        edition_date: str,
        timezone: str,
        stages: Iterable[StageDefinition],
    ):
        self.root = root.resolve()
        self.edition_date = date.fromisoformat(edition_date).isoformat()
        self.timezone = timezone
        self.definitions = list(stages)
        self.stage_names = [stage.name for stage in self.definitions]
        if not self.stage_names or len(self.stage_names) != len(set(self.stage_names)):
            raise ValueError("STAGE_REGISTRY_INVALID")
        known: set[str] = set()
        for stage in self.definitions:
            if any(item not in known for item in stage.prerequisites):
                raise ValueError(f"STAGE_PREREQUISITE_INVALID:{stage.name}")
            known.add(stage.name)
        self.store = StateStore(
            self.root, self.edition_date, self.timezone, self.stage_names
        )

    def status(self) -> dict:
        return self.store.initialize()

    def invalidate_from(self, stage_name: str, *, reason: str) -> dict:
        if stage_name not in self.stage_names:
            raise ValueError(f"STAGE_UNKNOWN:{stage_name}")
        state = self.store.initialize()
        start = self.stage_names.index(stage_name)
        for name in self.stage_names[start:]:
            record = state["stages"][name]
            prior = record["status"]
            if prior != "PENDING":
                record["recovery_history"].append(
                    {"at": now_iso(self.timezone), "action": reason, "prior_status": prior}
                )
            record.update(
                status="PENDING",
                started_at=None,
                ended_at=None,
                error_code=None,
                error_detail=None,
                artifact_hashes={},
                outputs=[],
            )
        checkpoints = [
            name
            for name in self.stage_names[:start]
            if state["stages"][name]["status"] == "COMPLETE"
        ]
        state["last_successful_checkpoint"] = checkpoints[-1] if checkpoints else None
        self.store.save(state)
        return state

    def run(
        self,
        *,
        resume: bool = False,
        retry_stage: str | None = None,
        from_stage: str | None = None,
    ) -> dict:
        if retry_stage and from_stage:
            raise ValueError("COMMAND_CONFLICT: --retry and --from are mutually exclusive")
        if retry_stage:
            self.invalidate_from(retry_stage, reason="targeted_retry")
        elif from_stage:
            self.invalidate_from(from_stage, reason="explicit_from")
        state = self.store.initialize()
        start_at = retry_stage or from_stage

        for definition in self.definitions:
            record = state["stages"][definition.name]
            if start_at and self.stage_names.index(definition.name) < self.stage_names.index(start_at):
                continue
            if record["status"] == "COMPLETE":
                if self.store.verify_checkpoint(record):
                    continue
                # A changed upstream artifact invalidates every dependent
                # checkpoint, even when those downstream bytes still exist.
                state = self.invalidate_from(
                    definition.name, reason="checkpoint_invalidated"
                )
                record = state["stages"][definition.name]
            elif resume and record["status"] == "RUNNING":
                record["recovery_history"].append(
                    {
                        "at": now_iso(self.timezone),
                        "action": "resume_interrupted_attempt",
                        "prior_status": "RUNNING",
                    }
                )
                record["status"] = "PENDING"
                self.store.save(state)

            missing = [
                name
                for name in definition.prerequisites
                if state["stages"][name]["status"] != "COMPLETE"
            ]
            if missing:
                self._block(state, definition.name, "PREREQUISITE_INCOMPLETE", ", ".join(missing))
                break
            if record["status"] in {"FAILED", "BLOCKED"} and not (resume or start_at):
                break
            if record["status"] == "DEGRADED":
                continue
            if not self._run_stage(state, definition):
                break
        return state

    def _context(self, name: str, attempt: int) -> StageContext:
        parsed = date.fromisoformat(self.edition_date)
        return StageContext(
            root=self.root,
            edition_date=self.edition_date,
            run_dir=self.store.run_dir,
            edition_dir=self.root
            / "editions"
            / f"{parsed:%Y}"
            / f"{parsed:%m}"
            / self.edition_date,
            attempt=attempt,
        )

    def _run_stage(self, state: dict, definition: StageDefinition) -> bool:
        record = state["stages"][definition.name]
        record["attempt_count"] += 1
        record.update(
            status="RUNNING",
            started_at=now_iso(self.timezone),
            ended_at=None,
            error_code=None,
            error_detail=None,
        )
        self.store.save(state)
        logger = StageLogger(
            self.store.run_dir / "logs" / f"{definition.name}.jsonl", self.timezone
        )
        logger.write("stage_started", stage=definition.name, attempt=record["attempt_count"])
        context = self._context(definition.name, record["attempt_count"])
        try:
            result = definition.runner(context)
            if result.status not in {"COMPLETE", "DEGRADED"}:
                raise StageFailure("STAGE_RESULT_INVALID", f"unsupported result {result.status}")
            issues = definition.validator(context, result)
            if issues:
                raise StageFailure("STAGE_ACCEPTANCE_FAILED", "; ".join(issues))
            outputs: list[str] = []
            hashes: dict[str, str] = {}
            for output in result.outputs:
                resolved = output.resolve()
                relative = str(resolved.relative_to(self.root)).replace("\\", "/")
                outputs.append(relative)
                hashes[relative] = sha256_file(resolved)
            record.update(
                status=result.status,
                ended_at=now_iso(self.timezone),
                outputs=outputs,
                artifact_hashes=hashes,
                error_code=None,
                error_detail=None,
            )
            if result.status == "COMPLETE":
                state["last_successful_checkpoint"] = definition.name
            state["output_paths"].update({definition.name: outputs})
            state["hashes"].update(hashes)
            self.store.save(state)
            logger.write(
                "stage_completed",
                stage=definition.name,
                attempt=record["attempt_count"],
                status=result.status,
                outputs=outputs,
            )
            return True
        except StageFailure as exc:
            code, detail = exc.code, exc.detail
            trace = None
        except Exception as exc:  # stage boundary must persist unexpected defects
            code, detail = "UNHANDLED_STAGE_EXCEPTION", str(exc)
            trace = traceback.format_exc()
        record.update(
            status="FAILED",
            ended_at=now_iso(self.timezone),
            error_code=code,
            error_detail=detail,
        )
        failure = {
            "at": record["ended_at"],
            "stage": definition.name,
            "attempt": record["attempt_count"],
            "error_code": code,
            "error_detail": detail,
        }
        state["failure_history"].append(failure)
        self.store.save(state)
        logger.write("stage_failed", **failure, traceback=trace)
        return False

    def _block(self, state: dict, name: str, code: str, detail: str) -> None:
        record = state["stages"][name]
        record.update(
            status="BLOCKED",
            ended_at=now_iso(self.timezone),
            error_code=code,
            error_detail=detail,
        )
        self.store.save(state)
