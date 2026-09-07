"""Configuration loading for the V5 local runtime."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_mapping(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"CONFIG_INVALID: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"CONFIG_INVALID: {path} must contain a mapping")
    return value


def load_local_config(root: Path) -> dict[str, Any]:
    config = load_mapping(root / "config" / "local-automation.yaml")
    if config.get("version") != 5:
        raise ValueError("CONFIG_VERSION_UNSUPPORTED: local automation must be Version 5")
    stages = config.get("orchestrator", {}).get("stages")
    if not isinstance(stages, list) or not stages or len(stages) != len(set(stages)):
        raise ValueError("CONFIG_STAGES_INVALID: stages must be a non-empty unique list")
    return config
