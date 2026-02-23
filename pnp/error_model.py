"""
Shared typed error envelope model for machine-readable
failures.
"""
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Any


WORKFLOW_STEP_CODES: dict[str, str] = {
    "repository": "PNP_GIT_REPOSITORY_FAIL",
    "hooks": "PNP_REL_HOOKS_FAIL",
    "machete": "PNP_GIT_MACHETE_FAIL",
    "commit": "PNP_GIT_COMMIT_FAIL",
    "push": "PNP_NET_PUSH_FAIL",
    "publish": "PNP_REL_PUBLISH_FAIL",
    "release": "PNP_REL_RELEASE_FAIL",
}

DEPRECATED_ERROR_CODE_ALIASES: dict[str, str] = {
    "PNP_WORKFLOW_EXIT_NONZERO": "PNP_INT_WORKFLOW_EXIT_NONZERO",
    "PNP_WORKFLOW_REPOSITORY_FAIL": "PNP_GIT_REPOSITORY_FAIL",
    "PNP_WORKFLOW_HOOKS_FAIL": "PNP_REL_HOOKS_FAIL",
    "PNP_WORKFLOW_MACHETE_FAIL": "PNP_GIT_MACHETE_FAIL",
    "PNP_WORKFLOW_COMMIT_FAIL": "PNP_GIT_COMMIT_FAIL",
    "PNP_WORKFLOW_PUSH_FAIL": "PNP_NET_PUSH_FAIL",
    "PNP_WORKFLOW_PUBLISH_FAIL": "PNP_REL_PUBLISH_FAIL",
    "PNP_WORKFLOW_RELEASE_FAIL": "PNP_REL_RELEASE_FAIL",
    "PNP_RES_NETWORK_CONNECTIVITY": "PNP_NET_CONNECTIVITY",
    "PNP_RES_DUBIOUS_OWNERSHIP": "PNP_GIT_DUBIOUS_OWNERSHIP",
    "PNP_RES_INVALID_OBJECT": "PNP_GIT_INVALID_OBJECT",
    "PNP_RES_REMOTE_URL_INVALID": "PNP_NET_REMOTE_URL_INVALID",
    "PNP_RES_REMOTE_UNREADABLE": "PNP_NET_REMOTE_UNREADABLE",
    "PNP_RES_UNCLASSIFIED": "PNP_GIT_UNCLASSIFIED",
    "PNP_RES_EMPTY_STDERR": "PNP_GIT_EMPTY_STDERR",
    "PNP_RES_AUTH_FAIL": "PNP_NET_AUTH_FAIL",
    "PNP_RES_LARGE_FILE_REJECTED": "PNP_NET_LARGE_FILE_REJECTED",
    "PNP_RES_HOOK_DECLINED": "PNP_GIT_HOOK_DECLINED",
    "PNP_RES_SUBMODULE_INCONSISTENT": "PNP_GIT_SUBMODULE_INCONSISTENT",
    "PNP_RES_NON_FAST_FORWARD": "PNP_GIT_NON_FAST_FORWARD",
    "PNP_RES_PROTECTED_BRANCH": "PNP_GIT_PROTECTED_BRANCH",
    "PNP_RES_DIRTY_WORKTREE": "PNP_GIT_DIRTY_WORKTREE",
    "PNP_RES_LINE_ENDING_NORMALIZATION": "PNP_GIT_LINE_ENDING_NORMALIZATION",
    "PNP_RES_DETACHED_HEAD": "PNP_GIT_DETACHED_HEAD",
    "PNP_RES_REF_CONFLICT": "PNP_GIT_REF_CONFLICT",
    "PNP_RES_LOCK_CONTENTION": "PNP_GIT_LOCK_CONTENTION",
    "PNP_RES_UPSTREAM_MISSING": "PNP_GIT_UPSTREAM_MISSING",
    "PNP_RES_TLS_FAIL": "PNP_NET_TLS_FAIL",
    "PNP_RES_TIMEOUT": "PNP_NET_TIMEOUT",
    "PNP_RES_INDEX_WORKTREE_MISMATCH": "PNP_GIT_INDEX_WORKTREE_MISMATCH",
}

ERROR_CODE_POLICY: dict[str, dict[str, Any]] = {
    "PNP_INT_UNHANDLED_EXCEPTION": {
        "severity": "error",
        "category": "internal",
    },
    "PNP_INT_KEYBOARD_INTERRUPT": {
        "severity": "warn",
        "category": "workflow",
    },
    "PNP_INT_EOF_INTERRUPT": {
        "severity": "warn",
        "category": "workflow",
    },
    "PNP_INT_WORKFLOW_EXIT_NONZERO": {
        "severity": "error",
        "category": "workflow",
    },
    "PNP_GIT_REPOSITORY_FAIL": {
        "severity": "error",
        "category": "git",
    },
    "PNP_REL_HOOKS_FAIL": {
        "severity": "error",
        "category": "release",
    },
    "PNP_GIT_MACHETE_FAIL": {
        "severity": "error",
        "category": "git",
    },
    "PNP_GIT_COMMIT_FAIL": {
        "severity": "error",
        "category": "git",
    },
    "PNP_NET_PUSH_FAIL": {
        "severity": "error",
        "category": "network",
    },
    "PNP_REL_PUBLISH_FAIL": {
        "severity": "error",
        "category": "release",
    },
    "PNP_REL_RELEASE_FAIL": {
        "severity": "error",
        "category": "release",
    },
    "PNP_NET_CONNECTIVITY": {
        "severity": "error",
        "category": "network",
    },
    "PNP_GIT_DUBIOUS_OWNERSHIP": {
        "severity": "warn",
        "category": "git",
    },
    "PNP_GIT_INVALID_OBJECT": {
        "severity": "error",
        "category": "git",
    },
    "PNP_NET_REMOTE_URL_INVALID": {
        "severity": "error",
        "category": "network",
    },
    "PNP_NET_REMOTE_UNREADABLE": {
        "severity": "error",
        "category": "network",
    },
    "PNP_NET_AUTH_FAIL": {
        "severity": "error",
        "category": "network",
    },
    "PNP_NET_LARGE_FILE_REJECTED": {
        "severity": "error",
        "category": "network",
    },
    "PNP_GIT_HOOK_DECLINED": {
        "severity": "error",
        "category": "git",
    },
    "PNP_GIT_SUBMODULE_INCONSISTENT": {
        "severity": "error",
        "category": "git",
    },
    "PNP_NET_TLS_FAIL": {
        "severity": "error",
        "category": "network",
    },
    "PNP_NET_TIMEOUT": {
        "severity": "error",
        "category": "network",
    },
    "PNP_GIT_NON_FAST_FORWARD": {
        "severity": "error",
        "category": "git",
    },
    "PNP_GIT_PROTECTED_BRANCH": {
        "severity": "error",
        "category": "git",
    },
    "PNP_GIT_DIRTY_WORKTREE": {
        "severity": "error",
        "category": "git",
    },
    "PNP_GIT_LINE_ENDING_NORMALIZATION": {
        "severity": "warn",
        "category": "git",
    },
    "PNP_GIT_INDEX_WORKTREE_MISMATCH": {
        "severity": "error",
        "category": "git",
    },
    "PNP_GIT_DETACHED_HEAD": {
        "severity": "error",
        "category": "git",
    },
    "PNP_GIT_REF_CONFLICT": {
        "severity": "error",
        "category": "git",
    },
    "PNP_GIT_LOCK_CONTENTION": {
        "severity": "error",
        "category": "git",
    },
    "PNP_GIT_UPSTREAM_MISSING": {
        "severity": "error",
        "category": "git",
    },
    "PNP_GIT_UNCLASSIFIED": {
        "severity": "warn",
        "category": "git",
    },
    "PNP_GIT_EMPTY_STDERR": {
        "severity": "warn",
        "category": "git",
    },
}


def canonical_error_code(code: str) -> str:
    """Resolve deprecated codes to the current stable code namespace."""
    token = code.strip()
    return DEPRECATED_ERROR_CODE_ALIASES.get(token, token)


def resolve_failure_code(
    step: str = "",
    preferred_code: str = "",
    fallback_code: str = "PNP_INT_WORKFLOW_EXIT_NONZERO",
) -> str:
    """Resolve a stable code for a runtime failure."""
    code = canonical_error_code(preferred_code)
    if code: return code
    resolved = WORKFLOW_STEP_CODES.get(step.strip(),
               fallback_code)
    return canonical_error_code(resolved)


def error_policy_for(
    code: str,
    fallback_severity: str = "error",
    fallback_category: str = "workflow",
) -> dict[str, str]:
    """Resolve canonical severity/category for a stable code."""
    code = canonical_error_code(code)
    policy = ERROR_CODE_POLICY.get(code, {})
    severity = str(policy.get("severity", fallback_severity)).strip()
    category = str(policy.get("category", fallback_category)).strip()
    return {
        "severity": severity or fallback_severity,
        "category": category or fallback_category,
    }


@dataclass(frozen=True)
class FailureEvent:
    """Typed runtime workflow failure signal propagated to CLI."""
    step: str
    label: str
    result: str
    message: str
    code: str = ""
    severity: str = ""
    category: str = ""


@dataclass(frozen=True)
class ErrorEnvelope:
    code: str
    severity: str
    category: str
    actionable: bool
    message: str
    operation: str
    step: str
    stderr_excerpt: str
    raw_ref: str
    retryable: bool
    user_action_required: bool
    suggested_fix: str
    context: dict[str, object]

    def as_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "severity": self.severity,
            "category": self.category,
            "actionable": self.actionable,
            "message": self.message,
            "operation": self.operation,
            "step": self.step,
            "stderr_excerpt": self.stderr_excerpt,
            "raw_ref": self.raw_ref,
            "retryable": self.retryable,
            "user_action_required": self.user_action_required,
            "suggested_fix": self.suggested_fix,
            "context": self.context,
        }

    def with_runtime_schema(self) -> dict[str, object]:
        payload = self.as_dict()
        payload["schema"] = "pnp.error_envelope.v1"
        payload["schema_version"] = 1
        payload["generated_at"] = datetime.now(timezone.utc).isoformat(
            timespec="seconds"
        ).replace("+00:00", "Z")
        return payload


def build_error_envelope(
    code: str,
    severity: str,
    category: str,
    message: str,
    operation: str,
    step: str,
    context: dict[str, object],
    actionable: bool = True,
    retryable: bool = False,
    user_action_required: bool = True,
    suggested_fix: str = "",
    stderr_excerpt: str = "",
    raw_ref: str = "",
) -> ErrorEnvelope:
    """Construct a typed error envelope."""
    return ErrorEnvelope(
        code=code,
        severity=severity,
        category=category,
        actionable=actionable,
        message=message,
        operation=operation,
        step=step,
        stderr_excerpt=stderr_excerpt,
        raw_ref=raw_ref,
        retryable=retryable,
        user_action_required=user_action_required,
        suggested_fix=suggested_fix,
        context=context,
    )
