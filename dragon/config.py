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


def _editorial_word_budget(root: Path) -> dict[str, Any]:
    """Read the established generation range without duplicating it in prompts."""
    path = root / "config" / "editorial-depth.yaml"
    if not path.is_file():
        return {}
    depth = load_mapping(path)
    edition = depth.get("edition")
    if not isinstance(edition, dict):
        raise ValueError("EDITORIAL_WORD_BUDGET_CONFIG_INVALID")
    try:
        floor = int(edition["hard_min_words"])
        low_text, high_text = str(edition["target_words"]).split("-", 1)
        target, maximum = int(low_text.strip()), int(high_text.strip())
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("EDITORIAL_WORD_BUDGET_CONFIG_INVALID") from exc
    if floor < 1 or target < floor or maximum < target:
        raise ValueError("EDITORIAL_WORD_BUDGET_CONFIG_INVALID")
    roles = depth.get("v5_article_roles")
    if not isinstance(roles, dict) or set(roles) != {"LEAD", "STANDARD", "INVESTIGATION"}:
        raise ValueError("EDITORIAL_WORD_BUDGET_CONFIG_INVALID")
    role_targets: dict[str, dict[str, int]] = {}
    for role, values in roles.items():
        if not isinstance(values, dict):
            raise ValueError("EDITORIAL_WORD_BUDGET_CONFIG_INVALID")
        try:
            target_words = int(values["target_words"])
            maximum_words = int(values["maximum_words"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("EDITORIAL_WORD_BUDGET_CONFIG_INVALID") from exc
        if target_words < 350 or maximum_words < target_words:
            raise ValueError("EDITORIAL_WORD_BUDGET_CONFIG_INVALID")
        role_targets[role] = {
            "target_words": target_words,
            "maximum_words": maximum_words,
        }
    return {
        "acceptance_floor_words": floor,
        "generation_target_edition_words": target,
        "generation_maximum_edition_words": maximum,
        "role_quality_targets": role_targets,
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
    config["editorial_word_budget"] = _editorial_word_budget(root)
    return config
