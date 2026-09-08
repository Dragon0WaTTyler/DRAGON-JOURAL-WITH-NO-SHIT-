import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from dragon.preflight import (
    _clean_worktree,
    _v5_generated_prefixes,
    run_preflight,
)


BASE_CONFIG = {
    "version": 5,
    "timezone": "Africa/Casablanca",
    "providers": {
        "ai": {
            "type": "local-command",
            "integration_test_status": "PASS",
            "command": ["python"],
        },
        "github_archive": {"type": "git-cli", "enabled": False},
        "whatsapp": {"type": "unconfigured", "enabled": False},
    },
    "preflight": {
        "expected_remote_contains": "DRAGON",
        "expected_branch": "main",
        "require_clean_worktree": True,
        "minimum_python": [3, 12],
        "minimum_free_bytes": 1,
        "required_modules": ["json"],
        "network_probe": {"enabled": True, "host": "example.test", "port": 443},
        "require_ai_provider": True,
    },
}
ARABIC_CONFIG = {
    "fonts": {"preferred_families": ["Amiri"], "local_fallback_families": []}
}


class V5PreflightTests(unittest.TestCase):
    def run_with(self, config, provider=None, git_override=None, trial_result=None):
        class Provider:
            available = (
                config.get("providers", {}).get("ai", {}).get("type") == "local-command"
                and config.get("providers", {}).get("ai", {}).get("integration_test_status") == "PASS"
            )

            def healthcheck(self):
                return {"status": "PASS", "unattended": True, "provider": "test-local"}

        provider = provider or Provider()

        def git_result(_root, *args):
            if args == ("remote", "get-url", "origin"):
                return "https://github.com/DRAGON/repo"
            if args == ("branch", "--show-current"):
                return "main"
            if args == ("status", "--porcelain", "--untracked-files=all"):
                return ""
            return str(_root)

        stack = [
            patch("dragon.preflight.load_local_config", return_value=config),
            patch("dragon.preflight.load_mapping", return_value=ARABIC_CONFIG),
            patch("dragon.preflight._git", side_effect=git_override or git_result),
            patch("dragon.preflight._font_available", return_value="Amiri.ttf"),
            patch("dragon.preflight._network", return_value="reachable"),
            patch("dragon.preflight._import", return_value="importable"),
            patch("dragon.preflight._storage", return_value="enough"),
            patch("dragon.preflight.shutil.which", return_value="git"),
            patch("dragon.preflight.editorial_provider_from_config", return_value=provider),
            patch(
                "dragon.preflight._provider_trial_evidence",
                return_value=trial_result if trial_result is not None else (
                    True,
                    [{"date": "2026-09-08", "status": "PASS", "issues": []}],
                ),
            ),
        ]
        with tempfile.TemporaryDirectory() as directory:
            with stack[0], stack[1], stack[2], stack[3], stack[4], stack[5], stack[6], stack[7], stack[8], stack[9]:
                return run_preflight(Path(directory), "2026-09-08")

    def test_all_required_capabilities_pass(self):
        report = self.run_with(BASE_CONFIG)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["blocking_failures"], [])

    def test_missing_ai_provider_is_blocking(self):
        config = {
            **BASE_CONFIG,
            "providers": {**BASE_CONFIG["providers"], "ai": {"type": "unconfigured"}},
        }
        report = self.run_with(config)
        self.assertEqual(report["status"], "FAIL")
        self.assertIn("ai_provider", [item["name"] for item in report["blocking_failures"]])

    def test_untested_ai_provider_is_blocking(self):
        config = {
            **BASE_CONFIG,
            "providers": {
                **BASE_CONFIG["providers"],
                "ai": {"type": "local-command", "integration_test_status": "NOT_RUN"},
            },
        }
        report = self.run_with(config)
        self.assertEqual(report["status"], "FAIL")

    def test_proven_provider_live_health_failure_is_blocking(self):
        class BrokenProvider:
            available = True

            def healthcheck(self):
                raise RuntimeError("provider authentication expired")

        report = self.run_with(BASE_CONFIG, BrokenProvider())
        item = next(check for check in report["checks"] if check["name"] == "ai_provider")
        self.assertEqual(item["status"], "FAIL")
        self.assertTrue(item["blocking"])
        self.assertIn("expired", item["detail"])

    def test_proven_provider_without_reviewed_trial_is_blocking(self):
        report = self.run_with(BASE_CONFIG, trial_result=(False, []))
        item = next(
            check for check in report["blocking_failures"]
            if check["name"] == "ai_provider_evidence"
        )
        self.assertIn("PREFLIGHT_AI_PROVIDER_EVIDENCE_INVALID", item["detail"])

    def test_disabled_whatsapp_is_non_blocking(self):
        report = self.run_with(BASE_CONFIG)
        item = next(
            check for check in report["checks"] if check["name"] == "optional_provider:whatsapp"
        )
        self.assertEqual(item["status"], "PASS")
        self.assertFalse(item["blocking"])

    def test_enabled_archive_probes_identity_and_remote_read_access(self):
        config = {
            **BASE_CONFIG,
            "providers": {
                **BASE_CONFIG["providers"],
                "github_archive": {
                    "type": "git-cli",
                    "enabled": True,
                    "remote": "origin",
                    "branch": "main",
                },
            },
        }
        calls = []

        def git_result(root, *args):
            calls.append(args)
            if args == ("remote", "get-url", "origin"):
                return "https://github.com/DRAGON/repo"
            if args == ("branch", "--show-current"):
                return "main"
            if args == ("status", "--porcelain", "--untracked-files=all"):
                return ""
            if args == ("config", "user.name"):
                return "Archive Operator"
            if args == ("config", "user.email"):
                return "archive@example.test"
            if args[:2] == ("ls-remote", "--exit-code"):
                return "abc123\trefs/heads/main"
            return str(root)

        report = self.run_with(config, git_override=git_result)
        item = next(
            check for check in report["checks"]
            if check["name"] == "optional_provider:github_archive"
        )
        self.assertEqual(item["status"], "PASS")
        self.assertFalse(item["blocking"])
        self.assertIn(("config", "user.name"), calls)
        self.assertIn(("ls-remote", "--exit-code", "origin", "refs/heads/main"), calls)

    def test_archive_probe_failure_is_a_nonblocking_warning(self):
        config = {
            **BASE_CONFIG,
            "providers": {
                **BASE_CONFIG["providers"],
                "github_archive": {"type": "git-cli", "enabled": True},
            },
        }

        def git_result(root, *args):
            if args == ("remote", "get-url", "origin"):
                return "https://github.com/DRAGON/repo"
            if args == ("branch", "--show-current"):
                return "main"
            if args == ("status", "--porcelain", "--untracked-files=all"):
                return ""
            if args == ("config", "user.name"):
                return "Archive Operator"
            if args == ("config", "user.email"):
                return "archive@example.test"
            if args[:2] == ("ls-remote", "--exit-code"):
                raise RuntimeError("remote unavailable")
            return str(root)

        report = self.run_with(config, git_override=git_result)
        item = next(
            warning for warning in report["warnings"]
            if warning["name"] == "optional_provider:github_archive"
        )
        self.assertEqual(item["status"], "FAIL")
        self.assertFalse(item["blocking"])

    def test_current_run_artifacts_do_not_make_preflight_fail_dirty(self):
        self.assertEqual(
            _clean_worktree(
                "?? daily-runs/2026-09-08/state.json\n"
                "?? editions/2026/09/2026-09-08/edition.md",
                (
                    "daily-runs/2026-09-08/",
                    "editions/2026/09/2026-09-08/",
                ),
            ),
            "clean",
        )

    def test_prior_state_backed_untracked_outputs_do_not_block_next_day(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = root / "daily-runs" / "2026-09-07" / "state.json"
            state.parent.mkdir(parents=True)
            state.write_text(
                '{"schema_version":5,"date":"2026-09-07"}', encoding="utf-8"
            )
            prefixes = _v5_generated_prefixes(root, exclude_date="2026-09-08")
            self.assertEqual(
                _clean_worktree(
                    "?? daily-runs/2026-09-07/run-report.json\n"
                    "?? editions/2026/09/2026-09-07/edition.pdf",
                    (),
                    prefixes,
                ),
                "clean",
            )

    def test_prior_tracked_modification_remains_blocking(self):
        with self.assertRaisesRegex(RuntimeError, "working tree has unrelated changes"):
            _clean_worktree(
                " M editions/2026/09/2026-09-07/edition.md",
                (),
                ("editions/2026/09/2026-09-07/",),
            )

    def test_untracked_acceptance_evidence_does_not_block_production(self):
        with tempfile.TemporaryDirectory() as directory:
            prefixes = _v5_generated_prefixes(
                Path(directory), exclude_date="2026-09-08"
            )
            self.assertEqual(
                _clean_worktree(
                    "?? acceptance/machine/\n"
                    "?? acceptance/provider-trials/\n"
                    "?? acceptance/evidence/",
                    (),
                    prefixes,
                ),
                "clean",
            )

    def test_tracked_acceptance_evidence_edit_remains_blocking(self):
        with self.assertRaisesRegex(RuntimeError, "acceptance/evidence"):
            _clean_worktree(
                " M acceptance/evidence/failure-injection.json",
                (),
                ("acceptance/evidence/",),
            )

    def test_unrelated_dirty_source_blocks_preflight(self):
        with self.assertRaisesRegex(RuntimeError, "dragon/preflight.py"):
            _clean_worktree(
                " M dragon/preflight.py",
                ("daily-runs/2026-09-08/",),
            )


if __name__ == "__main__":
    unittest.main()
