"""Integration scenarios for end-to-end workflow reliability."""


from contextlib import redirect_stdout
from argparse import Namespace
from unittest.mock import Mock

from io import StringIO
import unittest

from pnp.workflow_engine import Orchestrator
from tests._gitfixture import GitFixture
from pnp import utils, gitutils


class _Resolver:
    @staticmethod
    def normalize_stderr(err: object, prefix: str = "") -> str:
        if prefix: return f"{prefix} {err}"
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
        "project_type": "auto",
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
    def test_publish_aborts_when_adapter_publish_command_fails(self) -> None:
        args = _args(
            publish=True,
            project_type="node",
            tag_bump="patch",
            path=".",
        )
        setattr(
            args,
            "_pnp_adapter_config",
            {"node": {"publish-command": "false"}},
        )
        o = Orchestrator(args, repo_path=".")
        o.repo = "."
        o.subpkg = "."
        o.resolver = _Resolver()
        o.log_text = "release"
        o.latest = "v1.0.0"

        fake_git = Mock()
        fake_git.tags_sorted.return_value = []
        fake_git.create_tag.return_value = None
        fake_git.push.return_value = None
        o.gitutils = fake_git

        with redirect_stdout(StringIO()):
            msg, result = o.publish()
        self.assertIs(result, utils.StepResult.ABORT)
        self.assertIsInstance(msg, tuple)
        assert isinstance(msg, tuple)
        self.assertIn("adapter publish failed", msg[0])

    def test_publish_aborts_when_adapter_pre_publish_command_fails(self) -> None:
        fix = GitFixture()
        try:
            repo = fix.init_repo("repo")
            fix.set_identity(repo, "pnp-test", "pnp@example.com")
            (repo / "package.json").write_text(
                "{\"name\": \"app\", \"version\": \"1.0.0\"}\n",
                encoding="utf-8",
            )
            fix.commit_all(repo, "init")

            args = _args(
                publish=True,
                path=str(repo),
                project_type="node",
                tag_bump="patch",
            )
            setattr(
                args,
                "_pnp_adapter_config",
                {"node": {"pre-publish-hook": "false"}},
            )
            o = Orchestrator(args, repo_path=str(repo))
            o.repo = str(repo)
            o.subpkg = str(repo)
            o.gitutils = gitutils
            o.resolver = _Resolver()
            o.log_text = "release"
            o.latest = "v1.0.0"

            with redirect_stdout(StringIO()):
                msg, result = o.publish()
            self.assertIs(result, utils.StepResult.ABORT)
            self.assertIsInstance(msg, tuple)
            assert isinstance(msg, tuple)
            self.assertIn("adapter pre-publish failed", msg[0])
        finally:
            fix.close()

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
