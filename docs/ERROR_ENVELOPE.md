# Error Envelope Contract (v1)

This document defines the canonical structured failure envelope
for `pnp`.

## Purpose

The envelope provides a stable machine-readable error shape across:

- `--doctor --doctor-json`
- `--check-json`
- normal workflow runtime failures (persisted to `pnplog/last_error_envelope.json`)

## Schema (v1)

```json
{
  "code": "string",
  "severity": "info|warn|error|critical",
  "category": "string",
  "actionable": true,
  "message": "string",
  "operation": "string",
  "step": "string",
  "stderr_excerpt": "string",
  "raw_ref": "string",
  "retryable": false,
  "user_action_required": true,
  "suggested_fix": "string",
  "context": {
    "path": "string",
    "repo": "string",
    "branch": "string",
    "remote": "string",
    "ci_mode": true,
    "dry_run": false
  }
}
```

## Field Notes

- `code`: stable machine code for automation/policy.
- `severity`: normalized impact level.
- `category`: broad family (`preflight`, `workflow`, `internal`, etc.).
- `actionable`: indicates whether the user/system can act now.
- `operation`: high-level operation (`doctor`, `check_only`, `workflow`).
- `step`: closest logical step where failure surfaced.
- `stderr_excerpt`: normalized short error excerpt (or equivalent detail).
- `raw_ref`: optional pointer to fuller diagnostics/log artifact.
- `retryable`: whether automatic retry is generally safe.
- `user_action_required`: whether manual action is needed.
- `suggested_fix`: concise remediation hint.
- `context`: run context values relevant for triage.

## Stability Policy

- Envelope key names are contract-stable in v1.
- Backward-compatible key additions are allowed.
- Breaking removals/renames require versioned contract evolution.
