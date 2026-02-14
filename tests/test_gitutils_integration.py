"""Integration tests for gitutils using local temporary repositories."""
from __future__ import annotations

from argparse import Namespace
from pathlib import Path
import subprocess
import tempfile
import unittest

from pnp import _constants as const
from pnp import gitutils


def _reset_flags() -> None:
    args = Namespace(
        path=".",
        batch_commit=False,
        hooks=None,
        changelog_file="changes.log",
        push=False,
        publish=False,
        remote=None,
        force=False,
        no_transmission=False,
        quiet=False,
        plain=False,
        verbose=False,
        debug=False,
        auto_fix=False,
        dry_run=False,
        ci=False,
        interactive=True,
        gh_release=False,
        gh_repo=None,
        gh_token=None,
        gh_draft=False,
        gh_prerelease=False,
        gh_assets=None,
        tag_prefix="v",
        tag_message=None,
        tag_sign=False,
        tag_bump="patch",
    )
    const.sync_runtime_flags(args)


class GitUtilsIntegrationTests(unittest.TestCase):
    def test_push_and_tag_to_local_bare_remote(self) -> None:
        _reset_flags()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            remote = root / "remote.git"
            work = root / "work"
            work.mkdir()

            subprocess.run(
                ["git", "init", "--bare", str(remote)],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "init", str(work)],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "-C", str(work), "config", "user.name", "pnp-test"],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "-C", str(work), "config", "user.email", "pnp@example.com"],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "-C", str(work), "remote", "add", "origin", str(remote)],
                check=True,
                capture_output=True,
                text=True,
            )

            (work / "README.md").write_text("hello\n", encoding="utf-8")
            gitutils.stage_all(str(work))
            gitutils.commit(str(work), "initial commit")

            branch = gitutils.current_branch(str(work))
            self.assertIsNotNone(branch)

            gitutils.push(str(work), remote="origin", branch=branch, push_tags=False)
            cp_branch = subprocess.run(
                ["git", "--git-dir", str(remote), "show-ref", f"refs/heads/{branch}"],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(cp_branch.returncode, 0, cp_branch.stderr)

            gitutils.create_tag(str(work), "v0.0.1", message="release")
            gitutils.push(str(work), remote="origin", branch=None, push_tags=True)
            cp_tag = subprocess.run(
                ["git", "--git-dir", str(remote), "show-ref", "refs/tags/v0.0.1"],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(cp_tag.returncode, 0, cp_tag.stderr)


if __name__ == "__main__":
    unittest.main()
