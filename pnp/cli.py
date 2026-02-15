#!/usr/bin/env python3
"""
Primary CLI entry point for the `pnp` automation tool.

This module orchestrates the end-to-end workflow for
preparing and publishing a Python package or monorepo
component.

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
from __future__ import annotations

# ======================= STANDARDS =======================
import argparse
import shutil
import subprocess
import sys

# ======================== LOCALS =========================
from . import _constants as const
from . import __version__
from .help_menu import help_msg
from . import config
from . import utils
from .ops import run_hook, manage_git_extension_install
from .ops import show_effective_config
from . import audit as flow_ops
from . import workflow_engine as engine_mod

DOCTOR_SCHEMA = flow_ops.DOCTOR_SCHEMA
CHECK_SCHEMA = flow_ops.CHECK_SCHEMA


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=help_msg())
    p.add_argument(
        "--version",
        action="version",
        version=f"pnp {__version__}",
    )
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
    p.add_argument("--traverse", "-t", dest="machete_traverse",
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
    p.add_argument("--tag-message", default=None)
    p.add_argument("--edit-message", action="store_true")
    p.add_argument("--editor", default=None)
    p.add_argument("--tag-sign", action="store_true")
    p.add_argument("--tag-bump", choices=["major", "minor",
                   "patch"], default="patch")
    return p


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Add and parse arguments."""
    p = _build_parser()
    parsed = p.parse_args(argv)
    return config.apply_layered_config(parsed, argv, p)


def _find_repo_noninteractive(path: str) -> str | None:
    """Compatibility wrapper for tests/patching."""
    return flow_ops._find_repo_noninteractive(path)


def run_doctor(path: str, out: utils.Output,
               json_mode: bool = False,
               report_file: str | None = None) -> int:
    """Compatibility wrapper for extracted doctor implementation."""
    return flow_ops.run_doctor(
        path,
        out,
        json_mode=json_mode,
        report_file=report_file,
        repo_finder=_find_repo_noninteractive,
    )


def run_check_only(args: argparse.Namespace,
                   out: utils.Output) -> int:
    """Compatibility wrapper for extracted check-only implementation."""
    return flow_ops.run_check_only(
        args,
        out,
        doctor_fn=run_doctor,
        repo_finder=_find_repo_noninteractive,
    )


def _run_hook_proxy(cmd: str, cwd: str, dryrun: bool,
                    no_transmission: bool = False) -> int:
    """Bridge for legacy patch points (`pnp.cli.run_hook`)."""
    return run_hook(cmd, cwd, dryrun, no_transmission=no_transmission)


# Keep workflow engine bound to cli-level patch targets used by tests.
engine_mod.run_hook = _run_hook_proxy

_WorkflowOrchestrator = engine_mod.Orchestrator


class Orchestrator(_WorkflowOrchestrator):
    """Compatibility wrapper around extracted workflow engine."""

    def __init__(self, argv: list[str] | argparse.Namespace,
                 repo_path: str | None = None):
        if isinstance(argv, list):
            argv = parse_args(argv)
        super().__init__(argv, repo_path=repo_path)

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
    if args.batch_commit and not args.verbose:
        args.quiet = True
    const.sync_runtime_flags(args)
    out  = utils.Output(quiet=args.quiet)
    code = 0
    try:
        if args.install_git_ext and args.uninstall_git_ext:
            out.warn("choose only one: --install-git-ext or --uninstall-git-ext")
            code = 1
            return None
        if args.show_config:
            code = show_effective_config(args, out)
            return None
        if args.check_only or args.check_json:
            code = run_check_only(args, out)
            return None
        if args.install_git_ext:
            code = manage_git_extension_install(out, uninstall=False,
                                                target_dir=args.git_ext_dir)
            return None
        if args.uninstall_git_ext:
            code = manage_git_extension_install(out, uninstall=True,
                                                target_dir=args.git_ext_dir)
            return None
        if args.doctor:
            code = run_doctor(
                args.path,
                out,
                json_mode=args.doctor_json,
                report_file=args.doctor_report,
            )
            return None
        if args.batch_commit:
            paths = utils.find_repo(
                args.path,
                batch=True,
                return_none=False,
            )
        else:
            paths = [None]
        for path in paths:
            orchestrator = Orchestrator(args, path)
            orchestrator.orchestrate()
    except BaseException as e:
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
        status = out.success if code == 0 else out.warn
        status("done"); out.raw(); sys.exit(code)
