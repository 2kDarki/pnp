"""Workflow orchestration engine for pnp."""


from datetime import datetime
from typing import Any, cast
from pathlib import Path
import argparse
import time
import sys
import os

from tuikit.textools import strip_ansi, Align

from .error_model import (
    FailureEvent,
    error_policy_for,
    resolve_failure_code,
)
from . import _constants as const
from .tui import tui_runner
from .ops import run_hook
from . import utils
from . import ops


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

    def __init__(self, argv: argparse.Namespace,
                 repo_path: str | None = None):
        """
        Initialize the orchestrator for the `pnp` CLI tool.

        Parses CLI arguments, resolves the working directory,
        sets up output behavior, and initializes key
        attributes used in the release process (e.g. Git repo
        path, changelog data, etc.).

        Args:
            argv (argparse.Namespace): Parsed CLI namespace.
        """
        self.args: argparse.Namespace = argv
        const.sync_runtime_flags(self.args)

        self.path = os.path.abspath(repo_path
                 or self.args.path)
        self.out  = utils.Output(quiet=self.args.quiet)

        self.repo:       str | None = None
        self.subpkg:     str | None = None
        self.gitutils:          Any = None
        self.resolver:          Any = None
        self.latest:     str | None = None
        self.commit_msg: str | None = None
        self.tag:        str | None = None
        self.log_dir:   Path | None = None
        self.log_text:   str | None = None
        self._temp_message_files: list[str] = []
        self.failure_hint: FailureEvent | None = None

    def _resolver_classification(self) -> tuple[str, str, str]:
        """Best-effort resolver classification from the last git error."""
        resolver_inst = getattr(self.resolver, "resolve", None)
        last = getattr(resolver_inst, "last_error", None)
        if not isinstance(last, dict):
            return "", "", ""
        code = str(last.get("code", "")).strip()
        severity = str(last.get("severity", "")).strip()
        category = ""
        if code:
            policy = error_policy_for(code, fallback_category="workflow")
            category = policy["category"]
            if not severity:
                severity = policy["severity"]
        return code, severity, category

    def _set_failure_hint(
        self,
        step: str,
        label: str,
        result: str,
        message: str,
    ) -> None:
        code, severity, category = self._resolver_classification()
        code = resolve_failure_code(step=step, preferred_code=code)
        policy = error_policy_for(
            code,
            fallback_severity=severity or "error",
            fallback_category=category or "workflow",
        )
        severity = severity or policy["severity"]
        category = category or policy["category"]
        self.failure_hint = FailureEvent(
            step=step,
            label=label,
            result=result,
            message=message.strip(),
            code=code,
            severity=severity,
            category=category,
        )

    # ---------- Internal Utilities ----------
    def _cleanup_temp_message_files(self) -> None:
        ops.cleanup_temp_files(self._temp_message_files)
        self._temp_message_files.clear()

    def _git_core_editor(self) -> str | None:
        return ops.git_core_editor(self.repo)

    def _resolve_editor_command(self) -> list[str]:
        preferred = getattr(self.args, "editor", None)
        return ops.resolve_editor_command(preferred,
               repo=self.repo)

    def _edit_message_in_editor(self, initial: str,
                                kind: str,
                                step_idx: int | None = None
                               ) -> str:
        editor     = self._resolve_editor_command()
        text, path = ops.edit_message_in_editor(initial,
                     kind, editor, self.out, step_idx)
        self._temp_message_files.append(path)
        return text

    def _git_head(self, path: str) -> str | None:
        return ops.git_head(path)

    def _rollback_unstage(self, path: str,
                          step_idx: int | None = None
                         ) -> None:
        ops.rollback_unstage(path, self.out, step_idx)

    def _rollback_delete_tag(self, repo: str, tag: str,
                             step_idx: int | None = None
                            ) -> None:
        ops.rollback_delete_tag(repo, tag, self.out, step_idx)

    # ---------- Workflow Plan ----------
    def _workflow_plan(self) -> tuple[list[Any], list[str], list[str]]:
        steps = [
            self.find_repo,
            self.run_hooks,
            self.run_machete,
            self.stage_and_commit,
            self.push,
            self.publish,
            self.release,
        ]
        labels = [
            "Detect repository",
            "Run hooks",
            "Run git machete",
            "Stage and commit changes",
            "Push to remote",
            "Publish tag",
            "Create GitHub release",
        ]
        keys = [
            "repository",
            "hooks",
            "machete",
            "commit",
            "push",
            "publish",
            "release",
        ]
        return steps, labels, keys

    # ---------- Orchestration ----------
    def orchestrate(self) -> None:
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
        steps, labels, keys = self._workflow_plan()

        use_ui = bool(const.CI_MODE and not const.PLAIN
             and sys.stdout.isatty())

        with tui_runner(labels, enabled=use_ui) as ui:
            try:
                if use_ui: utils.bind_console(ui)

                for i, step in enumerate(steps):
                    ui.start(i)
                    start = time.time()
                    msg, result = step(step_idx=i)
                    end = time.time()
                    if end - start < 1: time.sleep(1)
                    ui.finish(i, result)
                    if result is utils.StepResult.DONE: return None
                    if result is utils.StepResult.SKIP: continue
                    if result is utils.StepResult.FAIL:
                        detail = ""
                        if isinstance(msg, tuple):
                            detail = str(msg[0])
                        elif isinstance(msg, str):
                            detail = msg
                        self._set_failure_hint(
                            step=keys[i],
                            label=labels[i],
                            result="fail",
                            message=detail,
                        )
                        sys.exit(1)
                    if result is utils.StepResult.ABORT:
                        detail = ""
                        if isinstance(msg, tuple):
                            detail = str(msg[0])
                        elif isinstance(msg, str):
                            detail = msg
                        self._set_failure_hint(
                            step=keys[i],
                            label=labels[i],
                            result="abort",
                            message=detail,
                        )
                        if isinstance(msg, tuple):
                            self.out.abort(*msg)
                        else: self.out.abort(msg)
            finally: self._cleanup_temp_message_files()

        if self.args.dry_run:
            self.out.success(const.DRYRUN + "no changes made")

    # ---------- Step: Repository ----------
    def find_repo(self, step_idx: int | None = None
                 ) -> tuple[str | None, utils.StepResult]:
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
            found_repo = utils.find_repo(self.path)
            if not isinstance(found_repo, str):
                raise RuntimeError("unexpected repository resolution")
            self.repo = found_repo

            # Setup logging and import runtime-dependent
            # modules
            self.log_dir = utils.get_log_dir(self.repo)
            modules      = utils.import_deps(self.log_dir)
        except RuntimeError:
            if not const.CI_MODE:
                prompt = utils.wrap("no repo found. "
                       + "Initialize here? [y/n]")
                if utils.intent(prompt, "y", "return"):
                    self.log_dir = utils.get_log_dir(
                                   self.path)
                    modules = utils.import_deps(self.log_dir)
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
        assert self.repo is not None
        self.out.success(f"repo root: {utils.pathit(self.repo)}", step_idx)

        # monorepo detection: are we in a package folder?
        subpkg = utils.detect_subpackage(self.path, self.repo)
        if subpkg:
            self.subpkg = subpkg
            msg = "operating on detected package at: " \
                + f"{utils.pathit(self.subpkg)}\n"
            self.out.success(msg, step_idx)
        else: self.subpkg = self.repo
        assert self.subpkg is not None

        return None, utils.StepResult.OK

    # ---------- Step: Hooks ----------
    def run_hooks(self, step_idx: int | None = None
                 ) -> tuple[str | None, utils.StepResult]:
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

        hooks = [h.strip() for h in self.args.hooks.split(";"
                ) if h.strip()]
        assert self.subpkg is not None
        self.out.info("running hooks:\n" + utils
            .to_list(hooks), step_idx=step_idx)
        for i, cmd in enumerate(hooks):
            try:
                run_hook(cmd, self.subpkg, self.args.dry_run,
                    self.args.no_transmission)
            except (RuntimeError, ValueError) as e:
                msg = " ".join(e.args[0].split())
                if isinstance(e, RuntimeError):
                    msg = f"hook failed {msg}"
                self.out.warn(msg, step_idx=step_idx)
                prompt = "hook failed. Continue? [y/n]"
                if const.CI_MODE:
                    return None, utils.StepResult.FAIL
                if utils.intent(prompt, "n", "return"):
                    msg = "aborting due to hook failure"
                    return msg, utils.StepResult.ABORT

        if self.args.dry_run and const.PLAIN: print()

        return None, utils.StepResult.OK

    # ---------- Step: Git Machete ----------
    def run_machete(self, step_idx: int | None = None
                   ) -> tuple[str | None, utils.StepResult]:
        """Run optional git-machete checks/operations."""
        enabled = any((
            self.args.machete_status,
            self.args.machete_sync,
            self.args.machete_traverse,
        ))
        if not enabled: return None, utils.StepResult.SKIP
        assert self.repo is not None

        return ops.run_machete(self.repo, self.args.dry_run,
               self.args.machete_sync,
               self.args.machete_traverse, self.out,
               step_idx)

    # ---------- Step: Changelog ----------
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
        assert self.repo is not None
        tags        = self.gitutils.tags_sorted(self.repo)
        self.latest = tags[0] if tags else None
        timestamp   = datetime.now().isoformat()[:-7]

        assert self.log_dir is not None
        log_file: Path = self.log_dir / Path("changes.log")
        if self.args.changelog_file:
            log_name = self.args.changelog_file
            if os.sep not in log_name:
                log_file = self.log_dir / Path(log_name)
            else: log_file = Path(log_name)

        if get: return log_file

        msg = self.commit_msg if self.args.dry_run else None
        hue = const.GOOD
        div = f"------| {timestamp} |------"
        try:
            self.log_text = utils.gen_changelog(
                            self.repo, since=self.latest,
                            dry_run=msg) + "\n"
        except Exception as e:
            hue = const.BAD
            add = ""
            if self.args.dry_run and "ambiguous" in e.args[0]:
                add = "NB: Potentially due to dry-run "\
                    + "skipping certain processes\n"
            self.log_text = utils.color("changelog "
                          + f"generation failed: {e}{add}\n",
                            hue)

        # log changes
        self.out.raw(const.PNP, end="")
        prompt = utils.color("changelog↴\n", hue)
        self.out.raw(utils.wrap(prompt))
        self.out.raw(Align().center(div, "-"))
        self.out.raw(utils.wrap(self.log_text), end="")
        if not self.args.dry_run and self.args.changelog_file:
            os.makedirs(log_file.parent, exist_ok=True)
            with open(log_file, "a+", encoding="utf-8") as f:
                f.write(strip_ansi(f"{div}\n{self.log_text}"))

        return None

    # ---------- Step: Commit ----------
    def stage_and_commit(self, step_idx: int | None = None
                        ) -> tuple[tuple[str, bool] | None,
                             utils.StepResult]:
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
        assert self.subpkg is not None
        if not self.gitutils.has_uncommitted(self.subpkg):
            log_file = self.gen_changelog(get=True)
            assert isinstance(log_file, Path)

            self.log_text = utils\
                .retrieve_latest_changelog(log_file)
            self.out.success("no changes to commit", step_idx)
            return None, utils.StepResult.SKIP

        if not const.CI_MODE:
            prompt = utils.wrap("uncommitted changes "
                   + "found. Stage and commit? [y/n]")
            if utils.intent(prompt, "n", "return"):
                return None, utils.StepResult.ABORT

        head_before = self._git_head(self.subpkg)
        staged      = False
        try:
            msg = self.args.tag_message\
               or utils.gen_commit_message(self.subpkg)

            edit_message = bool(getattr(self.args,
                           "edit_message", False))
            can_open_editor = not any((
                bool(getattr(self.args,    "ci", False)),
                bool(getattr(self.args, "quiet", False)),
                bool(getattr(self.args, "plain", False)),
            ))
            if edit_message and can_open_editor:
                msg = self._edit_message_in_editor(msg,
                      "commit", step_idx)
            elif not const.CI_MODE:
                if edit_message and not can_open_editor:
                    self.out.warn("edit-message skipped in "
                        "ci/quiet/plain mode",
                        step_idx=step_idx)
                m = "enter commit message. Type 'no' to " \
                  + "exclude commit message"
                self.out.prompt(m)
                m = input(const.CURSOR).strip() or "no"
                if const.PLAIN: self.out.raw()
                msg = msg if m.lower() == "no" else m

            self.commit_msg = msg

            if not self.args.dry_run:
                self.gitutils.stage_all(self.subpkg)
                staged = True
                self.gitutils.commit(self.subpkg, msg)
                staged = False
            else:
                msg = const.DRYRUN + f"would commit {msg!r}"
                self.out.info(msg, step_idx=step_idx)
        except Exception as e:
            if staged and not self.args.dry_run:
                head_after = self._git_head(self.subpkg)
                if head_before and head_after == head_before:
                    self._rollback_unstage(self.subpkg,
                        step_idx=step_idx)

            e = self.resolver.normalize_stderr(e)
            return (f"{e}\n", False), utils.StepResult.ABORT

        # generate changelog between self.latest and HEAD
        self.gen_changelog()
        return None, utils.StepResult.OK

    # ---------- Step: Push ----------
    def push(self, step_idx: int | None = None
            ) -> tuple[str | tuple[str, bool] | None,
                 utils.StepResult]:
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
        assert self.subpkg is not None and self.repo is not None

        try: self.gitutils.fetch_all(self.repo)
        except Exception as e:
            self.out.warn(self.resolver.normalize_stderr(e),
                False, step_idx=step_idx)
            if const.CI_MODE and not self.args.dry_run:
                return None, utils.StepResult.ABORT
            self.out.prompt(const.DRYRUN +
                "continuing regardless", step_idx=step_idx)

        branchless = False
        branch     = self.gitutils.current_branch(self.subpkg)
        if not branch:
            self.out.warn("no branch detected",
                step_idx=step_idx)
            if not self.args.dry_run:
                return None, utils.StepResult.ABORT
            self.out.prompt(const.DRYRUN +
                "continuing regardless", step_idx=step_idx)
            branchless = True

        if not branchless:
            upstream = self.args.remote or self.gitutils\
                       .upstream_for_branch(self.subpkg,
                       branch)
            if upstream: remote_name = upstream.split("/")[0]
            else: remote_name = self.args.remote or "origin"
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
                    self.out.warn(m, step_idx=step_idx)
                    if self.args.force: force = True
                    elif not const.CI_MODE:
                        msg   = utils.wrap("force push and "
                              + "overwrite remote? [y/n]")
                        force = bool(utils.intent(msg, "y",
                                "return"))
                    else: return None, utils.StepResult.ABORT

        if not branchless:
            try: self.gitutils.push(self.repo,
                    remote=remote_name,
                    branch=branch,
                    force=force,
                    push_tags=False)
            except Exception as e:
                return (self.resolver.normalize_stderr(e),
                       False), utils.StepResult.ABORT

        return None, utils.StepResult.OK

    # ---------- Step: Publish Tag ----------
    def publish(self, step_idx: int | None = None
               ) -> tuple[str | tuple[str, bool] | None,
                    utils.StepResult]:
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
                   self.latest or "", self.args.tag_bump,
                   prefix=self.args.tag_prefix)
        self.out.success(f"new tag: {self.tag}", step_idx)

        if self.args.dry_run:
            msg = const.DRYRUN + "would create tag " \
                + utils.color(self.tag, const.INFO)
            self.out.prompt(msg, step_idx=step_idx)
        else:
            assert self.repo is not None
            existing    = self.gitutils.tags_sorted(
                          self.repo, self.tag)
            tag_created = False
            try: self.gitutils.create_tag(self.repo,
                 self.tag, message=self.args.tag_message
                 or self.log_text, sign=self.args.tag_sign)
            except Exception as e:
                if self.tag in existing:
                    self.out.warn(f"tag {self.tag!r} already exists locally; reusing",
                                  step_idx=step_idx)
                else:
                    return f"tag creation failed: {e}", \
                           utils.StepResult.ABORT
            else: tag_created = True

            try: self.gitutils.push(self.repo,
                 remote=self.args.remote or "origin",
                 branch=None, force=self.args.force,
                 push_tags=True)
            except Exception as e:
                if tag_created:
                    self._rollback_delete_tag(self.repo,
                        self.tag, step_idx=step_idx)
                e = self.resolver.normalize_stderr(e,
                    "failed to push tags:")
                return (e, False), utils.StepResult.ABORT

        return None, utils.StepResult.OK

    # ---------- Step: Release ----------
    def release(self, step_idx: int | None = None
               ) -> tuple[tuple[str, bool] | None,
                    utils.StepResult]:
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

        if not self.tag:
            assert self.repo is not None
            tags = self.gitutils.tags_sorted(self.repo)
            if tags:
                self.tag = tags[0]
                self.out.warn(
                    "no publish step detected; using latest"
                    f"tag {self.tag!r} for release",
                    step_idx=step_idx,
                )
            elif not self.args.dry_run:
                self.out.warn("cannot create GitHub release: no tag available",
                    step_idx=step_idx)
                return None, utils.StepResult.FAIL
            else: self.tag = "v0.0.0-dry-run"

        token = self.args.gh_token \
             or os.environ.get("GITHUB_TOKEN")
        if not token:
            m = "GitHub token required for release. Set " \
              + "--gh-token or GITHUB_TOKEN env var"
            self.out.warn(m, step_idx=step_idx)
            if not self.args.dry_run:
                return None, utils.StepResult.FAIL
        if not self.args.gh_repo:
            self.out.warn("--gh-repo required for GitHub release", step_idx=step_idx)
            if not self.args.dry_run:
                return None, utils.StepResult.FAIL

        from . import github as gh

        self.out.success(f"creating GitHub release for tag {self.tag}", step_idx)

        if self.args.dry_run:
            self.out.prompt(const.DRYRUN +
                "skipping process...", step_idx=step_idx)
        else:
            assert token is not None and self.tag is not None
            release_info = gh.create_release(token,
                           self.args.gh_repo, self.tag,
                           self.tag, self.log_text,
                           self.args.gh_draft,
                           self.args.gh_prerelease)

        if self.args.gh_assets:
            files = [f.strip() for f in self.args.gh_assets
                    .split(",") if f.strip()]
            for fpath in files:
                self.out.success(f"uploading asset: {fpath}",
                    step_idx=step_idx)
                if self.args.dry_run:
                    self.out.prompt(const.DRYRUN +
                        "skipping process...",
                        step_idx=step_idx)
                else:
                    assert token is not None
                    try: gh.upload_asset(token,
                         self.args.gh_repo,
                         int(cast(int, release_info["id"])),
                         fpath)
                    except RuntimeError as e:
                        e = self.resolver.normalize_stderr(e)
                        return (e, False), \
                               utils.StepResult.ABORT

        return None, utils.StepResult.OK
