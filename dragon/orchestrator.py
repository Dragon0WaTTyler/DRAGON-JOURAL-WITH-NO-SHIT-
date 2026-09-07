"""Single-owner, checkpoint-aware DRAGON V5 orchestrator."""

from __future__ import annotations

from datetime import date
from pathlib import Path
import traceback
from typing import Iterable

from dragon.incidents import IncidentWriter
from dragon.lock import RunLock
from dragon.recovery import RecoveryEngine
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
        recovery_engine: RecoveryEngine | None = None,
        use_lock: bool = True,
    ):
        self.root = root.resolve()
        self.edition_date = date.fromisoformat(edition_date).isoformat()
        self.timezone = timezone
        self.recovery_engine = recovery_engine
        self.use_lock = use_lock
        self._last_traceback: str | None = None
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
            self.root,
            self.edition_date,
            self.timezone,
            self.stage_names,
            {stage.name: list(stage.prerequisites) for stage in self.definitions},
        )

    def status(self) -> dict:
        if not self.store.path.exists():
            return {
                "schema_version": 5,
                "date": self.edition_date,
                "timezone": self.timezone,
                "run_status": "NO_RUN",
            }
        return self.store.load()

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
        if self.use_lock:
            with RunLock(self.store.run_dir / "run.lock", self.timezone) as lock:
                state = self.store.initialize()
                lock.set_run_id(state["run_id"])
                return self._run_owned(
                    resume=resume,
                    retry_stage=retry_stage,
                    from_stage=from_stage,
                    lock=lock,
                )
        return self._run_owned(
            resume=resume,
            retry_stage=retry_stage,
            from_stage=from_stage,
            lock=None,
        )

    def _run_owned(
        self,
        *,
        resume: bool,
        retry_stage: str | None,
        from_stage: str | None,
        lock: RunLock | None,
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
            if lock:
                lock.heartbeat(stage=definition.name)
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
            while not self._run_stage(state, definition):
                if lock:
                    lock.heartbeat(stage=definition.name)
                if not self._recover(state, definition):
                    return state
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
        self._last_traceback = None
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
            allowed_updates = {
                "publication_status",
                "archive_status",
                "delivery_status",
            }
            state_updates = result.metadata.get("state_updates", {})
            if not isinstance(state_updates, dict) or any(
                key not in allowed_updates for key in state_updates
            ):
                raise StageFailure(
                    "STAGE_STATE_UPDATE_INVALID",
                    f"invalid state updates from {definition.name}",
                )
            for key, value in state_updates.items():
                if value not in {"PENDING", "COMPLETE", "FAILED", "BLOCKED", "DEGRADED"}:
                    raise StageFailure(
                        "STAGE_STATE_UPDATE_INVALID",
                        f"invalid {key} value {value}",
                    )
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
            for key, value in state_updates.items():
                state[key] = value
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
            diagnostic_outputs = exc.outputs
        except Exception as exc:  # stage boundary must persist unexpected defects
            code, detail = "UNHANDLED_STAGE_EXCEPTION", str(exc)
            trace = traceback.format_exc()
            diagnostic_outputs = ()
        self._last_traceback = trace
        outputs: list[str] = []
        hashes: dict[str, str] = {}
        for output in diagnostic_outputs:
            resolved = output.resolve()
            try:
                relative = str(resolved.relative_to(self.root)).replace("\\", "/")
            except ValueError:
                continue
            if resolved.is_file():
                outputs.append(relative)
                hashes[relative] = sha256_file(resolved)
        record.update(
            status="FAILED",
            ended_at=now_iso(self.timezone),
            error_code=code,
            error_detail=detail,
            outputs=outputs,
            artifact_hashes=hashes,
        )
        self._set_outcome_for_stage(state, definition.name, "FAILED")
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

    def _recover(self, state: dict, definition: StageDefinition) -> bool:
        if self.recovery_engine is None:
            return False
        record = state["stages"][definition.name]
        decision = self.recovery_engine.decide(
            str(record["error_code"]), int(record["attempt_count"])
        )
        record["error_category"] = decision.category.value
        recovery = {
            "at": now_iso(self.timezone),
            "action": decision.action,
            "category": decision.category.value,
            "attempt": decision.attempt,
            "max_attempts": decision.max_attempts,
            "delay_seconds": decision.delay_seconds,
            "reason": decision.reason,
        }
        record["recovery_history"].append(recovery)
        self.store.save(state)
        if decision.action == "RETRY":
            self.recovery_engine.wait(decision)
            return True
        if decision.action == "BLOCK":
            record["status"] = "BLOCKED"
            self._set_outcome_for_stage(state, definition.name, "BLOCKED")
            self.store.save(state)
            return False

        writer = IncidentWriter(self.root, self.store.run_dir, self.timezone)
        relevant = [self.root / path for path in record.get("outputs", [])]
        relevant.append(self.store.run_dir / "logs" / f"{definition.name}.jsonl")
        incident = writer.create(
            stage=definition.name,
            state=state,
            error_code=str(record["error_code"]),
            error_detail=str(record["error_detail"]),
            traceback_text=self._last_traceback,
            attempted_fixes=record["recovery_history"],
            relevant_files=relevant,
        )
        relative = str(incident.relative_to(self.root)).replace("\\", "/")
        state.setdefault("incidents", []).append(relative)
        record["incident_path"] = relative
        record["repair_status"] = "REQUIRES_INTERVENTION"
        self.store.save(state)
        return False

    def _block(self, state: dict, name: str, code: str, detail: str) -> None:
        record = state["stages"][name]
        record.update(
            status="BLOCKED",
            ended_at=now_iso(self.timezone),
            error_code=code,
            error_detail=detail,
        )
        self._set_outcome_for_stage(state, name, "BLOCKED")
        self.store.save(state)

    def _set_outcome_for_stage(self, state: dict, name: str, status: str) -> None:
        if name == "github_archive":
            state["archive_status"] = status
        elif name == "whatsapp_delivery":
            state["delivery_status"] = status
        elif "final_qa" not in self.stage_names or self.stage_names.index(name) <= self.stage_names.index("final_qa"):
            state["publication_status"] = status
