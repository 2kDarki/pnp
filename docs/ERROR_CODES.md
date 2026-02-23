# Error Codes

Stable machine-readable failure codes emitted by `pnp`.

## Namespace (v1)

- `PNP_GIT_*`: Git/process failures.
- `PNP_CFG_*`: Configuration/validation failures.
- `PNP_NET_*`: Network/remote/auth failures.
- `PNP_REL_*`: Publish/release workflow failures.
- `PNP_INT_*`: Internal/system/runtime failures.

## Resolver Classification Schema

```json
{
  "code": "PNP_GIT_*|PNP_NET_*",
  "severity": "warn|error",
  "handler": "<resolver handler name>"
}
```

## Current Codes

- `PNP_GIT_EMPTY_STDERR`
- `PNP_GIT_DUBIOUS_OWNERSHIP`
- `PNP_GIT_INVALID_OBJECT`
- `PNP_GIT_NON_FAST_FORWARD`
- `PNP_GIT_PROTECTED_BRANCH`
- `PNP_GIT_DIRTY_WORKTREE`
- `PNP_GIT_LINE_ENDING_NORMALIZATION`
- `PNP_GIT_HOOK_DECLINED`
- `PNP_GIT_SUBMODULE_INCONSISTENT`
- `PNP_GIT_DETACHED_HEAD`
- `PNP_GIT_REF_CONFLICT`
- `PNP_GIT_LOCK_CONTENTION`
- `PNP_GIT_UPSTREAM_MISSING`
- `PNP_GIT_UNCLASSIFIED`
- `PNP_GIT_REPOSITORY_FAIL`
- `PNP_GIT_MACHETE_FAIL`
- `PNP_GIT_COMMIT_FAIL`

- `PNP_NET_CONNECTIVITY`
- `PNP_NET_REMOTE_URL_INVALID`
- `PNP_NET_REMOTE_UNREADABLE`
- `PNP_NET_AUTH_FAIL`
- `PNP_NET_LARGE_FILE_REJECTED`
- `PNP_NET_TLS_FAIL`
- `PNP_NET_TIMEOUT`
- `PNP_NET_PUSH_FAIL`

- `PNP_REL_HOOKS_FAIL`
- `PNP_REL_PUBLISH_FAIL`
- `PNP_REL_RELEASE_FAIL`

- `PNP_INT_UNHANDLED_EXCEPTION`
- `PNP_INT_KEYBOARD_INTERRUPT`
- `PNP_INT_EOF_INTERRUPT`
- `PNP_INT_WORKFLOW_EXIT_NONZERO`

## Deprecation and Replacement Policy

- Error codes are treated as contract IDs and cannot be silently repurposed.
- If a code is renamed, keep an alias map for at least one minor release.
- Emit only canonical codes in new payloads.
- Accept deprecated codes as input and canonicalize them internally.
- Record deprecations and replacements in this file and `CHANGELOG.md`.
- Breaking changes require migration notes using:
  - `docs/ERROR_CODE_MIGRATION_TEMPLATE.md`

## CI Contract Gate

- CI validates error-code contract compatibility via:
  - `tools/error_code_gate.py`
  - lock file: `docs/error_code_lock.json`
- Breaking changes are blocked unless explicitly approved:
  - set env var `PNP_ALLOW_ERROR_CODE_BREAK=1`, or
  - add repository file `.error_code_breaking_change_approved`

## Compatibility: Deprecated -> Canonical

- `PNP_WORKFLOW_EXIT_NONZERO` -> `PNP_INT_WORKFLOW_EXIT_NONZERO`
- `PNP_WORKFLOW_REPOSITORY_FAIL` -> `PNP_GIT_REPOSITORY_FAIL`
- `PNP_WORKFLOW_HOOKS_FAIL` -> `PNP_REL_HOOKS_FAIL`
- `PNP_WORKFLOW_MACHETE_FAIL` -> `PNP_GIT_MACHETE_FAIL`
- `PNP_WORKFLOW_COMMIT_FAIL` -> `PNP_GIT_COMMIT_FAIL`
- `PNP_WORKFLOW_PUSH_FAIL` -> `PNP_NET_PUSH_FAIL`
- `PNP_WORKFLOW_PUBLISH_FAIL` -> `PNP_REL_PUBLISH_FAIL`
- `PNP_WORKFLOW_RELEASE_FAIL` -> `PNP_REL_RELEASE_FAIL`
- `PNP_RES_NETWORK_CONNECTIVITY` -> `PNP_NET_CONNECTIVITY`
- `PNP_RES_DUBIOUS_OWNERSHIP` -> `PNP_GIT_DUBIOUS_OWNERSHIP`
- `PNP_RES_INVALID_OBJECT` -> `PNP_GIT_INVALID_OBJECT`
- `PNP_RES_REMOTE_URL_INVALID` -> `PNP_NET_REMOTE_URL_INVALID`
- `PNP_RES_REMOTE_UNREADABLE` -> `PNP_NET_REMOTE_UNREADABLE`
- `PNP_RES_UNCLASSIFIED` -> `PNP_GIT_UNCLASSIFIED`
- `PNP_RES_EMPTY_STDERR` -> `PNP_GIT_EMPTY_STDERR`
- `PNP_RES_AUTH_FAIL` -> `PNP_NET_AUTH_FAIL`
- `PNP_RES_LARGE_FILE_REJECTED` -> `PNP_NET_LARGE_FILE_REJECTED`
- `PNP_RES_NON_FAST_FORWARD` -> `PNP_GIT_NON_FAST_FORWARD`
- `PNP_RES_PROTECTED_BRANCH` -> `PNP_GIT_PROTECTED_BRANCH`
- `PNP_RES_DIRTY_WORKTREE` -> `PNP_GIT_DIRTY_WORKTREE`
- `PNP_RES_LINE_ENDING_NORMALIZATION` -> `PNP_GIT_LINE_ENDING_NORMALIZATION`
- `PNP_RES_HOOK_DECLINED` -> `PNP_GIT_HOOK_DECLINED`
- `PNP_RES_SUBMODULE_INCONSISTENT` -> `PNP_GIT_SUBMODULE_INCONSISTENT`
- `PNP_RES_DETACHED_HEAD` -> `PNP_GIT_DETACHED_HEAD`
- `PNP_RES_REF_CONFLICT` -> `PNP_GIT_REF_CONFLICT`
- `PNP_RES_LOCK_CONTENTION` -> `PNP_GIT_LOCK_CONTENTION`
- `PNP_RES_UPSTREAM_MISSING` -> `PNP_GIT_UPSTREAM_MISSING`
- `PNP_RES_TLS_FAIL` -> `PNP_NET_TLS_FAIL`
- `PNP_RES_TIMEOUT` -> `PNP_NET_TIMEOUT`
