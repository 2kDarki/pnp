"""Sequence tests for orchestrator non-happy control-flow chains."""


from argparse import Namespace
import unittest

from pnp.workflow_engine import Orchestrator
from pnp import utils


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
        "tag_message": None,
        "tag_sign": False,
        "tag_bump": "patch",
        "doctor": False,
        "doctor_json": False,
        "doctor_report": None,
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


class OrchestratorSequenceTests(unittest.TestCase):
    def test_fail_stops_following_steps(self) -> None:
        o = Orchestrator(_args(), repo_path=".")
        calls: list[str] = []

        def ok(name: str):
            def _fn(step_idx: int | None = None):
                calls.append(name)
                return None, utils.StepResult.OK
            return _fn

        def fail(name: str):
            def _fn(step_idx: int | None = None):
                calls.append(name)
                return None, utils.StepResult.FAIL
            return _fn

        o.find_repo = ok("find_repo")  # type: ignore[method-assign]
        o.run_hooks = fail("run_hooks")  # type: ignore[method-assign]
        o.run_machete = ok("run_machete")  # type: ignore[method-assign]
        o.stage_and_commit = ok("stage_and_commit")  # type: ignore[method-assign]
        o.push = ok("push")  # type: ignore[method-assign]
        o.publish = ok("publish")  # type: ignore[method-assign]
        o.release = ok("release")  # type: ignore[method-assign]

        with self.assertRaises(SystemExit) as ex:
            o.orchestrate()
        self.assertEqual(ex.exception.code, 1)
        self.assertEqual(calls, ["find_repo", "run_hooks"])

    def test_skip_chain_then_abort_short_circuits(self) -> None:
        o = Orchestrator(_args(), repo_path=".")
        calls: list[str] = []

        def ok(name: str):
            def _fn(step_idx: int | None = None):
                calls.append(name)
                return None, utils.StepResult.OK
            return _fn

        def skip(name: str):
            def _fn(step_idx: int | None = None):
                calls.append(name)
                return None, utils.StepResult.SKIP
            return _fn

        def abort(name: str):
            def _fn(step_idx: int | None = None):
                calls.append(name)
                return ("simulated abort", False), utils.StepResult.ABORT
            return _fn

        o.find_repo = ok("find_repo")  # type: ignore[method-assign]
        o.run_hooks = skip("run_hooks")  # type: ignore[method-assign]
        o.run_machete = skip("run_machete")  # type: ignore[method-assign]
        o.stage_and_commit = ok("stage_and_commit")  # type: ignore[method-assign]
        o.push = abort("push")  # type: ignore[method-assign]
        o.publish = ok("publish")  # type: ignore[method-assign]
        o.release = ok("release")  # type: ignore[method-assign]

        with self.assertRaises(SystemExit) as ex:
            o.orchestrate()
        self.assertEqual(ex.exception.code, 1)
        self.assertEqual(
            calls,
            ["find_repo", "run_hooks", "run_machete", "stage_and_commit", "push"],
        )


if __name__ == "__main__":
    unittest.main()
