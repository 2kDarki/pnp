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


if __name__ == "__main__":
    unittest.main()
