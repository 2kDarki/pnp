"""Tests for rollback verification helpers in ops."""


from subprocess import CompletedProcess
from unittest.mock import Mock, patch
import unittest

from pnp import ops


class OpsRollbackTests(unittest.TestCase):
    def test_rollback_unstage_verification_success(self) -> None:
        out = Mock()
        reset_ok = CompletedProcess(args=["git", "reset"], returncode=0, stdout="", stderr="")
        verify_ok = CompletedProcess(args=["git", "diff"], returncode=0, stdout="", stderr="")
        with patch("pnp.ops.subprocess.run", side_effect=[reset_ok, verify_ok]):
            ops.rollback_unstage(".", out)
        calls = [str(c.args[0]) for c in out.warn.call_args_list]
        self.assertTrue(any("unstaged index" in c for c in calls))
        self.assertTrue(any("rollback verified" in c for c in calls))

    def test_rollback_unstage_verification_failure(self) -> None:
        out = Mock()
        reset_ok = CompletedProcess(args=["git", "reset"], returncode=0, stdout="", stderr="")
        verify_bad = CompletedProcess(args=["git", "diff"], returncode=0, stdout="a.py\n", stderr="")
        with patch("pnp.ops.subprocess.run", side_effect=[reset_ok, verify_bad]):
            ops.rollback_unstage(".", out)
        calls = [str(c.args[0]) for c in out.warn.call_args_list]
        self.assertTrue(any("verification failed" in c for c in calls))

    def test_rollback_delete_tag_verification_success(self) -> None:
        out = Mock()
        del_ok = CompletedProcess(args=["git", "tag", "-d", "v1"], returncode=0, stdout="", stderr="")
        verify_ok = CompletedProcess(args=["git", "tag", "--list", "v1"], returncode=0, stdout="", stderr="")
        with patch("pnp.ops.subprocess.run", side_effect=[del_ok, verify_ok]):
            ops.rollback_delete_tag(".", "v1", out)
        calls = [str(c.args[0]) for c in out.warn.call_args_list]
        self.assertTrue(any("removed local tag" in c for c in calls))
        self.assertTrue(any("rollback verified" in c for c in calls))


if __name__ == "__main__":
    unittest.main()
