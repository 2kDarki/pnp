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
        "tag_prefix": "v",
        "tag_message": None,
        "tag_sign": False,
        "tag_bump": "patch",
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


if __name__ == "__main__":
    unittest.main()
