"""Narrow provider boundary for optional unattended code repair."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RepairRequest:
    incident_path: Path
    source_revision: str
    failed_stage: str
    error_code: str


@dataclass(frozen=True)
class RepairResult:
    status: str
    detail: str
    patch_path: Path | None = None


class RepairAgent(ABC):
    @property
    @abstractmethod
    def available(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def repair(self, request: RepairRequest) -> RepairResult:
        raise NotImplementedError


class UnavailableRepairAgent(RepairAgent):
    def __init__(self, reason: str = "no tested unattended local repair provider"):
        self.reason = reason

    @property
    def available(self) -> bool:
        return False

    def repair(self, request: RepairRequest) -> RepairResult:
        return RepairResult("REQUIRES_INTERVENTION", self.reason)


def repair_agent_from_config(config: dict[str, Any]) -> RepairAgent:
    provider = config.get("providers", {}).get("repair", {})
    provider_type = provider.get("type", "unconfigured")
    proven = provider.get("integration_test_status") == "PASS"
    if provider_type == "unconfigured" or not proven:
        return UnavailableRepairAgent()
    # No executable provider is shipped or assumed. Adding one requires its own
    # isolated-worktree, rollback and end-to-end acceptance implementation.
    return UnavailableRepairAgent(f"repair provider {provider_type!r} is not implemented")
