"""Policy engine for resolver classifications."""
from typing import Callable, Protocol
from dataclasses import dataclass

from .resolver_classifier import ErrorClassification
from .utils import StepResult


@dataclass(frozen=True)
class PolicyDecision:
    """Typed resolver decision for git stderr handling."""
    classification: ErrorClassification
    result: StepResult
    handled: bool = True

    def as_dict(self) -> dict[str, str]:
        payload = self.classification.as_dict()
        payload["result"] = str(self.result.value)
        payload["handled"] = "1" if self.handled else "0"
        return payload


class RemediationHandlers(Protocol):
    """Remediation callbacks used by policy dispatch."""
    def internet_con_err(self, stderr: str, _type: int = 1) -> None: ...
    def dubious_ownership(self, stderr: str, cwd: str) -> StepResult: ...
    def invalid_object(self, stderr: str, cwd: str) -> StepResult: ...
    def missing_remote(self, stderr: str, cwd: str) -> StepResult: ...
    def lock_contention(self, stderr: str, cwd: str) -> StepResult: ...
    def upstream_missing(self, stderr: str, cwd: str) -> StepResult: ...
    def repo_corruption(self, cwd: str) -> StepResult: ...
    def diverged_branch(self, stderr: str, cwd: str) -> StepResult: ...
    def auth_failure(self, stderr: str, cwd: str) -> StepResult: ...
    def large_file_rejection(self, stderr: str, cwd: str) -> StepResult: ...
    def hook_declined(self, stderr: str, cwd: str) -> StepResult: ...
    def submodule_inconsistent(self, stderr: str, cwd: str) -> StepResult: ...
    def ref_conflict(self, stderr: str, cwd: str) -> StepResult: ...
    def protected_branch(self, stderr: str, cwd: str) -> StepResult: ...
    def dirty_worktree(self, stderr: str, cwd: str) -> StepResult: ...
    def line_endings(self, stderr: str, cwd: str) -> StepResult: ...
    def index_worktree_mismatch(self, stderr: str, cwd: str) -> StepResult: ...
    def detached_head(self, stderr: str, cwd: str) -> StepResult: ...


def decide(
    classification: ErrorClassification,
    stderr: str,
    cwd: str,
    remediation: RemediationHandlers,
    on_unhandled: Callable[[], None] | None = None,
    on_decision: Callable[[PolicyDecision], None] | None = None,
) -> PolicyDecision:
    """Apply policy engine dispatch for a classification."""
    lowered = stderr.lower()

    def done(result: StepResult, handled: bool = True) -> PolicyDecision:
        decision = PolicyDecision(
            classification=classification,
            result=result,
            handled=handled,
        )
        if on_decision is not None:
            on_decision(decision)
        return decision

    def _dispatch_internet_con_err() -> StepResult:
        error_type = 1
        if classification.code == "PNP_NET_REMOTE_URL_INVALID":
            error_type = 2
        elif classification.code == "PNP_NET_TLS_FAIL":
            error_type = 3
        done(StepResult.FAIL)
        remediation.internet_con_err(stderr, error_type)
        return StepResult.FAIL

    dispatch_map: dict[str, Callable[[], StepResult]] = {
        "internet_con_err": _dispatch_internet_con_err,
        "dubious_ownership": lambda: remediation.dubious_ownership(stderr, cwd),
        "invalid_object": lambda: remediation.invalid_object(lowered, cwd),
        "missing_remote": lambda: remediation.missing_remote(lowered, cwd),
        "lock_contention": lambda: remediation.lock_contention(lowered, cwd),
        "upstream_missing": lambda: remediation.upstream_missing(lowered, cwd),
        "repo_corruption": lambda: remediation.repo_corruption(cwd),
        "diverged_branch": lambda: remediation.diverged_branch(lowered, cwd),
        "auth_failure": lambda: remediation.auth_failure(lowered, cwd),
        "large_file_rejection": lambda: remediation.large_file_rejection(lowered, cwd),
        "hook_declined": lambda: remediation.hook_declined(lowered, cwd),
        "submodule_inconsistent": lambda: remediation.submodule_inconsistent(lowered, cwd),
        "ref_conflict": lambda: remediation.ref_conflict(lowered, cwd),
        "protected_branch": lambda: remediation.protected_branch(lowered, cwd),
        "dirty_worktree": lambda: remediation.dirty_worktree(lowered, cwd),
        "line_endings": lambda: remediation.line_endings(lowered, cwd),
        "index_worktree_mismatch": lambda: remediation.index_worktree_mismatch(lowered, cwd),
        "detached_head": lambda: remediation.detached_head(lowered, cwd),
    }
    dispatch = dispatch_map.get(classification.handler)
    if dispatch is not None: return done(dispatch())

    if classification.code == "PNP_GIT_EMPTY_STDERR":
        return done(StepResult.FAIL, handled=False)

    if on_unhandled is not None: on_unhandled()
    return done(StepResult.FAIL, handled=False)
