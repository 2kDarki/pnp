# Operator Runbook

This runbook is for operating and triaging `pnp` failures in CI and local environments.

## Quick Triage Flow

1. Capture machine-readable artifacts:
   - `pnplog/last_error_envelope.json`
   - `pnplog/events.jsonl`
   - `pnplog/debug-report-*.json` (if `--debug-report` enabled)
2. Identify the stable error code from envelope (`code`).
3. Route by category:
   - `PNP_GIT_*` -> repository/git state
   - `PNP_NET_*` -> remote/auth/network
   - `PNP_REL_*` -> publish/release workflow
   - `PNP_INT_*` -> runtime/system failure
4. Apply the code-specific remediation playbook below.
5. If unresolved, escalate with required payload bundle.

## Common Failures and Playbooks

### `PNP_GIT_REPOSITORY_FAIL`
- Symptom: repository discovery/init step failed.
- Checks:
  - confirm working directory
  - verify `.git` exists
  - verify CI checkout step is present
- Actions:
  - run from repo root, or initialize with `git init`
  - in CI, add/repair checkout step

### `PNP_REL_HOOKS_FAIL`
- Symptom: pre-push hooks failed.
- Checks:
  - run failing hook command directly
  - confirm toolchain/deps for hook command
- Actions:
  - fix hook failures first, then rerun `pnp`
  - keep `--ci` fail-fast for pipeline consistency

### `PNP_NET_CONNECTIVITY` / `PNP_NET_REMOTE_UNREADABLE` / `PNP_NET_PUSH_FAIL`
- Symptom: remote access/push failure.
- Checks:
  - `git remote -v`
  - credential/token validity
  - network reachability to remote host
- Actions:
  - refresh credentials and retry
  - verify remote URL correctness
  - if transient, rerun to leverage retry policy

### `PNP_REL_PUBLISH_FAIL` / `PNP_REL_RELEASE_FAIL`
- Symptom: tag/release creation failed.
- Checks:
  - existing local/remote tag conflicts
  - release token and target repository
- Actions:
  - resolve conflicting tags
  - verify `--gh-repo`/token scope and rerun release

### `PNP_INT_UNHANDLED_EXCEPTION`
- Symptom: internal runtime failure.
- Checks:
  - inspect envelope `message` and `stderr_excerpt`
  - inspect `events.jsonl` and `debug.log` tail
- Actions:
  - rerun with `--debug --debug-report`
  - escalate with bundle if reproducible

## Escalation Guidance

Escalate when:
- a stable code repeats after playbook actions
- the same failure affects multiple repos/pipelines
- an internal (`PNP_INT_*`) failure is reproducible

Escalation bundle must include:
- `pnplog/last_error_envelope.json`
- `pnplog/events.jsonl`
- `pnplog/debug-report-*.json` (or `--debug-report-file` output)
- exact command line used
- environment summary (CI/local, OS, Python, Git version)

## Operational Commands

- Validate JSON contracts:
  - `python tools/schema_gate.py`
- Validate error-code contract:
  - `python tools/error_code_gate.py`
- Run stress flake gate:
  - `python tools/flake_stress_gate.py --runs 20 --flake-threshold 0.05`
- Generate/track SLO metrics:
  - `python tools/slo_report.py --events-file pnplog/events.jsonl --report-file pnplog/slo_report.json --fail-on-thresholds`
