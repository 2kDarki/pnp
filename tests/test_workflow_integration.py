"""Integration scenarios for end-to-end workflow reliability."""
from __future__ import annotations

from argparse import Namespace
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import unittest

from pnp import utils, gitutils
from pnp.cli import Orchestrator
from tests._gitfixture import GitFixture


class _Resolver:
    @staticmethod
    def normalize_stderr(err: object, prefix: str = "") -> str:
        if prefix:
            return f"{prefix} {err}"
        return str(err)


def _args(**overrides: object) -> Namespace:
    base: dict[str, object] = {
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
        "ci": True,
        "interactive": False,
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
        "tag_message": "release",
        "tag_sign": False,
        "tag_bump": "patch",
        "show_config": False,
        "doctor": False,
        "doctor_json": False,
        "doctor_report": None,
        "install_git_ext": False,
        "uninstall_git_ext": False,
        "git_ext_dir": None,
        "machete_status": False,
        "machete_sync": False,
        "machete_traverse": False,
    }
    base.update(overrides)
    return Namespace(**base)


class WorkflowIntegrationTests(unittest.TestCase):
    def test_publish_rollback_deletes_local_tag_on_push_failure(self) -> None:
        fix = GitFixture()
        try:
            repo = fix.init_repo("repo")
            fix.set_identity(repo, "pnp-test", "pnp@example.com")
            (repo / "README.md").write_text("hello\n", encoding="utf-8")
            fix.commit_all(repo, "init")

            o = Orchestrator(_args(publish=True, path=str(repo)), repo_path=str(repo))
            o.repo = str(repo)
            o.subpkg = str(repo)
            o.gitutils = gitutils
            o.resolver = _Resolver()
            o.log_text = "release"

            with redirect_stdout(StringIO()):
                _, result = o.publish()
            self.assertIs(result, utils.StepResult.ABORT)

            cp = fix.run(
                ["-C", str(repo), "tag", "--list", "v0.0.1"],
                check=False,
            )
            self.assertEqual(cp.returncode, 0, cp.stderr)
            self.assertEqual(cp.stdout.strip(), "")
        finally:
            fix.close()

    def test_push_aborts_when_remote_is_ahead_in_ci_without_force(self) -> None:
        fix = GitFixture()
        try:
            remote = fix.init_bare()
            work = fix.init_repo("work")
            fix.set_identity(work, "pnp-test", "pnp@example.com")
            fix.add_remote(work, "origin", remote)
            (work / "a.txt").write_text("one\n", encoding="utf-8")
            fix.commit_all(work, "init")
            branch = fix.branch(work)
            fix.push_upstream(work, "origin", branch)

            peer = fix.clone(remote, "peer")
            fix.set_identity(peer, "pnp-peer", "peer@example.com")
            (peer / "a.txt").write_text("peer-change\n", encoding="utf-8")
            fix.commit_all(peer, "peer")
            fix.run(["-C", str(peer), "push", "origin", branch])

            o = Orchestrator(_args(push=True, force=False, path=str(work)), repo_path=str(work))
            o.repo = str(work)
            o.subpkg = str(work)
            o.gitutils = gitutils
            o.resolver = _Resolver()

            with redirect_stdout(StringIO()):
                _, result = o.push()
            self.assertIs(result, utils.StepResult.ABORT)
        finally:
            fix.close()

    def test_push_allows_force_when_remote_is_ahead(self) -> None:
        fix = GitFixture()
        try:
            remote = fix.init_bare()
            work = fix.init_repo("work")
            fix.set_identity(work, "pnp-test", "pnp@example.com")
            fix.add_remote(work, "origin", remote)
            (work / "a.txt").write_text("one\n", encoding="utf-8")
            fix.commit_all(work, "init")
            branch = fix.branch(work)
            fix.push_upstream(work, "origin", branch)

            peer = fix.clone(remote, "peer")
            fix.set_identity(peer, "pnp-peer", "peer@example.com")
            (peer / "a.txt").write_text("peer-change\n", encoding="utf-8")
            fix.commit_all(peer, "peer")
            fix.run(["-C", str(peer), "push", "origin", branch])

            o = Orchestrator(_args(push=True, force=True, path=str(work)), repo_path=str(work))
            o.repo = str(work)
            o.subpkg = str(work)
            o.gitutils = gitutils
            o.resolver = _Resolver()

            with redirect_stdout(StringIO()):
                _, result = o.push()
            self.assertIs(result, utils.StepResult.OK)
        finally:
            fix.close()


if __name__ == "__main__":
    unittest.main()
