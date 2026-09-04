#!/usr/bin/env python3
"""Validate DRAGON configuration and tested Scheduled Work contracts."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]

EXPECTED_ROLES = {
    "chief-editor", "morocco", "meknes", "palestine", "world", "ai",
    "science", "history", "literature-culture", "investigations",
    "fact-check", "darija-editor", "publishing",
}
EXPECTED_JOBS = [
    ("current-news-desk", 1, "07:45"),
    ("deep-features-desk", 2, "08:00"),
    ("chief-editor", 3, "08:50"),
    ("cover-director", 4, "09:25"),
    ("publication-builder", 5, "09:55"),
]
ARABIC_RANGES = (
    "U+0600-U+06FF", "U+0750-U+077F", "U+08A0-U+08FF",
    "U+FB50-U+FDFF", "U+FE70-U+FEFF",
)


def load_yaml(path: Path) -> dict:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a mapping")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--allow-enabled", action="store_true")
    args = parser.parse_args()
    errors: list[str] = []

    try:
        roles = load_yaml(ROOT / "config/roles.yaml")
        schedule = load_yaml(ROOT / "config/schedule.yaml")
        workflow = load_yaml(ROOT / "config/scheduled-workflow.yaml")
        constraints = load_yaml(ROOT / "config/execution-constraints.yaml")
        depth = load_yaml(ROOT / "config/editorial-depth.yaml")
        quality = load_yaml(ROOT / "config/quality-gates.yaml")
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"CONFIGURATION FAIL: {exc}")
        return 1

    role_list = roles.get("roles")
    role_ids = {item.get("id") for item in role_list} if isinstance(role_list, list) else set()
    if len(role_list or []) != 13 or role_ids != EXPECTED_ROLES:
        errors.append("role registry must contain exactly the authoritative 13 roles")
    if roles.get("language") != "darija-latin":
        errors.append("role registry language must be darija-latin")

    if not args.allow_enabled and schedule.get("enabled") is not False:
        errors.append("config/schedule.yaml must remain disabled")
    if schedule.get("timezone") != "Africa/Casablanca":
        errors.append("config/schedule.yaml timezone must remain Africa/Casablanca")
    if workflow.get("enabled") is not False:
        errors.append("scheduled-workflow contract must not itself enable scheduling")
    if workflow.get("timezone") != "Africa/Casablanca":
        errors.append("scheduled-workflow timezone must be Africa/Casablanca")

    jobs = workflow.get("jobs")
    actual_jobs = [(j.get("id"), j.get("task_number"), j.get("local_time")) for j in jobs or []]
    if actual_jobs != EXPECTED_JOBS:
        errors.append(f"scheduled-workflow must define exactly the five tested super-jobs: {EXPECTED_JOBS}")
    if any(j.get("timezone") != "Africa/Casablanca" for j in jobs or []):
        errors.append("all Scheduled Work jobs must use Africa/Casablanca")
    if len(role_list or []) != 13:
        errors.append("five super-jobs must not reduce the 13 editorial roles")

    production = constraints.get("production", {})
    if constraints.get("subscription") != "chatgpt-plus":
        errors.append("execution constraints must target ChatGPT Plus")
    for key in (
        "openai_api_allowed", "openai_api_key_required", "pay_as_you_go_openai_allowed",
        "github_actions_openai_api_allowed",
        "external_paid_compute_allowed", "self_hosted_runner_required", "local_pc_required",
    ):
        if production.get(key) is not False:
            errors.append(f"execution constraint {key} must be false")
    if production.get("scheduled_execution_environment") != "chatgpt-scheduled-work":
        errors.append("scheduled execution environment must be chatgpt-scheduled-work")
    if production.get("scheduled_repository_executable_runtime") != "NOT_AVAILABLE":
        errors.append("tested Scheduled Work repository runtime limitation must be NOT_AVAILABLE")

    capabilities = workflow.get("connector_capabilities", {})
    expected_caps = {
        "github_scheduled_text_read": "PASS",
        "github_scheduled_utf8_text_write": "PASS",
        "github_scheduled_text_read_back": "PASS",
        "github_binary_image_write": "UNSUPPORTED",
        "pdf_binary_write": "UNSUPPORTED",
        "epub_binary_write": "UNSUPPORTED",
        "scheduled_repository_executable_runtime": "NOT_AVAILABLE",
        "scheduled_image_generation": "PASS",
    }
    for key, value in expected_caps.items():
        if capabilities.get(key) != value:
            errors.append(f"connector capability {key} must be {value}")

    chief = next((j for j in jobs or [] if j.get("task_number") == 3), {})
    chief_text = yaml.safe_dump(chief, sort_keys=False)
    chief_responsibilities = [str(x) for x in chief.get("responsibilities", [])]
    for unicode_range in ARABIC_RANGES:
        if unicode_range not in chief_text:
            errors.append(f"Task 3 must scan Arabic range {unicode_range}")
    if "arabic_script_count == 0" not in chief_text:
        errors.append("Task 3 must have the zero Arabic-script hard gate")
    if not any("repeat the repair loop" in x and "exactly zero" in x for x in chief_responsibilities):
        errors.append("Task 3 must require same-run repair/rescan")

    builder = next((j for j in jobs or [] if j.get("id") == "publication-builder"), {})
    if builder.get("id") != "publication-builder" or builder.get("label") != "PUBLICATION BUILDER":
        errors.append("Task 5 must be PUBLICATION BUILDER")
    if builder.get("mode") != "TEXT_ONLY":
        errors.append("Task 5 must be text-only")
    output_paths = {item.get("path") for item in builder.get("outputs", []) if isinstance(item, dict)}
    required_sources = {
        "editions/YYYY/MM/YYYY-MM-DD/edition.html",
        "editions/YYYY/MM/YYYY-MM-DD/print.css",
        "editions/YYYY/MM/YYYY-MM-DD/epub-content.xhtml",
        "daily-runs/YYYY-MM-DD/publishing-report.json",
        "editions/YYYY/MM/YYYY-MM-DD/manifest.json",
    }
    if output_paths != required_sources:
        errors.append("Task 5 outputs must be exactly the tested publication-source package")
    builder_text = yaml.safe_dump(builder, sort_keys=False).lower()
    if "edition.pdf" in builder_text or "edition.epub" in builder_text:
        errors.append("Task 5 must not require Scheduled Work PDF/EPUB binary generation")
    set_binary = builder.get("completion", {}).get("set_binary_state", {})
    if set_binary.get("pdf_binary") != "NOT_GENERATED_NO_RUNTIME":
        errors.append("Task 5 COMPLETE must leave pdf_binary NOT_GENERATED_NO_RUNTIME")
    if set_binary.get("epub_binary") != "NOT_GENERATED_NO_RUNTIME":
        errors.append("Task 5 COMPLETE must leave epub_binary NOT_GENERATED_NO_RUNTIME")
    if set_binary.get("binary_artifacts") != "PENDING_AUTOMATIC_RENDER":
        errors.append("Task 5 COMPLETE must hand binaries to manual Codex rendering")
    if set_binary.get("ready_for_codex_rendering") is not True:
        errors.append("Task 5 COMPLETE must set ready_for_codex_rendering true")

    cover = next((j for j in jobs or [] if j.get("id") == "cover-director"), {})
    cover_responsibilities = [str(x) for x in cover.get("responsibilities", [])]
    if workflow.get("tested_capabilities", {}).get("task_4_cover_director", {}).get("retry_limit") != 1:
        errors.append("Cover Director retry limit must be exactly one")
    if not any("at most two secondary teasers" in x for x in cover_responsibilities):
        errors.append("Cover Director must cap secondary teasers at two")
    if production.get("github_actions_external_compute_allowed") is not True:
        errors.append("automatic binary rendering requires scoped GitHub Actions authorization")
    if production.get("github_actions_scope") != "deterministic publication rendering, validation, persistence only":
        errors.append("GitHub Actions authorization must remain binary-only")
    if cover.get("prerequisites", {}).get("all") != ["editorial == COMPLETE"]:
        errors.append("cover must not depend on downstream publishing")
    if builder.get("prerequisites", {}).get("all") != ["editorial == COMPLETE", "cover == COMPLETE"]:
        errors.append("publishing requires editorial and cover")

    status = workflow.get("daily_status", {})
    required_binary = {"pdf_binary", "epub_binary", "binary_artifacts", "cover_binary_archive"}
    if set(status.get("required_binary_state_fields", [])) != required_binary:
        errors.append("daily status contract must require explicit binary-state fields")
    if "final_publication_status COMPLETE" not in status.get("overall_completion_rule", ""):
        errors.append("overall COMPLETE must require final binary publication")

    language_required = quality.get("gates", {}).get("language", {}).get("required", [])
    if "deterministic_arabic_scan_repair_rescan" not in language_required:
        errors.append("quality gates must include deterministic Arabic scan/repair/rescan")
    if "scheduled_publication_source" not in quality.get("gates", {}):
        errors.append("quality gates must include scheduled_publication_source")
    if "manual_binary_render" not in quality.get("gates", {}):
        errors.append("quality gates must separate manual binary rendering")

    expected_depth = {
        "edition": 4000, "history": 800, "literature_culture": 800,
        "morocco": 700, "palestine": 500, "meknes": 300, "science": 500,
    }
    for key, minimum in expected_depth.items():
        if depth.get(key, {}).get("hard_min_words") != minimum:
            errors.append(f"editorial depth {key}.hard_min_words must remain {minimum}")
        target = depth.get(key, {}).get("target_words")
        if not isinstance(target, str) or not re.fullmatch(r"\d+\s*-\s*\d+", target):
            errors.append(f"editorial depth {key}.target_words must remain a numeric range")

    if errors:
        print("CONFIGURATION FAIL")
        print("\n".join(errors))
        return 1
    print("CONFIGURATION PASS: 13 roles, five tested super-jobs, schedule disabled, text-only publication source semantics")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
