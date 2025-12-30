"""
Git error handlers for pnp

Design goals:
  - Match common git stderr patterns and route to a handler
  - Avoid destructive defaults; require explicit user
    consent for risky ops unless auto-fix is set
  - Work in interactive and non-interactive (CI) modes
  - Provide clear return values for callers to act on
  - Log actions and preserve backups with timestamps
"""

from __future__ import annotations

# ======================= STANDARDS =======================
from subprocess import CompletedProcess, run
from typing import NoReturn
from pathlib import Path
import logging as log
import getpass
import shutil
import time
import sys
import os
import re

# ======================== LOCALS =========================
from pnp.utils import transmit, any_in, color, wrap, Output
from pnp._constants import I, BAD, INFO, CURSOR, CI_MODE
from pnp.utils import wrap_text, intent, auto
from pnp._constants import AUTOFIX


# Configure module logger
logger = log.getLogger("pnp.giterr")
logger.setLevel(log.DEBUG)
if not logger.handlers:
    with open(Path().cwd() / "log_dir") as f:
        for path in f: log_dir = Path(path)

    os.remove(Path().cwd() / "log_dir")

    try: os.mkdir(log_dir)
    except FileExistsError: pass

    pnp_errors   = log_dir / "debug.log"
    file_handler = log.FileHandler(str(pnp_errors))

    fmt = log.Formatter("GitError: %(asctime)s - %"
        + "(levelname)s - %(message)s")
    file_handler.setFormatter(fmt)

    logger.addHandler(file_handler)


def _run(cmd: list[str], cwd: str, check: bool = False,
         capture: bool = True, text: bool = True
         ) -> CompletedProcess:
    """Wrapper around subprocess.run with consistent kwargs"""
    logger.debug("RUN: %s (cwd=%s)", " ".join(cmd), cwd)
    try: cp = run(cmd, cwd=cwd, check=check,
              capture_output=capture, text=text)
    except Exception as e:
        exc = "Subprocess invocation failed: %s\n"
        logger.exception(exc, e)
    logger.debug("RC=%s stdout=%r stderr=%r\n",
        cp.returncode, cp.stdout, cp.stderr)
    return cp


def _timestamped_backup_name(base: Path) -> Path:
    ts = time.strftime("%Y%m%d_%H%M%S")
    return base.parent / f"{base.name}-backup-{ts}"


def _safe_copytree(src: Path, dst: Path, ignore=None) -> None:
    """Copy tree with dirs_exist_ok semantics and safe error messages"""
    try: shutil.copytree(src, dst, dirs_exist_ok=True,
         ignore=ignore)
    except Exception:
        exc = "Failed to copy tree from %s to %s"
        logger.exception(exc, src, dst); raise


class Handlers:
    """
    Instance with callable interface
    Returns status codes or raises to signal fatal conditions

    API notes:
        - stderr: the stderr string as captured from a failed
                  git command
        - cwd: current working directory
        - Caller should inspect return value:
             0 -> handled successfully and caller may
                  continue
            10 -> recoverable with suggested action
            -1 -> user aborted
    Exception -> fatal
    """
    def __init__(self):
        out          = Output()
        self.success = out.success
        self.prompt  = out.prompt
        self.info    = out.info
        self.warn    = out.warn
        self.abort   = out.abort

    def __call__(self, stderr: str, cwd: str) -> int:
        """Dispatch based on stderr content"""
        if not stderr:
            logger.debug("Empty stderr passed to handler")
            return -1

        s = stderr.lower()

        internet_err = ("no address associated with "
                     + "hostname", "could not resolve host",
                       "software caused connection abort",
                       "failed to connect")
        invd_obj_err = ("invalid object", "broken pipe",
                        "has null sha1", "object corrupt",
                        "unexpected diff status a")
        #remort_r_err = ("remote contains work",
        #                "non-fast-forward",
        #                "failed to push some refs")
        missing_rmot = "could not read from remote"

        # internet failure
        if any_in(internet_err, eq=s):
            self.internet_con_err(stderr)

        # dubious ownership
        if "dubious ownership" in s:
            return self.dubious_ownership(cwd)

        # invalid object / corruption
        if any_in(invd_obj_err, eq=s):
            return self.invalid_object(s, cwd)

        # remote contains work / non-fast-forward (under review)
        #if any_in(remort_r_err, eq=s):
        #    return self.repo_corruption(cwd)

        # failure to read from remote
        if any_in(missing_rmot, eq=s):
            error_type = self._classify_remote_issue(s)
            if not error_type:
                return self.missing_remote(s, cwd)
            self.internet_con_err(stderr, error_type)

        # fallback: log and bubble up
        print()
        logger.warning("Unhandled git stderr pattern. "
                       "Showing normalized message.\n")
        return -1

    def _classify_remote_issue(self, s: str) -> int:
        """Return error type for remote/internet issues"""
        if "could not read from remote" in s:
            url_pattern = re.compile(r"https?://[^\s']+")
            if url_pattern.search(s):
                return 2  # Invalid/non-existent remote URL
        return 0

    def dubious_ownership(self, cwd: str) -> int:
        """Handle 'dubious ownership' by asking to add safe.directory to git config"""
        prompt = wrap("git reported dubious ownership "
                 f"for repository at {cwd!r}. Mark this "
                 "directory as safe? [y/n]")
        if CI_MODE and not AUTOFIX:
            logger.info("CI mode: refusing to change global"
                        " git config")
            return -1

        if not AUTOFIX and not intent(prompt, "y", "return"):
            self.warn("user declined to mark as safe "
                      "directory")
            sys.exit(1)

        cmd = ["git", "config", "--global", "--add",
               "safe.directory", cwd]
        cp = _run(cmd, cwd)
        if cp.returncode == 0:
            self.success("marked directory as safe")
            return 0
        self.warn("failed to mark safe directory; see git "
                  "output for details")
        return -1

    def invalid_object(self, stderr: str, cwd: str) -> int:
        """
        Handle invalid object errors

        Strategy:
            - Show diagnostics (git fsck --full)
            - Offer: (1) open shell for manual fix
                     (2) attempt hard reset (git reset)
                     (3) skip commit & continue
                     (4) abort
        """
        if not any_in("diff status", "null sha1", eq=stderr):
            step  = "commit"
            issue = "missing/dangling blobs"
            # try to extract filename if present
            file_hint = None
            try:
                # common format: "Encountered an invalid
                # object for 'path/to/file'"
                tail = stderr.split("for", 1)[-1]
                if "'" in tail:
                    file_hint = tail.split("'")[1]
            except Exception: file_hint = None

            self.warn("git commit failed: encountered "
                    + f"invalid object for {file_hint!r}"
                   if file_hint else "git commit failed: "
                    + "encountered invalid object")
        elif "diff status" in stderr:
            step  = "staging"
            issue = "bad index file sha1 signature"
            self.warn("git add failed: unexpected diff status A")
        else:
            step  = "staging"
            issue = "cache entry's null sha1"
            self.warn("git add failed: cache entry has null sha1")

        # run diagnostics
        try:
            cmd   = "git fsck --full"
            cmd_m = color(cmd, INFO)
            self.prompt(f"running {cmd_m} for diagnostics...")
            cp          = _run(cmd.split(), cwd)
            diagnostics = cp.stdout + "\n" + cp.stderr

            # print truncated diagnostic (but log full)
            self.prompt("↴\n" + diagnostics[:400]
                     + ("...(see logs for full output)"
                    if len(diagnostics) > 400 else "")
                     + "\n", False)
            logger.debug("Full git fsck output:\n%s\n",
                   diagnostics)
        except Exception as e:
            exc = "git fsck invocation failed: %s\n"
            logger.exception(exc, e)

        if CI_MODE and not AUTOFIX:
            self.warn("CI mode: cannot perform interactive "
                   + "repair")
            return -1

        if not AUTOFIX:
            # Present choices to user
            choices = {
                "1": "Open a shell for manual fix",
                "2": "Attempt destructive reset",
                "3": "Attempt safe reset (requires internet)",
                "4": f"Skip {step} and continue",
                "5": "Abort"
            }
            self.info("Choose an action: ")
            for key, desc in choices.items():
                print(wrap_text(f"{key}. {desc}", I + 3, I))

            opt = input(CURSOR).strip().lower(); print()
        else:
            self.prompt(auto("attempting hard auto-repair to"
                            f" resolve {issue}"))
            opt = "2"

        if opt == "1":
            self.info("opening subshell...")

            # try to open interactive shell
            os_shell = shutil.which("bash") \
                    or shutil.which("zsh") \
                    or shutil.which("sh")
            if not os_shell:
                self.warn("no shell available")
                return -1
            _run([os_shell], cwd, check=False,
                capture=False, text=True)
            return 10
        if opt == "2":
            if "null sha1" in stderr:
                _run(["rm", ".git/index"], cwd, check=True)
            try:
                _run(["git", "reset"], cwd, check=True)
                _run(["git", "add", "."], cwd, check=True)
                return 10
            except Exception as e:
                logger.exception("auto-repair failed: %s", e)
                self.warn("auto-repair failed — manual "
                          "intervention may be required")
                return -1
        if opt == "4":
            self.prompt("skipping commit and continuing")
            return 0

        # default: abort
        self.abort("aborting as requested")

    def repo_corruption(self, cwd: str) -> int:
        """
        Handle remote / non-fast-forward conflicts by making
        a safe backup, synchronizing to remote state, and
        restoring local changes on top
        """
        # Determine current branch
        try:
            cp = _run(["git", "branch", "--show-current"],
                 cwd=str(cwd))
            branch = (cp.stdout or "").strip()
        except Exception:
            self.warn("could not determine current branch")
            return -1
        if not branch:
            self.warn("no branch detected")
            return -1

        backup_dir = _timestamped_backup_name(Path(cwd))

        # Step 1: backup local (exclude .git)
        try:
            self.success("backing up current project to "
                        f"{backup_dir}")
            ignore = shutil.ignore_patterns(".git",
                     ".github", "__pycache__")
            _safe_copytree(cwd, backup_dir, ignore=ignore)
        except Exception:
            self.warn("backup failed")
            return -1

        # Step 2: fetch + reset to remote
        try:
            self.warn("fetching remote and resetting local "
                      "branch to origin/" + branch)
            _run(["git", "fetch", "origin"], cwd,
                 check=True)
            _run(["git", "reset", "--hard",
                "origin/" + branch], cwd, check=True)
        except Exception:
            self.prompt("could not sync with remote. "
                      + "Attempting to restore backup...")
            # attempt restore from backup
            try:
                # restore files (non-destructive) by
                # copying back
                for item in backup_dir.iterdir():
                    if item.name.startswith("."): continue
                    dest = cwd / item.name
                    if item.is_dir():
                        shutil.copytree(item, dest,
                            dirs_exist_ok=True)
                    else:
                        shutil.copy2(item, dest)
                self.success("restored files from backup")
            except Exception:
                self.warn("restore failed. Manual"
                        + "intervention required")
            return -1

        # Step 3: restore backed-up non-hidden files into
        #         cwd
        try:
            self.prompt("restoring local (uncommitted) "
                      + "changes from backup...")
            for item in backup_dir.iterdir():
                if item.name.startswith("."): continue
                dest = cwd / item.name
                if item.is_dir():
                    shutil.copytree(item, dest,
                        dirs_exist_ok=True)
                else: shutil.copy2(item, dest)
        except Exception:
            self.warn("failed to copy back local files")
            return -1

        # Step 4: stage restored changes
        try:
            _run(["git", "add", "."], cwd=str(cwd),
                check=True)
        except Exception:
            self.warn("failed to stage restored files")
            return -1

        # Step 5: prompt commit message
        default = "restored local changes after remote " \
                + "conflict"
        if CI_MODE: commit_msg = default
        else:
            self.prompt("remote contains work you "
                        "don't have locally. Provide a "
                        "commit message for restoring your "
                        "changes (or press enter to use "
                        "default)")
            commit_msg = input(CURSOR).strip() or default

        try:
            _run(["git", "commit", "-m", commit_msg],
                cwd=str(cwd), check=True)
            self.success("restored local changes "
                         "committed on top of remote "
                         "state")
            return 10  # caller should retry original
                       # operation
        except Exception as e:
            exc = "commit of restored changes failed: %s"
            logger.exception(exc, e)
            self.warn("committing restored changes failed. "
                      "Manual fix required")
            return -1

    def missing_remote(self, stderr: str, cwd: str) -> int:
        """
        Handle 'remote not valid' errors during push.

        Args:
            stderr: stderr text from git (expected to contain
                    remote name)
            cwd: current working directory
        """
        # try to parse remote name
        remote = None
        try:
            low = stderr
            if "'" in low:
                remote = low.split("'", 2)[1]
            else:
                # fallback heuristics
                parts = low.split()
                for idx, tok in enumerate(parts):
                    if tok.lower() in ("remote", "origin",
                            "push") and idx + 1 < len(parts):
                        candidate = parts[idx + 1].strip(
                                    ":'\",.")
                        if len(candidate) <= 64:
                            remote = candidate
                            break
        except Exception: remote = None

        if not remote:
            self.warn("could not determine missing remote "
                      "name from git output")
            logger.debug("stderr: %s", stderr)
            return -1

        self.warn(f"Git push failed: remote {remote!r} is "
                  "not configured or invalid")

        if CI_MODE and not AUTOFIX:
            self.warn("CI mode: cannot perform interactive repair")
            return -1

        if not AUTOFIX:
            self.info("Choose how you'd like to fix this:")
            options = {
                "1": "Add origin (HTTPS)",
                "2": "Add origin (SSH)",
                "3": "Add origin using GitHub token (HTTPS)",
                "4": "Open GitHub token page (browser)",
                "5": "Open shell to fix manually",
                "6": "Skip and continue",
                "7": "Abort"
            }

            for key, desc in options.items():
                print(wrap_text(f"{key}. {desc}", I + 3, I))

            try:
                raw = input(CURSOR).strip(); print()
                choice = raw or "7"
                if choice not in options:
                    transmit("invalid choice", fg=BAD)
                    return -1
            except (KeyboardInterrupt, EOFError) as e:
                if isinstance(e, EOFError): print()
                transmit("exiting...", fg=BAD)
                sys.exit(1)
        else:
            msg = auto("attempting to add origin via SSH")
            self.prompt(msg)
            choice = "2"

        def get_repo_info() -> tuple[str, str] | None:
            repo_arg = None
            if any(a.startswith("--gh-repo") for a in
                                            sys.argv):
                for i, a in enumerate(sys.argv):
                    if a.startswith("--gh-repo="):
                        repo_arg = a.split("=", 1)[1]
                        break
                    if a == "--gh-repo" and i + 1 < len(
                                               sys.argv):
                        repo_arg = sys.argv[i + 1]
                        break
            if repo_arg:
                if "/" in repo_arg:
                    user, repo = repo_arg.split("/", 1)
                    return user.strip(), repo.strip()

            try:
                user = input("GitHub username: ").strip()
                repo = input("Repository name: ").strip()
                print()
                return user, repo
            except (KeyboardInterrupt, EOFError):
                self.abort()

        # handle choices
        g = "github.com"
        if choice == "1":
            info = get_repo_info()
            if not info: return -1
            user, repo = info
            url = f"https://{g}/{user}/{repo}.git"
        elif choice == "2":
            info = get_repo_info()
            if not info: return -1
            user, repo = info
            url = f"git@{g}:{user}/{repo}.git"
        elif choice == "3":
            try:
                msg = "paste GitHub token (input hidden)"
                self.prompt(msg)
                token = getpass.getpass(CURSOR).strip()
            except Exception:
                self.warn("could not read token")
                return -1
            if not token:
                self.warn("empty token provided")
                return -1
            info = get_repo_info()
            if not info: return -1
            user, repo = info
            url = f"https://{token}@{g}/{user}/{repo}.git"
        elif choice == "4":
            self.prompt(f"visit https://{g}/settings/tokens "
                        "to create a token")
            return -1
        elif choice == "5":
            self.prompt("opening subshell. Fix remotes "
                        "manually. Exit to continue")
            os_shell = shutil.which("bash") \
                    or shutil.which("zsh") \
                    or shutil.which("sh")
            if not os_shell:
                self.warn("no shell available")
                return -1
            _run([os_shell], cwd, check=False,
                capture=False, text=True)
            return 10
        elif choice == "6":
            self.prompt("skipping fix and continuing")
            return 0
        else:
            self.abort("aborting as requested")

        try:
            self.info(f"adding remote {remote!r} -> {url}")
            cp = _run(["git", "remote", "add", remote,
                 url], cwd, check=True)
            if cp.returncode != 0:
                self.warn("failed to add remote")
                logger.debug("git remote add stderr: %s",
                    cp.stderr)
                return -1
        except Exception as e:
            logger.exception("Failed to add remote: %s", e)
            e = normalize_stderr(e)
            self.warn("failed to add remote:", e)
            return -1

        # show remotes for confirmation
        try:
            cp2 = _run(["git", "remote", "-v"], cwd)
            self.prompt("updated remotes↴")
            self.info(cp2.stdout.strip(), prefix=False)
        except Exception as e:
            logger.exception("Failed to list remotes: %s", e)

        # success — suggest retry original operation
        return 10

    def internet_con_err(self, stderr: str, _type: int = 1
                        ) -> int | NoReturn:
        """Handle network or remote URL issues"""

        if "'" in stderr: host = stderr.split("'")[1]
        else: host = ""
        host = f": {host!r}." if host else "."

        suggestion = "Check network"
        if _type == 2:
            reason = "invalid or non-existent Git remote"
            cmd = color("git remote set-url origin "
                + "<correct-url>", INFO)
            suggestion = f"Run {cmd}"
        else: reason = "network/connectivity problem"

        self.warn(f"git failed due to {reason}{host} "
                  f"{suggestion} and retry")

        sys.exit(1)


def normalize_stderr(stderr: Exception | str,
                     head: str | None = None,
                     max_len: int = 400) -> str:
    """
    Turn stderr (or an Exception) into a readable, wrapped
    paragraph

    Returns a string suitable for display
    """
    if isinstance(stderr, Exception):
        stderr = str(stderr)

    # Collapse repeated whitespace and trim
    text = " ".join(stderr.strip().split())
    if head: text = f"{head} {text}"
    # Shorten very long outputs for display
    # full output should be logged
    if len(text) > max_len:
        logger.debug("Truncating stderr for display. Full "
                     "content logged")
        logger.debug("Full stderr:\n%s", text)
        text = text[:max_len].rstrip() + " ...(truncated)"
    return wrap(text)


# module-level reusable instance for importers
handle = Handlers()
