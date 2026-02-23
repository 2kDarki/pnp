"""Unit tests for gitutils command behavior."""


from subprocess import CompletedProcess
from unittest.mock import patch
from argparse import Namespace
import unittest

from pnp import _constants as const
from pnp import gitutils
from pnp import utils


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

    def test_run_git_uses_policy_decision_retry(self) -> None:
        const.sync_runtime_flags(_args(dry_run=False))
        failing = CompletedProcess(
            args=["git", "push"],
            returncode=1,
            stdout="",
            stderr="fatal: could not read from remote repository",
        )
        success = CompletedProcess(
            args=["git", "push"],
            returncode=0,
            stdout="ok",
            stderr="",
        )

        class _Decision:
            def __init__(self, result: utils.StepResult):
                self.result = result
                self.classification = type("_C", (), {"code": "PNP_NET_REMOTE_UNREADABLE"})()

        with patch("pnp.gitutils.subprocess.run", side_effect=[failing, success]):
            with patch("pnp.gitutils.resolver.resolve.decide",
                       return_value=_Decision(utils.StepResult.RETRY)):
                rc, out = gitutils.run_git(["push", "origin"], cwd=".")
        self.assertEqual(rc, 0)
        self.assertEqual(out, "ok")

    def test_run_git_network_retry_uses_backoff_and_multiple_attempts(self) -> None:
        const.sync_runtime_flags(_args(dry_run=False))
        failing = CompletedProcess(
            args=["git", "push"],
            returncode=1,
            stdout="",
            stderr="fatal: could not resolve host: github.com",
        )
        success = CompletedProcess(
            args=["git", "push"],
            returncode=0,
            stdout="ok",
            stderr="",
        )

        class _Decision:
            def __init__(self, result: utils.StepResult):
                self.result = result
                self.classification = type("_C", (), {"code": "PNP_NET_CONNECTIVITY"})()

        with patch("pnp.gitutils.subprocess.run", side_effect=[failing, failing, success]):
            with patch("pnp.gitutils.resolver.resolve.decide",
                       return_value=_Decision(utils.StepResult.RETRY)):
                with patch("pnp.gitutils.random.uniform", return_value=0.0):
                    with patch("pnp.gitutils._retry_delay_seconds",
                               return_value=0.0) as delay_fn:
                        rc, out = gitutils.run_git(["push", "origin"], cwd=".")
        self.assertEqual(rc, 0)
        self.assertEqual(out, "ok")
        self.assertEqual(delay_fn.call_count, 2)

    def test_run_git_retries_once_for_resolver_retry_even_if_code_denylisted(self) -> None:
        const.sync_runtime_flags(_args(dry_run=False))
        failing = CompletedProcess(
            args=["git", "push"],
            returncode=1,
            stdout="",
            stderr="fatal: invalid object",
        )
        success = CompletedProcess(
            args=["git", "push"],
            returncode=0,
            stdout="ok",
            stderr="",
        )

        class _Decision:
            def __init__(self, result: utils.StepResult):
                self.result = result
                self.classification = type("_C", (), {"code": "PNP_GIT_INVALID_OBJECT"})()

        with patch("pnp.gitutils.subprocess.run", side_effect=[failing, success]) as run:
            with patch("pnp.gitutils.resolver.resolve.decide",
                       return_value=_Decision(utils.StepResult.RETRY)):
                with patch("pnp.gitutils.time.sleep") as sleep:
                    rc, out = gitutils.run_git(["push", "origin"], cwd=".")
        self.assertEqual(rc, 0)
        self.assertEqual(out, "ok")
        self.assertEqual(run.call_count, 2)
        self.assertGreaterEqual(sleep.call_count, 1)

    def test_run_git_stops_when_timeout_budget_exhausted(self) -> None:
        const.sync_runtime_flags(_args(dry_run=False))
        failing = CompletedProcess(
            args=["git", "push"],
            returncode=1,
            stdout="",
            stderr="fatal: could not resolve host: github.com",
        )

        class _Decision:
            def __init__(self, result: utils.StepResult):
                self.result = result
                self.classification = type("_C", (), {"code": "PNP_NET_CONNECTIVITY"})()

        with patch("pnp.gitutils.subprocess.run", return_value=failing):
            with patch("pnp.gitutils.resolver.resolve.decide",
                       return_value=_Decision(utils.StepResult.RETRY)):
                with patch("pnp.gitutils._retry_delay_seconds", return_value=0.5):
                    with patch("pnp.gitutils.time.monotonic",
                               side_effect=[10.0, 10.1, 10.6]):
                        with patch("pnp.gitutils.time.sleep"):
                            rc, out = gitutils.run_git(
                                ["push", "origin"],
                                cwd=".",
                                timeout_budget_s=0.2,
                            )
        self.assertEqual(rc, 124)
        self.assertIn("timeout budget", out)

    def test_run_git_cancellation_interrupts_retry(self) -> None:
        const.sync_runtime_flags(_args(dry_run=False))
        failing = CompletedProcess(
            args=["git", "push"],
            returncode=1,
            stdout="",
            stderr="fatal: could not resolve host: github.com",
        )

        class _Decision:
            def __init__(self, result: utils.StepResult):
                self.result = result
                self.classification = type("_C", (), {"code": "PNP_NET_CONNECTIVITY"})()

        with patch("pnp.gitutils.subprocess.run", return_value=failing):
            with patch("pnp.gitutils.resolver.resolve.decide",
                       return_value=_Decision(utils.StepResult.RETRY)):
                with patch("pnp.gitutils._retry_delay_seconds", return_value=0.1):
                    with patch("pnp.gitutils.time.sleep",
                               side_effect=KeyboardInterrupt):
                        rc, out = gitutils.run_git(["push", "origin"], cwd=".")
        self.assertEqual(rc, 130)
        self.assertIn("cancelled by user", out)

    def test_run_git_idempotency_guard_for_repeated_identical_failure(self) -> None:
        const.sync_runtime_flags(_args(dry_run=False))
        failing = CompletedProcess(
            args=["git", "push"],
            returncode=1,
            stdout="",
            stderr="fatal: could not read from remote repository",
        )

        class _Decision:
            def __init__(self, result: utils.StepResult):
                self.result = result
                self.classification = type("_C", (), {"code": "PNP_NET_REMOTE_UNREADABLE"})()

        with patch("pnp.gitutils.subprocess.run", side_effect=[failing, failing]):
            with patch("pnp.gitutils.resolver.resolve.decide",
                       return_value=_Decision(utils.StepResult.RETRY)):
                with patch("pnp.gitutils._retry_delay_seconds", return_value=0.0):
                    rc, out = gitutils.run_git(["push", "origin"], cwd=".")
        self.assertEqual(rc, 65)
        self.assertIn("idempotency guard", out)

    def test_run_git_circuit_breaker_for_repeated_code_failures(self) -> None:
        const.sync_runtime_flags(_args(dry_run=False))
        failing = CompletedProcess(
            args=["git", "push"],
            returncode=1,
            stdout="",
            stderr="fatal: could not resolve host: github.com",
        )

        class _Decision:
            def __init__(self, result: utils.StepResult):
                self.result = result
                self.classification = type("_C", (), {"code": "PNP_NET_CONNECTIVITY"})()

        custom_policy = {"retryable": True, "max_retries": 10, "base_delay_s": 0.0, "max_delay_s": 0.0, "jitter_s": 0.0}
        with patch("pnp.gitutils.subprocess.run", side_effect=[failing, failing, failing, failing]):
            with patch("pnp.gitutils.resolver.resolve.decide",
                       return_value=_Decision(utils.StepResult.RETRY)):
                with patch("pnp.gitutils._retry_policy_for", return_value=custom_policy):
                    rc, out = gitutils.run_git(["push", "origin"], cwd=".")
        self.assertEqual(rc, 75)
        self.assertIn("circuit breaker", out)

    def test_run_git_upstream_missing_uses_resolver_retry(self) -> None:
        const.sync_runtime_flags(_args(dry_run=False))
        failing = CompletedProcess(
            args=["git", "push"],
            returncode=1,
            stdout="",
            stderr="fatal: no upstream configured for branch 'main'",
        )
        success = CompletedProcess(
            args=["git", "push"],
            returncode=0,
            stdout="ok",
            stderr="",
        )

        class _Decision:
            def __init__(self, result: utils.StepResult):
                self.result = result
                self.classification = type("_C", (), {"code": "PNP_GIT_UPSTREAM_MISSING"})()

        with patch("pnp.gitutils.subprocess.run", side_effect=[failing, success]) as run_cmd:
            with patch("pnp.gitutils.resolver.resolve.decide",
                       return_value=_Decision(utils.StepResult.RETRY)) as decide:
                with patch("pnp.gitutils._retry_delay_seconds", return_value=0.0):
                    rc, out = gitutils.run_git(["push", "origin"], cwd=".")
        self.assertEqual(rc, 0)
        self.assertEqual(out, "ok")
        self.assertEqual(run_cmd.call_count, 2)
        decide.assert_called_once()


if __name__ == "__main__":
    unittest.main()
