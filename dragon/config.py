"""Configuration loading for the V5 local runtime."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from dragon.providers import configured_byline


def load_mapping(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"CONFIG_INVALID: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"CONFIG_INVALID: {path} must contain a mapping")
    return value


def _editorial_readiness(root: Path) -> dict[str, Any]:
    """Derive provider preflight requirements from the inherited newspaper plan."""
    architecture = load_mapping(root / "config" / "edition-architecture.yaml")
    edition = architecture.get("edition")
    coverage = architecture.get("coverage_rules")
    if not isinstance(edition, dict) or not isinstance(coverage, list):
        raise ValueError("EDITORIAL_READINESS_CONFIG_INVALID")
    try:
        minimum_active_sections = int(edition["lead_articles"][0]) + int(
            edition["secondary_articles"][0]
        )
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise ValueError("EDITORIAL_READINESS_CONFIG_INVALID") from exc
    rules = []
    for rule in coverage:
        if (
            not isinstance(rule, dict)
            or not isinstance(rule.get("id"), str)
            or not isinstance(rule.get("sections"), list)
            or not all(isinstance(section, str) for section in rule["sections"])
        ):
            raise ValueError("EDITORIAL_READINESS_CONFIG_INVALID")
        try:
            minimum = int(rule["minimum_active"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("EDITORIAL_READINESS_CONFIG_INVALID") from exc
        if minimum < 1:
            raise ValueError("EDITORIAL_READINESS_CONFIG_INVALID")
        rules.append(
            {
                "id": rule["id"],
                "sections": list(rule["sections"]),
                "minimum_active": minimum,
            }
        )
    if minimum_active_sections < 1:
        raise ValueError("EDITORIAL_READINESS_CONFIG_INVALID")
    return {
        "minimum_active_sections": minimum_active_sections,
        "coverage_rules": rules,
    }


def load_local_config(root: Path) -> dict[str, Any]:
    config = load_mapping(root / "config" / "local-automation.yaml")
    if config.get("version") != 5:
        raise ValueError("CONFIG_VERSION_UNSUPPORTED: local automation must be Version 5")
    stages = config.get("orchestrator", {}).get("stages")
    if not isinstance(stages, list) or not stages or len(stages) != len(set(stages)):
        raise ValueError("CONFIG_STAGES_INVALID: stages must be a non-empty unique list")
    configured_byline(config)
    config["editorial_readiness"] = _editorial_readiness(root)
    return config
