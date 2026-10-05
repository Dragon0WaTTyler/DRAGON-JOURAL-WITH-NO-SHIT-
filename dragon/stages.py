"""Durable stage interface used by the local orchestrator."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Mapping


@dataclass(frozen=True)
class StageContext:
    root: Path
    edition_date: str
    run_dir: Path
    edition_dir: Path
    attempt: int


@dataclass(frozen=True)
class StageResult:
    outputs: tuple[Path, ...] = ()
    status: str = "COMPLETE"
    metadata: Mapping[str, object] = field(default_factory=dict)
    inputs: tuple[Path, ...] = ()


StageRunner = Callable[[StageContext], StageResult]
StageValidator = Callable[[StageContext, StageResult], list[str]]


def validate_declared_outputs(context: StageContext, result: StageResult) -> list[str]:
    issues: list[str] = []
    for output in result.outputs:
        resolved = output.resolve()
        try:
            resolved.relative_to(context.root.resolve())
        except ValueError:
            issues.append(f"OUTPUT_OUTSIDE_REPOSITORY:{output}")
            continue
        if not resolved.is_file():
            issues.append(f"OUTPUT_MISSING:{output}")
        elif resolved.stat().st_size == 0:
            issues.append(f"OUTPUT_EMPTY:{output}")
    return issues


@dataclass(frozen=True)
class StageDefinition:
    name: str
    prerequisites: tuple[str, ...]
    runner: StageRunner
    validator: StageValidator = validate_declared_outputs


class StageFailure(RuntimeError):
    def __init__(self, code: str, detail: str, *, outputs: tuple[Path, ...] = ()):
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.outputs = outputs


def unavailable_stage(name: str) -> StageDefinition:
    def run(_: StageContext) -> StageResult:
        raise StageFailure(
            "STAGE_NOT_IMPLEMENTED",
            f"{name} has no configured V5 implementation yet",
        )

    return StageDefinition(name=name, prerequisites=(), runner=run)
