"""
Git error handlers for pnp.

Design goals:
  - Match common git stderr patterns and route to a handler
  - Avoid destructive defaults; require explicit user
    consent for risky ops unless auto-fix is set
  - Work in interactive and non-interactive (CI) modes
  - Provide clear return values for callers to act on
  - Log actions and preserve backups with timestamps
"""
# ======================= STANDARDS =======================
from subprocess import CompletedProcess, run
from typing import Callable, Iterable
from pathlib import Path
import logging as log
import getpass
import shutil
import time
import os
import re

# ======================== LOCALS =========================
from .resolver_classifier import (
    ErrorClassification,
    classify as classify_error,
    classify_stderr as classifier_classify_stderr,
    reset_telemetry as reset_classifier_telemetry,
    rule_conflict_count as classifier_rule_conflict_count,
    unknown_classification_count as classifier_unknown_count
)
from .utils import transmit, any_in, color, wrap, Output
from .utils import StepResult, wrap_text, intent, auto
from .resolver_policy import decide as apply_policy
from .remediation_policy import can_run_remediation
from ._constants import I, BAD, INFO, CURSOR
from .resolver_policy import PolicyDecision
from . import _constants as const
from .utils import get_shell
from . import telemetry


# Configure module logger
logger = log.getLogger("pnp.resolver")
logger.setLevel(log.DEBUG)
def configure_logger(log_dir: Path) -> None:
    """Configure resolver logger once per process."""
    telemetry.init_event_stream(Path(log_dir))
    if logger.handlers: return
    os.makedirs(log_dir, exist_ok=True)
    pnp_errors   = log_dir / "debug.log"
    file_handler = log.FileHandler(str(pnp_errors))
    fmt          = log.Formatter("GitError: %(asctime)s - %"
                 + "(levelname)s - %(message)s")
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)


def _run(cmd: list[str], cwd: str, check: bool = False,
         capture: bool = True, text: bool = True
         ) -> CompletedProcess:
    """
    Wrapper around subprocess.run with consistent kwargs.
    """
    logger.debug("RUN: %s (cwd=%s)", " ".join(cmd), cwd)
    try:
        cp = run(cmd, cwd=cwd, check=check,
                 capture_output=capture, text=text)
    except Exception as e:
        exc = "Subprocess invocation failed: %s\n"
        logger.exception(exc, e)
        raise
    logger.debug("RC=%s stdout=%r stderr=%r\n",
        cp.returncode, cp.stdout, cp.stderr)
    return cp


def _timestamped_backup_name(base: Path) -> Path:
    ts = time.strftime("%Y%m%d_%H%M%S")
    return base.parent / f"{base.name}-backup-{ts}"


def _https_fallback_remote(remote_url: str) -> str | None:
    """Return HTTPS fallback for common SSH remote formats."""
    text = remote_url.strip()
    match = re.match(r"^git@([^:]+):(.+)$", text)
    if match is not None:
        host, repo = match.group(1), match.group(2)
        return f"https://{host}/{repo}"
    match = re.match(r"^ssh://git@([^/]+)/(.+)$", text)
    if match is not None:
        host, repo = match.group(1), match.group(2)
        return f"https://{host}/{repo}"
    return None


def _safe_reset_manual_steps(
    remote_url: str,
    cwd: Path,
    backup_dir: Path,
    branch: str,
) -> list[str]:
    """Build explicit manual recovery steps after safe-reset clone failures."""
    steps = [
        f"1) verify remote is reachable: git ls-remote {remote_url}",
        "2) if SSH fails, verify keys: ssh -T git@github.com",
    ]
    https_url = _https_fallback_remote(remote_url)
    if https_url:
        steps.append(f"3) switch to HTTPS fallback: git -C {cwd} remote set-url origin {https_url}")
    else:
        steps.append("3) set a working HTTPS remote URL for origin")
    branch_name = branch or "main"
    steps.extend(
        [
            f"4) fresh clone manually: git clone <working-remote-url> {cwd.name}-reclone",
            "5) copy recovered .git into repo and restore files from backup:",
            f"   backup path: {backup_dir}",
            f"6) retry pnp with: python -m pnp {cwd} --ci --auto-fix --safe-reset",
            f"7) if still blocked, checkout branch explicitly: git -C {cwd} checkout {branch_name}",
        ]
    )
    return steps


def _safe_copytree(src: Path, dst: Path,
                   ignore: Callable[[str, list[str]],
                           Iterable[str]] | Callable[[str |
                           os.PathLike[str], list[str]],
                           Iterable[str]] | None = None
                           ) -> None:
    """
    Copy tree with dirs_exist_ok semantics and safe error
    messages.
    """
    try: shutil.copytree(src, dst, dirs_exist_ok=True,
         ignore=ignore)
    except Exception:
        exc = "Failed to copy tree from %s to %s"
        logger.exception(exc, src, dst); raise


def _emit_remediation_event(
    action: str,
    outcome: str,
    details: dict[str, str] | None = None,
) -> None:
    """Write structured remediation event for observability."""
    payload: dict[str, object] = {
        "action": action,
        "outcome": outcome,
        "details": details or {},
    }
    telemetry.emit_event(
        event_type="remediation",
        step_id=action,
        payload=payload,
    )


class Handlers:
    """
    Instance with callable interface.
    Returns status codes or raises to signal fatal
    conditions.

    API notes:
        - stderr: the stderr string as captured from a
                  failed git command
        - cwd: current working directory
        - Caller should inspect StepResult:
               OK -> handled successfully and caller may
                     continue
            RETRY -> recoverable with suggested action
             FAIL -> resolution failed
    """
    def __init__(self) -> None:
        out          = Output()
        self.success = out.success
        self.prompt  = out.prompt
        self.info    = out.info
        self.warn    = out.warn
        self.abort   = out.abort
        self.last_error: dict[str, str] | None = None
        self.last_decision: PolicyDecision | None = None

    def classify(self, stderr: str) -> ErrorClassification:
        """Classify git stderr into stable code/severity/handler."""
        return classify_error(stderr)

    def decide(self, stderr: str, cwd: str) -> PolicyDecision:
        """Dispatch and return a typed policy decision."""
        cls = self.classify(stderr)
        self.last_error = cls.as_dict()
        def _on_unhandled() -> None:
            print()
            logger.warning("Unhandled git stderr pattern. "
                           "Showing normalized message.\n")

        def _on_decision(decision: PolicyDecision) -> None:
            self.last_decision = decision

        return apply_policy(
            classification=cls,
            stderr=stderr,
            cwd=cwd,
            remediation=self,
            on_unhandled=_on_unhandled,
            on_decision=_on_decision,
        )

    def __call__(self, stderr: str, cwd: str) -> StepResult:
        """Backward-compatible callable interface."""
        return self.decide(stderr, cwd).result

    def _allow_remediation(self, action: str) -> tuple[bool, str]:
        if const.AUTOFIX and action == "safe_fix_network":
            if not bool(const.ALLOW_SAFE_RESET):
                allowed, reason = False, "action requires --safe-reset in auto-fix mode"
                _emit_remediation_event(action, "blocked", {"reason": reason})
                return allowed, reason
        if const.AUTOFIX and action == "destructive_reset":
            if not bool(const.ALLOW_DESTRUCTIVE_RESET):
                allowed, reason = False, "action requires --destructive-reset in auto-fix mode"
                _emit_remediation_event(action, "blocked", {"reason": reason})
                return allowed, reason

        allowed, reason = can_run_remediation(
            action=action,
            ci_mode=bool(const.CI_MODE),
            autofix=bool(const.AUTOFIX),
            interactive=not bool(const.CI_MODE),
        )
        if not allowed and const.AUTOFIX:
            if action == "safe_fix_network" and bool(const.ALLOW_SAFE_RESET):
                allowed, reason = True, ""
            elif (
                action == "destructive_reset"
                and bool(const.ALLOW_DESTRUCTIVE_RESET)
            ):
                allowed, reason = True, ""
        outcome = "allowed" if allowed else "blocked"
        detail  = {"reason": reason} if reason else {}
        _emit_remediation_event(action, outcome, detail)
        return allowed, reason

    def _simulate_remediation(
        self,
        action: str,
        result: StepResult,
        note: str = "",
    ) -> tuple[bool, StepResult]:
        if not const.DRY_RUN: return False, result
        msg = f"{const.DRYRUN}simulate remediation: {action}"
        self.prompt(msg)
        detail: dict[str, str] = {"result": str(result.value)}
        if note:
            detail["note"] = note
        _emit_remediation_event(action, "simulated", detail)
        return True, result

    def dubious_ownership(self, stderr: str, cwd: str) -> StepResult:
        """
        Handle 'dubious ownership' by asking to add
        safe.directory to git config
        """
        allowed, reason = self._allow_remediation(
                          "git_safe_directory")
        if not allowed:
            self.warn(reason)
            return StepResult.FAIL
        matched = re.search(r"safe\.directory\s+([^\n\r]+)", stderr)
        suggested = ""
        if matched is not None:
            suggested = matched.group(1).strip().strip("'\"")
        targets: list[str] = []
        if suggested:
            targets.append(suggested)
        targets.append(str(Path(cwd).resolve()))
        targets.append(cwd)
        dedup_targets: list[str] = []
        seen = set()
        for item in targets:
            token = item.strip()
            if not token or token in seen:
                continue
            seen.add(token)
            dedup_targets.append(token)
        prompt = wrap("git reported dubious ownership "
                 f"for repository at {dedup_targets[0]!r}. Mark this "
                 "directory as safe? [y/n]")

        if not const.AUTOFIX and not intent(prompt, "y", "return"):
            msg = "user declined to mark as safe directory"
            self.abort(msg)

        simulated, result = self._simulate_remediation(
            action="git_safe_directory",
            result=StepResult.RETRY,
            note="would run git config --global --add safe.directory",
        )
        if simulated: return result

        failed = False
        for target in dedup_targets:
            cmd = ["git", "config", "--global", "--add",
                   "safe.directory", target]
            cp = _run(cmd, cwd)
            if cp.returncode != 0:
                failed = True
                break
        if not failed:
            _emit_remediation_event("git_safe_directory", "success")
            self.success("marked directory as safe")
            return StepResult.RETRY
        _emit_remediation_event("git_safe_directory", "failed")
        self.warn("failed to mark safe directory; see git "
                  "output for details")
        return StepResult.FAIL

    def invalid_object(self, stderr: str, cwd: str
                      ) -> StepResult:
        """
        Handle invalid object errors

        Strategy:
            - Show diagnostics (git fsck --full)
            - Offer: (1) open shell for manual fix
                     (2) attempt hard reset (git reset)
                     (3) attempt safe reset
                     (4) skip staging/commit & continue
                     (5) abort
        """
        step = "staging"
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
                    + "encountered an invalid object")
        elif "diff status" in stderr:
            issue = "bad index file sha1 signature"
            self.warn("git add failed: unexpected diff status A")
        else:
            issue = "cache entry's null sha1"
            self.warn("git add failed: cache entry has null sha1")

        # run diagnostics
        try:
            cmd   = "git fsck --full"
            cmd_m = cmd if const.CI_MODE else color(cmd, INFO)
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

        if const.CI_MODE and not const.AUTOFIX:
            self.warn("CI mode: cannot perform interactive "
                   + "repair")
            return StepResult.FAIL

        if not const.AUTOFIX:
            # Present choices to user
            choices = {
                "1": "Open a shell for manual fix",
                "2": "Attempt destructive reset",
                "3": "Attempt safe fix (requires internet)",
                "4": f"Skip {step} and continue",
                "5": "Abort"
            }
            self.info("Choose an action: ")
            for key, desc in choices.items():
                print(wrap_text(f"{key}. {desc}", I + 3, I))

            opt = input(CURSOR).strip().lower(); print()
        else:
            can_reset, _ = self._allow_remediation(
                           "destructive_reset")
            if can_reset:
                self.prompt(auto("attempting hard "
                    f"auto-repair to resolve {issue}"))
                opt = "2"
            else:
                can_safe, _ = self._allow_remediation(
                              "safe_fix_network")
                if can_safe:
                    self.prompt(auto("destructive reset disabled; "
                        "attempting safe network repair"))
                    opt = "3"
                else:
                    self.prompt(auto("destructive reset "
                        "disabled by policy; skipping and "
                        "continuing"))
                    opt = "4"

        if opt == "1":
            allowed, reason = self._allow_remediation(
                              "open_shell_manual")
            if not allowed:
                self.warn(reason)
                return StepResult.FAIL
            simulated, result = self._simulate_remediation(
                action="open_shell_manual",
                result=StepResult.RETRY,
            )
            if simulated: return result
            self.info("opening subshell...")

            # try to open interactive shell
            shell = get_shell()
            if not shell:
                self.warn("no shell available")
                return StepResult.FAIL
            _run([shell], cwd, check=False,
                capture=False, text=True)
            _emit_remediation_event("open_shell_manual", "success")
            return StepResult.RETRY
        if opt == "2":
            allowed, reason = self._allow_remediation(
                              "destructive_reset")
            if not allowed:
                self.warn(reason)
                return StepResult.FAIL
            simulated, result = self._simulate_remediation(
                action="destructive_reset",
                result=StepResult.RETRY,
            )
            if simulated: return result
            if "null sha1" in stderr:
                _run(["rm", ".git/index"], cwd, check=True)
            try:
                _run(["git", "reset"], cwd, check=True)
                _run(["git", "add", "."], cwd, check=True)
                _emit_remediation_event("destructive_reset", "success")
                return StepResult.RETRY
            except Exception as e:
                logger.exception("auto-repair failed: %s", e)
                _emit_remediation_event("destructive_reset", "failed")
                self.warn("auto-repair failed — manual "
                          "intervention may be required")
                return StepResult.FAIL
        if opt == "3":  # TODO
            allowed, reason = self._allow_remediation(
                              "safe_fix_network")
            if not allowed:
                self.warn(reason)
                return StepResult.FAIL
            cwd_path = Path(cwd).resolve()
            backup_dir = _timestamped_backup_name(cwd_path)
            ts = time.strftime("%Y%m%d_%H%M%S")
            clone_dir = cwd_path.parent / f"{cwd_path.name}-reclone-{ts}"
            simulated, result = self._simulate_remediation(
                action="safe_fix_network",
                result=StepResult.RETRY,
                note=f"would backup {cwd_path} and refresh git metadata via clone",
            )
            if simulated:
                return result
            try:
                cp_remote = _run(
                    ["git", "remote", "get-url", "origin"],
                    cwd,
                    check=True,
                )
                remote_url = (cp_remote.stdout or "").strip()
                cp_branch = _run(
                    ["git", "branch", "--show-current"],
                    cwd,
                )
                branch = (cp_branch.stdout or "").strip()
                if not remote_url:
                    self.warn("remote origin URL is not configured")
                    _emit_remediation_event(
                        "safe_fix_network",
                        "failed",
                        {"reason": "missing origin remote url"},
                    )
                    return StepResult.FAIL

                self.prompt(f"creating backup at {backup_dir}")
                _safe_copytree(cwd_path, backup_dir)

                self.prompt("cloning fresh repository copy for metadata recovery...")
                clone_errors: list[str] = []
                clone_urls = [remote_url]
                fallback_url = _https_fallback_remote(remote_url)
                if fallback_url and fallback_url != remote_url:
                    clone_urls.append(fallback_url)
                clone_ok = False
                used_remote = remote_url
                for candidate_url in clone_urls:
                    try:
                        _run(
                            ["git", "clone", candidate_url, str(clone_dir)],
                            str(cwd_path.parent),
                            check=True,
                        )
                        used_remote = candidate_url
                        clone_ok = True
                        break
                    except Exception as clone_exc:
                        clone_errors.append(f"{candidate_url}: {clone_exc}")
                if not clone_ok:
                    self.warn("safe network repair clone failed for all remote candidates")
                    for step_text in _safe_reset_manual_steps(
                        remote_url=remote_url,
                        cwd=cwd_path,
                        backup_dir=backup_dir,
                        branch=branch,
                    ):
                        self.warn(step_text)
                    _emit_remediation_event(
                        "safe_fix_network",
                        "failed",
                        {
                            "reason": "clone failed",
                            "remote": remote_url,
                            "attempts": " | ".join(clone_errors),
                        },
                    )
                    return StepResult.FAIL
                if branch:
                    _run(["git", "-C", str(clone_dir), "checkout", branch], str(cwd_path.parent), check=False)

                # Replace corrupted .git metadata with a fresh clone copy.
                git_dir = cwd_path / ".git"
                if git_dir.exists():
                    shutil.rmtree(git_dir)
                shutil.copytree(clone_dir / ".git", git_dir)

                # Restore backed-up working files on top of refreshed metadata.
                for item in backup_dir.iterdir():
                    if item.name == ".git":
                        continue
                    dest = cwd_path / item.name
                    if item.is_dir():
                        shutil.copytree(item, dest, dirs_exist_ok=True)
                    else:
                        shutil.copy2(item, dest)

                _run(["git", "add", "."], cwd, check=False)
                try:
                    shutil.rmtree(backup_dir, ignore_errors=False)
                except Exception as cleanup_exc:
                    logger.exception("safe network backup cleanup failed: %s", cleanup_exc)
                    self.warn(f"safe reset succeeded but backup cleanup failed: {backup_dir}")
                _emit_remediation_event(
                    "safe_fix_network",
                    "success",
                    {
                        "remote": used_remote,
                        "branch": branch or "<detached>",
                        "backup": str(backup_dir),
                    },
                )
                return StepResult.RETRY
            except Exception as e:
                logger.exception("safe network fix failed: %s", e)
                _emit_remediation_event(
                    "safe_fix_network",
                    "failed",
                    {"reason": str(e)},
                )
                self.warn("safe network repair failed")
                return StepResult.FAIL
            finally:
                if clone_dir.exists():
                    shutil.rmtree(clone_dir, ignore_errors=True)
        if opt == "4":
            allowed, reason = self._allow_remediation(
                              "skip_continue")
            if not allowed:
                self.warn(reason)
                return StepResult.FAIL
            simulated, result = self._simulate_remediation(
                action="skip_continue",
                result=StepResult.OK,
            )
            if simulated: return result
            self.prompt(f"skipping {step} and continuing")
            _emit_remediation_event("skip_continue", "success")
            return StepResult.OK

        # default: abort
        allowed, reason = self._allow_remediation("abort")
        if not allowed:
            self.warn(reason)
            return StepResult.FAIL
        self.abort("aborting as requested")
        return StepResult.FAIL

    def repo_corruption(self, cwd: str) -> StepResult:
        """
        Handle remote / non-fast-forward conflicts by making
        a safe backup, synchronizing to remote state, and
        restoring local changes on top
        """
        cwd_path = Path(cwd)
        # Determine current branch
        try:
            cp = _run(["git", "branch", "--show-current"],
                 cwd=str(cwd_path))
            branch = (cp.stdout or "").strip()
        except Exception:
            self.warn("could not determine current branch")
            return StepResult.FAIL
        if not branch:
            self.warn("no branch detected")
            return StepResult.FAIL

        backup_dir = _timestamped_backup_name(cwd_path)

        # Step 1: backup local (exclude .git)
        try:
            self.success("backing up current project to "
                        f"{backup_dir}")
            ignore = shutil.ignore_patterns(".git",
                     ".github", "__pycache__")
            _safe_copytree(cwd_path, backup_dir, ignore=ignore)
        except Exception:
            self.warn("backup failed")
            return StepResult.FAIL

        # Step 2: fetch + reset to remote
        try:
            self.warn("fetching remote and resetting local "
                      "branch to origin/" + branch)
            _run(["git", "fetch", "origin"], str(cwd_path),
                 check=True)
            _run(["git", "reset", "--hard",
                "origin/" + branch], str(cwd_path), check=True)
        except Exception:
            self.prompt("could not sync with remote. "
                      + "Attempting to restore backup...")
            # attempt restore from backup
            try:
                # restore files (non-destructive) by
                # copying back
                for item in backup_dir.iterdir():
                    if item.name.startswith("."): continue
                    dest = cwd_path / item.name
                    if item.is_dir():
                        shutil.copytree(item, dest,
                            dirs_exist_ok=True)
                    else: shutil.copy2(item, dest)
                self.success("restored files from backup")
            except Exception:
                self.warn("restore failed. Manual "
                          "intervention required")
            return StepResult.FAIL

        # Step 3: restore backed-up non-hidden files into
        #         cwd
        try:
            self.prompt("restoring local (uncommitted) "
                        "changes from backup...")
            for item in backup_dir.iterdir():
                if item.name.startswith("."): continue
                dest = cwd_path / item.name
                if item.is_dir():
                    shutil.copytree(item, dest,
                        dirs_exist_ok=True)
                else: shutil.copy2(item, dest)
        except Exception:
            self.warn("failed to copy back local files")
            return StepResult.FAIL

        # Step 4: stage restored changes
        try:
            _run(["git", "add", "."], cwd=str(cwd_path),
                check=True)
        except Exception:
            self.warn("failed to stage restored files")
            return StepResult.FAIL

        # Step 5: prompt commit message
        default = "restored local changes after remote " \
                + "conflict"
        if const.CI_MODE: commit_msg = default
        else:
            self.prompt("remote contains work you "
                        "don't have locally. Provide a "
                        "commit message for restoring your "
                        "changes (or press enter to use "
                        "default)")
            commit_msg = input(CURSOR).strip() or default

        try:
            _run(["git", "commit", "-m", commit_msg],
                cwd=str(cwd_path), check=True)
            self.success("restored local changes "
                         "committed on top of remote "
                         "state")
            return StepResult.RETRY
        except Exception as e:
            exc = "commit of restored changes failed: %s"
            logger.exception(exc, e)
            self.warn("committing restored changes failed. "
                      "Manual fix required")
            return StepResult.FAIL

    def lock_contention(self, stderr: str, cwd: str) -> StepResult:
        """Handle stale git lock-file contention when safe to clean."""
        self.warn("git lock contention detected")
        allowed, reason = self._allow_remediation(
                          "stale_lock_cleanup")
        if not allowed:
            self.warn(reason)
            return StepResult.FAIL
        repo = Path(cwd)
        lock_candidates: list[Path] = []
        for match in re.findall(r"([./A-Za-z0-9_-]+\.lock)", stderr):
            token = match.strip().strip("'\"")
            if token.startswith(".git/"):
                lock_candidates.append(repo / token)
            elif token.startswith("/"):
                lock_candidates.append(Path(token))
        lock_candidates.extend(
            [
                repo / ".git" / "index.lock",
                repo / ".git" / "shallow.lock",
                repo / ".git" / "packed-refs.lock",
                repo / ".git" / "HEAD.lock",
                repo / ".git" / "config.lock",
            ]
        )
        seen: set[str] = set()
        unique_candidates: list[Path] = []
        for candidate in lock_candidates:
            key = str(candidate.resolve()) \
               if candidate.exists() else str(candidate)
            if key in seen: continue
            seen.add(key)
            unique_candidates.append(candidate)
        lock: Path | None = None
        for candidate in unique_candidates:
            if candidate.exists() and candidate.suffix == ".lock":
                lock = candidate
                break
        if lock is None:
            self.warn("no known stale lock file found to clean")
            _emit_remediation_event(
                "stale_lock_cleanup",
                "failed",
                {"reason": "no lock file detected"},
            )
            return StepResult.FAIL
        git_dir = (repo / ".git").resolve()
        try: lock_resolved = lock.resolve()
        except Exception: lock_resolved = lock
        if git_dir not in lock_resolved.parents:
            self.warn("refusing lock cleanup outside repository .git directory")
            _emit_remediation_event(
                "stale_lock_cleanup",
                "failed",
                {"path": str(lock), "reason": "outside .git"},
            )
            return StepResult.FAIL
        simulated, result = self._simulate_remediation(
            action="stale_lock_cleanup",
            result=StepResult.RETRY,
            note=f"would remove {lock}",
        )
        if simulated: return result
        try:
            if lock.exists():
                lock.unlink()
                _emit_remediation_event(
                    "stale_lock_cleanup",
                    "success",
                    {"path": str(lock)},
                )
                return StepResult.RETRY
            _emit_remediation_event(
                "stale_lock_cleanup",
                "failed",
                {"path": str(lock), "reason": "lock file not found"},
            )
            self.warn("lock file not found for cleanup")
            return StepResult.FAIL
        except Exception as e:
            _emit_remediation_event(
                "stale_lock_cleanup",
                "failed",
                {"path": str(lock), "reason": str(e)},
            )
            self.warn("failed to clean stale lock")
            return StepResult.FAIL

    def upstream_missing(self, stderr: str, cwd: str) -> StepResult:
        """Handle missing upstream branch by setting tracking branch."""
        self.warn("branch has no upstream tracking configuration")
        allowed, reason = self._allow_remediation(
                          "set_upstream_tracking")
        if not allowed:
            self.warn(reason)
            return StepResult.FAIL
        simulated, result = self._simulate_remediation(
            action="set_upstream_tracking",
            result=StepResult.RETRY,
            note="would run git push --set-upstream <remote> <branch>",
        )
        if simulated: return result
        try:
            cp_branch = _run(
                ["git", "branch", "--show-current"],
                cwd,
            )
            branch = (cp_branch.stdout or "").strip()
            if not branch:
                self.warn("could not determine current branch for upstream setup")
                _emit_remediation_event(
                    "set_upstream_tracking",
                    "failed",
                    {"reason": "empty current branch"},
                )
                return StepResult.FAIL
            cp_remote = _run(["git", "remote"], cwd)
            remotes   = [r.strip() for r in 
                        (cp_remote.stdout or ""
                        ).splitlines() if r.strip()]
            remote = remotes[0] if remotes else "origin"
            cp     = _run(["git", "push", "--set-upstream",
                     remote, branch], cwd)
            if cp.returncode == 0:
                _emit_remediation_event(
                    "set_upstream_tracking",
                    "success",
                    {"remote": remote, "branch": branch},
                )
                return StepResult.RETRY
            _emit_remediation_event(
                "set_upstream_tracking",
                "failed",
                {"remote": remote, "branch": branch},
            )
            self.warn("failed to set upstream tracking branch")
            return StepResult.FAIL
        except Exception as e:
            _emit_remediation_event(
                "set_upstream_tracking",
                "failed",
                {"reason": str(e)},
            )
            self.warn("upstream setup failed")
            return StepResult.FAIL

    def auth_failure(self, stderr: str, cwd: str) -> StepResult:
        """Handle remote authentication failures with guided options."""
        self.warn("remote authentication failed")
        if const.CI_MODE and not const.AUTOFIX:
            self.warn("CI mode: interactive auth remediation unavailable")
            return StepResult.FAIL
        if not const.AUTOFIX:
            self.info("Choose an action:")
            options = {
                "1": "Open GitHub token page",
                "2": "Open shell to fix auth manually",
                "3": "Abort",
            }
            for key, desc in options.items():
                print(wrap_text(f"{key}. {desc}", I + 3, I))

            choice = input(CURSOR).strip() or "3"; print()
        else: choice = "1"
        if choice == "1":
            allowed, reason = self._allow_remediation(
                              "open_token_page")
            if not allowed:
                self.warn(reason)
                return StepResult.FAIL
            self.prompt("visit https://github.com/settings/tokens to refresh credentials")
            return StepResult.FAIL
        if choice == "2":
            allowed, reason = self._allow_remediation(
                              "open_shell_manual")
            if not allowed:
                self.warn(reason)
                return StepResult.FAIL
            shell = get_shell()
            if not shell:
                self.warn("no shell available")
                return StepResult.FAIL
            _run([shell], cwd, check=False, capture=False, text=True)
            _emit_remediation_event("open_shell_manual", "success")
            return StepResult.RETRY
        allowed, reason = self._allow_remediation("abort")
        if not allowed:
            self.warn(reason)
            return StepResult.FAIL
        self.abort("aborting due to authentication failure")
        return StepResult.FAIL

    def ref_conflict(self, stderr: str, cwd: str) -> StepResult:
        """Handle ref/tag conflicts with safe skip or manual intervention."""
        self.warn("git ref/tag conflict detected")
        if const.CI_MODE and not const.AUTOFIX:
            self.warn("CI mode: cannot resolve ref conflict interactively")
            return StepResult.FAIL
        if not const.AUTOFIX:
            self.info("Choose an action:")
            options = {
                "1": "Open shell to fix refs manually",
                "2": "Skip and continue",
                "3": "Abort",
            }
            for key, desc in options.items():
                print(wrap_text(f"{key}. {desc}", I + 3, I))

            choice = input(CURSOR).strip() or "3"; print()
        else: choice = "2"
        if choice == "1":
            allowed, reason = self._allow_remediation(
                              "open_shell_manual")
            if not allowed:
                self.warn(reason)
                return StepResult.FAIL
            shell = get_shell()
            if not shell:
                self.warn("no shell available")
                return StepResult.FAIL
            _run([shell], cwd, check=False, capture=False, text=True)
            _emit_remediation_event("open_shell_manual", "success")
            return StepResult.RETRY
        if choice == "2":
            allowed, reason = self._allow_remediation("skip_continue")
            if not allowed:
                self.warn(reason)
                return StepResult.FAIL
            _emit_remediation_event("skip_continue", "success")
            return StepResult.OK
        allowed, reason = self._allow_remediation("abort")
        if not allowed:
            self.warn(reason)
            return StepResult.FAIL
        self.abort("aborting due to ref conflict")
        return StepResult.FAIL

    def missing_remote(self, stderr: str, cwd: str
                      ) -> StepResult:
        """Handle 'remote not valid' errors during push."""
        # try to parse remote name
        remote = None
        try:
            low = stderr
            if "'" in low: remote = low.split("'", 2)[1]
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
            return StepResult.FAIL

        self.warn(f"Git push failed: remote {remote!r} is "
                  "not configured or invalid")

        if const.CI_MODE and not const.AUTOFIX:
            self.warn("CI mode: cannot perform interactive repair")
            return StepResult.FAIL

        if not const.AUTOFIX:
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
                raw    = input(CURSOR).strip(); print()
                choice = raw or "7"
                if choice not in options:
                    transmit("invalid choice", fg=BAD)
                    return StepResult.FAIL
            except (KeyboardInterrupt, EOFError) as e:
                if isinstance(e, EOFError): print()
                self.abort()
        else:
            can_ssh, _ = self._allow_remediation(
                         "add_origin_ssh")
            if can_ssh:
                msg = auto("attempting to add origin via SSH")
                self.prompt(msg)
                choice = "2"
            else: choice = "6"

        def get_repo_info() -> tuple[str, str]:
            repo_arg = const.GH_REPO
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
                raise RuntimeError("unreachable")

        # handle choices
        gh   = "github.com"
        prvt = None
        if choice == "1":
            allowed, reason = self._allow_remediation(
                              "add_origin_https")
            if not allowed:
                self.warn(reason)
                return StepResult.FAIL
            info = get_repo_info()
            if not info: return StepResult.FAIL
            user, repo = info
            url = f"https://{gh}/{user}/{repo}.git"
        elif choice == "2":
            allowed, reason = self._allow_remediation(
                              "add_origin_ssh")
            if not allowed:
                self.warn(reason)
                return StepResult.FAIL
            info = get_repo_info()
            if not info: return StepResult.FAIL
            user, repo = info
            url = f"git@{gh}:{user}/{repo}.git"
        elif choice == "3":
            allowed, reason = self._allow_remediation(
                              "add_origin_token")
            if not allowed:
                self.warn(reason)
                return StepResult.FAIL
            try:
                msg = "paste GitHub token (input hidden)"
                self.prompt(msg)
                token = getpass.getpass(CURSOR).strip()
                print()
            except Exception:
                self.warn("could not read token")
                return StepResult.FAIL
            if not token:
                self.warn("empty token provided")
                return StepResult.FAIL
            info = get_repo_info()
            if not info: return StepResult.FAIL
            user, repo = info
            url  = f"https://{token}@{gh}/{user}/{repo}.git"
            prvt = f"https://***@{gh}/{user}/{repo}.git"
        elif choice == "4":
            allowed, reason = self._allow_remediation(
                             "open_token_page")
            if not allowed:
                self.warn(reason)
                return StepResult.FAIL
            self.prompt(f"visit https://{gh}/settings/"
                "tokens to create a token")
            return StepResult.FAIL
        elif choice == "5":
            allowed, reason = self._allow_remediation(
                              "open_shell_manual")
            if not allowed:
                self.warn(reason)
                return StepResult.FAIL
            self.prompt("opening subshell. Fix remotes "
                        "manually. Exit to continue")
            shell = get_shell()
            if not shell:
                self.warn("no shell available")
                return StepResult.FAIL
            _run([shell], cwd, check=False,
                capture=False, text=True)
            return StepResult.RETRY
        elif choice == "6":
            allowed, reason = self._allow_remediation(
                              "skip_continue")
            if not allowed:
                self.warn(reason)
                return StepResult.FAIL
            simulated, result = self._simulate_remediation(
                action="skip_continue",
                result=StepResult.OK,
            )
            if simulated: return result
            self.prompt("skipping fix and continuing")
            _emit_remediation_event("skip_continue", "success")
            return StepResult.OK
        else:
            allowed, reason = self._allow_remediation("abort")
            if not allowed:
                self.warn(reason)
                return StepResult.FAIL
            self.abort("aborting as requested")
            return StepResult.FAIL

        prvt       = prvt if prvt else url
        action_map = {
            "1": "add_origin_https",
            "2": "add_origin_ssh",
            "3": "add_origin_token",
        }
        action = action_map.get(choice, "add_origin_unknown")
        simulated, result = self._simulate_remediation(
            action=action,
            result=StepResult.RETRY,
        )
        if simulated: return result
        try:
            self.prompt(f"adding remote {remote!r}↴\n{prvt}")
            cp = _run(["git", "remote", "add", remote,
                 url], cwd, check=True)
            if cp.returncode != 0:
                _emit_remediation_event(action, "failed")
                self.warn("failed to add remote")
                logger.debug("git remote add stderr: %s",
                    cp.stderr)
                return StepResult.FAIL
        except Exception as e:
            logger.exception("Failed to add remote: %s", e)
            _emit_remediation_event(action, "failed")
            exc = normalize_stderr(e)
            self.warn(f"failed to add remote: {exc}")
            return StepResult.FAIL

        # show remotes for confirmation
        try:
            cp2 = _run(["git", "remote", "-v"], cwd)
            self.prompt("updated remotes↴")
            r1, r2 = cp2.stdout.strip().splitlines()
            r1, r2 = r1.split(), r2.split()
            r1[1]  = r2[1] = prvt
            r1, r2 = " ".join(r1), " ".join(r2)
            self.info(f"{r1}\n{r2}", prefix=False)
        except Exception as e:
            logger.exception("Failed to list remotes: %s", e)

        # success — suggest retry original operation
        _emit_remediation_event(action, "success")
        return StepResult.RETRY

    def internet_con_err(self, stderr: str, _type: int = 1
                        ) -> None:
        """Handle network or remote URL issues."""
        if "'" in stderr: host = stderr.split("'")[1]
        else: host = ""
        host = f": {host!r}." if host else "."

        suggestion = "Check network"
        if _type == 2:
            reason = "invalid or non-existent Git remote"
            cmd_text = "git remote set-url origin <correct-url>"
            cmd = cmd_text if const.CI_MODE else color(cmd_text, INFO)
            suggestion = f"Run {cmd}"
        else: reason = "network/connectivity problem"

        self.abort(f"git failed due to {reason}{host} "
                   f"{suggestion} and retry")
        raise RuntimeError("unreachable")


def normalize_stderr(stderr: Exception | str,
                     prefix: str | None = None,
                     max_len: int = 400) -> str:
    """
    Turn stderr (or an Exception) into a readable, wrapped
    paragraph

    Returns a string suitable for display
    """
    if isinstance(stderr, Exception): stderr = str(stderr)

    # Collapse repeated whitespace and trim
    text = " ".join(stderr.strip().split())
    if prefix: text = f"{prefix} {text}"
    # Shorten very long outputs for display
    # full output should be logged
    if len(text) > max_len:
        logger.debug("Truncating stderr for display. Full "
                     "content logged")
        logger.debug("Full stderr:\n%s", text)
        text = text[:max_len].rstrip() + " ...(truncated)"
    return wrap(text)


def classify_stderr(stderr: str) -> dict[str, str]:
    """Return stable machine-readable classification metadata."""
    return classifier_classify_stderr(stderr)


def resolver_telemetry() -> dict[str, int]:
    """Return classifier telemetry counters for diagnostics/tests."""
    return {
        "unknown_classifications": classifier_unknown_count(),
        "rule_conflicts": classifier_rule_conflict_count(),
    }


def reset_resolver_telemetry() -> None:
    """Reset classifier telemetry counters."""
    reset_classifier_telemetry()


# module-level reusable instance for importers
resolve = Handlers()
