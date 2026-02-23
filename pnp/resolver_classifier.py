"""Pure stderr classification for resolver error taxonomy."""
from dataclasses import asdict, dataclass
from typing import Callable
import re

from .error_model import error_policy_for


@dataclass(frozen=True)
class ErrorClassification:
    """Stable classification for resolver stderr matching."""
    code: str
    severity: str
    handler: str

    def as_dict(self) -> dict[str, str]: return asdict(self)


@dataclass(frozen=True)
class ClassificationRule:
    """Declarative stderr classification rule."""
    code: str
    handler: str
    matcher: Callable[[str], bool]


def _match_any(needles: tuple[str, ...]) -> Callable[[str], bool]:
    """Return predicate that matches if any needle exists in stderr."""
    def _matcher(stderr: str) -> bool:
        return any(needle in stderr for needle in needles)
    return _matcher


def _match_substring(needle: str) -> Callable[[str], bool]:
    """Return predicate that matches a single substring."""
    def _matcher(stderr: str) -> bool:
        return needle in stderr
    return _matcher


NETWORK_ERROR_NEEDLES: tuple[str, ...] = (
    "no address associated with hostname",
    "could not resolve host",
    "software caused connection abort",
    "failed to connect",
    "connect to",
)

NETWORK_TIMEOUT_NEEDLES: tuple[str, ...] = (
    "operation timed out",
    "connection timed out",
    "timed out",
)

NETWORK_TLS_NEEDLES: tuple[str, ...] = (
    "ssl certificate problem",
    "server certificate verification failed",
    "tls handshake timeout",
    "gnutls_handshake()",
    "ssl connect error",
)

AUTH_ERROR_NEEDLES: tuple[str, ...] = (
    "authentication failed",
    "permission denied (publickey)",
    "could not read username",
    "repository not found",
)

LARGE_FILE_NEEDLES: tuple[str, ...] = (
    "exceeds github's file size limit",
    "exceeds gitlab's file size limit",
    "file size limit of 100.00 mb",
    "file size limit of",
)

HOOK_DECLINED_NEEDLES: tuple[str, ...] = (
    "pre-push hook declined",
    "pre-commit hook declined",
    "hook declined",
)

SUBMODULE_INCONSISTENT_NEEDLES: tuple[str, ...] = (
    "upload-pack: not our ref",
    "not our ref",
    "in a submodule path",
    "no submodule mapping found in .gitmodules",
)

PROTECTED_BRANCH_NEEDLES: tuple[str, ...] = (
    "protected branch update failed",
    "gh006",
    "required status check",
    "approving review is required",
)

NON_FAST_FORWARD_NEEDLES: tuple[str, ...] = (
    "non-fast-forward",
    "fetch first",
    "failed to push some refs",
    "tip of your current branch is behind",
)

DIRTY_WORKTREE_NEEDLES: tuple[str, ...] = (
    "would be overwritten by merge",
    "please commit your changes or stash them before you merge",
    "please commit your changes or stash them before you rebase",
    "your local changes to the following files would be overwritten",
)

LINE_ENDING_NEEDLES: tuple[str, ...] = (
    "lf will be replaced by crlf",
    "crlf will be replaced by lf",
)

LOCK_CONTENTION_NEEDLES: tuple[str, ...] = (
    "another git process seems to be running",
    "unable to create '.git/index.lock'",
    "unable to create '.git/shallow.lock'",
    "index.lock",
)

DETACHED_HEAD_NEEDLES: tuple[str, ...] = (
    "you are not currently on a branch",
    "you are in 'detached head' state",
    "detached head",
)

REF_CONFLICT_NEEDLES: tuple[str, ...] = (
    "cannot lock ref",
    "tag already exists",
    "would clobber existing tag",
    "failed to update ref",
)

UPSTREAM_MISSING_NEEDLES: tuple[str, ...] = (
    "has no upstream branch",
    "no upstream configured",
    "set-upstream",
)

INVALID_OBJECT_NEEDLES: tuple[str, ...] = (
    "invalid object",
    "broken pipe",
    "has null sha1",
    "object corrupt",
    "unexpected diff status a",
    "is empty fatal:",
)

CLASSIFICATION_RULES: tuple[ClassificationRule, ...] = (
    ClassificationRule(
        code="PNP_GIT_UPSTREAM_MISSING",
        handler="upstream_missing",
        matcher=_match_any(UPSTREAM_MISSING_NEEDLES),
    ),
    ClassificationRule(
        code="PNP_NET_AUTH_FAIL",
        handler="auth_failure",
        matcher=_match_any(AUTH_ERROR_NEEDLES),
    ),
    ClassificationRule(
        code="PNP_NET_LARGE_FILE_REJECTED",
        handler="large_file_rejection",
        matcher=_match_any(LARGE_FILE_NEEDLES),
    ),
    ClassificationRule(
        code="PNP_GIT_HOOK_DECLINED",
        handler="hook_declined",
        matcher=_match_any(HOOK_DECLINED_NEEDLES),
    ),
    ClassificationRule(
        code="PNP_GIT_SUBMODULE_INCONSISTENT",
        handler="submodule_inconsistent",
        matcher=_match_any(SUBMODULE_INCONSISTENT_NEEDLES),
    ),
    ClassificationRule(
        code="PNP_GIT_PROTECTED_BRANCH",
        handler="protected_branch",
        matcher=_match_any(PROTECTED_BRANCH_NEEDLES),
    ),
    ClassificationRule(
        code="PNP_GIT_NON_FAST_FORWARD",
        handler="diverged_branch",
        matcher=_match_any(NON_FAST_FORWARD_NEEDLES),
    ),
    ClassificationRule(
        code="PNP_GIT_DIRTY_WORKTREE",
        handler="dirty_worktree",
        matcher=_match_any(DIRTY_WORKTREE_NEEDLES),
    ),
    ClassificationRule(
        code="PNP_GIT_LINE_ENDING_NORMALIZATION",
        handler="line_endings",
        matcher=_match_any(LINE_ENDING_NEEDLES),
    ),
    ClassificationRule(
        code="PNP_GIT_DETACHED_HEAD",
        handler="detached_head",
        matcher=_match_any(DETACHED_HEAD_NEEDLES),
    ),
    ClassificationRule(
        code="PNP_GIT_REF_CONFLICT",
        handler="ref_conflict",
        matcher=_match_any(REF_CONFLICT_NEEDLES),
    ),
    ClassificationRule(
        code="PNP_GIT_LOCK_CONTENTION",
        handler="lock_contention",
        matcher=_match_any(LOCK_CONTENTION_NEEDLES),
    ),
    ClassificationRule(
        code="PNP_NET_TLS_FAIL",
        handler="internet_con_err",
        matcher=_match_any(NETWORK_TLS_NEEDLES),
    ),
    ClassificationRule(
        code="PNP_NET_TIMEOUT",
        handler="internet_con_err",
        matcher=_match_any(NETWORK_TIMEOUT_NEEDLES),
    ),
    ClassificationRule(
        code="PNP_NET_CONNECTIVITY",
        handler="internet_con_err",
        matcher=_match_any(NETWORK_ERROR_NEEDLES),
    ),
    ClassificationRule(
        code="PNP_GIT_DUBIOUS_OWNERSHIP",
        handler="dubious_ownership",
        matcher=_match_substring("dubious ownership"),
    ),
    ClassificationRule(
        code="PNP_GIT_INVALID_OBJECT",
        handler="invalid_object",
        matcher=_match_any(INVALID_OBJECT_NEEDLES),
    ),
    ClassificationRule(
        code="INTERNAL_REMOTE_ROUTE",
        handler="missing_remote",
        matcher=_match_substring("could not read from remote"),
    ),
)

_UNKNOWN_CLASSIFICATION_COUNT = 0
_RULE_CONFLICT_COUNT          = 0
_URL_PATTERN                  = re.compile(
                                r"https?://[^\s'\"`]+")
_HTTPS_TOKEN_PATTERN          = re.compile(
                                r"(https://)[^/\s@]+(@)")


def normalize_stderr(stderr: str) -> str:
    """Normalize stderr for resilient, deterministic classification."""
    text = stderr.strip().lower()
    if not text: return ""
    text = text\
           .replace("`", "'")\
           .replace("’", "'")\
           .replace('"', "'")
    text = _HTTPS_TOKEN_PATTERN.sub(r"\1<token>\2", text)
    text = _URL_PATTERN.sub("<url>", text)
    text = re.sub(r"\s+", " ", text)
    return text


def unknown_classification_count() -> int:
    """Return number of fallback/unknown classifications."""
    return _UNKNOWN_CLASSIFICATION_COUNT


def rule_conflict_count() -> int:
    """Return number of multi-match rule conflicts observed."""
    return _RULE_CONFLICT_COUNT


def reset_telemetry() -> None:
    """Reset classifier counters for test isolation."""
    global _UNKNOWN_CLASSIFICATION_COUNT
    global _RULE_CONFLICT_COUNT
    _UNKNOWN_CLASSIFICATION_COUNT = 0
    _RULE_CONFLICT_COUNT          = 0


def _classify_code(code: str, handler: str) -> ErrorClassification:
    policy = error_policy_for(code, fallback_category="git")
    return ErrorClassification(
        code=code,
        severity=policy["severity"],
        handler=handler,
    )


def _classify_remote_issue(stderr_lower: str) -> int:
    """Return error type for remote/internet issues."""
    if "could not read from remote" in stderr_lower:
        if "<url>" in stderr_lower: return 2
    return 0


def classify(stderr: str) -> ErrorClassification:
    """Classify git stderr into stable code/severity/handler."""
    global _UNKNOWN_CLASSIFICATION_COUNT
    global _RULE_CONFLICT_COUNT
    if not stderr:
        return _classify_code("PNP_GIT_EMPTY_STDERR", "fallback")
    lowered = normalize_stderr(stderr)
    matched = [rule for rule in CLASSIFICATION_RULES if rule.matcher(lowered)]
    if not matched:
        _UNKNOWN_CLASSIFICATION_COUNT += 1
        return _classify_code("PNP_GIT_UNCLASSIFIED", "fallback")
    if len(matched) > 1:
        # Conflict is expected to be rare and actionable for rule tuning.
        non_route = [r for r in matched if r.code
                 != "INTERNAL_REMOTE_ROUTE"]
        resolved  = {r.code for r in non_route}
        if len(resolved) > 1: _RULE_CONFLICT_COUNT += 1
    for rule in matched:
        if rule.code != "INTERNAL_REMOTE_ROUTE":
            return _classify_code(rule.code, rule.handler)
        issue = _classify_remote_issue(lowered)
        if issue == 2:
            return _classify_code("PNP_NET_REMOTE_URL_INVALID", "internet_con_err")
        return _classify_code("PNP_NET_REMOTE_UNREADABLE", "missing_remote")
    _UNKNOWN_CLASSIFICATION_COUNT += 1
    return _classify_code("PNP_GIT_UNCLASSIFIED", "fallback")


def classify_stderr(stderr: str) -> dict[str, str]:
    """Return stable machine-readable classification metadata."""
    return classify(stderr).as_dict()
