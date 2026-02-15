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
- [ ] Define a canonical failure envelope schema used everywhere:
  - `code`, `severity`, `category`, `actionable`, `message`
  - `operation`, `step`, `stderr_excerpt`, `raw_ref`
  - `retryable`, `user_action_required`, `suggested_fix`
  - `context` (repo, branch, remote, ci_mode, dry_run)
- [ ] Add schema doc in `docs/ERROR_ENVELOPE.md`.
- [ ] Add schema lock file + CI gate similar to existing JSON contracts.

### 1.2 Stable Code System v1
- [ ] Introduce versioned error code namespace:
  - `PNP_GIT_*` (git/process errors)
  - `PNP_CFG_*` (config/validation errors)
  - `PNP_NET_*` (network/auth/remote errors)
  - `PNP_REL_*` (publish/release errors)
  - `PNP_INT_*` (internal/system errors)
- [ ] Add strict policy for deprecation and replacement of codes.
- [ ] Add compatibility section in `docs/ERROR_CODES.md`.

### 1.3 End-to-End Surface
- [ ] Emit failure envelope in machine-readable paths:
  - `--check-json`
  - `--doctor --doctor-json`
  - future `--error-json` for normal workflow failures
- [ ] Ensure every abort/fail path maps to at least one stable code.

---

## Phase 2: Resolver Architecture Refactor

### 2.1 Classifier/Handler Separation
- [ ] Split resolver into:
  - classifier (pure, deterministic)
  - policy engine (retry/fail/abort decision)
  - remediation handlers (side-effectful actions)
- [ ] Ensure classifiers are pure functions with no I/O.
- [ ] Add typed data models for classifications and outcomes.

### 2.2 Rule Engine
- [ ] Replace ad-hoc string checks with explicit rules table:
  - regex/predicate
  - precedence
  - code/severity
  - handler binding
- [ ] Add conflict detection (two rules matching same stderr with different codes).
- [ ] Add unknown/fallback telemetry counter.

### 2.3 Localization/Variance Resilience
- [ ] Normalize stderr before classification:
  - whitespace, quoting, URL/token redaction
  - locale-sensitive substrings where possible
- [ ] Add fixtures across git versions and platform variants.

---

## Phase 3: Recovery Intelligence

### 3.1 Retry Policy
- [ ] Add per-code retry strategy:
  - max attempts
  - exponential backoff + jitter
  - non-retryable code allowlist/denylist
- [ ] Add hard timeout budget per step.
- [ ] Add cancellation support for interactive mode.

### 3.2 Safe Auto-Remediation
- [ ] Add remediation policy matrix:
  - allowed in CI vs interactive
  - destructive vs non-destructive actions
  - required confirmation thresholds
- [ ] Add dry-run simulation for every remediation path.
- [ ] Record remediation attempts in structured logs.

### 3.3 Guardrails
- [ ] Add idempotency checks for repeated failures.
- [ ] Add circuit breaker for repeated same-code failures in one run.
- [ ] Add rollback verification checks (not just rollback attempt).

---

## Phase 4: Observability & Debuggability

### 4.1 Structured Logs
- [ ] Add JSONL error event stream in `pnplog/`.
- [ ] Include correlation/run ID and step ID in all events.
- [ ] Add redaction for tokens/secrets/remote credentials.

### 4.2 Debug Bundle
- [ ] Implement `--debug-report` to generate sanitized support bundle:
  - environment snapshot
  - git state snapshot (safe subset)
  - failure envelopes
  - resolver decisions and retries
- [ ] Add `--debug-report-file` path override.

### 4.3 UX Layer
- [ ] Show concise “human summary + one-liner fix” for common failures.
- [ ] Add “advanced details” block in verbose/debug mode.
- [ ] Keep TUI clean: no spinner/live conflicts with external tools.

---

## Phase 5: Testing to SOTA Bar

### 5.1 Classification Test Matrix
- [ ] Build golden test corpus:
  - representative stderr samples per code
  - ambiguous/multi-match samples
  - malformed/empty inputs
- [ ] Enforce deterministic classifier output snapshots.

### 5.2 Fault Injection Harness
- [ ] Build test harness that injects failures at each workflow step:
  - git process failures
  - network timeouts/auth failures
  - filesystem permission and lock errors
  - tag/release conflicts
- [ ] Verify policy outcome and emitted code for each injected fault.

### 5.3 Non-Determinism/Flake Controls
- [ ] Add randomized stress runs in CI nightly:
  - repeated runs with seeded faults
  - retry timing variance checks
- [ ] Track flake rate and enforce threshold budget.

### 5.4 Cross-Platform Validation
- [ ] Validate full error path behavior on Linux/macOS/Windows.
- [ ] Validate shell/editor combinations for interactive remediation.

---

## Phase 6: Governance & Release Discipline

### 6.1 Error Contract Versioning
- [ ] Add explicit error contract version in emitted payloads.
- [ ] Add migration notes template for any breaking error code change.
- [ ] Add CI rule: block breaking changes without approval flag.

### 6.2 Documentation
- [ ] Add operator runbook:
  - common failures
  - remediation playbooks
  - escalation guidance
- [ ] Add contributor guide for adding new resolver rules/codes safely.

### 6.3 SLOs
- [ ] Define and track:
  - unknown/unclassified error rate
  - mean time to actionable diagnosis
  - successful auto-remediation rate
  - rollback success verification rate

---

## Definition of Done (State-of-the-Art)

- [ ] 100% fail/abort paths emit stable, versioned error envelopes.
- [ ] Classifier is deterministic, side-effect free, and fully snapshot-tested.
- [ ] Retry/remediation policy is explicit, test-covered, and safety-gated.
- [ ] Unknown/unclassified error rate stays below agreed threshold in real usage.
- [ ] Structured logs + debug bundle make support triage reproducible.
- [ ] Contract changes are governed and backward compatibility is enforced.

---

## Suggested Execution Order

1. Phase 1 (contracts)  
2. Phase 2 (architecture split)  
3. Phase 5.1 (classifier test corpus)  
4. Phase 3 (retry/remediation policy)  
5. Phase 4 (observability/debug bundle)  
6. Phase 5.2-5.4 (fault injection + platform hardening)  
7. Phase 6 (governance + SLO operations)
