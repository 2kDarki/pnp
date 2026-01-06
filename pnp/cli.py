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
# ======================= STANDARDS =======================
from datetime import datetime
from typing import NoReturn
from pathlib import Path
import subprocess
import argparse
import time
import sys
import os
import re

# ==================== THIRD-PARTIES ======================
from tuikit.textools import strip_ansi

# ======================== LOCALS =========================
from ._constants import DRYRUN, PNP, INFO, GOOD, BAD
from ._constants import CI_MODE, CURSOR, DEBUG
from .help_menu import wrap, help_msg
from . import utils


def run_hook(cmd: str, cwd: str, dryrun: bool) -> int:
    """
    Run a validated hook command safely with optional dry-run.

    NB: This function is not to be misunderstood as being
        'safe' against malicious hooks — that's strictly none
        of my business. So the few guards that are present
        are just me guarding against my own absentmindedness.
    """
    # Reject unsafe shell characters
    if re.search(r'[$&;|><`()]', cmd):
        err = f"rejected potentially unsafe hook: {cmd!r}"
        raise ValueError(err)

    # Decide whether to capture output based on CLI flags and
    # exclusions
    exclude = "drace", "pytest"
    capture = "--no-transmission" not in sys.argv \
          and not utils.any_in(exclude, eq=cmd)

    # Support optional prefix via 'type::command' format
    # Parse and validate command
    parts  = cmd.split("::")
    prefix = "run"
    if len(parts) == 2: prefix, cmd = parts
    args = cmd.split()

    # Blacklist disallowed commands
    disallowed = {
        "rm", "mv", "dd", "shutdown", "reboot", "mkfs",
        "kill", "killall", ">:(", "sudo", "tsu", "chown",
        "chmod", "wget", "curl"
    }
    if args[0] in disallowed:
        err = f"hook command '{args[0]}' not allowed"
        raise ValueError(err)

    # Add [dry-run] status if in dry-run mode and exit early
    # to simulate success
    add = f" {DRYRUN}skips" if dryrun else ""
    m   = utils.wrap(f"[{prefix}] {cmd}{add}")
    utils.transmit(m, fg=GOOD)
    if dryrun: return 0

    if "pytest" in cmd: print()

    # Run the shell command
    # NB: DON'T REMOVE `shell=True`!!! HOOKS WILL NOT WORK!!!
    proc   = subprocess.run(cmd, cwd=cwd, shell=True,
             check=True, text=True, capture_output=capture)
    code   = proc.returncode
    stdout = proc.stdout
    stderr = proc.stderr
    if not capture or stderr: print()
    if code != 0:
        err = f"[{code}]: {cmd} {stderr}"
        raise RuntimeError(err)

    if capture:
        for line in stdout.splitlines():
            print(line); time.sleep(0.005)
        print()
    return code


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Add and parse arguments."""
    p = argparse.ArgumentParser(description=help_msg())

    # Global arguments
    p.add_argument('path', nargs='?', default='.')
    p.add_argument('--batch-commit', '-b', action='store_true')
    p.add_argument('--hooks', default=None)
    p.add_argument('--changelog-file', default="changes.log")
    p.add_argument('--push', '-p', action='store_true')
    p.add_argument('--publish', '-P', action='store_true')
    p.add_argument('--remote', '-r', default=None)
    p.add_argument('--force', '-f', action='store_true')
    p.add_argument('--no-transmission', action='store_true')
    p.add_argument('--quiet', '-q', action='store_true')
    p.add_argument('--verbose', '-v', action='store_true')
    p.add_argument('--debug', '-d', action='store_true')
    p.add_argument('--auto-fix', '-a', action='store_true')
    p.add_argument('--dry-run', '-n', action='store_true')
    p.add_argument('--ci', action='store_true')
    p.add_argument('--interactive', '-i', action='store_true')

    # Github arguments
    p.add_argument("--gh-release", action="store_true")
    p.add_argument("--gh-repo", default=None)
    p.add_argument("--gh-token", default=None)
    p.add_argument("--gh-draft", action="store_true")
    p.add_argument("--gh-prerelease", action="store_true")
    p.add_argument("--gh-assets", default=None)

    # Tagging arguments
    p.add_argument('--tag-prefix', default='v')
    p.add_argument('--tag-message', default=None)
    p.add_argument('--tag-sign', action='store_true')
    p.add_argument('--tag-bump', choices=['major', 'minor',
                   'patch'], default='patch')

    return p.parse_args(argv)


class Orchestrator:
    """
    Main orchestrator for the pnp CLI tool.

    Orchestrates the full release workflow including:
      - Parsing CLI arguments and resolving paths
      - Locating or initializing a Git repository
      - Handling monorepo package detection
      - Executing pre-push hooks
      - Generating changelog between self.latest tag and HEAD
      - Optionally staging and committing uncommitted changes
      - Writing changelog to file if specified
      - Pushing changes and tags
      - Creating GitHub releases and uploading assets

    Supports dry-run and quiet modes for safe evaluation and
    silent execution.
    """

    def __init__(self, argv: list[str] | argparse.Namespace,
                 repo_path: str | None = None):
        """
        Initialize the orchestrator for the `pnp` CLI tool.

        Parses CLI arguments, resolves the working directory,
        sets up output behavior, and initializes key
        attributes used in the release process (e.g. Git repo
        path, changelog data, etc.).

        If `argv` is not provided (i.e. normal execution),
        the full workflow is immediately triggered via
        `self.orchestrate()`.

        Args:
            argv (list[str] | None): Optional CLI arguments
            for testing purposes. Defaults to `sys.argv[1:]`
            when not provided.
        """
        if isinstance(argv, list): argv = parse_args(argv)

        self.args: argparse.Namespace = argv
        self.path       = os.path.abspath(repo_path
                       or self.args.path)
        self.out        = utils.Output(quiet=self.args.quiet)
        self.repo       = None
        self.subpkg     = None
        self.gitutils   = None
        self.resolver   = None
        self.latest     = None
        self.commit_msg = None
        self.tag        = None
        self.log_dir    = None
        self.log_text   = None

    def orchestrate(self) -> None | NoReturn:
        """
        Execute the full release workflow.

        Runs a predefined series of steps in sequence,
        including:
          - Locating or initializing a Git repository
          - Running pre-push hooks
          - Staging and committing changes
          - Pushing to the remote repository
          - Publishing to package registries
          - Creating GitHub releases

        Each step returns a message and a `StepResult` enum
        that determines control flow:
          - SKIP: silently continues to the next step
          - FAIL: exits with code 1
          - ABORT: prints error and terminates

        If `--dry-run` is enabled, no actual changes are made
        and a reassuarance/confirmation message is shown.
        """
        steps = [
            self.find_repo,
            self.run_hooks,
            self.stage_and_commit,
            self.push,
            self.publish,
            self.release,
        ]

        for step in steps:
            msg, result = step()
            if result is utils.StepResult.DONE: return None
            if result is utils.StepResult.SKIP: continue
            if result is utils.StepResult.FAIL: sys.exit(1)
            if result is utils.StepResult.ABORT:
                if isinstance(msg, tuple):
                    self.out.abort(*msg)
                else: self.out.abort(msg)

        if self.args.dry_run:
            self.out.success(DRYRUN + "no changes made")

        return None

    def find_repo(self) -> tuple[str
                         | None, utils.StepResult]:
        """
        Locate the Git repository root and sets up project
        context.

        Attempts to find the repository starting from the
        provided path. If none is found and not in CI mode,
        prompts the user to initialize a new repository.

        Also:
          - Initializes logging directory
          - Dynamically imports Git-related modules
          - Detects monorepo subpackages if applicable

        Returns:
            tuple[str | None, StepResult]: An optional error
            message and a StepResult indicating whether to
            continue, fail, or abort.
        """
        try:
            self.repo = utils.find_repo(self.path)

            # Setup logging and import runtime-dependent
            # modules
            self.log_dir = utils.get_log_dir(self.repo)
            modules      = utils.import_deps()
        except RuntimeError:
            if not CI_MODE:
                prompt = utils.wrap("no repo found. "
                       + "Initialize here? [y/n]")
                if utils.intent(prompt, "y", "return"):
                    self.log_dir = utils.get_log_dir(
                                   self.path)
                    modules = utils.import_deps()
                    modules[0].git_init(self.path)
                    self.repo = self.path
                else:
                    result = utils.StepResult.ABORT
                    if self.args.batch_commit:
                        result = utils.StepResult.DONE
                    return None, result
            else:
                return "no git repository found", \
                       utils.StepResult.ABORT

        self.gitutils, self.resolver = modules
        self.out.success(f"repo root: {self.repo}")

        # monorepo detection: are we in a package folder?
        subpkg = utils.detect_subpackage(self.path, self.repo)
        if subpkg:
            self.subpkg = subpkg
            msg = "operating on detected package at: " \
                + f"{utils.pathit(self.subpkg)}\n"
            self.out.success(msg)
        else: self.subpkg = self.repo

        return None, utils.StepResult.OK

    def run_hooks(self) -> tuple[str
                         | None, utils.StepResult]:
        """
        Execute pre-push shell hooks defined via CLI
        arguments.

        Parses and runs each hook command, respecting dry-run
        mode.

        If a hook fails:
          - In CI mode: the process fails immediately.
          - Otherwise: user is prompted whether to continue
                       or abort.

        Skips execution entirely if no hooks are provided.

        Returns:
            tuple[str | None, StepResult]: An optional
            message and a StepResult indicating whether to
            continue, fail, or abort.
        """
        if not self.args.hooks:
            return None, utils.StepResult.SKIP

        hooks = [h.strip() for h in self.args.hooks.split(';'
                ) if h.strip()]
        self.out.info('running hooks:\n' + utils
            .to_list(hooks))
        for i, cmd in enumerate(hooks):
            try:
                run_hook(cmd, self.subpkg, self.args.dry_run)
                if not self.args.dry_run and i < len(hooks
                        ) - 1:
                    if "drace" not in cmd: print()
            except (RuntimeError, ValueError) as e:
                msg = " ".join(e.args[0].split())
                if isinstance(e, RuntimeError):
                    msg = f"hook failed {msg}"
                self.out.warn(msg)
                prompt = "hook failed. Continue? [y/n]"
                if CI_MODE:
                    return None, utils.StepResult.FAIL
                if utils.intent(prompt, "n", "return"):
                    msg = "aborting due to hook failure"
                    return msg, utils.StepResult.ABORT

        if self.args.dry_run: print()

        return None, utils.StepResult.OK

    def gen_changelog(self, get: bool = False) -> None\
                                                | Path:
        """
        Generate a changelog from the latest Git tag to HEAD.

        If `get` is True, returns the resolved changelog file
        path without generating the changelog. Otherwise,
        generates the changelog text, optionally writes it to
        a specified file, and prints it to the output stream.

        In dry-run mode:
          - No changes are written to disk.
          - A mock commit message can be passed to simulate
            output.

        Handles exceptions gracefully and displays contextual
        error messages, especially in dry-run mode where
        changelog generation may fail due to skipped
        operations.

        Args:
            get (bool): If True, returns the changelog file
                        path without running the generation
                        process.

        Returns:
            None | Path: Returns the changelog path if `get`
                         is True; otherwise, returns None.
        """
        tags        = self.gitutils.tags_sorted(self.repo)
        self.latest = tags[0] if tags else None
        timestamp   = datetime.now().isoformat()[:-7]

        if self.args.changelog_file:
            log_file = self.args.changelog_file
            if os.sep not in log_file:
                log_file = self.log_dir / Path(log_file)

        if get: return log_file

        msg = self.commit_msg if self.args.dry_run else None
        hue = GOOD
        div = f"------| {timestamp} |------"
        try:
            self.log_text = utils.gen_changelog(
                            self.repo, since=self.latest,
                            dry_run=msg) + "\n"
        except Exception as e:
            hue = BAD
            add = ""
            if self.args.dry_run and "ambiguous" in e.args[0]:
                add = "NB: Potentially due to dry-run "\
                    + "skipping certain processes\n"
            self.log_text = utils.color("changelog "
                          + f"generation failed: {e}{add}\n",
                            hue)

        # log changes
        self.out.raw(PNP, end="")
        prompt = utils.color("changelog↴\n", hue)
        self.out.raw(wrap(prompt))
        self.out.raw(utils.Align().center(div, "-"))
        self.out.raw(wrap(self.log_text), end="")
        if not self.args.dry_run and self.args.changelog_file:
            os.makedirs(log_file.parent, exist_ok=True)
            with open(log_file, 'a+', encoding='utf-8') as f:
                f.write(strip_ansi(f"{div}\n{self.log_text}"))

        return None

    def stage_and_commit(self) -> tuple[tuple[str, bool]
                                | None, utils.StepResult]:
        """
        Stage and commit any uncommitted changes in the
        target directory.

        If no changes are found, the latest changelog is
        retrieved and the step is skipped. Otherwise, prompts
        the user (if not in CI mode) to confirm staging and
        committing. In dry-run mode, actions are logged but
        not executed.

        Generates a commit message either automatically or
        via user input, and stores it for later use. After
        committing, the changelog is regenerated to reflect
        the new commit.

        Returns:
            tuple[tuple[str, bool] | None, utils.StepResult]:
              - (error_msg, False), ABORT if an error occurs
              - None, SKIP if no changes are found
              - None, OK if commit is successful
        """
        if not self.gitutils.has_uncommitted(self.subpkg):
            log_file      = self.gen_changelog(get=True)
            self.log_text = utils\
                .retrieve_latest_changelog(log_file)
            self.out.success('no changes to commit')
            return None, utils.StepResult.SKIP

        if not CI_MODE:
            prompt = utils.wrap("uncommitted changes "
                   + "found. Stage and commit? [y/n]")
            if utils.intent(prompt, "n", "return"):
                return None, utils.StepResult.ABORT
        try:
            if not self.args.dry_run:
                self.gitutils.stage_all(self.subpkg)
            else: self.out.prompt(DRYRUN + "skipping...")

            msg = self.args.tag_message\
               or utils.gen_commit_message(self.subpkg)

            if not CI_MODE:
                m = "enter commit message. Type 'no' to " \
                  + "exclude commit message"
                self.out.prompt(m)
                m = input(CURSOR).strip() or "no"
                self.out.raw()
                msg = msg if m.lower() == "no" else m

            self.commit_msg = msg

            if not self.args.dry_run:
                self.gitutils.commit(self.subpkg, msg)
            else:
                prompt = DRYRUN + f"would commit {msg!r}"
                self.out.prompt(prompt)
        except Exception as e:
            e = self.resolver.normalize_stderr(e)
            return (f'{e}\n', False), utils.StepResult.ABORT

        # generate changelog between self.latest and HEAD
        self.gen_changelog()
        return None, utils.StepResult.OK

    def push(self) -> tuple[str
                    | tuple[str, bool]
                    | None, utils.StepResult]:
        """
        Push local commits to a remote Git repository.

        Fetches all remotes and determines the current
        branch. If no branch is detected and not in dry-run
        mode, aborts. Otherwise, checks if the remote is
        ahead of the local branch. If so, prompts for force
        push (unless in CI mode or force is pre-specified).

        Handles push execution with optional force, excluding
        tags. Supports dry-run mode where actual push is
        skipped but flow continues with user prompts.

        Returns:
            tuple[str | tuple[str, bool] | None,
            utils.StepResult]
              - error_msg, ABORT if fetch fails or branchless
              - (error_msg, False), ABORT if push fails
              - None, SKIP if push flag is not set
              - None, OK if push succeeds
        """
        if not self.args.push:
            return None, utils.StepResult.SKIP

        try: self.gitutils.fetch_all(self.repo)
        except Exception as e:
            self.out.warn(self.resolver.normalize_stderr(e), False)
            if CI_MODE and not self.args.dry_run:
                return None, utils.StepResult.ABORT
            self.out.prompt(DRYRUN + "continuing regardless")

        branchless = False
        branch     = self.gitutils.current_branch(self.subpkg)
        if not branch:
            self.out.warn("no branch detected")
            if not self.args.dry_run:
                return None, utils.StepResult.ABORT
            self.out.prompt(DRYRUN + "continuing regardless")
            branchless = True

        if not branchless:
            upstream = self.args.remote or self.gitutils\
                       .upstream_for_branch(self.subpkg,
                       branch)
            if upstream:
                remote_name = upstream.split('/')[0]
            else: remote_name = self.args.remote or 'origin'
        else: upstream = None

        # check ahead/behind
        force = False
        if upstream:
            counts = self.gitutils.rev_list_counts(self.repo,
                     upstream, branch)
            if counts:
                remote_ahead, _ = counts
                if remote_ahead > 0:
                    m = f"remote ({upstream}) ahead by " \
                      + f"{remote_ahead} commit(s)"
                    self.out.warn(m)
                    if self.args.force: force = True
                    elif not CI_MODE:
                        msg   = utils.wrap("force push and "
                              + "overwrite remote? [y/n]")
                        force = utils.intent(msg, "y",
                                "return")
                    else: return None, utils.StepResult.ABORT

        if not branchless:
            try: self.gitutils.push(self.repo,
                    remote=remote_name,
                    branch=branch,
                    force=force,
                    push_tags=False)
            except Exception as e:
                msg = self.resolver.normalize_stderr(e), False
                return msg, utils.StepResult.ABORT

        return None, utils.StepResult.OK

    def publish(self) -> tuple[str
                       | tuple[str, bool]
                       | None, utils.StepResult]:
        """
        Create and push a new Git tag based on the latest
        tag and version bump strategy.

        If `--publish` is not set, skips the step. Computes
        the new tag using the specified version bump and
        optional prefix, then creates the tag (signed or
        annotated) and pushes it to the remote.

        Handles dry-run mode by skipping actual tag creation
        and push but displaying the intended actions.

        Returns:
            tuple[str | tuple[str, bool] | None,
            utils.StepResult]:
              - Error message or (message, False), ABORT if
                tag creation or push fails.
              - None, SKIP if publishing is disabled.
              - None, OK if tag creation and push succeed.
        """
        if not self.args.publish:
            return None, utils.StepResult.SKIP

        self.tag = utils.bump_semver_from_tag(
                   self.latest or '', self.args.tag_bump,
                   prefix=self.args.tag_prefix)
        self.out.success(utils.wrap(f"new tag: {self.tag}"))

        if self.args.dry_run:
            msg = DRYRUN + "would create tag " \
                + utils.color(self.tag, INFO)
            self.out.prompt(msg)
        else:
            try: self.gitutils.create_tag(self.repo, self.tag,
                 message=self.args.tag_message
                 or self.log_text, sign=self.args.tag_sign)
            except Exception as e:
                return f"tag creation failed: {e}", \
                       utils.StepResult.ABORT

            try: self.gitutils.push(self.repo,
                 remote=self.args.remote or 'origin',
                 branch=None, force=self.args.force,
                 push_tags=True)
            except Exception as e:
                e = self.resolver.normalize_stderr(e,
                    'failed to push tags:')
                return (e, False), utils.StepResult.ABORT

        return None, utils.StepResult.OK

    def release(self) -> tuple[tuple[str, bool]
                       | None, utils.StepResult]:
        """
        Create a GitHub release for the current tag and
        optionally uploads assets.

        Checks for required GitHub token (`--gh-token` or
        `GITHUB_TOKEN`) and repository (`--gh-repo`). If both
        are provided, creates a release with the changelog as
        the body, and optionally marks it as a draft or
        prerelease.

        If `--gh-assets` is specified, uploads the given file
        paths (comma-separated) as release assets.

        Supports dry-run mode by skipping actual API calls
        while displaying intended actions.

        Returns:
            tuple[tuple[str, bool] | None, utils.StepResult]:
              - (Error message, False), ABORT if GitHub
                release raises an error
              - None, FAIL if required inputs are missing.
              - None, SKIP if GitHub release is not enabled.
              - None, OK if the release (and assets) are
                successfully created or dry-run simulated.
        """
        if not self.args.gh_release:
            return None, utils.StepResult.SKIP

        token = self.args.gh_token \
             or os.environ.get("GITHUB_TOKEN")
        if not token:
            m = "GitHub token required for release. Set " \
              + "--gh-token or GITHUB_TOKEN env var"
            self.out.warn(m)
            if not self.args.dry_run:
                return None, utils.StepResult.FAIL
        if not self.args.gh_repo:
            self.out.warn("--gh-repo required for GitHub release")
            if not self.args.dry_run:
                return None, utils.StepResult.FAIL

        from . import github as gh

        self.out.success(f"creating GitHub release for tag {self.tag}")

        if self.args.dry_run:
            self.out.prompt(DRYRUN + "skipping process...")
        else:
            release_info = gh.create_release(token,
                           self.args.gh_repo, self.tag,
                           self.tag, self.log_text,
                           self.args.gh_draft,
                           self.args.gh_prerelease)

        if self.args.gh_assets:
            files = [f.strip() for f in self.args.gh_assets
                    .split(",") if f.strip()]
            for fpath in files:
                self.out.success(f"uploading asset: {fpath}")
                if self.args.dry_run:
                    self.out.prompt(DRYRUN + "skipping process...")
                else:
                    try: gh.upload_asset(token,
                         self.args.gh_repo,
                         release_info["id"], fpath)
                    except RuntimeError as e:
                        e = self.resolver.normalize_stderr(e)
                        return (e, False), \
                               utils.StepResult.ABORT

        return None, utils.StepResult.OK


def main() -> NoReturn:
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
    batch = utils.any_in("-b", "--batch-commit", eq=sys.argv)
    noisy = utils.any_in("-v", "--verbose", eq=sys.argv)
    if batch and not noisy: sys.argv.append("-q")

    args = parse_args(sys.argv[1:])
    out  = utils.Output(quiet=args.quiet)
    code = 0
    try:
        paths = utils.find_repo(args.path, batch, True)
        for path in paths:
            orchestrator = Orchestrator(args, path)
            orchestrator.orchestrate()
    except BaseException as e:
        code = 1
        exit = (KeyboardInterrupt, EOFError, SystemExit)
        if DEBUG: raise e
        if isinstance(e, SystemExit):
            if isinstance(e.code, int): code = e.code
        if not isinstance(e, exit): out.warn(f"ERROR: {e}")
        elif not isinstance(e, exit[2]):
            i = 1 if not isinstance(e, EOFError) else 2
            out.raw("\n" * i + PNP, end="")
            out.raw(utils.color("forced exit", BAD))
    finally:
        status = out.success if code == 0 else out.warn
        status("done"); out.raw(); sys.exit(code)
