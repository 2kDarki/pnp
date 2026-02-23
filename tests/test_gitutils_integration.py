"""Integration tests for gitutils using local temporary repositories."""


from argparse import Namespace
import unittest

from tests._gitfixture import GitFixture
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
        fix = GitFixture()
        try:
            remote = fix.init_bare()
            work = fix.init_repo("work")
            fix.set_identity(work, "pnp-test", "pnp@example.com")
            fix.add_remote(work, "origin", remote)
            (work / "README.md").write_text("hello\n", encoding="utf-8")
            gitutils.stage_all(str(work))
            gitutils.commit(str(work), "initial commit")

            branch = gitutils.current_branch(str(work))
            self.assertIsNotNone(branch)

            gitutils.push(str(work), remote="origin", branch=branch, push_tags=False)
            cp_branch = fix.run(
                ["--git-dir", str(remote), "show-ref", f"refs/heads/{branch}"],
                check=False,
            )
            self.assertEqual(cp_branch.returncode, 0, cp_branch.stderr)

            gitutils.create_tag(str(work), "v0.0.1", message="release")
            gitutils.push(str(work), remote="origin", branch=None, push_tags=True)
            cp_tag = fix.run(
                ["--git-dir", str(remote), "show-ref", "refs/tags/v0.0.1"],
                check=False,
            )
            self.assertEqual(cp_tag.returncode, 0, cp_tag.stderr)
        finally:
            fix.close()


if __name__ == "__main__":
    unittest.main()
