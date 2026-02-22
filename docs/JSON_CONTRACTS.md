# JSON Contracts

This file defines the machine-readable contracts for:
- `pnp --doctor --doctor-json`
- `pnp --check-json` (or `pnp --check-only --check-json`)

## Compatibility Policy
- Schema identity is carried by `schema` and `schema_version`.
- Backward-compatible additions are allowed in the same major schema (`v1`).
- Breaking changes require a new schema identifier/version.
- CI enforces compatibility via `tools/schema_gate.py`.
- CI also enforces error-code contract compatibility via `tools/error_code_gate.py`.
- To explicitly override a breaking change check:
  - set env var `PNP_ALLOW_SCHEMA_BREAK=1`, or
  - add repository file `.schema_breaking_change_approved`.
  - for error-code breaking changes: set `PNP_ALLOW_ERROR_CODE_BREAK=1`
    or add `.error_code_breaking_change_approved`.

## Doctor Contract (`pnp.doctor.v1`)

Required top-level keys:
- `schema` (string) = `pnp.doctor.v1`
- `schema_version` (int) = `1`
- `generated_at` (string, UTC ISO-8601)
- `path` (string)
- `summary` (object)
- `checks` (array)
- `error_envelope` (object)

`summary` keys:
- `critical` (int)
- `warnings` (int)
- `healthy` (bool)

`checks` item keys:
- `name` (string)
- `status` (string: `ok` | `warn` | `fail`)
- `details` (string)

`error_envelope` keys:
- `code` (string)
- `severity` (string)
- `category` (string)
- `actionable` (bool)
- `message` (string)
- `operation` (string)
- `step` (string)
- `stderr_excerpt` (string)
- `raw_ref` (string)
- `retryable` (bool)
- `user_action_required` (bool)
- `suggested_fix` (string)
- `context` (object)

## Check Contract (`pnp.check.v1`)

Required top-level keys:
- `schema` (string) = `pnp.check.v1`
- `schema_version` (int) = `1`
- `generated_at` (string, UTC ISO-8601)
- `path` (string)
- `strict` (bool)
- `summary` (object)
- `findings` (array)
- `error_envelope` (object)

`summary` keys:
- `exit_code` (int: `0`, `10`, or `20`)
- `blockers` (int)
- `warnings` (int)

`findings` item keys:
- `level` (string: `ok` | `warn` | `blocker`)
- `check` (string)
- `message` (string)

`error_envelope` keys:
- `code` (string)
- `severity` (string)
- `category` (string)
- `actionable` (bool)
- `message` (string)
- `operation` (string)
- `step` (string)
- `stderr_excerpt` (string)
- `raw_ref` (string)
- `retryable` (bool)
- `user_action_required` (bool)
- `suggested_fix` (string)
- `context` (object)
