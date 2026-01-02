"""
Small helpers for interacting with git. All operations use 
the git CLI via subprocess

These helpers raise RuntimeError on fatal failures; callers 
should handle prompts and dry-run
"""

# ======================= STANDARDS =======================
import subprocess
import sys
import os

# ======================== LOCALS =========================
from .utils import transmit, any_in, Output
from .handlers import giterr
from ._constants import *


def run_git(args: list[str], cwd: str | None = None,
            capture: bool = True,
            tries: int = 0) -> tuple[int, str]:
    """
    Run a git command and route stderr through giterr
    handlers when needed

    Behavior:
    - If git writes to stderr and a handler recognizes the 
      error, the handler is invoked with (stderr, cwd)
    - If the handler returns 10 -> retry the original git 
      command once
    - If the handler returns 0 -> attempt one retry (handler
      handled issue)
    - If the handler returns -1 (or other) -> return original
      proc rc/output
    - `tries` stops repeated retries (max 1 retry)
    """
    if any_in("-d", "--dry-run", eq=sys.argv): 
        return 1, DRYRUN + "skips process"
    proc = subprocess.run(["git"] + args, cwd=cwd, text=True,
           capture_output=capture)
    stdout = proc.stdout or ""
    stderr = proc.stderr or ""
    out    = (stdout or stderr).strip()

    # nothing to handle
    if not stderr: return proc.returncode, out

    # quick bypass for benign message
    if "no upstream configured" in stderr.lower():
        return proc.returncode, out

    try: rc = giterr.handle(stderr, cwd)
    except Exception as e:
        exc = f"giterr handler failed: {e}"
        giterr.logger.exception(exc)
        transmit(exc, fg=BAD)
        return proc.returncode, out

    outr = Output(quiet=any_in("-q", "--quiet", eq=sys.argv))
    if rc == 10 and tries < 1:  # retry once
        outr.prompt("retrying step...")
        return run_git(args, cwd=cwd, capture=capture, 
               tries=tries + 1)

    if rc == 0:
        return rc, out

    return proc.returncode, out


def is_git_repo(path: str) -> bool:
    rc, _ = run_git(["rev-parse", "--is-inside-work-tree"], 
            cwd=path)
    return rc == 0


def git_init(path: str) -> None:
    rc, out = run_git(["init"], cwd=path)
    if rc != 0:
        raise RuntimeError(f"git init failed: {out}")


def current_branch(path: str) -> str|None:
    rc, out = run_git(["rev-parse", "--abbrev-ref", 
              "HEAD"], cwd=path)
    return out if rc == 0 else None


def status_short(path: str) -> str:
    rc, out = run_git(["status", "--short", "--branch"], 
              cwd=path)
    return out if out.strip() else None


def has_uncommitted(path: str) -> bool:
    rc, out = run_git(["status", "--porcelain"], cwd=path)
    return bool(out.strip())


def stage_all(path: str) -> None:
    rc, out = run_git(["add", "-A"], cwd=path)
    if rc != 0:
        raise RuntimeError("git add failed: " + out)


def commit(path: str, message: str|None, 
           allow_empty: bool = False) -> None:
    args = ["commit"]
    if message is not None: args += ["-m", message]
    else: args += ["-m", f"{APP} auto commit"]
    if allow_empty: args.append("--allow-empty")
    rc, out = run_git(args, cwd=path)
    if rc != 0:
        raise RuntimeError("git commit failed: " + out)


def remotes(path: str) -> list[str]:
    rc, out = run_git(["remote"], cwd=path)
    if rc == 0 and out.strip(): return out.splitlines()
    return []


def fetch_all(path: str) -> None:
    rc, out = run_git(["fetch", "--all", "--tags"], 
              cwd=path)
    if rc != 0:
        raise RuntimeError("git fetch failed: " + out)


def upstream_for_branch(path: str, branch: str) -> str|None:
    rc, out = run_git(["rev-parse", "--abbrev-ref", 
              f"{branch}@{{u}}"], cwd=path)
    return out if rc == 0 and out.strip() else None


def rev_list_counts(path: str, left: str, right: str
                   ) -> tuple[int, int] | None:
    rc, out = run_git(["rev-list", "--left-right", 
              "--count", f"{left}...{right}"], cwd=path)
    if rc != 0 or not out.strip(): return None
    a, b = out.split()
    return int(a), int(b)


def tags_sorted(path: str, pattern: str|None = None) -> list[str]:
    args = ["tag", "--list"]
    if pattern: args += [pattern]
    args += ["--sort=-v:refname"]
    rc, out = run_git(args, cwd=path)
    if rc == 0 and out.strip(): return out.splitlines()
    return []


def create_tag(path: str, tag: str,
               message: str|None = None, 
               sign: bool = False) -> None:
    args = ["tag"]
    if message: args += ["-a", tag, "-m", message]
    else: args += [tag]
    if sign: args.insert(1, "-s")
    rc, out = run_git(args, cwd=path)
    if rc != 0:
        raise RuntimeError("git tag failed: " + out)


def push(path: str, remote: str = "origin", 
         branch: str|None = None, force: bool = False, 
         push_tags: bool = True) -> None:
    args = ["push"]
    if force: args.append("--force")
    args.append(remote)
    if branch: args.append(branch)
    rc, out = run_git(args, cwd=path)
    if rc != 0:
        raise RuntimeError("git push failed: " + out)
    if push_tags:
        rc, out = run_git(["push", remote, "--tags"], 
                  cwd=path)
        if rc != 0:
            raise RuntimeError("git push --tags failed: "
                + out)
