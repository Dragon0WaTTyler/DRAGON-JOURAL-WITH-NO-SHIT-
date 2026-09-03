#!/usr/bin/env python3
"""Validate the declarative role, pipeline, and Cloud safety contracts."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_ROLES = {
    "chief-editor", "morocco", "meknes", "palestine", "world", "ai",
    "science", "history", "literature-culture", "investigations",
    "fact-check", "darija-editor", "publishing",
}
RESEARCH_ROLES = {
    "morocco", "meknes", "palestine", "world", "ai", "science",
    "history", "literature-culture", "investigations",
}
EXPECTED_STAGES = ["research", "synthesis", "fact-check", "darija-qa", "publishing", "archive"]


def load_yaml(path: Path) -> dict:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a mapping")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--allow-enabled",
        action="store_true",
        help="allow schedule.yaml to be enabled (only for a reviewed production configuration)",
    )
    args = parser.parse_args()
    errors: list[str] = []

    try:
        roles_config = load_yaml(ROOT / "config/roles.yaml")
        permissions = load_yaml(ROOT / "config/permissions.yaml")
        pipeline = load_yaml(ROOT / "config/pipeline.yaml")
        constraints = load_yaml(ROOT / "config/execution-constraints.yaml")
        depth = load_yaml(ROOT / "config/editorial-depth.yaml")
        quality_gates = load_yaml(ROOT / "config/quality-gates.yaml")
        editorial = load_yaml(ROOT / "config/editorial.yaml")
        schedule = load_yaml(ROOT / "config/schedule.yaml")
        scheduled_workflow = load_yaml(ROOT / "config/scheduled-workflow.yaml")
        output_schema = json.loads((ROOT / "config/output-schema.json").read_text(encoding="utf-8"))
        investigation_schema = json.loads((ROOT / "config/investigation-schema.json").read_text(encoding="utf-8"))
        manifest_schema = json.loads((ROOT / "config/edition-manifest-schema.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError, yaml.YAMLError) as exc:
        print(f"CONFIGURATION FAIL: {exc}")
        return 1

    roles = roles_config.get("roles")
    role_ids = {role.get("id") for role in roles} if isinstance(roles, list) else set()
    if role_ids != EXPECTED_ROLES:
        errors.append(f"role registry mismatch: {sorted(role_ids)}")
    if roles_config.get("language") != "darija-latin":
        errors.append("role registry language must be darija-latin")

    chief = next((role for role in roles if role.get("id") == "chief-editor"), None) if isinstance(roles, list) else None
    if not chief or set(chief.get("can_spawn", [])) != RESEARCH_ROLES:
        errors.append("chief-editor must spawn exactly the nine research roles")
    for role in roles or []:
        if role.get("id") != "chief-editor" and role.get("can_spawn", []) not in ([], None):
            errors.append(f"non-chief role {role.get('id')} must not spawn roles")

    if set(permissions) - {"default", *EXPECTED_ROLES}:
        errors.append("permissions contains an unknown role")
    if permissions.get("default", {}).get("execution") != "cloud-only":
        errors.append("default execution must be cloud-only")
    if permissions.get("default", {}).get("external_writes") != "github-push-after-gates":
        errors.append("external writes must be github-push-after-gates")

    stages = pipeline.get("stages")
    stage_ids = [stage.get("id") for stage in stages] if isinstance(stages, list) else []
    if stage_ids != EXPECTED_STAGES:
        errors.append(f"pipeline stage order must be {EXPECTED_STAGES}")
    if pipeline.get("execution") != "hosted-codex-cloud":
        errors.append("pipeline execution must be hosted-codex-cloud")
    if pipeline.get("source_of_truth") != "github-origin-main":
        errors.append("pipeline source_of_truth must be github-origin-main")
    if "remote-sha-match" not in (stages[-1].get("required_checks", []) if stages else []):
        errors.append("archive stage must require remote-sha-match")
    if pipeline.get("failure_policy", {}).get("force_push") != "forbidden":
        errors.append("force pushes must be forbidden")

    production = constraints.get("production", {})
    if constraints.get("subscription") != "chatgpt-plus":
        errors.append("execution constraints must target the existing ChatGPT Plus subscription")
    for key in (
        "openai_api_allowed", "openai_api_key_required", "pay_as_you_go_openai_allowed",
        "github_actions_openai_api_allowed", "external_paid_compute_allowed",
        "self_hosted_runner_required", "local_pc_required",
    ):
        if production.get(key) is not False:
            errors.append(f"execution constraint {key} must be false")
    if production.get("execution_environment") != "hosted-codex-cloud":
        errors.append("production execution environment must be hosted-codex-cloud")
    if constraints.get("scheduling", {}).get("until_native_recurring_cloud_scheduler") != "manual-cloud-run-only":
        errors.append("schedule fallback must remain manual-cloud-run-only")

    expected_depth = {
        "edition": 4000,
        "history": 800,
        "literature_culture": 800,
        "morocco": 700,
        "palestine": 500,
        "meknes": 300,
        "science": 500,
    }
    for key, minimum in expected_depth.items():
        if depth.get(key, {}).get("hard_min_words") != minimum:
            errors.append(f"editorial depth {key}.hard_min_words must be {minimum}")
        target = depth.get(key, {}).get("target_words")
        if not isinstance(target, str) or not re.fullmatch(r"\d+\s*-\s*\d+", target):
            errors.append(f"editorial depth {key}.target_words must be a numeric range")
    if depth.get("investigations", {}).get("publication_min_words") != 600:
        errors.append("editorial depth investigations.publication_min_words must be 600")
    if depth.get("meknes", {}).get("allow_thin_news_exception") is not True:
        errors.append("editorial depth must allow the documented Meknes thin-news exception")
    if depth.get("investigations", {}).get("allow_dossier_update_without_publication") is not True:
        errors.append("editorial depth must allow explicit non-publication dossier updates")
    if "depth" not in quality_gates.get("gates", {}) or "editorial_quality_report" not in quality_gates.get("gates", {}):
        errors.append("quality gates must include depth and editorial_quality_report gates")
    if "workflow_state" not in quality_gates.get("gates", {}):
        errors.append("quality gates must include the workflow_state gate")
    state_contract = pipeline.get("state_contract", {})
    if state_contract.get("initializer") != "scripts/workflow_state.py":
        errors.append("pipeline must name scripts/workflow_state.py as the state initializer")
    if state_contract.get("explicit_resume_only") is not True or state_contract.get("local_file_existence_is_not_remote_persistence") is not True:
        errors.append("pipeline state contract must require explicit resume and remote persistence evidence")

    required_persistence = ["artifact_validation", "git_commit", "git_push", "remote_sha_match"]
    if editorial.get("publication_status_requires") != required_persistence:
        errors.append("editorial publication_status_requires is not the exact archive gate")
    if not args.allow_enabled and schedule.get("enabled") is not False:
        errors.append("schedule must remain disabled before Cloud-only acceptance")
    if schedule.get("hard_requirement") != "cloud-only":
        errors.append("schedule hard_requirement must be cloud-only")

    workflow_jobs = scheduled_workflow.get("jobs")
    expected_workflow_jobs = {
        "current-news-desk", "deep-features-desk", "chief-editor",
        "publishing-desk", "cover-director",
    }
    if scheduled_workflow.get("enabled") is not False:
        errors.append("scheduled-workflow contract must remain disabled")
    if scheduled_workflow.get("timezone") != "Africa/Casablanca":
        errors.append("scheduled-workflow timezone must be Africa/Casablanca")
    if not isinstance(workflow_jobs, list) or len(workflow_jobs) != 5:
        errors.append("scheduled-workflow must define exactly five super-jobs")
    elif {job.get("id") for job in workflow_jobs} != expected_workflow_jobs:
        errors.append("scheduled-workflow job definitions do not match the five required super-jobs")
    for job in workflow_jobs or []:
        if job.get("timezone") != "Africa/Casablanca":
            errors.append(f"scheduled-workflow job {job.get('id')} has the wrong timezone")
    workflow_constraints = scheduled_workflow.get("execution_constraints", {})
    required_false = (
        "openai_api_allowed", "openai_api_key_required", "pay_as_you_go_openai_allowed",
        "github_actions_allowed", "external_paid_services_allowed",
        "self_hosted_runner_allowed", "local_pc_dependency_allowed",
    )
    for key in required_false:
        if workflow_constraints.get(key) is not False:
            errors.append(f"scheduled-workflow constraint {key} must be false")
    capabilities = scheduled_workflow.get("connector_capabilities", {})
    if capabilities.get("github_binary_image_write_through_current_connector") != "UNSUPPORTED/BLOCKED":
        errors.append("scheduled-workflow must document current binary connector limitation")
    if capabilities.get("scheduled_image_generation") not in {"PASS", "UNSUPPORTED/BLOCKED", "UNTESTED"}:
        errors.append("scheduled-workflow must record the actual scheduled image-generation result")
    if not (ROOT / "design/DRAGON-COVER-STYLE.md").is_file():
        errors.append("DRAGON cover style contract is missing")
    production_state = scheduled_workflow.get("production_state", {})
    fresh = production_state.get("fresh_run_initialization", {})
    fresh_values = fresh.get("values", {})
    for field in ("current_research", "deep_research", "editorial", "publishing", "cover", "overall_status"):
        if fresh_values.get(field) != "PENDING":
            errors.append(f"fresh production initialization must reset {field} to PENDING")
    if fresh_values.get("blocking_reason", "missing") is not None:
        errors.append("fresh production initialization must reset blocking_reason to null")
    if fresh.get("remove_stale_completion_fields") is not True:
        errors.append("fresh production initialization must remove stale completion fields")
    resume = production_state.get("resume", {})
    if resume.get("explicit_only") is not True or resume.get("require_remote_read_back_before_retaining_complete") is not True:
        errors.append("resume must be explicit and require remote read-back")
    invariants = production_state.get("invariants", {})
    if not invariants.get("editorial_complete_requires") or not invariants.get("overall_complete_requires"):
        errors.append("scheduled-workflow must declare editorial and overall state invariants")
    remote = scheduled_workflow.get("remote_persistence", {})
    if remote.get("local_or_runtime_file_is_not_remote_persistence") is not True:
        errors.append("scheduled-workflow must distinguish local existence from remote persistence")
    if len(remote.get("chief_editor_required_read_back", [])) != 3:
        errors.append("scheduled-workflow must require three Chief Editor canonical remote read-backs")

    for schema, name in ((output_schema, "output"), (investigation_schema, "investigation"), (manifest_schema, "manifest")):
        schema_errors: list[str] = []
        try:
            Draft202012Validator.check_schema(schema)
        except Exception as exc:
            schema_errors.append(str(exc))
        if schema_errors:
            errors.append(f"{name} schema invalid: {schema_errors[0]}")

    agent_files = {p.stem for p in (ROOT / "agents").glob("*.md")}
    expected_agent_files = {role.replace("-", "-") for role in EXPECTED_ROLES}
    if agent_files != expected_agent_files:
        errors.append(f"agent files mismatch: {sorted(agent_files)}")
    for role in roles or []:
        agent_path = ROOT / "agents" / f"{role['id']}.md"
        if agent_path.exists():
            text = agent_path.read_text(encoding="utf-8")
            if not re.search(rf"role_id:\s*{re.escape(role['id'])}\s*$", text, re.M):
                errors.append(f"{agent_path.name} role_id does not match registry")

    if errors:
        print("CONFIGURATION FAIL")
        print("\n".join(errors))
        return 1
    print("CONFIGURATION PASS: 13 roles, six ordered stages, Cloud-only archive gate, schedule disabled")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
