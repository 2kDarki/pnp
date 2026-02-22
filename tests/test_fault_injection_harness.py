"""Fault injection harness for step-level workflow failure policies."""


from argparse import Namespace
import unittest

from pnp.cli import _build_runtime_error_envelope
from pnp.error_model import WORKFLOW_STEP_CODES
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
        "debug_report": False,
        "debug_report_file": None,
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


def _inject_failure(
    orchestrator: Orchestrator,
    failing_step: str,
    outcome: utils.StepResult,
    detail: str,
    calls: list[str],
) -> None:
    step_map = {
        "repository": "find_repo",
        "hooks": "run_hooks",
        "machete": "run_machete",
        "commit": "stage_and_commit",
        "push": "push",
        "publish": "publish",
        "release": "release",
    }
    if failing_step not in step_map:
        raise ValueError(f"unknown step: {failing_step}")
    failing_method = step_map[failing_step]
    passed_failure = False

    for key, method_name in step_map.items():
        if method_name == failing_method:
            passed_failure = True
            continue
        if passed_failure:
            def _after(
                step_idx: int | None = None,
                method_name: str = method_name,
            ) -> tuple[str | None, utils.StepResult]:
                calls.append(method_name)
                return None, utils.StepResult.OK
            setattr(orchestrator, method_name, _after)  # type: ignore[method-assign]
            continue

        def _ok(
            step_idx: int | None = None,
            method_name: str = method_name,
        ) -> tuple[str | None, utils.StepResult]:
            calls.append(method_name)
            return None, utils.StepResult.OK

        setattr(orchestrator, method_name, _ok)  # type: ignore[method-assign]

    if outcome is utils.StepResult.ABORT:
        payload: str | tuple[str, bool] = (detail, False)
    else:
        payload = detail

    def _fail(step_idx: int | None = None) -> tuple[str | tuple[str, bool], utils.StepResult]:
        calls.append(failing_method)
        return payload, outcome

    setattr(orchestrator, failing_method, _fail)  # type: ignore[method-assign]


class FaultInjectionHarnessTests(unittest.TestCase):
    def test_fault_injection_matrix_policy_and_emitted_code(self) -> None:
        cases = [
            ("repository", utils.StepResult.ABORT, "git process failed during repository discovery"),
            ("hooks", utils.StepResult.FAIL, "filesystem permission denied for hook output"),
            ("machete", utils.StepResult.ABORT, "git process failure in machete status"),
            ("commit", utils.StepResult.FAIL, "index.lock prevents commit"),
            ("push", utils.StepResult.ABORT, "network auth failed while pushing to remote"),
            ("publish", utils.StepResult.ABORT, "tag conflict: already exists on remote"),
            ("release", utils.StepResult.FAIL, "release conflict: GitHub API rejected tag"),
        ]
        expected_codes = WORKFLOW_STEP_CODES.copy()
        expected_result = {
            utils.StepResult.FAIL: "fail",
            utils.StepResult.ABORT: "abort",
        }
        method_order = [
            "find_repo",
            "run_hooks",
            "run_machete",
            "stage_and_commit",
            "push",
            "publish",
            "release",
        ]
        method_by_step = {
            "repository": "find_repo",
            "hooks": "run_hooks",
            "machete": "run_machete",
            "commit": "stage_and_commit",
            "push": "push",
            "publish": "publish",
            "release": "release",
        }
        for step, outcome, detail in cases:
            with self.subTest(step=step, outcome=outcome.name):
                o = Orchestrator(_args(), repo_path=".")
                calls: list[str] = []
                _inject_failure(o, step, outcome, detail, calls)
                with self.assertRaises(SystemExit) as ex:
                    o.orchestrate()
                self.assertEqual(ex.exception.code, 1)
                assert o.failure_hint is not None
                self.assertEqual(o.failure_hint.step, step)
                self.assertEqual(o.failure_hint.code, expected_codes[step])
                self.assertEqual(o.failure_hint.result, expected_result[outcome])
                expected_chain = method_order[: method_order.index(method_by_step[step]) + 1]
                self.assertEqual(calls, expected_chain)

                envelope = _build_runtime_error_envelope(
                    _args(),
                    SystemExit(1),
                    exit_code=1,
                    failure_hint=o.failure_hint,
                )
                self.assertEqual(envelope["code"], expected_codes[step])
                self.assertEqual(envelope["step"], step)
                self.assertEqual(envelope["schema"], "pnp.error_envelope.v1")
                self.assertEqual(envelope["schema_version"], 1)


if __name__ == "__main__":
    unittest.main()
