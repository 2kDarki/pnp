"""Seeded stress tests for fault injection paths and retry timing variance."""


from argparse import Namespace
import unittest
import random
import os

from pnp.error_model import WORKFLOW_STEP_CODES
from pnp.workflow_engine import Orchestrator
from pnp import gitutils
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
    failing_method = step_map[failing_step]

    for method_name in step_map.values():
        def _ok(
            step_idx: int | None = None,
            method_name: str = method_name,
        ) -> tuple[str | None, utils.StepResult]:
            calls.append(method_name)
            return None, utils.StepResult.OK

        setattr(orchestrator, method_name, _ok)  # type: ignore[method-assign]

    payload: str | tuple[str, bool] = detail
    if outcome is utils.StepResult.ABORT:
        payload = (detail, False)

    def _fail(step_idx: int | None = None) -> tuple[str | tuple[str, bool], utils.StepResult]:
        calls.append(failing_method)
        return payload, outcome

    setattr(orchestrator, failing_method, _fail)  # type: ignore[method-assign]


class FaultInjectionStressTests(unittest.TestCase):
    def test_seeded_fault_injection_stress(self) -> None:
        seed = int(os.environ.get("PNP_STRESS_SEED", "7"))
        iterations = int(os.environ.get("PNP_STRESS_ITERATIONS", "25"))
        rng = random.Random(seed)
        steps = list(WORKFLOW_STEP_CODES.keys())
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
        for _ in range(iterations):
            step = rng.choice(steps)
            outcome = rng.choice((utils.StepResult.FAIL, utils.StepResult.ABORT))
            detail = f"seeded fault at {step}"
            o = Orchestrator(_args(), repo_path=".")
            calls: list[str] = []
            _inject_failure(o, step, outcome, detail, calls)
            with self.assertRaises(SystemExit):
                o.orchestrate()
            assert o.failure_hint is not None
            self.assertEqual(o.failure_hint.step, step)
            self.assertEqual(o.failure_hint.code, WORKFLOW_STEP_CODES[step])
            expected_chain = method_order[: method_order.index(method_by_step[step]) + 1]
            self.assertEqual(calls, expected_chain)

    def test_seeded_retry_delay_variance_bounds(self) -> None:
        seed = int(os.environ.get("PNP_STRESS_SEED", "7"))
        runs = int(os.environ.get("PNP_STRESS_RETRY_SAMPLES", "40"))
        policy = {
            "base_delay_s": 0.25,
            "max_delay_s": 2.0,
            "jitter_s": 0.10,
        }
        random.seed(seed)
        first = [gitutils._retry_delay_seconds(tries=1, policy=policy) for _ in range(runs)]
        random.seed(seed)
        second = [gitutils._retry_delay_seconds(tries=1, policy=policy) for _ in range(runs)]
        self.assertEqual(first, second)
        self.assertTrue(any(first[i] != first[i - 1] for i in range(1, len(first))))
        base = min(policy["base_delay_s"] * (2 ** 1), policy["max_delay_s"])
        low = base
        high = base + policy["jitter_s"]
        self.assertTrue(all(low <= d <= high for d in first))


if __name__ == "__main__":
    unittest.main()
