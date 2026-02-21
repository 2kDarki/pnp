# pnp Handoff (2026-02-15)

## Snapshot

Project is at a stable production baseline with CI, schema contracts, and expanded failure-path coverage passing.

Latest structural cleanup grouped code by concern:
- `pnp/cli.py`: entrypoint and dispatch only (no compatibility shim layer).
- `pnp/workflow_engine.py`: workflow orchestration and step control flow.
- `pnp/ops.py`: shared utility/process/git/editor operations.
- `pnp/audit.py`: doctor + check-only audit/preflight logic.

## Validation Baseline

Last full gate status: pass.

Run this first in any new session:

```bash
make check
```

This covers:
- `compileall` on `pnp`, `tests`, `tools`
- `mypy`
- full unittest suite
- JSON schema contract gate (`tools/schema_gate.py`)

## Compatibility Constraints

No legacy compatibility shim layer is required. Patch and extend canonical modules directly:
- workflow: `pnp.workflow_engine`
- operations: `pnp.ops`
- preflight/audit: `pnp.audit`

## Current Top Priorities

Use `ERROR_HANDLING_TASKLIST.md` as source of truth for next major upgrade track.

Recommended execution order:
1. Phase 1: define and lock a canonical error envelope contract.
2. Phase 2: split resolver into classifier/policy/remediation boundaries.
3. Phase 2.1: build golden stderr corpus and deterministic snapshot tests.
4. Phase 3: add retry/remediation policies with explicit safety gates.
5. Phase 4: structured logs and debug bundle.

## Practical Next Session Plan

1. Add `docs/ERROR_ENVELOPE.md` and a versioned schema (v1).
2. Emit envelope in machine-readable outputs (`--check-json`, `--doctor-json`).
3. Add schema lock + gate extension (similar to existing JSON contract gate).
4. Add tests asserting every fail/abort path maps to stable codes/envelope fields.

## Release Hygiene Checklist

Before release/tag:
1. `make check`
2. verify docs drift:
   - `README.md`
   - `docs/JSON_CONTRACTS.md`
   - `docs/ERROR_CODES.md`
   - `ERROR_HANDLING_TASKLIST.md`
3. run a smoke command set:
   - `python -m pnp --help`
   - `python -m pnp . --doctor`
   - `python -m pnp . --check-only --check-json`
