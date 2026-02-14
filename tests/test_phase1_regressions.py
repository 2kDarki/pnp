"""Regression tests for core pnp hardening fixes."""
from __future__ import annotations

from argparse import Namespace
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import subprocess
import tempfile
import unittest
import sys
from unittest.mock import patch
import json

from pnp import _constants as const
from pnp import utils
from pnp.cli import Orchestrator, run_hook


def make_args(**overrides) -> Namespace:
    """Build a complete args namespace used by Orchestrator."""
    base = {
        "path": ".",
        "batch_commit": False,
        "hooks": None,
        "changelog_file": "changes.log",
        "push": False,
        "publish": False,
        "remote": None,
        "force": False,
        "no_transmission": False,
        "quiet": False,
        "plain": False,
        "verbose": False,
        "debug": False,
        "auto_fix": False,
        "dry_run": False,
        "ci": False,
        "interactive": True,
        "gh_release": False,
        "gh_repo": None,
        "gh_token": None,
        "gh_draft": False,
        "gh_prerelease": False,
        "gh_assets": None,
        "check_only": False,
        "check_json": False,
        "strict": False,
        "tag_prefix": "v",
        "tag_message": None,
        "edit_message": False,
        "editor": None,
        "tag_sign": False,
        "tag_bump": "patch",
        "show_config": False,
        "install_git_ext": False,
        "uninstall_git_ext": False,
        "git_ext_dir": None,
        "machete_status": False,
        "machete_sync": False,
        "machete_traverse": False,
    }
    base.update(overrides)
    return Namespace(**base)


class _DummyGit:
    def tags_sorted(self, path: str) -> list[str]:
        return []


class _TaggedDummyGit:
    def tags_sorted(self, path: str) -> list[str]:
        return ["v1.2.3"]


class Phase1RegressionTests(unittest.TestCase):
    def test_batch_find_repo_returns_and_does_not_hang(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(
                ["git", "init", tmp],
                check=True,
                capture_output=True,
                text=True,
            )
            const.sync_runtime_flags(make_args(batch_commit=True))
            found = utils.find_repo(tmp, batch=True, return_none=False)
            self.assertEqual(found, [str(Path(tmp))])

    def test_run_hook_failure_raises_runtime_error(self) -> None:
        with redirect_stdout(StringIO()):
            with self.assertRaises(RuntimeError):
                run_hook("false", ".", dryrun=False)

    def test_run_hook_disallowed_command_raises_value_error(self) -> None:
        with redirect_stdout(StringIO()):
            with self.assertRaises(ValueError):
                run_hook("rm -rf /tmp/whatever", ".", dryrun=False)

    def test_gitutils_import_works_in_clean_process(self) -> None:
        cp = subprocess.run(
            [sys.executable, "-c", "import pnp.gitutils; print('ok')"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(cp.returncode, 0, cp.stderr)
        self.assertIn("ok", cp.stdout)

    def test_release_fails_when_no_tag_available(self) -> None:
        args = make_args(gh_release=True, dry_run=False, ci=True)
        o = Orchestrator(args, repo_path=".")
        o.gitutils = _DummyGit()
        o.repo = "."
        with redirect_stdout(StringIO()):
            _, result = o.release()
        self.assertIs(result, utils.StepResult.FAIL)

    def test_release_uses_latest_tag_when_publish_not_run(self) -> None:
        args = make_args(gh_release=True, dry_run=False, ci=True)
        o = Orchestrator(args, repo_path=".")
        o.gitutils = _TaggedDummyGit()
        o.repo = "."
        with redirect_stdout(StringIO()):
            _, result = o.release()
        self.assertEqual(o.tag, "v1.2.3")
        self.assertIs(result, utils.StepResult.FAIL)

    def test_runtime_flags_sync_respects_interactive_mode(self) -> None:
        const.sync_runtime_flags(make_args(interactive=True, ci=False, quiet=False, plain=False))
        self.assertFalse(const.CI_MODE)
        const.sync_runtime_flags(make_args(interactive=True, quiet=True))
        self.assertTrue(const.CI_MODE)

    def test_run_machete_skips_when_not_enabled(self) -> None:
        o = Orchestrator(make_args(), repo_path=".")
        o.repo = "."
        with redirect_stdout(StringIO()):
            _, result = o.run_machete()
        self.assertIs(result, utils.StepResult.SKIP)

    def test_run_machete_fails_when_binary_missing(self) -> None:
        o = Orchestrator(make_args(machete_status=True), repo_path=".")
        o.repo = "."
        with patch("pnp.cli.shutil.which", return_value=None):
            with redirect_stdout(StringIO()):
                msg, result = o.run_machete()
        self.assertIs(result, utils.StepResult.ABORT)
        self.assertIn("git-machete not found", str(msg))

    def test_run_machete_status_executes(self) -> None:
        o = Orchestrator(make_args(machete_status=True), repo_path=".")
        o.repo = "."
        cp = subprocess.CompletedProcess(
            args=["git", "machete", "status"],
            returncode=0,
            stdout="ok",
            stderr="",
        )
        with patch("pnp.cli.shutil.which", return_value="/usr/bin/git-machete"):
            with patch("pnp.cli.subprocess.run", return_value=cp) as run:
                with redirect_stdout(StringIO()):
                    _, result = o.run_machete()
        self.assertIs(result, utils.StepResult.OK)
        run.assert_called()

    def test_check_only_strict_escalates_doctor_warnings(self) -> None:
        from pnp.cli import run_check_only

        def fake_doctor(path: str, out: utils.Output, json_mode: bool = False,
                        report_file: str | None = None) -> int:
            if report_file:
                payload = {
                    "summary": {"critical": 0, "warnings": 2, "healthy": False},
                    "checks": [],
                }
                Path(report_file).write_text(json.dumps(payload), encoding="utf-8")
            return 0

        args = make_args(check_only=True, strict=True, push=False, publish=False)
        with patch("pnp.cli.run_doctor", side_effect=fake_doctor):
            with patch("pnp.cli._find_repo_noninteractive", return_value="."):
                with redirect_stdout(StringIO()):
                    code = run_check_only(args, utils.Output(quiet=False))
        self.assertEqual(code, 20)

    def test_check_only_warnings_only_returns_warning_exit_code(self) -> None:
        from pnp.cli import run_check_only

        def fake_doctor(path: str, out: utils.Output, json_mode: bool = False,
                        report_file: str | None = None) -> int:
            if report_file:
                payload = {
                    "summary": {"critical": 0, "warnings": 2, "healthy": False},
                    "checks": [],
                }
                Path(report_file).write_text(json.dumps(payload), encoding="utf-8")
            return 0

        args = make_args(check_only=True, strict=False, push=False, publish=False)
        with patch("pnp.cli.run_doctor", side_effect=fake_doctor):
            with patch("pnp.cli._find_repo_noninteractive", return_value="."):
                with redirect_stdout(StringIO()):
                    code = run_check_only(args, utils.Output(quiet=False))
        self.assertEqual(code, 10)

    def test_run_hooks_ci_fails_fast_on_first_error(self) -> None:
        o = Orchestrator(make_args(hooks="a; b", ci=True, interactive=False), repo_path=".")
        o.subpkg = "."
        with patch("pnp.cli.run_hook", side_effect=RuntimeError("[1]: boom")) as hook:
            with redirect_stdout(StringIO()):
                _, result = o.run_hooks()
        self.assertIs(result, utils.StepResult.FAIL)
        self.assertEqual(hook.call_count, 1)

    def test_run_hooks_interactive_continue_resumes_next_hook(self) -> None:
        o = Orchestrator(make_args(hooks="a; b", ci=False, interactive=True), repo_path=".")
        o.subpkg = "."

        calls = {"n": 0}

        def fake_run_hook(cmd: str, cwd: str, dryrun: bool,
                          no_transmission: bool = False) -> int:
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("[1]: first failed")
            return 0

        with patch("pnp.cli.run_hook", side_effect=fake_run_hook) as hook:
            with patch("pnp.cli.utils.intent", return_value=False) as intent:
                with redirect_stdout(StringIO()):
                    _, result = o.run_hooks()
        self.assertIs(result, utils.StepResult.OK)
        self.assertEqual(hook.call_count, 2)
        intent.assert_called_once()

    def test_run_hooks_interactive_abort_on_user_choice(self) -> None:
        o = Orchestrator(make_args(hooks="a; b", ci=False, interactive=True), repo_path=".")
        o.subpkg = "."
        with patch("pnp.cli.run_hook", side_effect=RuntimeError("[1]: failed")) as hook:
            with patch("pnp.cli.utils.intent", return_value=True) as intent:
                with redirect_stdout(StringIO()):
                    msg, result = o.run_hooks()
        self.assertIs(result, utils.StepResult.ABORT)
        self.assertEqual(msg, "aborting due to hook failure")
        self.assertEqual(hook.call_count, 1)
        intent.assert_called_once()

    def test_resolve_editor_prefers_git_core_editor(self) -> None:
        o = Orchestrator(make_args(), repo_path=".")
        o.repo = "."
        cp = subprocess.CompletedProcess(
            args=["git", "-C", ".", "config", "--get", "core.editor"],
            returncode=0,
            stdout="nano\n",
            stderr="",
        )
        with patch("pnp.cli.subprocess.run", return_value=cp):
            with patch("pnp.cli.shutil.which", return_value="/usr/bin/nano"):
                editor = o._resolve_editor_command()
        self.assertEqual(editor, ["nano"])

    def test_edit_message_temp_file_is_cleaned(self) -> None:
        o = Orchestrator(make_args(edit_message=True, editor="fake-editor"), repo_path=".")
        o.repo = "."

        def fake_run(cmd: list[str], check: bool = False) -> subprocess.CompletedProcess[str]:
            path = cmd[-1]
            Path(path).write_text(
                "custom subject\n\ncustom body\n# comment\n",
                encoding="utf-8",
            )
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

        with patch.object(o, "_resolve_editor_command", return_value=["fake-editor"]):
            with patch("pnp.cli.subprocess.run", side_effect=fake_run):
                msg = o._edit_message_in_editor("seed message", "commit")
        self.assertEqual(msg, "custom subject\n\ncustom body")
        self.assertEqual(len(o._temp_message_files), 1)
        self.assertTrue(Path(o._temp_message_files[0]).exists())
        o._cleanup_temp_message_files()
        self.assertEqual(o._temp_message_files, [])


if __name__ == "__main__":
    unittest.main()
