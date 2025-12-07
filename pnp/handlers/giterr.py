"""
Git error handlers for pnp

Design goals:
- Match common git stderr patterns and route to a handler
- Avoid destructive defaults; require explicit user consent for risky ops
- Work in interactive and non-interactive (CI) modes
- Provide clear return values for callers to act on
- Log actions and preserve backups with timestamps
"""

from __future__ import annotations

# ======================= STANDARDS =======================
from subprocess import CompletedProcess, run
from typing import NoReturn, Callable
from pathlib import Path
import logging as log
import getpass
import shutil
import time
import sys
import re

# ==================== THIRD-PARTIES ======================
from tuikit.textools import wrap_text as wrap

# ======================== LOCALS =========================
from pnp._constants import CURSOR, BAD, GOOD, UPDATE, I
from pnp import utils


# Configure module logger
logger = log.getLogger("pnp.giterr")
logger.setLevel(log.DEBUG)
if not logger.handlers:
    file_handler = log.FileHandler("pnp_errors.log")

    fmt = log.Formatter("[pnp] GitError: %(asctime)s - %"
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


def _safe_copytree(src:Path, dst:Path, ignore=None)-> None:
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
          0 -> handled successfully and caller may continue
         10 -> recoverable with suggested action
         -1 -> user aborted
  Exception -> fatal
    """
    def __call__(self, stderr: str, cwd: str, 
                 ci: bool = False) -> int:
        """Dispatch based on stderr content"""
        if not stderr:
            logger.debug("Empty stderr passed to handler")
            return -1

        s = stderr.lower()

        internet_err = ("no address associated with "
                     + "hostname","could not resolve host",
                        "failed to connect")
        invd_obj_err = ("invalid object", "broken pipe",
                        "object corrupt")
        remort_r_err = ("remote contains work",
                        "non-fast-forward",
                        "failed to push some refs")
        missing_rmot = "could not read from remote"

        # internet failure
        if utils.any_in(internet_err, eq=s):
            self.internet_con_err(stderr)

        # dubious ownership
        if "dubious ownership" in s:
            return self.dubious_ownership(cwd, ci=ci)

        # invalid object / corruption
        if utils.any_in(invd_obj_err, eq=s):
            return self.invalid_object(s, cwd, ci=ci)

        # remote contains work / non-fast-forward
        if utils.any_in(remort_r_err, eq=s):
            return self.repo_corruption(cwd, ci=ci)

        # failure to read from remote
        if utils.any_in(missing_rmot, eq=s):
            error_type = self._classify_remote_issue(s)
            if not error_type:
                return self.missing_remote(s, cwd)
            self.internet_con_err(stderr, error_type)
        
        # fallback: log and bubble up
        print()
        logger.warning("Unhandled git stderr pattern. "
                      +"Showing normalized message.\n")
        return -1

    def _classify_remote_issue(self, s: str) -> int:
        """Return error type for remote/internet issues"""
        if "could not read from remote" in s:
            url_pattern = re.compile(r"https?://[^\s']+")
            if url_pattern.search(s):
                return 2  # Invalid/non-existent remote URL
        return 0

    def dubious_ownership(self, cwd: str,
                          ci: bool = False) -> int:
        """Handle 'dubious ownership' by asking to add safe.directory to git config"""
        prompt = utils.wrap("git reported dubious ownershi"
                           f"p for repository at {cwd!r}. "
                            "Mark this directory as safe "
                            "(git config --global --add "
                            "safe.directory)? [y/n]")
        if ci:
            logger.info("CI mode: refusing to change "
                       +"global git config. Abort")
            return -1

        if not utils.intent(prompt, "y", "return"):
            utils.transmit("User declined to mark as safe "
                          +"directory. Aborting operation", 
                          fg=BAD)
            return -1

        cmd = ["git", "config", "--global", "--add", 
               "safe.directory", cwd]
        cp = _run(cmd, cwd)
        if cp.returncode == 0:
            utils.transmit("Marked directory as safe", 
                fg=GOOD)
            return 0
        utils.transmit("Failed to mark safe directory; "
                      +"see git output for details", 
                      fg=BAD)
        return -1

    def invalid_object(self, stderr: str, cwd: str,
                       ci: bool = False) -> int:
        """
Handle invalid object errors

Strategy:
    - Show diagnostics (git fsck --full)
    - Offer: (1) open shell for manual fix
             (2) attempt safe reset (git reset --soft HEAD)
             (3) skip commit & continue
             (4) abort
        """
        # try to extract filename if present
        file_hint = None
        try:
            # common format: "Encountered an invalid object 
            # for 'path/to/file'"
            tail = stderr.split("for", 1)[-1]
            if "'" in tail:
                file_hint = tail.split("'")[1]
        except Exception: file_hint = None

        msg = utils.wrap("git commit failed: encountered "
            +  f"invalid object for {file_hint!r}"
           if file_hint else "git commit failed: "
            + "encountered invalid object")
        utils.transmit(msg, fg=BAD)

        # run diagnostics
        try:
            cmd = "git fsck --full"
            cmd_m = utils.color(cmd, UPDATE)
            utils.transmit(f"Running {cmd_m} for",
                            "diagnostics...")
            cp = _run(cmd.split(), cwd)
            diagnostics = cp.stdout + "\n" + cp.stderr
            
            # print truncated diagnostic (but log full)
            utils.transmit("↴\n" + diagnostics[:400]
                  + ("...(see logs for full output)" 
                 if len(diagnostics) > 400 else "")+"\n")
            logger.debug("Full git fsck output:\n%s\n", 
                   diagnostics)
        except Exception as e:
            exc = "git fsck invocation failed: %s\n"
            logger.exception(exc, e)

        if ci:
            msg = utils.wrap("CI mode: cannot perform "
                + "interactive repair. Aborting")
            utils.transmit(msg, fg=BAD)
            return -1

        # Present choices to user
        choices = [
            ("o", "Open a shell for manual fix (exit "
                 +"shell to continue)"),
            ("a", "Attempt hard auto-repair (git reset && "
                 +" git add .)"),
            ("s", "Skip commit and continue (not "
                 +"recommended)"),
            ("q", "Abort")
        ]
        utils.transmit("Choose an action: ", fg=UPDATE)
        for key, desc in choices:
            print(wrap(f"{key} — {desc}", I + 4, I))      

        sel = input(CURSOR).strip().lower() or "q"; print()
        if sel == "o":
            utils.transmit("Opening subshell...", 
                fg=UPDATE)
            
            # try to open interactive shell
            os_shell = shutil.which("bash") \
                    or shutil.which("sh")
            if not os_shell:
                utils.transmit("No shell available",fg=BAD)
                return -1
            _run([os_shell], cwd, check=False, 
                capture=False, text=True)
            return 10
        if sel == "a":
            # attempt had reset and re-add files
            try:
                _run(["git", "reset"], cwd, check=True)
                _run(["git", "add", "."], cwd, check=True)                
                return 10
            except Exception:
                msg = utils.wrap("Auto-repair failed. ")
                utils.transmit(msg, fg=BAD)
                return -1
        if sel == "s":
            msg = utils.wrap("Skipping commit and "
                + "continuing")
            utils.transmit(msg)
            return 0
        
        # default: abort
        utils.transmit("Aborting as requested", fg=BAD)
        sys.exit(1)

    def repo_corruption(self, cwd: str,
                        ci: bool = False) -> int:
        """
Handle remote / non-fast-forward conflicts by making a safe 
backup, synchronizing to remote state, and restoring 
local changes on top
        """
        # Determine current branch
        try:
            cp = _run(["git", "branch", "--show-current"],
                 cwd=str(cwd))
            branch = (cp.stdout or "").strip()
        except Exception:
            msg = utils.wrap("Could not determine current "
                            +"branch")
            utils.transmit(msg, fg=BAD)
            return -1
        if not branch:
            utils.transmit("No branch detected", fg=BAD)
            return -1

        backup_dir = _timestamped_backup_name(Path(cwd))

        # Step 1: backup local (exclude .git)
        try:
            msg = utils.wrap("Backing up current project "+
                            f"to {backup_dir}")
            utils.transmit(msg, fg=UPDATE)
            ignore = shutil.ignore_patterns(".git", 
                     ".github", "__pycache__")
            _safe_copytree(cwd, backup_dir, ignore=ignore)
        except Exception:
            utils.transmit("Backup failed", fg=BAD)
            return -1

        # Step 2: fetch + reset to remote
        try:
            utils.transmit("Fetching remote and resetting",
                          "local branch to origin/"+branch)
            _run(["git", "fetch", "origin"], cwd,
                 check=True)
            _run(["git", "reset", "--hard", 
                "origin/"+branch], cwd, check=True)
        except Exception:
            msg = utils.wrap("Could not sync with remote. "
                + "Attempting to restore backup...")
            utils.transmit(msg)
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
                utils.transmit("Restored files from",
                               "backup", fg=GOOD)
            except Exception:
                msg = utils.wrap()
                utils.transmit("Restore failed. Manual",
                               "intervention required", 
                               fg=BAD)
            return -1

        # Step 3: restore backed-up non-hidden files into
        #         cwd
        try:
            utils.transmit("Restoring local (uncommitted)",
                           "changes from backup...")
            for item in backup_dir.iterdir():
                if item.name.startswith("."): continue
                dest = cwd / item.name
                if item.is_dir():
                    shutil.copytree(item, dest, 
                        dirs_exist_ok=True)
                else: shutil.copy2(item, dest)
        except Exception:
            utils.transmit("Failed to copy back local",
                           "files. Aborting", fg=BAD)
            return -1

        # Step 4: stage restored changes
        try:
            _run(["git", "add", "."], cwd=str(cwd), 
                check=True)
        except Exception:
            utils.transmit("Staging restored files failed", 
                fg=BAD); return -1

        # Step 5: prompt commit message
        default = "Restored local changes after remote " \
                + "conflict"
        if ci: commit_msg = default
        else:
            prompt = utils.wrap("Remote contains work you "
                     "don't have locally. Provide a "
                     "commit message for restoring your "
                     "changes (or press enter to use "
                     "default)")
            utils.transmit(prompt)
            commit_msg = input(CURSOR).strip() or default

        try:
            _run(["git", "commit", "-m", commit_msg], 
                cwd=str(cwd), check=True)
            utils.transmit("Restored local changes",
                           "committed on top of remote",
                           "state", fg=GOOD)
            return 10  # caller should retry original 
                       # operation
        except Exception as e:
            exc = "Commit of restored changes failed: %s"
            logger.exception(exc, e)
            utils.transmit("Committing restored changes",
                           "failed. Manual fix required", 
                           fg=BAD)
            return -1

    
    def missing_remote(self, stderr: str, cwd: str,
                       ci: bool = False) -> int:
        """
Handle 'remote not valid' errors during push.

Args:
    stderr: stderr text from git (expected to contain 
            remote name)
    cwd: current working directory
    ci: whether running in CI (non-interactive)
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
            msg = utils.wrap("Could not determine missing "
                + "remote name from git output. Aborting")
            utils.transmit(msg, fg=BAD)
            logger.debug("stderr: %s", stderr)
            return -1

        msg = utils.wrap("Git push failed: remote "
            + f"{remote!r} is not configured or invalid")
        utils.transmit(msg)

        if ci:
            msg = utils.wrap("CI mode: cannot prompt. "
                + "Aborting")
            utils.transmit(msg, fg=BAD)
            return -1

        header = utils.wrap("Choose how you'd like to fix "
               + "this:")
        utils.transmit(header, fg=UPDATE)
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
            print(wrap(f"{key}. {desc}", I + 3, I))

        try:
            raw = input(CURSOR).strip()
            choice = raw or "7"
            if choice not in options:
                utils.transmit("Invalid choice", fg=BAD)
                return -1
        except (KeyboardInterrupt, EOFError) as e:
            if isinstance(e, EOFError): print()
            utils.transmit("Aborting...", fg=BAD)
            sys.exit(1)

        def get_repo_info() -> tuple[str,str] | None:
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
                utils.transmit("Aborting...", fg=BAD)
                sys.exit(1)

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
                token = getpass.getpass("Paste GitHub "
                      + "token (input hidden): ").strip()
            except Exception:
                utils.transmit("Could not read token.",
                               "Aborting", fg=BAD)
                return -1
            if not token:
                utils.transmit("Empty token provided.",
                               "Aborting", fg=BAD)
                return -1
            info = get_repo_info()
            if not info: return -1
            user, repo = info
            url = f"https://{token}@{g}/{user}/{repo}.git"
        elif choice == "4":
            msg = utils.wrap(f"Visit https://{g}/settings/"
                + "tokens to create a token. Exiting")
            utils.transmit(msg)
            return -1
        elif choice == "5":
            msg = utils.wrap("Opening subshell. Fix "
                + "remotes manually. Exit to continue")
            utils.transmit(msg, fg=UPDATE)
            os_shell = shutil.which("bash") \
                    or shutil.which("sh")
            if not os_shell:
                utils.transmit("No shell available",fg=BAD)
                return -1
            _run([os_shell], cwd, check=False, 
                capture=False, text=True)
            return 10
        elif choice == "6":
            utils.transmit("Skipping fix and continuing", 
                fg=GOOD)
            return 0
        else:
            utils.transmit("Aborting as requested", fg=BAD)
            sys.exit(1)

        try:
            msg = utils.wrap(f"Adding remote {remote!r} ->"
                            +f" {url}")       
            utils.transmit(msg, fg=UPDATE)
            cp = _run(["git", "remote", "add", remote, 
                 url], cwd, check=True)
            if cp.returncode != 0:
                utils.transmit("Failed to add remote", 
                    fg=BAD)
                logger.debug("git remote add stderr: %s", 
                    cp.stderr)
                return -1
        except Exception as e:
            logger.exception("Failed to add remote: %s", e)
            utils.transmit("Failed to add remote", fg=BAD)
            return -1

        # show remotes for confirmation
        try:
            cp2 = _run(["git", "remote", "-v"], cwd)
            utils.transmit("Updated remotes:")
            print((cp2.stdout or cp2.stderr or "").strip())
        except Exception as e:
            logger.exception("Failed to list remotes: %s",
                e)

        # success — suggest retry original operation
        return 10

    def internet_con_err(self, stderr: str, 
                         _type: int = 1) -> NoReturn:
        """Handle network or remote URL issues"""

        if "'" in stderr: host = stderr.split("'")[1]
        else: host = ""
        host = f": {host!r}." if host else "."

        suggestion = "Check network"
        if _type == 2:
            reason = "invalid or non-existent Git remote"
            cmd = utils.color("git remote set-url origin " \
                + "<correct-url>", UPDATE)
            suggestion = f"Run {cmd}"
        else: reason = "network/connectivity problem"

        prompt = utils.wrap(f"git failed due to {reason}"
                 f"{host} {suggestion} and retry")
        utils.transmit(prompt, fg=BAD)
        sys.exit(1)


def normalize_stderr(stderr: Exception | str,
                     head: Optional[str] = None,
                     max_len: int = 400) -> str:
    """
Turn stderr (or an Exception) into a readable, wrapped paragraph
Returns a string (already wrapped) suitable for display
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
                    +"content logged")
        logger.debug("Full stderr:\n%s", text)
        text = text[:max_len].rstrip() + " ...(truncated)"
    return utils.wrap(text)


# module-level reusable instance for importers
handle = Handlers()
