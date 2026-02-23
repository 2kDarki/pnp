"""Resolver remediation dry-run and structured logging tests."""


from contextlib import contextmanager
from unittest.mock import patch
from argparse import Namespace
from pathlib import Path
import tempfile
import unittest
import json

from pnp import _constants as const
from pnp import resolver
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


@contextmanager
def _runtime_flags(**overrides: object):
    before = {
        "AUTOFIX": const.AUTOFIX,
        "DRY_RUN": const.DRY_RUN,
        "CI_MODE": const.CI_MODE,
        "GH_REPO": const.GH_REPO,
        "ALLOW_SAFE_RESET": const.ALLOW_SAFE_RESET,
        "ALLOW_DESTRUCTIVE_RESET": const.ALLOW_DESTRUCTIVE_RESET,
    }
    const.sync_runtime_flags(_args(**overrides))
    try:
        yield
    finally:
        const.AUTOFIX = before["AUTOFIX"]
        const.DRY_RUN = before["DRY_RUN"]
        const.CI_MODE = before["CI_MODE"]
        const.GH_REPO = before["GH_REPO"]
        const.ALLOW_SAFE_RESET = before["ALLOW_SAFE_RESET"]
        const.ALLOW_DESTRUCTIVE_RESET = before["ALLOW_DESTRUCTIVE_RESET"]


class ResolverRemediationTests(unittest.TestCase):
    def test_dry_run_simulates_safe_directory_remediation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            resolver.configure_logger(Path(tmp))
            h = resolver.Handlers()
            with _runtime_flags(auto_fix=True, dry_run=True, ci=True, interactive=False):
                with patch("pnp.resolver._run") as run_cmd:
                    result = h.dubious_ownership(
                        "fatal: detected dubious ownership in repository "
                        f"at '{tmp}'\n"
                        f"git config --global --add safe.directory {tmp}",
                        tmp,
                    )
            self.assertIs(result, utils.StepResult.RETRY)
            run_cmd.assert_not_called()

            events = Path(tmp) / "events.jsonl"
            self.assertTrue(events.exists())
            lines = [json.loads(x) for x in events.read_text(encoding="utf-8").splitlines()]
            rem = [e for e in lines if e.get("event_type") == "remediation"]
            self.assertTrue(rem)
            payloads = [e.get("payload", {}) for e in rem]
            self.assertTrue(any(p.get("action") == "git_safe_directory" and p.get("outcome") == "simulated" for p in payloads))
            self.assertTrue(all("run_id" in e for e in rem))
            self.assertTrue(any(e.get("step_id") == "git_safe_directory" for e in rem))

    def test_invalid_object_logs_blocked_destructive_action_in_autofix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            resolver.configure_logger(Path(tmp))
            h = resolver.Handlers()
            with _runtime_flags(auto_fix=True, dry_run=True, ci=True, interactive=False):
                with patch("pnp.resolver._run") as run_cmd:
                    result = h.invalid_object("null sha1", tmp)
            self.assertIs(result, utils.StepResult.OK)
            called = [call.args[0] for call in run_cmd.call_args_list if call.args]
            self.assertTrue(called)
            self.assertFalse(any(cmd[:2] == ["git", "reset"] for cmd in called))
            self.assertFalse(any(cmd[:2] == ["rm", ".git/index"] for cmd in called))

            events = Path(tmp) / "events.jsonl"
            lines = [json.loads(x) for x in events.read_text(encoding="utf-8").splitlines()]
            blocked = [
                e for e in lines
                if e.get("event_type") == "remediation"
                and isinstance(e.get("payload"), dict)
                and e["payload"].get("action") == "destructive_reset"
                and e["payload"].get("outcome") == "blocked"
            ]
            self.assertTrue(blocked)

    def test_lock_contention_removes_shallow_lock(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            resolver.configure_logger(Path(tmp))
            git_dir = Path(tmp) / ".git"
            git_dir.mkdir(parents=True, exist_ok=True)
            lock = git_dir / "shallow.lock"
            lock.write_text("busy", encoding="utf-8")
            h = resolver.Handlers()
            with _runtime_flags(auto_fix=True, dry_run=False, ci=True, interactive=False):
                result = h.lock_contention(
                    "fatal: Unable to create '.git/shallow.lock': File exists",
                    tmp,
                )
            self.assertIs(result, utils.StepResult.RETRY)
            self.assertFalse(lock.exists())

    def test_autofix_safe_fix_network_requires_explicit_flag(self) -> None:
        h = resolver.Handlers()
        with _runtime_flags(auto_fix=True, dry_run=False, ci=True, interactive=False):
            allowed, reason = h._allow_remediation("safe_fix_network")
        self.assertFalse(allowed)
        self.assertIn("--safe-reset", reason)

    def test_autofix_destructive_reset_requires_explicit_flag(self) -> None:
        h = resolver.Handlers()
        with _runtime_flags(auto_fix=True, dry_run=False, ci=True, interactive=False):
            allowed, reason = h._allow_remediation("destructive_reset")
        self.assertFalse(allowed)
        self.assertIn("--destructive-reset", reason)

    def test_autofix_safe_fix_network_allowed_with_flag(self) -> None:
        h = resolver.Handlers()
        with _runtime_flags(
            auto_fix=True,
            dry_run=False,
            ci=True,
            interactive=False,
            safe_reset=True,
        ):
            allowed, reason = h._allow_remediation("safe_fix_network")
        self.assertTrue(allowed)
        self.assertEqual(reason, "")


if __name__ == "__main__":
    unittest.main()
