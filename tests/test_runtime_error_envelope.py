"""Tests for runtime error-envelope code mapping."""


from argparse import Namespace
import unittest

from pnp.cli import _build_runtime_error_envelope
from pnp.error_model import FailureEvent


def _args(**overrides: object) -> Namespace:
    base: dict[str, object] = {
        "path": ".",
        "remote": None,
        "ci": True,
        "dry_run": False,
    }
    base.update(overrides)
    return Namespace(**base)


class RuntimeErrorEnvelopeTests(unittest.TestCase):
    def test_system_exit_without_hint_uses_generic_code(self) -> None:
        payload = _build_runtime_error_envelope(
            _args(),
            SystemExit(1),
            exit_code=1,
            failure_hint=None,
        )
        self.assertEqual(payload["code"], "PNP_INT_WORKFLOW_EXIT_NONZERO")
        self.assertEqual(payload["step"], "orchestrate")

    def test_repository_failure_maps_to_repository_code(self) -> None:
        payload = _build_runtime_error_envelope(
            _args(),
            SystemExit(1),
            exit_code=1,
            failure_hint={"step": "repository", "message": "no git repository found"},
        )
        self.assertEqual(payload["code"], "PNP_GIT_REPOSITORY_FAIL")
        self.assertEqual(payload["step"], "repository")

    def test_hooks_failure_maps_to_hooks_code(self) -> None:
        payload = _build_runtime_error_envelope(
            _args(),
            SystemExit(1),
            exit_code=1,
            failure_hint={"step": "hooks", "message": "hook failed"},
        )
        self.assertEqual(payload["code"], "PNP_REL_HOOKS_FAIL")
        self.assertEqual(payload["step"], "hooks")

    def test_machete_failure_maps_to_machete_code(self) -> None:
        payload = _build_runtime_error_envelope(
            _args(),
            SystemExit(1),
            exit_code=1,
            failure_hint={"step": "machete", "message": "git-machete failed"},
        )
        self.assertEqual(payload["code"], "PNP_GIT_MACHETE_FAIL")
        self.assertEqual(payload["step"], "machete")

    def test_commit_failure_maps_to_commit_code(self) -> None:
        payload = _build_runtime_error_envelope(
            _args(),
            SystemExit(1),
            exit_code=1,
            failure_hint={"step": "commit", "message": "git commit failed"},
        )
        self.assertEqual(payload["code"], "PNP_GIT_COMMIT_FAIL")
        self.assertEqual(payload["step"], "commit")

    def test_push_failure_maps_to_push_code(self) -> None:
        payload = _build_runtime_error_envelope(
            _args(),
            SystemExit(1),
            exit_code=1,
            failure_hint={"step": "push", "message": "git push failed"},
        )
        self.assertEqual(payload["code"], "PNP_NET_PUSH_FAIL")
        self.assertEqual(payload["step"], "push")

    def test_publish_failure_maps_to_publish_code(self) -> None:
        payload = _build_runtime_error_envelope(
            _args(),
            SystemExit(1),
            exit_code=1,
            failure_hint={"step": "publish", "message": "tag creation failed"},
        )
        self.assertEqual(payload["code"], "PNP_REL_PUBLISH_FAIL")
        self.assertEqual(payload["step"], "publish")

    def test_release_failure_maps_to_release_code(self) -> None:
        payload = _build_runtime_error_envelope(
            _args(),
            SystemExit(1),
            exit_code=1,
            failure_hint={"step": "release", "message": "release failed"},
        )
        self.assertEqual(payload["code"], "PNP_REL_RELEASE_FAIL")
        self.assertEqual(payload["step"], "release")

    def test_resolver_hint_code_uses_git_category_policy(self) -> None:
        payload = _build_runtime_error_envelope(
            _args(),
            SystemExit(1),
            exit_code=1,
            failure_hint={
                "step": "push",
                "message": "could not read from remote",
                "code": "PNP_NET_REMOTE_UNREADABLE",
            },
        )
        self.assertEqual(payload["code"], "PNP_NET_REMOTE_UNREADABLE")
        self.assertEqual(payload["severity"], "error")
        self.assertEqual(payload["category"], "network")

    def test_deprecated_hint_code_is_canonicalized(self) -> None:
        payload = _build_runtime_error_envelope(
            _args(),
            SystemExit(1),
            exit_code=1,
            failure_hint={
                "step": "push",
                "message": "legacy code input",
                "code": "PNP_RES_REMOTE_UNREADABLE",
            },
        )
        self.assertEqual(payload["code"], "PNP_NET_REMOTE_UNREADABLE")
        self.assertEqual(payload["category"], "network")

    def test_unhandled_exception_uses_internal_category_policy(self) -> None:
        payload = _build_runtime_error_envelope(
            _args(),
            RuntimeError("boom"),
            exit_code=1,
            failure_hint=None,
        )
        self.assertEqual(payload["code"], "PNP_INT_UNHANDLED_EXCEPTION")
        self.assertEqual(payload["severity"], "error")
        self.assertEqual(payload["category"], "internal")

    def test_typed_failure_hint_without_code_maps_by_step(self) -> None:
        payload = _build_runtime_error_envelope(
            _args(),
            SystemExit(1),
            exit_code=1,
            failure_hint=FailureEvent(
                step="publish",
                label="Publish tag",
                result="abort",
                message="publish aborted",
            ),
        )
        self.assertEqual(payload["code"], "PNP_REL_PUBLISH_FAIL")
        self.assertEqual(payload["step"], "publish")


if __name__ == "__main__":
    unittest.main()
