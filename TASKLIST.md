# PNP Top-Tier Extension Task List

## Current State
- [x] Production baseline reached (CI + tests + typing + publish gate).
- [x] Rich TUI workflow + doctor audit + machine-readable diagnostics.
- [x] Layered config (`default < git < env < cli`) with source introspection.
- [x] `--check-only` gate with CI exit taxonomy (`0`, `10`, `20`).
- [x] Git extension shim install/uninstall and git-machete integration.
- [x] Domain regrouping completed (`cli` entrypoint, `workflow_engine`, `ops`, `audit`).

## Remaining Work To Reach Top-Tier

### 1) CI Contracts (Highest Impact)
- [x] Freeze and version JSON schema for:
  - `--doctor --doctor-json`
  - `--check-only --check-json`
- [x] Add schema docs (field definitions, nullable behavior, backward-compat policy).
- [x] Add regression tests that validate schema keys/order-insensitive structure.
- [x] Add CI job that fails on schema-breaking changes unless explicitly approved.

### 2) End-to-End Scenario Reliability
- [x] Add integration scenarios covering:
  - branch behind upstream (force/no-force outcomes)
  - publish failure rollback (tag deletion verified)
  - hook failure + resume paths (interactive and CI)
  - machete enabled/disabled paths
- [x] Add non-happy-path sequence tests (multi-step failure chains).
- [x] Add deterministic test fixture for temporary repos + remotes to reduce flakiness.

### 3) Config Completeness
- [x] Add project config file support (`[tool.pnp]` in `pyproject.toml`).
- [x] Define final precedence including project file:
  - `defaults < pyproject < git < env < cli`.
- [x] Add `--show-config` source reporting for new `pyproject` layer.
- [x] Add conflict/invalid-value diagnostics with actionable messages.

### 4) Extension UX Parity Across Platforms
- [x] Harden extension shim behavior for Windows/macOS/Linux differences.
- [x] Add docs for PATH setup + shell profile examples per platform.
- [x] Add smoke tests for shim command discovery assumptions.

### 5) Operational Governance
- [x] Add `CHANGELOG.md` policy and release note template.
- [x] Add workflow badges + support matrix section in `README.md`.
- [x] Add contributor command entrypoint (`make check` or equivalent).
- [x] Add compatibility policy (supported Python/Git versions, shell assumptions).

### 6) Resolver/Failure Taxonomy (Advanced)
- [x] Refactor resolver into explicit handler taxonomy with severity classes.
- [x] Map resolver outcomes to stable machine-readable error codes.
- [x] Add tests proving resolver classification consistency.

## Definition Of Top-Tier Done
- [x] Stable, documented JSON contracts with compatibility policy.
- [x] Full end-to-end scenario coverage for critical failure/recovery paths.
- [x] Config system complete across all planned sources with provenance.
- [x] Cross-platform extension UX documented and validated.
- [x] Governance docs present (`CHANGELOG`, release template, support policy).
