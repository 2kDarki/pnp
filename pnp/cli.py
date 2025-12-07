 #!/usr/bin/env python3
"""Main CLI for pnp"""

# ======================= STANDARDS =======================
from datetime import datetime
from typing import NoReturn
import subprocess
import argparse
import sys
import os

# ==================== THIRD-PARTIES ======================
from tuikit.textools import strip_ansi
from tuikit.logictools import any_in

# ======================== LOCALS =========================
from .help_menu import wrap, transmit, help_msg
from . import gitutils, changelog
from .handlers import giterr
from ._constants import *
from . import utils


def run_cmd(cmd:str, cwd:str = None, dry_run:bool = False,
            check:bool = True) -> int | NoReturn:
    """Run command and argument(s) in shell"""
    capture = "--no-transmission" not in sys.argv \
          and "kitty lint" not in cmd
    add     = f" {DRYRUN}skips" if dry_run else ""
    m       = utils.wrap(f"[run] {cmd}{add}") 
    utils.transmit(m, fg=GOOD)
    if dry_run: return 0

    proc   = subprocess.run(cmd, cwd=cwd, shell=True,
             text=True, capture_output=capture)
    code   = proc.returncode
    stdout = proc.stdout
    stderr = proc.stderr
    if not capture or stderr: print()
    if check and code != 0:
        err = f"[{code}] Command failed: {cmd} {stderr}"
        err = giterr.normalize_stderr(utils.color(err,BAD))
        raise RuntimeError(err)

    if capture: print(stdout, speed=0, hold=0)
    return code


def find_repo(path:str) -> str:
    """Walks until .git present else raises RuntimeError"""
    # Walking is relative to current working directory
    def found(path):
        path = utils.pathit(path)
        return utils.wrap(f"Found repository in {path!r}. "
             + "Is it the correct repository? [y/n]")
 
    print()
    # walk up
    cur = os.path.abspath(path)
    while True:
        if os.path.isdir(os.path.join(cur, '.git')):
            if "--ci" in sys.argv: return path
            yes = utils.intent(found(cur), "y", "return")
            if yes: return cur
        parent = os.path.dirname(cur)
        if parent == cur: break
        cur = parent

    # walk down one level for performance reasons
    cur = os.path.abspath(path)
    paths = [f"{cur}{os.sep}{c}" for c in os.listdir(cur)]

    for path in paths:
        if os.path.isdir(os.path.join(path, '.git')):
            if "--ci" in sys.argv: return path
            yes = utils.intent(found(path), "y", "return")
            if yes: return path

    raise RuntimeError


def detect_subpackage(path:str, monorepo_path:str) -> str:
    """Find subpackage by checking if pyproject.toml is present"""
    # if path contains pyproject.toml, treat it  as package
    # root
    candidate = os.path.abspath(path)
    if os.path.exists(os.path.join(candidate,
       'pyproject.toml')): 
        if candidate != monorepo_path: return candidate

    # else, try to find nearest folder with pyproject 
    # relative to monorepo root
    for root, dirs, files in os.walk(monorepo_path):
        if 'pyproject.toml' in files:
            if candidate.startswith(root):
                if root != monorepo_path: return root


def bump_semver_from_tag(tag:str, bump:str,
                         prefix:str = 'v') -> str:
    """Bumps tag"""
    import re
    sem = tag
    if tag.startswith(prefix): sem = tag[len(prefix):]

    m = re.match(r'(\d+)\.(\d+)\.(\d+)$', sem)
    if not m:
        # start fresh
        if bump == 'minor': return f"{prefix}0.1.0"
        if bump == 'major': return f"{prefix}1.0.0"
        return f"{prefix}0.0.1"

    major, minor, patch = map(int, m.groups())
    if bump == 'patch': patch += 1
    if bump == 'minor': minor += 1; patch = 0
    if bump == 'major': major += 1; minor = 0; patch = 0
    return f"{prefix}{major}.{minor}.{patch}"


def parse_args(argv: list[str]) -> argparse.ArgumentParser:
    """Add and parse arguments"""
    p = argparse.ArgumentParser(prog='pnp',
        description=help_msg())

    # Global arguments
    p.add_argument('path', nargs='?', default='.')
    p.add_argument('--push', '-p', action='store_true')
    p.add_argument('--publish', '-P', action='store_true')
    p.add_argument('--dry-run', action='store_true')
    p.add_argument('--force', action='store_true')
    p.add_argument('--ci', action='store_true')
    p.add_argument('--remote', default=None)
    p.add_argument('--hooks', default=None)
    p.add_argument('--changelog-file', default="pnp.log")
    p.add_argument('--no-transmission',action='store_true')
    p.add_argument('--interactive', '-i',
                   action='store_true')

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
    p.add_argument('--tag-bump', choices=['major','minor',
                   'patch'], default='patch')

    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> None | NoReturn:
    """Control center for pnp"""
    args = parse_args(argv or sys.argv[1:])
    path = os.path.abspath(args.path)

    # =================== FIND GIT ROOT ===================
    try: repo_root = find_repo(path)
    except RuntimeError:
        if args.interactive and not args.ci:
            prompt = utils.wrap("No repo found. Initialize"
                   + " here? [y/n]")
            if utils.intent(prompt, "y", "return"):
                gitutils.git_init(path)
                repo_root = find_repo(path)
            else:
                utils.transmit('Exiting...', fg=BAD)
                sys.exit(1)
        else:
            msg = utils.wrap("No git repository found. "
                + "Exiting.")
            utils.transmit(msg, fg=BAD); sys.exit(1)

    msg = utils.wrap(f"repo root: {repo_root}")
    utils.transmit(msg, fg=GOOD)

    # monorepo detection: are we in a package folder?
    subpkg = detect_subpackage(path, repo_root)
    if subpkg:
        op_path = subpkg
        msg = utils.wrap("operating on detected package "
            + f"at: {utils.pathit(op_path)}\n")
        utils.transmit(msg, fg=GOOD)
    else: op_path = repo_root

    # ============= RUN PRE-PUSH HOOKS IF ANY =============
    if args.hooks:
        hooks = [h.strip()for h in args.hooks.split(';') if
                 h.strip()]
        utils.transmit('running hooks:\n' 
                      +utils.to_list(hooks), fg=UPDATE)
        for cmd in hooks:
            try: 
                run_cmd(cmd, cwd=op_path, check=True,
                        dry_run=args.dry_run)
                if not args.dry_run: print()
            except Exception as e:
                m = " ".join(e.args[0].split())
                m = utils.wrap(f"hook failed: {m}")
                utils.transmit(m, fg=BAD)
                if args.ci or not args.interactive: return
                else:
                    prompt = "Hook failed. Continue? [y/n]"
                    if utils.intent(prompt, "n", "return"):
                        m = "Aborting due to hook failure."
                        utils.transmit(m, fg=BAD)
                        sys.exit(1)
        if args.dry_run: print()

    # ============= STAGE & COMMIT IF NEEDED ==============
    if gitutils.has_uncommitted(op_path):
        if args.interactive and not args.ci:
            prompt = utils.wrap("Uncommitted changes "
                   + "found. Stage and commit? [y/n]")
            if utils.intent(prompt, "n", "return"):
                utils.transmit('Aborting...', fg=BAD)
                sys.exit(1)
        if not args.dry_run: gitutils.stage_all(op_path)
        else: utils.transmit(DRYRUN + "skipping...")
        try:
            msg = "pnp: auto commit"
            if "--ci" not in sys.argv and any_in("-i",
               "--interactive", eq=sys.argv):
                m = utils.wrap("Enter commit message. Type"
                  + " 'no' to exclude commit message")
                utils.transmit(m)
                m = input(CURSOR).strip() or "no"; print()
                msg = msg if m.lower() == "no" else m
            if not args.dry_run:
                gitutils.commit(op_path, message=msg)
            else:
               utils.transmit(DRYRUN+f"would commit {msg}")
        except Exception as e:
            e = giterr.normalize_stderr(e)
            utils.transmit(f'{e}\n', fg=BAD); sys.exit(1)
    else: utils.transmit('no changes to commit', fg=GOOD)

    # ==================== PUSH LOGIC =====================
    if args.push:        
        # fetch
        try: gitutils.fetch_all(repo_root)
        except Exception as e:
            if args.ci and not args.dry_run: raise 
            exc = giterr.normalize_stderr(e)
            utils.transmit(exc, fg=BAD)
            utils.transmit(DRYRUN+"would have aborted")

        no_branch = False
        branch    = gitutils.current_branch(op_path)
        if not branch:
            utils.transmit("No branch detected", fg=BAD)
            if not args.dry_run:
                utils.transmit("Exiting..."); sys.exit(1)
            utils.transmit(DRYRUN+"would have aborted")
            no_branch = True

        if not no_branch:
            upstream = args.remote or gitutils \
                      .upstream_for_branch(op_path, branch)
            if upstream:
                remote_name = upstream.split('/')[0]
            else: remote_name = args.remote or 'origin'

        # check ahead/behind
        do_force = False
        if no_branch: upstream = None
        if upstream:
            counts = gitutils.rev_list_counts(repo_root,
                     upstream, branch)
            if counts:
                remote_ahead, local_ahead = counts
                if remote_ahead > 0:
                    m = utils.wrap(f"remote ({upstream}"
                      + f") ahead by {remote_ahead} "
                      + "commit(s)")
                    utils.transmit(m)
                    if args.force: do_force = True
                    elif args.interactive and not args.ci:
                        msg = utils.wrap("Force push and "
                            + "overwrite remote? [y/n]")
                        do_force = utils.intent(msg, "y",
                                   "return")
                    else:
                        utils.transmit("Remote ahead. "
                             + "Aborting.", fg=BAD)
                        sys.exit(1)

        if not no_branch:
            try: gitutils.push(repo_root,
                               remote=remote_name,
                               branch=branch,
                               force=do_force,
                               push_tags=False)
            except Exception as e:
                e = giterr.normalize_stderr(e)
                utils.transmit(e, fg=BAD); sys.exit(1)

    # ================== PUBLISH VIA TAG ==================
    if args.publish:
        tags    = gitutils.tags_sorted(repo_root)
        latest  = tags[0] if tags else None
        new_tag = bump_semver_from_tag(latest or '',
                  args.tag_bump, prefix=args.tag_prefix)
        msg = utils.wrap(f"new tag: {new_tag}")
        utils.transmit(msg, fg=GOOD)

        # generate changelog between latest and HEAD
        since = latest
        hue = GOOD
        try:
            timestamp = datetime.now().isoformat()[:-7]
            changelog_text = changelog.gen_changelog(
                             repo_root, since=since) + "\n"
        except Exception as e:
            add = ""
            if args.dry_run:
                add = "NB: Potentially due to dry-run " \
                    + "skipping certain processes\n"
            hue = BAD
            changelog_text = utils.color(f"[{timestamp}] -"
                           + " changelog generation failed"
                           + ": ", hue)+f"{e}{add}\n"
        print(PNP, end="")
        prompt = utils.color("changelog:\n\n", hue)
        print(wrap(f'{prompt}{changelog_text}'), end="")
        if args.changelog_file:
            if args.dry_run:
                ex = "log"
                if "." in args.changelog_file:
                    ex = args.changelog_file.split(".")[-1]
                args.changelog_file += f".dry-run.{ex}"
            with open(args.changelog_file, 'a+') as f:
                f.write(strip_ansi(changelog_text))

        if args.dry_run:
            msg = utils.wrap(DRYRUN + "would create tag "
                + utils.color(new_tag, UPDATE))
            utils.transmit(msg)
        else:
            try: gitutils.create_tag(repo_root, new_tag,
                 message=args.tag_message or
                 changelog_text, sign=args.tag_sign)
            except Exception as e:
                utils.transmit(f"Tag creation failed: {e}",
                     fg=BAD); sys.exit(1)

            try: gitutils.push(repo_root,
                 remote=args.remote or 'origin',
                 branch=None, force=args.force,
                 push_tags=True)
            except Exception as e:
                e = giterr.normalize_stderr(e,
                    'Failed to push tags:')
                utils.transmit(e, fg=BAD); sys.exit(1)
    # ================= RELEASE TO GITHUB =================
    token = args.gh_token or os.environ.get("GITHUB_TOKEN")
    if args.gh_release:
        if not token:
            m = utils.wrap("GitHub token required for "
              + "release. Set --gh-token or GITHUB_TOKEN "
              + "env var")
            utils.transmit(m, fg=BAD)
            if not args.dry_run: sys.exit(1)
        if not args.gh_repo:
            m = utils.wrap("--gh-repo required for GitHub "
              + "release")
            utils.transmit(m, fg=BAD)
            if not args.dry_run: sys.exit(1)

        from . import github as gh

        m = utils.wrap("creating GitHub release for tag "
          + f"{new_tag}")
        utils.transmit(m, fg=GOOD)

        if args.dry_run:
            utils.transmit(DRYRUN + "skipping process...")
        else:
            release_info = gh.create_release(
                           token=token,
                           repo=args.gh_repo,
                           tag=new_tag,
                           name=new_tag,
                           body=changelog_text,
                           draft=args.gh_draft,
                           prerelease=args.gh_prerelease)

        if args.gh_assets:
            files = [f.strip() for f in
                    args.gh_assets.split(",") if f.strip()]
            for fpath in files:
                m = utils.wrap(f"uploading asset: {fpath}")
                utils.transmit(m, fg=BAD)
                if args.dry_run:
                    utils.transmit(DRYRUN
                         +"skipping process...")
                else:
                    gh.upload_asset(token, args.gh_repo,
                        release_info["id"], fpath)
    if args.dry_run:
        utils.transmit(DRYRUN + "no changes made", fg=GOOD)


def main_wrapper() -> NoReturn:
    """Wrap main() in a try-exception-finally block"""
    try: main()
    except BaseException as e:
        if isinstance(e, SystemExit): sys.exit(e)
        if not isinstance(e, (KeyboardInterrupt,EOFError)):
            err = utils.wrap(f"ERROR: {e}")
            utils.transmit(err, fg=BAD)
        else:
            i = 1 if not isinstance(e, EOFError) else 2
            print("\n" * i + PNP, end="")
            print(utils.color("Forced exit", BAD))
        sys.exit(1)
    finally: utils.transmit("done", fg=GOOD); print()
