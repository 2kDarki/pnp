#!/usr/bin/env python3
# ===========================================================
# imports
# ===========================================================
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any
from datetime import datetime
import argparse
import subprocess
import sys
import os
import re

# ===========================================================
# local imports (unchanged from your project)
# ===========================================================
from ._constants import DRYRUN, APP, PNP, INFO, GOOD, BAD, CI_MODE, CURSOR
from .help_menu import wrap, help_msg
from . import utils
from tuikit.textools import strip_ansi


# ===========================================================
# context.py
# ===========================================================
@dataclass
class Output:
    quiet: bool = False

    def info(self, msg: str, **kw):
        if not self.quiet:
            utils.transmit(msg, **kw)

    def warn(self, msg: str, **kw):
        utils.transmit(msg, **kw)

    def error(self, msg: str, **kw):
        utils.transmit(msg, **kw)

    def raw(self, msg: str):
        print(msg, end="")


@dataclass
class Context:
    args: Any
    out: Output

    repo_root: Path | None = None
    package_root: Path | None = None
    log_dir: Path | None = None

    latest_tag: str | None = None
    changelog: str | None = None

    branch: str | None = None
    upstream: str | None = None

    gitutils: Any = None
    changelog_mod: Any = None
    giterr: Any = None

    artifacts: dict = field(default_factory=dict)


# ===========================================================
# pipeline.py
# ===========================================================
class StepResult(Enum):
    OK = auto()
    SKIP = auto()
    FAIL = auto()
    ABORT = auto()


class Step:
    name = "unnamed"
    allow_ci = True

    def run(self, ctx: Context) -> StepResult:
        raise NotImplementedError


# ===========================================================
# helpers
# ===========================================================
def import_deps():
    from . import gitutils, changelog
    from .handlers import giterr
    return gitutils, changelog, giterr


def bump_semver_from_tag(tag: str, bump: str, prefix: str = "v") -> str:
    sem = tag[len(prefix):] if tag.startswith(prefix) else tag
    m = re.match(r"(\d+)\.(\d+)\.(\d+)$", sem)

    if not m:
        return {
            "patch": f"{prefix}0.0.1",
            "minor": f"{prefix}0.1.0",
            "major": f"{prefix}1.0.0",
        }[bump]

    major, minor, patch = map(int, m.groups())
    if bump == "patch":
        patch += 1
    elif bump == "minor":
        minor += 1
        patch = 0
    else:
        major += 1
        minor = patch = 0

    return f"{prefix}{major}.{minor}.{patch}"


# ===========================================================
# steps/find_repo.py
# ===========================================================
class FindRepo(Step):
    name = "find-repo"

    def run(self, ctx: Context) -> StepResult:
        cur = Path(ctx.args.path).resolve()

        while True:
            if (cur / ".git").is_dir():
                ctx.repo_root = cur
                ctx.log_dir = utils.get_log_dir(cur)
                ctx.gitutils, ctx.changelog_mod, ctx.giterr = import_deps()
                ctx.out.info(wrap(f"repo root: {cur}"), fg=GOOD)
                return StepResult.OK
            if cur.parent == cur:
                break
            cur = cur.parent

        ctx.out.error("no git repository found", fg=BAD)
        return StepResult.ABORT


# ===========================================================
# steps/detect_package.py
# ===========================================================
class DetectPackage(Step):
    name = "detect-package"

    def run(self, ctx: Context) -> StepResult:
        path = Path(ctx.args.path).resolve()
        if (path / "pyproject.toml").exists():
            ctx.package_root = path
        else:
            ctx.package_root = ctx.repo_root

        ctx.out.info(
            wrap(f"operating on: {utils.pathit(ctx.package_root)}"),
            fg=GOOD,
        )
        return StepResult.OK


# ===========================================================
# steps/run_hooks.py
# ===========================================================
class RunHooks(Step):
    name = "run-hooks"

    def run(self, ctx: Context) -> StepResult:
        if not ctx.args.hooks:
            return StepResult.SKIP

        hooks = [h.strip() for h in ctx.args.hooks.split(";") if h.strip()]
        ctx.out.info("running hooks:\n" + utils.to_list(hooks), fg=INFO)

        for cmd in hooks:
            ctx.out.info(wrap(f"[hook] {cmd}"))

            if ctx.args.dry_run:
                ctx.out.info(DRYRUN + "skipping...")
                continue

            proc = subprocess.run(
                cmd,
                shell=True,
                cwd=ctx.package_root,
                capture_output=True,
                text=True,
            )

            if proc.returncode != 0:
                ctx.out.error(proc.stderr or f"hook failed: {cmd}", fg=BAD)
                return StepResult.FAIL

            if proc.stdout:
                ctx.out.raw(proc.stdout)

        return StepResult.OK


# ===========================================================
# steps/changelog.py
# ===========================================================
class GenerateChangelog(Step):
    name = "generate-changelog"

    def run(self, ctx: Context) -> StepResult:
        tags = ctx.gitutils.tags_sorted(ctx.repo_root)
        ctx.latest_tag = tags[0] if tags else None

        try:
            text = ctx.changelog_mod.gen_changelog(
                ctx.repo_root, since=ctx.latest_tag
            )
            ctx.changelog = text + "\n"
            return StepResult.OK
        except Exception as e:
            ctx.changelog = f"changelog generation failed: \n{e}\n"
            ctx.out.warn(ctx.changelog, fg=BAD)
            return StepResult.OK


# ===========================================================
# steps/commit.py
# ===========================================================
class CommitChanges(Step):
    name = "commit"

    def run(self, ctx: Context) -> StepResult:
        if not ctx.gitutils.has_uncommitted(ctx.package_root):
            ctx.out.info("no changes to commit", fg=GOOD)
            return StepResult.SKIP

        if not CI_MODE:
            prompt = wrap("uncommitted changes found. Commit? [y/n]")
            if utils.intent(prompt, "n", "return"):
                return StepResult.ABORT

        if ctx.args.dry_run:
            ctx.out.info(DRYRUN + "would commit changes")
            return StepResult.OK

        try:
            ctx.gitutils.stage_all(ctx.package_root)
            msg = ctx.args.tag_message or f"{APP} auto commit"
            ctx.gitutils.commit(ctx.package_root, msg)
            return StepResult.OK
        except Exception as e:
            ctx.out.error(ctx.giterr.normalize_stderr(e), fg=BAD)
            return StepResult.FAIL


# ===========================================================
# steps/push.py
# ===========================================================
class Push(Step):
    name = "push"

    def run(self, ctx: Context) -> StepResult:
        if not ctx.args.push:
            return StepResult.SKIP

        if ctx.args.dry_run:
            ctx.out.info(DRYRUN + "would push")
            return StepResult.OK

        try:
            ctx.gitutils.push(ctx.repo_root)
            return StepResult.OK
        except Exception as e:
            ctx.out.error(ctx.giterr.normalize_stderr(e), fg=BAD)
            return StepResult.FAIL


# ===========================================================
# steps/tag_publish.py
# ===========================================================
class Publish(Step):
    name = "publish"

    def run(self, ctx: Context) -> StepResult:
        if not ctx.args.publish:
            return StepResult.SKIP

        new_tag = bump_semver_from_tag(
            ctx.latest_tag or "",
            ctx.args.tag_bump,
            ctx.args.tag_prefix,
        )

        ctx.out.info(wrap(f"new tag: {new_tag}"), fg=GOOD)

        if ctx.args.dry_run:
            ctx.out.info(DRYRUN + f"would tag {new_tag}")
            return StepResult.OK

        try:
            ctx.gitutils.create_tag(
                ctx.repo_root,
                new_tag,
                message=ctx.changelog,
                sign=ctx.args.tag_sign,
            )
            ctx.gitutils.push(ctx.repo_root, push_tags=True)
            return StepResult.OK
        except Exception as e:
            ctx.out.error(str(e), fg=BAD)
            return StepResult.FAIL


# ===========================================================
# runner.py
# ===========================================================
class Runner:
    def __init__(self, steps: list[Step]):
        self.steps = steps

    def run(self, ctx: Context) -> int:
        for step in self.steps:
            if ctx.args.ci and not step.allow_ci:
                continue

            result = step.run(ctx)

            if result in (StepResult.FAIL, StepResult.ABORT):
                return 1

        return 0


# ===========================================================
# cli
# ===========================================================
def parse_args(argv: list[str]) -> argparse.Namespace:
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


def main(argv=None):
    args = parse_args(argv or sys.argv[1:])
    out = Output(quiet=args.quiet)
    ctx = Context(args=args, out=out)

    runner = Runner([
        FindRepo(),
        DetectPackage(),
        RunHooks(),
        GenerateChangelog(),
        CommitChanges(),
        Push(),
        Publish(),
    ])

    code = runner.run(ctx)
    sys.exit(code)


def main_wrapper():
    try:
        main()
    except KeyboardInterrupt:
        print("\n" + PNP + " forced exit")
        sys.exit(1)