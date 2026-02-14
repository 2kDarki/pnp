"""Unit tests for gitutils command behavior."""
from __future__ import annotations

from argparse import Namespace
from subprocess import CompletedProcess
from unittest.mock import patch
import unittest

from pnp import _constants as const
from pnp import gitutils


def _args(**overrides) -> Namespace:
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


class GitUtilsCoreTests(unittest.TestCase):
    def test_run_git_success_ignores_stderr_progress(self) -> None:
        const.sync_runtime_flags(_args(dry_run=False))
        cp = CompletedProcess(
            args=["git", "status"],
            returncode=0,
            stdout="",
            stderr="Enumerating objects...",
        )
        with patch("pnp.gitutils.subprocess.run", return_value=cp):
            with patch("pnp.gitutils.resolver.resolve") as resolve:
                rc, out = gitutils.run_git(["status"], cwd=".")
        self.assertEqual(rc, 0)
        self.assertIn("Enumerating objects", out)
        resolve.assert_not_called()

    def test_push_tag_only_does_not_require_branch_push(self) -> None:
        calls: list[list[str]] = []

        def fake_run_git(args: list[str], cwd: str, capture: bool = True, tries: int = 0):
            calls.append(args)
            return 0, "ok"

        with patch("pnp.gitutils.run_git", side_effect=fake_run_git):
            gitutils.push(".", remote="origin", branch=None, push_tags=True)
        self.assertEqual(calls, [["push", "origin", "--tags"]])


if __name__ == "__main__":
    unittest.main()
