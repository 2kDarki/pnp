"""Tests for remediation policy matrix behavior."""


import unittest

from pnp.remediation_policy import can_run_remediation


class RemediationPolicyTests(unittest.TestCase):
    def test_destructive_reset_disallowed_in_autofix(self) -> None:
        allowed, reason = can_run_remediation(
            action="destructive_reset",
            ci_mode=False,
            autofix=True,
            interactive=True,
        )
        self.assertFalse(allowed)
        self.assertIn("auto-fix", reason)

    def test_open_shell_disallowed_in_ci(self) -> None:
        allowed, reason = can_run_remediation(
            action="open_shell_manual",
            ci_mode=True,
            autofix=False,
            interactive=False,
        )
        self.assertFalse(allowed)
        self.assertIn("CI mode", reason)

    def test_add_origin_ssh_allowed_in_autofix(self) -> None:
        allowed, reason = can_run_remediation(
            action="add_origin_ssh",
            ci_mode=True,
            autofix=True,
            interactive=False,
        )
        self.assertTrue(allowed)
        self.assertEqual(reason, "")

    def test_unknown_action_is_rejected(self) -> None:
        allowed, reason = can_run_remediation(
            action="unknown_action",
            ci_mode=False,
            autofix=False,
            interactive=True,
        )
        self.assertFalse(allowed)
        self.assertIn("unknown", reason)

    def test_stale_lock_cleanup_allowed_in_ci_autofix(self) -> None:
        allowed, reason = can_run_remediation(
            action="stale_lock_cleanup",
            ci_mode=True,
            autofix=True,
            interactive=False,
        )
        self.assertTrue(allowed)
        self.assertEqual(reason, "")

    def test_set_upstream_tracking_allowed_in_ci_autofix(self) -> None:
        allowed, reason = can_run_remediation(
            action="set_upstream_tracking",
            ci_mode=True,
            autofix=True,
            interactive=False,
        )
        self.assertTrue(allowed)
        self.assertEqual(reason, "")

    def test_auto_stash_worktree_allowed_in_ci_autofix(self) -> None:
        allowed, reason = can_run_remediation(
            action="auto_stash_worktree",
            ci_mode=True,
            autofix=True,
            interactive=False,
        )
        self.assertTrue(allowed)
        self.assertEqual(reason, "")

    def test_line_ending_actions_allowed_in_ci_autofix(self) -> None:
        allowed_create, reason_create = can_run_remediation(
            action="create_gitattributes",
            ci_mode=True,
            autofix=True,
            interactive=False,
        )
        allowed_renorm, reason_renorm = can_run_remediation(
            action="renormalize_line_endings",
            ci_mode=True,
            autofix=True,
            interactive=False,
        )
        self.assertTrue(allowed_create)
        self.assertEqual(reason_create, "")
        self.assertTrue(allowed_renorm)
        self.assertEqual(reason_renorm, "")

    def test_large_file_actions_allowed_in_ci_autofix(self) -> None:
        allowed_lfs, reason_lfs = can_run_remediation(
            action="configure_git_lfs_tracking",
            ci_mode=True,
            autofix=True,
            interactive=False,
        )
        allowed_scrub, reason_scrub = can_run_remediation(
            action="history_scrub_guidance",
            ci_mode=True,
            autofix=True,
            interactive=False,
        )
        self.assertTrue(allowed_lfs)
        self.assertEqual(reason_lfs, "")
        self.assertTrue(allowed_scrub)
        self.assertEqual(reason_scrub, "")

    def test_pull_rebase_allowed_in_ci_autofix(self) -> None:
        allowed, reason = can_run_remediation(
            action="pull_rebase",
            ci_mode=True,
            autofix=True,
            interactive=False,
        )
        self.assertTrue(allowed)
        self.assertEqual(reason, "")

    def test_push_no_verify_disallowed_in_autofix(self) -> None:
        allowed, reason = can_run_remediation(
            action="push_no_verify",
            ci_mode=False,
            autofix=True,
            interactive=True,
        )
        self.assertFalse(allowed)
        self.assertIn("auto-fix", reason)

    def test_submodule_sync_update_allowed_in_ci_autofix(self) -> None:
        allowed, reason = can_run_remediation(
            action="submodule_sync_update",
            ci_mode=True,
            autofix=True,
            interactive=False,
        )
        self.assertTrue(allowed)
        self.assertEqual(reason, "")

    def test_submodule_fetch_prune_allowed_in_ci_autofix(self) -> None:
        allowed, reason = can_run_remediation(
            action="submodule_fetch_prune",
            ci_mode=True,
            autofix=True,
            interactive=False,
        )
        self.assertTrue(allowed)
        self.assertEqual(reason, "")


if __name__ == "__main__":
    unittest.main()
