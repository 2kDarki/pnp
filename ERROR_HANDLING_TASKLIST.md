# pnp State-of-the-Art Error Handling Tasklist

## Goal

Upgrade `pnp` error handling from robust pattern-based handling to a
state-of-the-art system with stable contracts, deterministic recovery
policies, and production-grade observability.

---

## Current Baseline

- [x] Resolver taxonomy exists with stable codes and severities.
- [x] Core rollback paths exist for critical workflow steps.
- [x] Regression and integration tests cover major known failure paths.
- [x] Human-readable diagnostics are strong in CLI/TUI mode.
- [x] Module boundaries are grouped by concern (`ops`, `audit`, `workflow_engine`, `cli`).

---

## Phase 1: Error Contract Foundation

### 1.1 Unified Failure Envelope
- [x] Define a canonical failure envelope schema used everywhere:
  - `code`, `severity`, `category`, `actionable`, `message`
  - `operation`, `step`, `stderr_excerpt`, `raw_ref`
  - `retryable`, `user_action_required`, `suggested_fix`
  - `context` (repo, branch, remote, ci_mode, dry_run)
- [x] Add schema doc in `docs/ERROR_ENVELOPE.md`.
- [x] Add schema lock file + CI gate similar to existing JSON contracts.

### 1.2 Stable Code System v1
- [x] Introduce versioned error code namespace:
  - `PNP_GIT_*` (git/process errors)
  - `PNP_CFG_*` (config/validation errors)
  - `PNP_NET_*` (network/auth/remote errors)
  - `PNP_REL_*` (publish/release errors)
  - `PNP_INT_*` (internal/system errors)
- [x] Add strict policy for deprecation and replacement of codes.
- [x] Add compatibility section in `docs/ERROR_CODES.md`.

### 1.3 End-to-End Surface
- [x] Emit failure envelope in machine-readable paths:
  - `--check-json`
  - `--doctor --doctor-json`
  - runtime failures persisted to `pnplog/last_error_envelope.json`
- [x] Ensure every abort/fail path maps to at least one stable code.

---

## Phase 2: Resolver Architecture Refactor

### 2.1 Classifier/Handler Separation
- [x] Split resolver into:
  - classifier (pure, deterministic)
  - policy engine (retry/fail/abort decision)
  - remediation handlers (side-effectful actions)
- [x] Ensure classifiers are pure functions with no I/O.
- [x] Add typed data models for classifications and outcomes.

### 2.2 Rule Engine
- [x] Replace ad-hoc string checks with explicit rules table:
  - regex/predicate
  - precedence
  - code/severity
  - handler binding
- [x] Add conflict detection (two rules matching same stderr with different codes).
- [x] Add unknown/fallback telemetry counter.

### 2.3 Localization/Variance Resilience
- [x] Normalize stderr before classification:
  - whitespace, quoting, URL/token redaction
  - locale-sensitive substrings where possible
- [x] Add fixtures across git versions and platform variants.

---

## Phase 3: Recovery Intelligence

### 3.1 Retry Policy
- [x] Add per-code retry strategy:
  - max attempts
  - exponential backoff + jitter
  - non-retryable code allowlist/denylist
- [x] Add hard timeout budget per step.
- [x] Add cancellation support for interactive mode.

### 3.2 Safe Auto-Remediation
- [x] Add remediation policy matrix:
  - allowed in CI vs interactive
  - destructive vs non-destructive actions
  - required confirmation thresholds
- [x] Add dry-run simulation for every remediation path.
- [x] Record remediation attempts in structured logs.

### 3.3 Guardrails
- [x] Add idempotency checks for repeated failures.
- [x] Add circuit breaker for repeated same-code failures in one run.
- [x] Add rollback verification checks (not just rollback attempt).

---

## Phase 4: Observability & Debuggability

### 4.1 Structured Logs
- [x] Add JSONL error event stream in `pnplog/`.
- [x] Include correlation/run ID and step ID in all events.
- [x] Add redaction for tokens/secrets/remote credentials.

### 4.2 Debug Bundle
- [x] Implement `--debug-report` to generate sanitized support bundle:
  - environment snapshot
  - git state snapshot (safe subset)
  - failure envelopes
  - resolver decisions and retries
- [x] Add `--debug-report-file` path override.

### 4.3 UX Layer
- [x] Show concise “human summary + one-liner fix” for common failures.
- [x] Add “advanced details” block in verbose/debug mode.
- [x] Keep TUI clean: no spinner/live conflicts with external tools.

---

## Phase 5: Testing to SOTA Bar

### 5.1 Classification Test Matrix
- [x] Build golden test corpus:
  - representative stderr samples per code
  - ambiguous/multi-match samples
  - malformed/empty inputs
- [x] Enforce deterministic classifier output snapshots.

### 5.2 Fault Injection Harness
- [x] Build test harness that injects failures at each workflow step:
  - git process failures
  - network timeouts/auth failures
  - filesystem permission and lock errors
  - tag/release conflicts
- [x] Verify policy outcome and emitted code for each injected fault.

### 5.3 Non-Determinism/Flake Controls
- [x] Add randomized stress runs in CI nightly:
  - repeated runs with seeded faults
  - retry timing variance checks
- [x] Track flake rate and enforce threshold budget.

### 5.4 Cross-Platform Validation
- [x] Validate full error path behavior on Linux/macOS/Windows.
- [x] Validate shell/editor combinations for interactive remediation.

---

## Phase 6: Governance & Release Discipline

### 6.1 Error Contract Versioning
- [x] Add explicit error contract version in emitted payloads.
- [x] Add migration notes template for any breaking error code change.
- [x] Add CI rule: block breaking changes without approval flag.

### 6.2 Documentation
- [x] Add operator runbook:
  - common failures
  - remediation playbooks
  - escalation guidance
- [x] Add contributor guide for adding new resolver rules/codes safely.

### 6.3 SLOs
- [x] Define and track:
  - unknown/unclassified error rate
  - mean time to actionable diagnosis
  - successful auto-remediation rate
  - rollback success verification rate

---

## Definition of Done (State-of-the-Art)

- [x] 100% fail/abort paths emit stable, versioned error envelopes.
- [x] Classifier is deterministic, side-effect free, and fully snapshot-tested.
- [x] Retry/remediation policy is explicit, test-covered, and safety-gated.
- [x] Unknown/unclassified error rate stays below agreed threshold in real usage.
- [x] Structured logs + debug bundle make support triage reproducible.
- [x] Contract changes are governed and backward compatibility is enforced.

---

## Suggested Execution Order

1. Phase 1 (contracts)  
2. Phase 2 (architecture split)  
3. Phase 5.1 (classifier test corpus)  
4. Phase 3 (retry/remediation policy)  
5. Phase 4 (observability/debug bundle)  
6. Phase 5.2-5.4 (fault injection + platform hardening)  
7. Phase 6 (governance + SLO operations)
