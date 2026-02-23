"""Resolver remediation dry-run and structured logging tests."""


from contextlib import contextmanager
from unittest.mock import patch
from subprocess import CompletedProcess
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
    def test_protected_branch_autofix_creates_feature_branch(self) -> None:
        h = resolver.Handlers()
        calls: list[list[str]] = []

        def fake_run(cmd: list[str], cwd: str, check: bool = False,
                     capture: bool = True, text: bool = True) -> CompletedProcess:
            del check, capture, text, cwd
            calls.append(cmd)
            if cmd[:2] == ["git", "remote"]:
                return CompletedProcess(cmd, 0, stdout="origin\n", stderr="")
            return CompletedProcess(cmd, 0, stdout="", stderr="")

        with _runtime_flags(auto_fix=True, dry_run=False, ci=True, interactive=False):
            with patch("pnp.resolver._run", side_effect=fake_run):
                result = h.protected_branch(
                    "remote: error: GH006: Protected branch update failed for refs/heads/main",
                    ".",
                )
        self.assertIs(result, utils.StepResult.OK)
        self.assertTrue(any(cmd[:3] == ["git", "checkout", "-b"] for cmd in calls))
        self.assertTrue(any(cmd[:3] == ["git", "push", "-u"] for cmd in calls))

    def test_dirty_worktree_autostash_retries_and_pops_on_success(self) -> None:
        h = resolver.Handlers()

        def fake_run(cmd: list[str], cwd: str, check: bool = False,
                     capture: bool = True, text: bool = True) -> CompletedProcess:
            del cwd, check, capture, text
            return CompletedProcess(cmd, 0, stdout="", stderr="")

        with _runtime_flags(auto_fix=True, dry_run=False, ci=True, interactive=False):
            with patch("pnp.resolver._run", side_effect=fake_run) as run_cmd:
                result = h.dirty_worktree(
                    "error: Your local changes to the following files would be overwritten by merge",
                    ".",
                )
                self.assertIs(result, utils.StepResult.RETRY)
                h.maybe_pop_stash(".")
        calls = [call.args[0] for call in run_cmd.call_args_list]
        self.assertTrue(any(cmd[:3] == ["git", "stash", "push"] for cmd in calls))
        self.assertTrue(any(cmd[:3] == ["git", "stash", "pop"] for cmd in calls))

    def test_detached_head_autofix_creates_recovery_branch(self) -> None:
        h = resolver.Handlers()

        def fake_run(cmd: list[str], cwd: str, check: bool = False,
                     capture: bool = True, text: bool = True) -> CompletedProcess:
            del cwd, check, capture, text
            return CompletedProcess(cmd, 0, stdout="", stderr="")

        with _runtime_flags(auto_fix=True, dry_run=False, ci=True, interactive=False):
            with patch("pnp.resolver._run", side_effect=fake_run) as run_cmd:
                result = h.detached_head(
                    "fatal: You are not currently on a branch.",
                    ".",
                )
        self.assertIs(result, utils.StepResult.RETRY)
        calls = [call.args[0] for call in run_cmd.call_args_list]
        self.assertTrue(any(cmd[:3] == ["git", "checkout", "-b"] for cmd in calls))

    def test_line_endings_autofix_creates_gitattributes_and_renormalizes(self) -> None:
        h = resolver.Handlers()
        with tempfile.TemporaryDirectory() as tmp:
            def fake_run(cmd: list[str], cwd: str, check: bool = False,
                         capture: bool = True, text: bool = True) -> CompletedProcess:
                del cwd, check, capture, text
                return CompletedProcess(cmd, 0, stdout="", stderr="")

            with _runtime_flags(auto_fix=True, dry_run=False, ci=True, interactive=False):
                with patch("pnp.resolver._run", side_effect=fake_run) as run_cmd:
                    result = h.line_endings(
                        "warning: in the working copy of 'a.txt', LF will be replaced by CRLF",
                        tmp,
                    )
            self.assertIs(result, utils.StepResult.RETRY)
            attrs = Path(tmp) / ".gitattributes"
            self.assertTrue(attrs.exists())
            self.assertIn("* text=auto", attrs.read_text(encoding="utf-8"))
            calls = [call.args[0] for call in run_cmd.call_args_list]
            self.assertTrue(any(cmd[:4] == ["git", "add", "--renormalize", "."] for cmd in calls))

    def test_line_endings_autofix_falls_back_when_renormalize_unsupported(self) -> None:
        h = resolver.Handlers()
        with tempfile.TemporaryDirectory() as tmp:
            def fake_run(cmd: list[str], cwd: str, check: bool = False,
                         capture: bool = True, text: bool = True) -> CompletedProcess:
                del cwd, check, capture, text
                if cmd[:4] == ["git", "add", "--renormalize", "."]:
                    return CompletedProcess(
                        cmd,
                        129,
                        stdout="",
                        stderr="error: unknown option `renormalize'",
                    )
                if cmd[:3] == ["git", "add", "-A"]:
                    return CompletedProcess(cmd, 0, stdout="", stderr="")
                return CompletedProcess(cmd, 0, stdout="", stderr="")

            with _runtime_flags(auto_fix=True, dry_run=False, ci=True, interactive=False):
                with patch("pnp.resolver._run", side_effect=fake_run) as run_cmd:
                    result = h.line_endings(
                        "warning: in the working copy of 'a.txt', LF will be replaced by CRLF",
                        tmp,
                    )
            self.assertIs(result, utils.StepResult.RETRY)
            calls = [call.args[0] for call in run_cmd.call_args_list]
            self.assertTrue(any(cmd[:4] == ["git", "add", "--renormalize", "."] for cmd in calls))
            self.assertTrue(any(cmd[:3] == ["git", "add", "-A"] for cmd in calls))

    def test_line_endings_autofix_rebuilds_index_on_nul_indexing_error(self) -> None:
        h = resolver.Handlers()
        with tempfile.TemporaryDirectory() as tmp:
            def fake_run(cmd: list[str], cwd: str, check: bool = False,
                         capture: bool = True, text: bool = True) -> CompletedProcess:
                del cwd, check, capture, text
                if cmd[:4] == ["git", "add", "--renormalize", "."]:
                    return CompletedProcess(
                        cmd,
                        1,
                        stdout="",
                        stderr="error: unknown option `renormalize'",
                    )
                if cmd[:3] == ["git", "add", "-A"]:
                    seen_add = getattr(fake_run, "_seen_add", 0)
                    setattr(fake_run, "_seen_add", seen_add + 1)
                    if seen_add == 0:
                        return CompletedProcess(
                            cmd,
                            128,
                            stdout="",
                            stderr=(
                                "error: short read while indexing NUL\n"
                                "error: NUL: failed to insert into database\n"
                                "error: unable to index 'NUL'\n"
                                "fatal: unable to stat 'missing/file.txt': No such file or directory"
                            ),
                        )
                    return CompletedProcess(cmd, 0, stdout="", stderr="")
                if cmd[:3] == ["git", "reset", "--mixed"]:
                    return CompletedProcess(cmd, 0, stdout="", stderr="")
                return CompletedProcess(cmd, 0, stdout="", stderr="")

            with _runtime_flags(auto_fix=True, dry_run=False, ci=True, interactive=False):
                with patch("pnp.resolver._run", side_effect=fake_run) as run_cmd:
                    result = h.line_endings(
                        "warning: in the working copy of 'a.txt', LF will be replaced by CRLF",
                        tmp,
                    )
            self.assertIs(result, utils.StepResult.RETRY)
            calls = [call.args[0] for call in run_cmd.call_args_list]
            self.assertTrue(any(cmd[:4] == ["git", "add", "--renormalize", "."] for cmd in calls))
            self.assertGreaterEqual(sum(1 for cmd in calls if cmd[:3] == ["git", "add", "-A"]), 2)
            self.assertTrue(any(cmd[:3] == ["git", "reset", "--mixed"] for cmd in calls))

    def test_line_endings_autofix_rebuilds_index_when_primary_renormalize_hits_nul(self) -> None:
        h = resolver.Handlers()
        with tempfile.TemporaryDirectory() as tmp:
            def fake_run(cmd: list[str], cwd: str, check: bool = False,
                         capture: bool = True, text: bool = True) -> CompletedProcess:
                del cwd, check, capture, text
                if cmd[:4] == ["git", "add", "--renormalize", "."]:
                    return CompletedProcess(
                        cmd,
                        128,
                        stdout="",
                        stderr=(
                            "error: short read while indexing NUL\n"
                            "error: NUL: failed to insert into database\n"
                            "error: unable to index 'NUL'\n"
                            "fatal: unable to stat 'missing/file.txt': No such file or directory"
                        ),
                    )
                if cmd[:3] == ["git", "reset", "--mixed"]:
                    return CompletedProcess(cmd, 0, stdout="", stderr="")
                if cmd[:3] == ["git", "add", "-A"]:
                    return CompletedProcess(cmd, 0, stdout="", stderr="")
                return CompletedProcess(cmd, 0, stdout="", stderr="")

            with _runtime_flags(auto_fix=True, dry_run=False, ci=True, interactive=False):
                with patch("pnp.resolver._run", side_effect=fake_run) as run_cmd:
                    result = h.line_endings(
                        "warning: in the working copy of 'a.txt', LF will be replaced by CRLF",
                        tmp,
                    )
            self.assertIs(result, utils.StepResult.RETRY)
            calls = [call.args[0] for call in run_cmd.call_args_list]
            self.assertTrue(any(cmd[:4] == ["git", "add", "--renormalize", "."] for cmd in calls))
            self.assertTrue(any(cmd[:3] == ["git", "reset", "--mixed"] for cmd in calls))
            self.assertTrue(any(cmd[:3] == ["git", "add", "-A"] for cmd in calls))

    def test_index_worktree_mismatch_handler_rebuilds_index_and_retries(self) -> None:
        h = resolver.Handlers()
        calls: list[list[str]] = []

        def fake_run(cmd: list[str], cwd: str, check: bool = False,
                     capture: bool = True, text: bool = True) -> CompletedProcess:
            del cwd, check, capture, text
            calls.append(cmd)
            return CompletedProcess(cmd, 0, stdout="", stderr="")

        with _runtime_flags(auto_fix=True, dry_run=False, ci=True, interactive=False):
            with patch("pnp.resolver._run", side_effect=fake_run):
                result = h.index_worktree_mismatch(
                    "error: short read while indexing NUL\n"
                    "error: unable to index 'NUL'\n"
                    "fatal: unable to stat 'missing/file.txt': No such file or directory",
                    ".",
                )
        self.assertIs(result, utils.StepResult.RETRY)
        self.assertTrue(any(cmd[:3] == ["git", "reset", "--mixed"] for cmd in calls))
        self.assertTrue(any(cmd[:3] == ["git", "add", "-A"] for cmd in calls))

    def test_index_worktree_mismatch_non_autofix_decline_does_not_run_recovery(self) -> None:
        h = resolver.Handlers()
        calls: list[list[str]] = []

        def fake_run(cmd: list[str], cwd: str, check: bool = False,
                     capture: bool = True, text: bool = True) -> CompletedProcess:
            del cwd, check, capture, text
            calls.append(cmd)
            return CompletedProcess(cmd, 0, stdout="", stderr="")

        with _runtime_flags(auto_fix=False, dry_run=False, ci=False, interactive=True):
            with patch("builtins.input", return_value="n"):
                with patch("pnp.resolver._run", side_effect=fake_run):
                    result = h.index_worktree_mismatch(
                        "error: short read while indexing NUL\n"
                        "error: unable to index 'NUL'\n"
                        "fatal: unable to stat 'missing/file.txt': No such file or directory",
                        ".",
                    )
        self.assertIs(result, utils.StepResult.FAIL)
        self.assertEqual(calls, [])

    def test_large_file_rejection_autofix_tracks_lfs_and_amends(self) -> None:
        h = resolver.Handlers()
        calls: list[list[str]] = []

        def fake_run(cmd: list[str], cwd: str, check: bool = False,
                     capture: bool = True, text: bool = True) -> CompletedProcess:
            del cwd, check, capture, text
            calls.append(cmd)
            return CompletedProcess(cmd, 0, stdout="", stderr="")

        with _runtime_flags(auto_fix=True, dry_run=False, ci=True, interactive=False):
            with patch("pnp.resolver._run", side_effect=fake_run):
                result = h.large_file_rejection(
                    "remote: error: File build/app.bin is 120.00 MB; this exceeds GitHub's file size limit of 100.00 MB",
                    ".",
                )
        self.assertIs(result, utils.StepResult.RETRY)
        self.assertTrue(any(cmd[:3] == ["git", "lfs", "version"] for cmd in calls))
        self.assertTrue(any(cmd[:3] == ["git", "lfs", "track"] for cmd in calls))
        self.assertTrue(any(cmd[:3] == ["git", "commit", "--amend"] for cmd in calls))

    def test_diverged_branch_autofix_runs_pull_rebase(self) -> None:
        h = resolver.Handlers()
        calls: list[list[str]] = []

        def fake_run(cmd: list[str], cwd: str, check: bool = False,
                     capture: bool = True, text: bool = True) -> CompletedProcess:
            del cwd, check, capture, text
            calls.append(cmd)
            if cmd[:4] == ["git", "branch", "--show-current"]:
                return CompletedProcess(cmd, 0, stdout="main\n", stderr="")
            if cmd[:2] == ["git", "remote"]:
                return CompletedProcess(cmd, 0, stdout="origin\n", stderr="")
            return CompletedProcess(cmd, 0, stdout="", stderr="")

        with _runtime_flags(auto_fix=True, dry_run=False, ci=True, interactive=False):
            with patch("pnp.resolver._run", side_effect=fake_run):
                result = h.diverged_branch(
                    "! [rejected] main -> main (non-fast-forward)",
                    ".",
                )
        self.assertIs(result, utils.StepResult.RETRY)
        self.assertTrue(any(cmd[:3] == ["git", "pull", "--rebase"] for cmd in calls))

    def test_diverged_branch_conflict_opens_shell_in_interactive_mode(self) -> None:
        h = resolver.Handlers()
        calls: list[list[str]] = []

        def fake_run(cmd: list[str], cwd: str, check: bool = False,
                     capture: bool = True, text: bool = True) -> CompletedProcess:
            del cwd, check, capture, text
            calls.append(cmd)
            if cmd[:4] == ["git", "branch", "--show-current"]:
                return CompletedProcess(cmd, 0, stdout="main\n", stderr="")
            if cmd[:2] == ["git", "remote"]:
                return CompletedProcess(cmd, 0, stdout="origin\n", stderr="")
            if cmd[:3] == ["git", "pull", "--rebase"]:
                return CompletedProcess(
                    cmd,
                    1,
                    stdout="",
                    stderr="CONFLICT (content): Merge conflict in README.md",
                )
            return CompletedProcess(cmd, 0, stdout="", stderr="")

        with _runtime_flags(auto_fix=False, dry_run=False, ci=False, interactive=True):
            with patch("builtins.input", return_value="1"):
                with patch("pnp.resolver.get_shell", return_value="/bin/sh"):
                    with patch("pnp.resolver._run", side_effect=fake_run):
                        result = h.diverged_branch(
                            "! [rejected] main -> main (non-fast-forward)",
                            ".",
                        )
        self.assertIs(result, utils.StepResult.RETRY)
        self.assertTrue(any(cmd == ["/bin/sh"] for cmd in calls))

    def test_hook_declined_can_retry_push_with_no_verify(self) -> None:
        h = resolver.Handlers()
        calls: list[list[str]] = []

        def fake_run(cmd: list[str], cwd: str, check: bool = False,
                     capture: bool = True, text: bool = True) -> CompletedProcess:
            del cwd, check, capture, text
            calls.append(cmd)
            if cmd[:4] == ["git", "branch", "--show-current"]:
                return CompletedProcess(cmd, 0, stdout="main\n", stderr="")
            if cmd[:2] == ["git", "remote"]:
                return CompletedProcess(cmd, 0, stdout="origin\n", stderr="")
            return CompletedProcess(cmd, 0, stdout="", stderr="")

        with _runtime_flags(auto_fix=False, dry_run=False, ci=False, interactive=True):
            with patch("builtins.input", return_value="1"):
                with patch("pnp.resolver._run", side_effect=fake_run):
                    result = h.hook_declined("error: pre-push hook declined", ".")
        self.assertIs(result, utils.StepResult.OK)
        self.assertTrue(any(cmd[:4] == ["git", "push", "--no-verify", "origin"] for cmd in calls))

    def test_hook_declined_surfaces_extracted_failure_hints(self) -> None:
        h = resolver.Handlers()
        sample = (
            "error: pre-push hook declined\n"
            "running pytest -q\n"
            "FAILED tests/test_api.py::test_ping - AssertionError\n"
        )
        with _runtime_flags(auto_fix=False, dry_run=False, ci=False, interactive=True):
            with patch("builtins.input", return_value="3"):
                with patch.object(h, "warn") as warn_mock:
                    with self.assertRaises(SystemExit):
                        h.hook_declined(sample, ".")
        joined = "\n".join(str(call.args[0]) for call in warn_mock.call_args_list if call.args)
        self.assertIn("detected hook:", joined)
        self.assertIn("suspected failing command: pytest -q", joined)
        self.assertIn("first failure signal:", joined)

    def test_hook_declined_emits_structured_hook_details(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            resolver.configure_logger(Path(tmp))
            h = resolver.Handlers()
            sample = (
                "error: pre-push hook declined\n"
                "running pytest -q\n"
                "FAILED tests/test_api.py::test_ping - AssertionError\n"
            )
            calls: list[list[str]] = []

            def fake_run(cmd: list[str], cwd: str, check: bool = False,
                         capture: bool = True, text: bool = True) -> CompletedProcess:
                del cwd, check, capture, text
                calls.append(cmd)
                if cmd[:4] == ["git", "branch", "--show-current"]:
                    return CompletedProcess(cmd, 0, stdout="main\n", stderr="")
                if cmd[:2] == ["git", "remote"]:
                    return CompletedProcess(cmd, 0, stdout="origin\n", stderr="")
                return CompletedProcess(cmd, 0, stdout="", stderr="")

            with _runtime_flags(auto_fix=False, dry_run=False, ci=False, interactive=True):
                with patch("builtins.input", return_value="1"):
                    with patch("pnp.resolver._run", side_effect=fake_run):
                        result = h.hook_declined(sample, tmp)
            self.assertIs(result, utils.StepResult.OK)

            events = Path(tmp) / "events.jsonl"
            self.assertTrue(events.exists())
            rows = [json.loads(x) for x in events.read_text(encoding="utf-8").splitlines()]
            rem = [e for e in rows if e.get("event_type") == "remediation"]
            analyses = [
                e for e in rem
                if isinstance(e.get("payload"), dict)
                and e["payload"].get("action") == "hook_failure_analysis"
            ]
            self.assertTrue(analyses)
            detail = analyses[-1]["payload"].get("details", {})
            self.assertEqual(detail.get("command"), "pytest -q")
            self.assertIn("pre-push hook declined", str(detail.get("hook")))

    def test_submodule_inconsistent_autofix_runs_sync_update(self) -> None:
        h = resolver.Handlers()
        calls: list[list[str]] = []

        def fake_run(cmd: list[str], cwd: str, check: bool = False,
                     capture: bool = True, text: bool = True) -> CompletedProcess:
            del cwd, check, capture, text
            calls.append(cmd)
            return CompletedProcess(cmd, 0, stdout="", stderr="")

        with _runtime_flags(auto_fix=True, dry_run=False, ci=True, interactive=False):
            with patch("pnp.resolver._run", side_effect=fake_run):
                result = h.submodule_inconsistent(
                    "fatal: remote error: upload-pack: not our ref deadbeef",
                    ".",
                )
        self.assertIs(result, utils.StepResult.RETRY)
        self.assertTrue(any(cmd[:4] == ["git", "submodule", "sync", "--recursive"] for cmd in calls))
        self.assertTrue(any(cmd[:5] == ["git", "submodule", "update", "--init", "--recursive"] for cmd in calls))

    def test_submodule_inconsistent_interactive_fetch_prune(self) -> None:
        h = resolver.Handlers()
        calls: list[list[str]] = []

        def fake_run(cmd: list[str], cwd: str, check: bool = False,
                     capture: bool = True, text: bool = True) -> CompletedProcess:
            del cwd, check, capture, text
            calls.append(cmd)
            return CompletedProcess(cmd, 0, stdout="", stderr="")

        stderr = "fatal: remote error: upload-pack: not our ref deadbeef in submodule path 'libs/core'"
        with _runtime_flags(auto_fix=False, dry_run=False, ci=False, interactive=True):
            with patch("builtins.input", return_value="2"):
                with patch("pnp.resolver._run", side_effect=fake_run):
                    result = h.submodule_inconsistent(stderr, ".")
        self.assertIs(result, utils.StepResult.RETRY)
        self.assertTrue(
            any(
                cmd[:8] == ["git", "-C", "libs/core", "fetch", "--all", "--tags", "--prune"]
                for cmd in calls
            )
        )

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
