#!/usr/bin/env python3
"""
Primary CLI entry point for the `pnp` automation tool.

This module orchestrates the end-to-end workflow for
preparing and publishing changes for any Git-based project
or monorepo component.

It handles:
  - Parsing command-line arguments
  - Detecting and initializing Git repositories
  - Running pre-push hooks (e.g., linting, tests)
  - Generating changelogs from Git history
  - Staging and committing changes
  - Tagging with semantic versioning
  - Optionally publishing GitHub releases with assets

Supports dry-run, interactive, auto-fix, and quiet modes for
safety and flexibility. All output is routed through a
utility transmission system for styling and formatting
consistency.

Uses `main` as the safe entry point to invoke the
CLI.
"""


# ======================= STANDARDS =======================
import argparse
import json
import sys
import os

# ======================== LOCALS =========================
from .ops import manage_git_extension_install, show_effective_config
from .debug_report import build_debug_report
from . import telemetry
from .error_model import (
    FailureEvent,
    build_error_envelope,
    error_policy_for,
    resolve_failure_code,
)
from .audit import run_doctor, run_check_only
from .workflow_engine import Orchestrator
from . import _constants as const
from .help_menu import help_msg
from . import __version__
from . import config
from . import utils


COMMON_FAILURE_FIXES: dict[str, tuple[str, str]] = {
    "PNP_GIT_REPOSITORY_FAIL": (
        "repository discovery failed",
        "Run from a Git repository root or initialize one with `git init`.",
    ),
    "PNP_REL_HOOKS_FAIL": (
        "pre-push hooks failed",
        "Run the failing hook locally, fix it, then rerun `pnp`.",
    ),
    "PNP_GIT_MACHETE_FAIL": (
        "git-machete step failed",
        "Install/configure git-machete or disable machete flags and rerun.",
    ),
    "PNP_GIT_COMMIT_FAIL": (
        "commit step failed",
        "Inspect staged changes and commit message, then rerun.",
    ),
    "PNP_NET_PUSH_FAIL": (
        "push step failed",
        "Verify remote/auth/network, then retry push.",
    ),
    "PNP_REL_PUBLISH_FAIL": (
        "publish/tag step failed",
        "Check local tag state and remote tag permissions, then retry publish.",
    ),
    "PNP_REL_RELEASE_FAIL": (
        "release creation failed",
        "Ensure tag and GitHub token/repo flags are valid, then rerun release.",
    ),
}


def _emit_runtime_failure_ux(
    args: argparse.Namespace,
    envelope: dict[str, object],
    out: utils.Output,
) -> None:
    """Emit concise failure summary with optional advanced details."""
    code = str(envelope.get("code", "")).strip()
    step = str(envelope.get("step", "")).strip()
    message = str(envelope.get("message", "")).strip()
    summary, one_liner = COMMON_FAILURE_FIXES.get(
        code,
        ("workflow failed", "Inspect pnplog and rerun with --debug-report."),
    )
    telemetry.emit_event(
        event_type="error_signal",
        step_id=step or "orchestrate",
        payload={"code": code, "message": message},
    )
    telemetry.emit_event(
        event_type="actionable_diagnosis",
        step_id=step or "orchestrate",
        payload={
            "code": code,
            "summary": summary,
            "fix": one_liner,
        },
    )
    out.warn(f"summary: {summary}")
    out.warn(f"fix: {one_liner}")

    advanced = bool(getattr(args, "verbose", False) or getattr(args, "debug", False))
    if not advanced:
        return

    severity = str(envelope.get("severity", "")).strip()
    category = str(envelope.get("category", "")).strip()
    suggested_fix = str(envelope.get("suggested_fix", "")).strip()
    stderr_excerpt = str(envelope.get("stderr_excerpt", "")).strip()
    raw_ref = str(envelope.get("raw_ref", "")).strip()
    out.warn("advanced details:")
    out.warn(f"code={code} step={step} severity={severity} category={category}")
    if message:
        out.warn(f"message={message}")
    if stderr_excerpt:
        out.warn(f"stderr_excerpt={stderr_excerpt}")
    if suggested_fix:
        out.warn(f"suggested_fix={suggested_fix}")
    if raw_ref:
        out.warn(f"envelope_ref={raw_ref}")


def _build_runtime_error_envelope(
    args: argparse.Namespace,
    error: BaseException,
    exit_code: int,
    failure_hint: FailureEvent | dict[str, str] | None = None,
) -> dict[str, object]:
    """Build a stable envelope for non-JSON workflow failures."""
    code = "PNP_INT_UNHANDLED_EXCEPTION"
    severity = "error"
    message = str(error).strip() or "workflow failure"
    suggested_fix = "Run with --debug for traceback and inspect pnplog."

    hint_step = ""
    hint_message = ""
    hint_code = ""
    hint_severity = ""
    hint_category = ""
    if isinstance(failure_hint, FailureEvent):
        hint_step = failure_hint.step
        hint_message = failure_hint.message
        hint_code = failure_hint.code
        hint_severity = failure_hint.severity
        hint_category = failure_hint.category
    elif isinstance(failure_hint, dict):
        hint_step = str(failure_hint.get("step", "")).strip()
        hint_message = str(failure_hint.get("message", "")).strip()
        hint_code = str(failure_hint.get("code", "")).strip()
        hint_severity = str(failure_hint.get("severity", "")).strip()
        hint_category = str(failure_hint.get("category", "")).strip()

    if isinstance(error, KeyboardInterrupt):
        code = "PNP_INT_KEYBOARD_INTERRUPT"
        severity = "warn"
        message = "workflow interrupted by keyboard input"
        suggested_fix = "Rerun command when ready."
    elif isinstance(error, EOFError):
        code = "PNP_INT_EOF_INTERRUPT"
        severity = "warn"
        message = "workflow interrupted by EOF/input stream closure"
        suggested_fix = "Ensure an interactive input stream and rerun."
    elif isinstance(error, SystemExit):
        severity = "error" if exit_code else "info"
        message = f"workflow exited with code {exit_code}"
        suggested_fix = "Inspect prior step output and rerun."
        code = resolve_failure_code(
            step=hint_step,
            preferred_code=hint_code,
            fallback_code="PNP_INT_WORKFLOW_EXIT_NONZERO",
        )
        if hint_message:
            message = hint_message

    policy = error_policy_for(
        code,
        fallback_severity=severity,
        fallback_category="workflow",
    )
    severity = policy["severity"]
    category = policy["category"]
    if hint_severity:
        severity = hint_severity
    if hint_category:
        category = hint_category

    target = os.path.abspath(getattr(args, "path", "."))
    context = {
        "path": target,
        "repo": "",
        "branch": "",
        "remote": getattr(args, "remote", "") or "",
        "ci_mode": bool(getattr(args, "ci", False)),
        "dry_run": bool(getattr(args, "dry_run", False)),
    }

    step = "orchestrate"
    if hint_step:
        step = hint_step

    envelope = build_error_envelope(
        code=code,
        severity=severity,
        category=category,
        message=message,
        operation="workflow",
        step=step,
        context=context,
        actionable=True,
        retryable=False,
        user_action_required=True,
        suggested_fix=suggested_fix,
        stderr_excerpt=message[:400],
        raw_ref="pnplog/last_error_envelope.json",
    )
    return envelope.with_runtime_schema()


def _persist_runtime_error_envelope(
    args: argparse.Namespace,
    envelope: dict[str, object],
    out: utils.Output,
) -> None:
    """Persist runtime envelope to project pnplog for postmortems."""
    target = os.path.abspath(getattr(args, "path", "."))
    if os.path.isfile(target):
        target = os.path.dirname(target)
    log_dir = os.path.join(target, "pnplog")
    path = os.path.join(log_dir, "last_error_envelope.json")
    try:
        os.makedirs(log_dir, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(envelope, f, indent=2)
        telemetry.emit_event(
            event_type="runtime_error",
            step_id=str(envelope.get("step", "orchestrate")),
            payload=dict(envelope),
        )
        out.warn(f"error envelope written: {utils.pathit(path)}")
    except Exception as e:
        out.warn(f"failed to persist error envelope: {e}")


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=help_msg())
    p.add_argument("--version", action="version",
        version=f"{const.PNP}{__version__}")

    p.add_argument("--doctor", action="store_true")
    p.add_argument("--doctor-json", action="store_true")
    p.add_argument("--doctor-report", default=None)
    p.add_argument("--check-only", action="store_true")
    p.add_argument("--check-json", action="store_true")
    p.add_argument("--strict", action="store_true")
    p.add_argument("--show-config", action="store_true")
    p.add_argument("--install-git-ext", action="store_true")
    p.add_argument("--uninstall-git-ext", action="store_true")
    p.add_argument("--git-ext-dir", default=None)
    p.add_argument("--status", "-s", dest="machete_status",
                   action="store_true")
    p.add_argument("--sync", "-S", dest="machete_sync",
                   action="store_true")
    p.add_argument("--traverse", "-t",
                   dest="machete_traverse",
                   action="store_true")

    # Global arguments
    p.add_argument("path", nargs="?", default=".")
    p.add_argument("--batch-commit", "-b", action="store_true")
    p.add_argument("--hooks", default=None)
    p.add_argument("--changelog-file", default="changes.log")
    p.add_argument("--push", "-p", action="store_true")
    p.add_argument("--publish", "-P", action="store_true")
    p.add_argument("--remote", "-r", default=None)
    p.add_argument("--force", "-f", action="store_true")
    p.add_argument("--no-transmission", action="store_true")
    p.add_argument("--quiet", "-q", action="store_true")
    p.add_argument("--plain", action="store_true")
    p.add_argument("--verbose", "-v", action="store_true")
    p.add_argument("--debug", "-d", action="store_true")
    p.add_argument("--debug-report", action="store_true")
    p.add_argument("--debug-report-file", default=None)
    p.add_argument("--auto-fix", "-a", action="store_true")
    p.add_argument("--dry-run", "-n", action="store_true")
    p.add_argument("--ci", action="store_true")
    p.add_argument("--interactive", "-i", action="store_true")

    # Github arguments
    p.add_argument("--gh-release", action="store_true")
    p.add_argument("--gh-repo", default=None)
    p.add_argument("--gh-token", default=None)
    p.add_argument("--gh-draft", action="store_true")
    p.add_argument("--gh-prerelease", action="store_true")
    p.add_argument("--gh-assets", default=None)

    # Tagging arguments
    p.add_argument("--tag-prefix", default="v")
    p.add_argument("--tag-message", "-m", default=None)
    p.add_argument("--edit-message", "-e", action="store_true")
    p.add_argument("--editor", default=None)
    p.add_argument("--tag-sign", action="store_true")
    p.add_argument("--tag-bump", choices=["major", "minor",
                   "patch"], default="patch")
    return p


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Add and parse arguments."""
    parser = _build_parser()
    parsed = parser.parse_args(argv)
    return config.apply_layered_config(parsed, argv, parser)


def main() -> None:
    """
    CLI entry point for the `pnp` tool.

    Handles CLI argument parsing, mode dispatch, and
    exception management for user-friendly execution.

    Features:
    - Supports normal and batch (`--batch-commit`) modes
    - Automatically applies default tag message and verbosity
      settings in batch mode
    - Discovers one or more repositories based on provided
      path
    - Delegates execution to `Orchestrator` per discovered
      repo
    - Gracefully handles unexpected exceptions, keyboard
      interrupts, and forced exits
    - Emits a final success message on completion

    This function is intended as the main launcher for CLI
    invocation of the tool.
    """
    args = parse_args(sys.argv[1:])
    telemetry.set_run_id()
    target = os.path.abspath(getattr(args, "path", "."))
    if os.path.isfile(target):
        target = os.path.dirname(target)
    telemetry.init_event_stream(os.path.join(target, "pnplog"))
    if args.batch_commit and not args.verbose:
        args.quiet = True
    const.sync_runtime_flags(args)
    out  = utils.Output(quiet=args.quiet)
    code = 0
    last_error: BaseException | None = None
    last_failure_hint: FailureEvent | None = None
    try:
        if args.install_git_ext and args.uninstall_git_ext:
            out.warn("choose only one: "
                "--install-git-ext or --uninstall-git-ext")
            code = 1
            return None
        if args.show_config:
            code = show_effective_config(args, out)
            return None
        if args.check_only or args.check_json:
            code = run_check_only(args, out)
            return None
        if args.install_git_ext:
            code = manage_git_extension_install(out,
                   uninstall=False,
                   target_dir=args.git_ext_dir)
            return None
        if args.uninstall_git_ext:
            code = manage_git_extension_install(out,
                   uninstall=True,
                   target_dir=args.git_ext_dir)
            return None
        if args.doctor:
            code = run_doctor(args.path, out,
                   json_mode=args.doctor_json,
                   report_file=args.doctor_report)
            return None
        if args.batch_commit:
            paths = utils.find_repo(args.path, batch=True,
                    return_none=False)
        else: paths = [None]
        for path in paths:
            orchestrator = Orchestrator(args, path)
            orchestrator.orchestrate()
    except BaseException as e:
        last_error = e
        if "orchestrator" in locals():
            last_failure_hint = orchestrator.failure_hint
        code = 1
        exit = (KeyboardInterrupt, EOFError, SystemExit)
        if const.DEBUG: raise e
        if isinstance(e, SystemExit):
            if isinstance(e.code, int): code = e.code
        if not isinstance(e, exit): out.warn(f"ERROR: {e}")
        elif not isinstance(e, exit[2]):
            i = 1 if not isinstance(e, EOFError) else 2
            out.raw("\n" * i + const.PNP, end="")
            out.raw(utils.color("forced exit", const.BAD))
    finally:
        if code != 0 and last_error is not None:
            envelope = _build_runtime_error_envelope(
                args, last_error, code, last_failure_hint
            )
            _emit_runtime_failure_ux(args, envelope, out)
            _persist_runtime_error_envelope(args, envelope, out)
        if getattr(args, "debug_report", False):
            try:
                report_path = build_debug_report(args)
                out.warn(f"debug report written: {utils.pathit(str(report_path))}")
            except Exception as e:
                out.warn(f"failed to write debug report: {e}")
        status = out.success if code == 0 else out.warn
        status("done"); out.raw(); sys.exit(code)
