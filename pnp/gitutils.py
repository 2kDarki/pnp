"""
Small helpers for interacting with git. All operations use
the git CLI via subprocess.

These helpers raise RuntimeError on fatal failures; callers
should handle prompts and dry-run.
"""
# ======================= STANDARDS =======================
import subprocess
import random
import time

# ======================== LOCALS =========================
from .utils import Output, StepResult, transmit
from .error_model import canonical_error_code
from ._constants import DRYRUN, APP, BAD
from . import _constants as const
from . import telemetry
from . import resolver


RETRYABLE_CODE_ALLOWLIST: set[str] = {
    "PNP_NET_CONNECTIVITY",
    "PNP_NET_REMOTE_UNREADABLE",
    "PNP_NET_TIMEOUT",
    "PNP_NET_PUSH_FAIL",
    "PNP_GIT_DUBIOUS_OWNERSHIP",
    "PNP_GIT_LOCK_CONTENTION",
    "PNP_GIT_UPSTREAM_MISSING",
    "PNP_GIT_NON_FAST_FORWARD",
    "PNP_GIT_LINE_ENDING_NORMALIZATION",
    "PNP_GIT_INDEX_WORKTREE_MISMATCH",
}

NON_RETRYABLE_CODE_DENYLIST: set[str] = {
    "PNP_GIT_INVALID_OBJECT",
    "PNP_GIT_EMPTY_STDERR",
    "PNP_GIT_UNCLASSIFIED",
    "PNP_INT_WORKFLOW_EXIT_NONZERO",
    "PNP_INT_UNHANDLED_EXCEPTION",
}

RETRY_POLICY_BY_CODE: dict[str, dict[str, float | int | bool]] = {
    "PNP_NET_CONNECTIVITY": {
        "retryable": True,
        "max_retries": 3,
        "base_delay_s": 0.25,
        "max_delay_s": 2.0,
        "jitter_s": 0.10,
    },
    "PNP_NET_REMOTE_UNREADABLE": {
        "retryable": True,
        "max_retries": 1,
        "base_delay_s": 0.10,
        "max_delay_s": 0.50,
        "jitter_s": 0.05,
    },
    "PNP_NET_TIMEOUT": {
        "retryable": True,
        "max_retries": 2,
        "base_delay_s": 0.25,
        "max_delay_s": 1.0,
        "jitter_s": 0.10,
    },
    "PNP_NET_PUSH_FAIL": {
        "retryable": True,
        "max_retries": 2,
        "base_delay_s": 0.20,
        "max_delay_s": 1.0,
        "jitter_s": 0.08,
    },
    "PNP_GIT_DUBIOUS_OWNERSHIP": {
        "retryable": True,
        "max_retries": 1,
        "base_delay_s": 0.05,
        "max_delay_s": 0.20,
        "jitter_s": 0.02,
    },
    "PNP_GIT_LOCK_CONTENTION": {
        "retryable": True,
        "max_retries": 1,
        "base_delay_s": 0.05,
        "max_delay_s": 0.20,
        "jitter_s": 0.02,
    },
    "PNP_GIT_UPSTREAM_MISSING": {
        "retryable": True,
        "max_retries": 1,
        "base_delay_s": 0.05,
        "max_delay_s": 0.20,
        "jitter_s": 0.02,
    },
    "PNP_GIT_NON_FAST_FORWARD": {
        "retryable": True,
        "max_retries": 1,
        "base_delay_s": 0.10,
        "max_delay_s": 0.30,
        "jitter_s": 0.04,
    },
    "PNP_GIT_LINE_ENDING_NORMALIZATION": {
        "retryable": True,
        "max_retries": 3,
        "base_delay_s": 0.05,
        "max_delay_s": 0.20,
        "jitter_s": 0.02,
    },
    "PNP_GIT_INDEX_WORKTREE_MISMATCH": {
        "retryable": True,
        "max_retries": 3,
        "base_delay_s": 0.05,
        "max_delay_s": 0.20,
        "jitter_s": 0.02,
    },
}

DEFAULT_STEP_TIMEOUT_BUDGET_S = 45.0

TIMEOUT_BUDGET_BY_CODE_S: dict[str, float] = {
    "PNP_NET_CONNECTIVITY": 30.0,
    "PNP_NET_REMOTE_UNREADABLE": 15.0,
    "PNP_NET_TIMEOUT": 20.0,
    "PNP_NET_PUSH_FAIL": 20.0,
    "PNP_GIT_DUBIOUS_OWNERSHIP": 12.0,
    "PNP_GIT_LOCK_CONTENTION": 12.0,
    "PNP_GIT_UPSTREAM_MISSING": 12.0,
    "PNP_GIT_NON_FAST_FORWARD": 20.0,
    "PNP_GIT_LINE_ENDING_NORMALIZATION": 20.0,
    "PNP_GIT_INDEX_WORKTREE_MISMATCH": 20.0,
}

REPEATABLE_FAILURE_CODES: set[str] = {
    "PNP_NET_CONNECTIVITY",
    "PNP_NET_TIMEOUT",
    "PNP_GIT_LINE_ENDING_NORMALIZATION",
    "PNP_GIT_INDEX_WORKTREE_MISMATCH",
}

CIRCUIT_BREAKER_MAX_PER_CODE = 3


def _resolver_error_code(decision: object) -> str:
    """Extract canonical resolver code from decision metadata."""
    code = ""
    classification = getattr(decision, "classification", None)
    if classification is not None:
        code = str(getattr(classification, "code", "")).strip()
    if not code:
        last = getattr(resolver.resolve, "last_error", None)
        if isinstance(last, dict):
            code = str(last.get("code", "")).strip()
    return canonical_error_code(code)


def _retry_policy_for(code: str) -> dict[str, float | int | bool]:
    """Return retry policy for a stable error code."""
    token = canonical_error_code(code)
    if token in NON_RETRYABLE_CODE_DENYLIST:
        return {"retryable": False, "max_retries": 0}
    if token in RETRYABLE_CODE_ALLOWLIST:
        return RETRY_POLICY_BY_CODE.get(token, {
            "retryable": True,
            "max_retries": 1,
            "base_delay_s": 0.1,
            "max_delay_s": 0.5,
            "jitter_s": 0.05,
        })
    return {"retryable": False, "max_retries": 0}


def _retry_delay_seconds(tries: int, policy: dict[str, float | int | bool]) -> float:
    """Compute exponential backoff delay with jitter."""
    base = float(policy.get("base_delay_s", 0.0))
    cap = float(policy.get("max_delay_s", base))
    jitter = float(policy.get("jitter_s", 0.0))
    delay = min(base * (2 ** max(tries, 0)), cap)
    if jitter > 0:
        delay += random.uniform(0.0, jitter)
    return max(delay, 0.0)


def _timeout_budget_for(code: str) -> float:
    """Return hard timeout budget for a code-specific step."""
    token = canonical_error_code(code)
    return TIMEOUT_BUDGET_BY_CODE_S.get(token, DEFAULT_STEP_TIMEOUT_BUDGET_S)


def run_git(args: list[str], cwd: str, capture: bool = True,
            tries: int = 0, started_at: float | None = None,
            timeout_budget_s: float | None = None,
            failure_counts: dict[str, int] | None = None,
            signature_counts: dict[str, int] | None = None) -> tuple[int, str]:
    """
    Run a git command and route stderr through resolver
    handlers when needed

    Behavior:
    - If git writes to stderr and a handler recognizes the
      error, the handler is invoked with (stderr, cwd)
    - If handler returns StepResult.RETRY -> retry per
      code policy (allowlist/denylist + max attempts)
    - If the handler returns StepResult.OK -> assume handler
      handled issue so continue workflow
    - If the handler returns StepResult.FAIL -> return
      original proc code/output
    - `tries` tracks retry attempt count
    """
    if const.DRY_RUN: return 1, DRYRUN + "skips process"
    now = time.monotonic()
    if started_at is None: started_at = now
    if timeout_budget_s is None:
        timeout_budget_s = DEFAULT_STEP_TIMEOUT_BUDGET_S
    if failure_counts is None: failure_counts = {}
    if signature_counts is None: signature_counts = {}
    elapsed = now - started_at
    remaining = timeout_budget_s - elapsed
    if remaining <= 0:
        return 124, "git step timeout budget exceeded"
    try:
        proc = subprocess.run(
            ["git"] + args,
            cwd=cwd,
            text=True,
            capture_output=capture,
            timeout=remaining,
        )
    except subprocess.TimeoutExpired:
        return 124, "git step timeout budget exceeded"
    except KeyboardInterrupt: return 130, "cancelled by user"
    stdout = proc.stdout or ""
    stderr = proc.stderr or ""
    out    = (stdout or stderr).strip()

    # Successful git commands often emit progress/warnings on
    # stderr. Treat non-zero return codes as failure signals.
    if proc.returncode == 0:
        try:
            resolver.resolve.maybe_pop_stash(cwd)
        except Exception:
            pass
        return 0, out

    # nothing to handle
    if not stderr: return proc.returncode, out

    try:
        decision = resolver.resolve.decide(stderr, cwd)
        policy_result = getattr(decision, "result", None)
        result: StepResult = (
            policy_result if isinstance(policy_result, StepResult)
            else StepResult.FAIL
        )
        code = _resolver_error_code(decision)
        telemetry.emit_event(
            event_type="resolver_decision",
            step_id="git",
            payload={
                "code": code,
                "result": result.value,
                "cwd": cwd,
                "args": list(args),
                "returncode": proc.returncode,
                "stderr_excerpt": stderr.strip()[:300],
            },
        )
    except Exception as e:
        exc = f"resolver handler failed: {e}"
        resolver.logger.exception(exc)
        transmit(exc, fg=BAD)
        return proc.returncode, out

    echo = Output(quiet=const.QUIET)

    signature = f"{cwd}|{' '.join(args)}|{code}|{stderr.strip()[:240]}"
    signature_counts[signature] = signature_counts.get(signature, 0) + 1
    if signature_counts[signature] > 1 and code not in REPEATABLE_FAILURE_CODES:
        return 65, "idempotency guard: repeated identical failure"

    if code:
        failure_counts[code] = failure_counts.get(code, 0) + 1
        if failure_counts[code] > CIRCUIT_BREAKER_MAX_PER_CODE:
            return 75, f"circuit breaker: repeated failures for {code}"

    if result is StepResult.RETRY:
        policy = _retry_policy_for(code)
        if code:
            timeout_budget_s = min(timeout_budget_s, _timeout_budget_for(code))
        max_retries = int(policy.get("max_retries", 0))
        retryable = bool(policy.get("retryable", False))
        # Resolver handlers return RETRY only after an explicit remediation path.
        # Allow one immediate retry even for denylisted codes so repaired state
        # can be re-evaluated in the same invocation.
        if not retryable and tries == 0:
            retryable = True
            max_retries = 1
        if retryable and tries < max_retries:
            attempt = tries + 1
            delay_s = _retry_delay_seconds(tries, policy)
            elapsed = time.monotonic() - started_at
            remaining = timeout_budget_s - elapsed
            if remaining <= 0:
                return 124, "git step timeout budget exceeded"
            if delay_s > 0:
                sleep_s = min(delay_s, max(remaining, 0.0))
                try: time.sleep(sleep_s)
                except KeyboardInterrupt:
                    return 130, "cancelled by user"
            telemetry.emit_event(
                event_type="retry",
                step_id="git",
                payload={
                    "code": code,
                    "attempt": attempt,
                    "max_retries": max_retries,
                    "delay_s": delay_s,
                    "cwd": cwd,
                    "args": list(args),
                },
            )
            echo.prompt(f"retrying step ({attempt}/{max_retries})...")
            return run_git(args, cwd=cwd, capture=capture,
                   tries=attempt,
                   started_at=started_at,
                   timeout_budget_s=timeout_budget_s,
                   failure_counts=failure_counts,
                   signature_counts=signature_counts)

    if result is StepResult.OK: return 0, out

    return proc.returncode, out


def is_git_repo(path: str) -> bool:
    rc, _ = run_git(["rev-parse", "--is-inside-work-tree"],
            cwd=path)
    return rc == 0


def git_init(path: str) -> None:
    rc, out = run_git(["init"], cwd=path)
    if rc != 0: raise RuntimeError(f"git init failed: {out}")


def current_branch(path: str) -> str | None:
    rc, out = run_git(["rev-parse", "--abbrev-ref", "HEAD"],
              cwd=path)
    return out if rc == 0 else None


def status_short(path: str) -> str | None:
    _, out = run_git(["status", "--short", "--branch"],
             cwd=path)
    return out if out.strip() else None


def has_uncommitted(path: str) -> bool:
    _, out = run_git(["status", "--porcelain"], cwd=path)
    return bool(out.strip())


def stage_all(path: str) -> None:
    rc, out = run_git(["add", "-A"], cwd=path)
    if rc != 0: raise RuntimeError("git add failed: " + out)


def commit(path: str, message: str | None,
           allow_empty: bool = False) -> None:
    args = ["commit"]
    if message is not None: args += ["-m", message]
    else: args += ["-m", f"{APP} auto commit"]
    if allow_empty: args.append("--allow-empty")
    rc, out = run_git(args, cwd=path)
    if rc != 0:
        raise RuntimeError("git commit failed: " + out)


def remotes(path: str) -> list[str] | list:
    rc, out = run_git(["remote"], cwd=path)
    if rc == 0 and out.strip(): return out.splitlines()
    return []


def fetch_all(path: str) -> None:
    rc, out = run_git(["fetch", "--all", "--tags"],
              cwd=path)
    if rc != 0:
        raise RuntimeError("git fetch failed: " + out)


def upstream_for_branch(path: str, branch: str) -> str | None:
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


def tags_sorted(path: str, pattern: str | None = None
               ) -> list[str] | list:
    args = ["tag", "--list"]
    if pattern: args += [pattern]
    args += ["--sort=-v:refname"]
    rc, out = run_git(args, cwd=path)
    if rc == 0 and out.strip(): return out.splitlines()
    return []


def create_tag(path: str, tag: str,
               message: str | None = None,
               sign: bool = False) -> None:
    args = ["tag"]
    if message: args += ["-a", tag, "-m", message]
    else: args += [tag]
    if sign: args.insert(1, "-s")
    rc, out = run_git(args, cwd=path)
    if rc != 0: raise RuntimeError("git tag failed: " + out)


def push(path: str, remote: str = "origin",
         branch: str | None = None, force: bool = False,
         push_tags: bool = True) -> None:
    should_push_branch = branch is not None or not push_tags
    if should_push_branch:
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
