# SLO Metrics

`pnp` tracks operational error-handling SLOs from `pnplog/events.jsonl`.

## Tracked Metrics

1. `unknown_unclassified_error_rate`
   - Definition: `PNP_GIT_UNCLASSIFIED` resolver decisions / total resolver decisions.
   - Source events: `resolver_decision`.

2. `mean_time_to_actionable_diagnosis_seconds`
   - Definition: average time from first `error_signal` to first `actionable_diagnosis` per run.
   - Source events: `error_signal`, `actionable_diagnosis`.

3. `successful_auto_remediation_rate`
   - Definition: remediation `success` / (`success` + `failed`).
   - Source events: `remediation`.

4. `rollback_success_verification_rate`
   - Definition: rollback verification `verified=true` / total rollback verification events.
   - Source events: `rollback_verification`.

## Reporting Tool

Generate SLO report:

```bash
python tools/slo_report.py --events-file pnplog/events.jsonl --report-file pnplog/slo_report.json
```

Enforce thresholds in CI/local checks:

```bash
python tools/slo_report.py --fail-on-thresholds
```

Default threshold policy:
- max unknown rate: `0.20`
- max mean diagnosis seconds: `30.0`
- min auto-remediation success rate: `0.50`
- min rollback verification success rate: `0.90`
