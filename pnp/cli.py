#!/usr/bin/env python3
"""
Primary CLI entry point for the `pnp` automation tool

This module orchestrates the end-to-end workflow for
preparing and publishing a Python package or monorepo
component

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
consistency

Uses `main_wrapper()` as the safe entry point to invoke the
CLI
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

# ==================== THIRD-PARTIES ======================
from tuikit.textools import strip_ansi

# ======================== LOCALS =========================
from ._constants import DRYRUN, PNP, INFO, GOOD, BAD
from ._constants import CI_MODE, CURSOR
from .help_menu import wrap, help_msg
from . import utils


def run_hook(cmd: str, cwd: str = None, dryrun: bool = False,
            ) -> int | NoReturn:
    """Run a shell hook command with optional dry-run and quiet modes"""
    # Decide whether to capture output based on CLI flags and
    # exclusions
    exclude = "drace", "pytest"
    capture = "--no-transmission" not in sys.argv \
          and not utils.any_in(exclude, eq=cmd)

    # Support optional prefix via 'type::command' format
    info    = cmd.split("::")
    prefix  = "run"
    if len(info) == 2: prefix, cmd = info

    # Add [dry-run] status if in dry-run mode and exit early
    # to simulate success
    add = f" {DRYRUN}skips" if dryrun else ""
    m   = utils.wrap(f"[{prefix}] {cmd}{add}")
    utils.transmit(m, fg=GOOD)
    if dryrun: return 0

    if "pytest" in cmd: print()

    # Run the shell command
    proc   = subprocess.run(cmd, cwd=cwd, shell=True,
             text=True, capture_output=capture)
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


def parse_args(argv: list[str]) -> argparse.ArgumentParser:
    """Add and parse arguments"""
    p = argparse.ArgumentParser(description=help_msg())

    # Global arguments
    p.add_argument('path', nargs='?', default='.')
    p.add_argument('--push', '-p', action='store_true')
    p.add_argument('--publish', '-P', action='store_true')
    p.add_argument('--dry-run', '-d', action='store_true')
    p.add_argument('--force', '-f', action='store_true')
    p.add_argument('--remote', '-r', default=None)
    p.add_argument('--hooks', default=None)
    p.add_argument('--changelog-file', default="changes.log")
    p.add_argument('--no-transmission', action='store_true')
    p.add_argument('--ci', action='store_true')
    p.add_argument('--auto-fix', '-a', action='store_true')
    p.add_argument('--quiet', '-q', action='store_true')
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


def main(argv: list[str] | None = None) -> None | NoReturn:
    """
    Main orchestrator for the pnp CLI tool

    Orchestrates the full release workflow including:
      - Parsing CLI arguments and resolving paths
      - Locating or initializing a Git repository
      - Handling monorepo package detection
      - Executing pre-push hooks
      - Generating changelog between latest tag and HEAD
      - Optionally staging and committing uncommitted changes
      - Writing changelog to file if specified
      - Pushing changes and tags
      - Creating GitHub releases and uploading assets

    Supports dry-run and quiet modes for safe evaluation and
    silent execution

    Args:
        argv (list[str] | None): Optional argument list for
        testing

    Returns:
        None or exits the program on error or completion.
    """
    args = parse_args(argv or sys.argv[1:])
    path = os.path.abspath(args.path)
    out  = utils.Output(quiet=args.quiet)

    # =================== FIND GIT ROOT ===================
    try:
        repo_root = utils.find_repo(path)

        # Setup logging and import runtime-dependent modules
        log_dir = utils.get_log_dir(repo_root)
        gitutils, giterr = utils.import_deps()
    except RuntimeError:
        if not CI_MODE:
            prompt = utils.wrap("no repo found. Initialize"
                   + " here? [y/n]")
            if utils.intent(prompt, "y", "return"):
                log_dir = utils.get_log_dir(path)
                gitutils, giterr = utils.import_deps()
                gitutils.git_init(path)
                repo_root = path
            else:
                out.abort()
        else:
            out.abort("no git repository found")

    out.success(f"repo root: {repo_root}")

    # monorepo detection: are we in a package folder?
    subpkg = utils.detect_subpackage(path, repo_root)
    if subpkg:
        op_path = subpkg
        msg = "operating on detected package at: " \
            + f"{utils.pathit(op_path)}\n"
        out.success(msg)
    else: op_path = repo_root

    # ============= RUN PRE-PUSH HOOKS IF ANY =============
    if args.hooks:
        hooks = [h.strip() for h in args.hooks.split(';') if
                h.strip()]
        out.info('running hooks:\n' + utils.to_list(hooks))
        for i, cmd in enumerate(hooks):
            try:
                run_hook(cmd, op_path, args.dry_run)
                if not args.dry_run and i < len(hooks) - 1:
                    if "drace" not in cmd: print()
            except Exception as e:
                msg = " ".join(e.args[0].split())
                msg = f"hook failed {msg}"
                out.warn(msg)
                prompt = "hook failed. Continue? [y/n]"
                if CI_MODE: sys.exit(1)
                if utils.intent(prompt, "n", "return"):
                    msg = "aborting due to hook failure"
                    out.abort(msg)

        if args.dry_run: print()

    # ============= PREPARE FOR CHANGELOG GEN =============
    tags      = gitutils.tags_sorted(repo_root)
    latest    = tags[0] if tags else None
    timestamp = datetime.now().isoformat()[:-7]

    if args.changelog_file:
        log_file = args.changelog_file
        if os.sep not in log_file:
            log_file = log_dir / Path(log_file)

    # ============= STAGE & COMMIT IF NEEDED ==============
    if gitutils.has_uncommitted(op_path):
        if not CI_MODE:
            prompt = utils.wrap("uncommitted changes "
                   + "found. Stage and commit? [y/n]")
            if utils.intent(prompt, "n", "return"):
                out.abort()
        try:
            if not args.dry_run: gitutils.stage_all(op_path)
            else: out.prompt(DRYRUN + "skipping...")

            msg = utils.gen_commit_message(op_path)

            if not CI_MODE:
                m = "enter commit message. Type 'no' to " \
                  + "exclude commit message"
                out.prompt(m)
                m   = input(CURSOR).strip() or "no"; print()
                msg = msg if m.lower() == "no" else m
            if not args.dry_run:
                gitutils.commit(op_path, message=msg)
            else:
                prompt = DRYRUN + f"would commit {msg!r}"
                out.prompt(prompt)
        except Exception as e:
            e = giterr.normalize_stderr(e)
            out.abort(f'{e}\n', False)

        # generate changelog between latest and HEAD
        hue   = GOOD
        stamp = f"------| {timestamp} |------\n"
        try:
            log_text = stamp + utils.gen_changelog(repo_root,
                       since=latest) + "\n"
        except Exception as e:
            hue = BAD
            add = ""
            if args.dry_run and "ambiguous" in e.args[0]:
                add = "NB: Potentially due to dry-run "\
                    + "skipping certain processes\n"
            log_text = stamp + utils.color("changelog "
                     + f"generation failed: {e}{add}\n", hue)

        # log changes
        out.raw(PNP, end="")
        prompt = utils.color("changelog↴\n\n", hue)
        out.raw(wrap(prompt + log_text), end="")
        if not args.dry_run and args.changelog_file:
            with open(log_file, 'a+') as f:
                f.write(strip_ansi(log_text))

    else:
        log_text = utils.retrieve_latest_changelog(log_file)
        out.success('no changes to commit')

    # ==================== PUSH LOGIC =====================
    if args.push:
        # fetch
        try: gitutils.fetch_all(repo_root)
        except Exception as e:
            if CI_MODE and not args.dry_run: raise
            exc = giterr.normalize_stderr(e)
            out.warn(exc, False)
            out.prompt(DRYRUN + "would have aborted")

        branchless = False
        branch     = gitutils.current_branch(op_path)
        if not branch:
            out.warn("no branch detected")
            if not args.dry_run:
                out.abort()
            out.prompt(DRYRUN + "would have aborted")
            branchless = True

        if not branchless:
            upstream = args.remote or gitutils\
                      .upstream_for_branch(op_path, branch)
            if upstream:
                remote_name = upstream.split('/')[0]
            else: remote_name = args.remote or 'origin'
        else: upstream = None

        # check ahead/behind
        do_force = False
        if upstream:
            counts = gitutils.rev_list_counts(repo_root,
                     upstream, branch)
            if counts:
                remote_ahead, _ = counts
                if remote_ahead > 0:
                    m = f"remote ({upstream}) ahead by " \
                      + f"{remote_ahead} commit(s)"
                    out.warn(m)
                    if args.force: do_force = True
                    elif not CI_MODE:
                        msg = utils.wrap("force push and "
                            + "overwrite remote? [y/n]")
                        do_force = utils.intent(msg, "y",
                                   "return")
                    else:
                        out.abort()

        if not branchless:
            try: gitutils.push(repo_root,
                    remote=remote_name,
                    branch=branch,
                    force=do_force,
                    push_tags=False)
            except Exception as e:
                out.abort(giterr.normalize_stderr(e), False)

    # ================== PUBLISH VIA TAG ==================
    if args.publish:
        new_tag = utils.bump_semver_from_tag(latest or '',
                  args.tag_bump, prefix=args.tag_prefix)
        msg     = utils.wrap(f"new tag: {new_tag}")
        out.success(msg)

        if args.dry_run:
            msg = DRYRUN + "would create tag " \
                + utils.color(new_tag, INFO)
            out.prompt(msg)
        else:
            try: gitutils.create_tag(repo_root, new_tag,
                 message=args.tag_message or
                 log_text, sign=args.tag_sign)
            except Exception as e:
                out.abort(f"tag creation failed: {e}")

            try: gitutils.push(repo_root,
                 remote=args.remote or 'origin',
                 branch=None, force=args.force,
                 push_tags=True)
            except Exception as e:
                e = giterr.normalize_stderr(e,
                    'failed to push tags:')
                out.abort(e, False)

    # ================= RELEASE TO GITHUB =================
    token = args.gh_token or os.environ.get("GITHUB_TOKEN")
    if args.gh_release:
        if not token:
            m = "GitHub token required for release. Set " \
              + "--gh-token or GITHUB_TOKEN env var"
            out.warn(m)
            if not args.dry_run: sys.exit(1)
        if not args.gh_repo:
            out.warn("--gh-repo required for GitHub release")
            if not args.dry_run: sys.exit(1)

        from . import github as gh

        out.success(f"creating GitHub release for tag {new_tag}")

        if args.dry_run:
            out.prompt(DRYRUN + "skipping process...")
        else:
            release_info = gh.create_release(
                           token=token,
                           repo=args.gh_repo,
                           tag=new_tag,
                           name=new_tag,
                           body=log_text,
                           draft=args.gh_draft,
                           prerelease=args.gh_prerelease)

        if args.gh_assets:
            files = [f.strip() for f in
                    args.gh_assets.split(",") if f.strip()]
            for fpath in files:
                out.success(f"uploading asset: {fpath}")
                if args.dry_run:
                    out.prompt(DRYRUN + "skipping process...")
                else:
                    gh.upload_asset(token, args.gh_repo,
                        release_info["id"], fpath)
    if args.dry_run:
        out.success(DRYRUN + "no changes made")


def main_wrapper() -> NoReturn:
    """
    Top-level wrapper for `main()`, providing controlled
    exception handling

    - Catches and processes uncaught exceptions from `main()`
    - Handles `KeyboardInterrupt`, `EOFError`, and
      `SystemExit` gracefully
    - Displays formatted error messages and ensures
      consistent exit behavior
    - Always emits a completion message regardless of outcome

    Intended as the CLI entry point for scripts or direct
    invocation
    """
    quiet = utils.any_in("-q", "--quiet", eq=sys.argv)
    out   = utils.Output(quiet=quiet)
    try: main()
    except BaseException as e:
        if isinstance(e, SystemExit):
            sys.exit(e)  # respect explicit exit calls
        if not isinstance(e, (KeyboardInterrupt, EOFError)):
            out.warn(f"ERROR: {e}")
        else:
            i = 1 if not isinstance(e, EOFError) else 2
            out.raw("\n" * i + PNP, end="")
            out.raw(utils.color("forced exit", BAD))
        sys.exit(1)
    finally: out.success("done"); out.raw()
