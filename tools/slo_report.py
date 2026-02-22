#!/usr/bin/env python3
"""Compute SLO metrics from pnplog events stream."""


from datetime import datetime
from pathlib import Path
from typing import Any
import argparse
import json


def _parse_ts(ts: str) -> datetime | None:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def _load_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if isinstance(obj, dict):
            rows.append(obj)
    return rows


def _rate(ok: int, total: int) -> float | None:
    if total <= 0:
        return None
    return ok / total


def compute_slos(events: list[dict[str, Any]]) -> dict[str, Any]:
    resolver = [e for e in events if e.get("event_type") == "resolver_decision"]
    unknown = 0
    for e in resolver:
        payload = e.get("payload", {})
        if not isinstance(payload, dict):
            continue
        code = str(payload.get("code", "")).strip()
        if code == "PNP_GIT_UNCLASSIFIED":
            unknown += 1
    unknown_rate = _rate(unknown, len(resolver))

    runs: dict[str, dict[str, datetime]] = {}
    for e in events:
        run_id = str(e.get("run_id", "")).strip()
        if not run_id:
            continue
        ts = _parse_ts(str(e.get("ts", "")))
        if ts is None:
            continue
        event_type = str(e.get("event_type", "")).strip()
        bucket = runs.setdefault(run_id, {})
        if event_type == "error_signal":
            prev = bucket.get("error_signal")
            bucket["error_signal"] = ts if prev is None else min(prev, ts)
        if event_type == "actionable_diagnosis":
            prev = bucket.get("actionable_diagnosis")
            bucket["actionable_diagnosis"] = ts if prev is None else min(prev, ts)
    diagnosis_samples: list[float] = []
    for sample in runs.values():
        start = sample.get("error_signal")
        done = sample.get("actionable_diagnosis")
        if start is None or done is None:
            continue
        delta = (done - start).total_seconds()
        if delta >= 0:
            diagnosis_samples.append(delta)
    mean_diagnosis = None
    if diagnosis_samples:
        mean_diagnosis = sum(diagnosis_samples) / len(diagnosis_samples)

    remediation = [e for e in events if e.get("event_type") == "remediation"]
    rem_success = 0
    rem_total = 0
    for e in remediation:
        payload = e.get("payload", {})
        if not isinstance(payload, dict):
            continue
        outcome = str(payload.get("outcome", "")).strip()
        if outcome not in {"success", "failed"}:
            continue
        rem_total += 1
        if outcome == "success":
            rem_success += 1
    remediation_rate = _rate(rem_success, rem_total)

    rollback = [e for e in events if e.get("event_type") == "rollback_verification"]
    rb_success = 0
    rb_total = 0
    for e in rollback:
        payload = e.get("payload", {})
        if not isinstance(payload, dict):
            continue
        verified = payload.get("verified")
        if not isinstance(verified, bool):
            continue
        rb_total += 1
        if verified:
            rb_success += 1
    rollback_rate = _rate(rb_success, rb_total)

    return {
        "unknown_unclassified_error_rate": {
            "value": unknown_rate,
            "numerator": unknown,
            "denominator": len(resolver),
        },
        "mean_time_to_actionable_diagnosis_seconds": {
            "value": mean_diagnosis,
            "samples": len(diagnosis_samples),
        },
        "successful_auto_remediation_rate": {
            "value": remediation_rate,
            "numerator": rem_success,
            "denominator": rem_total,
        },
        "rollback_success_verification_rate": {
            "value": rollback_rate,
            "numerator": rb_success,
            "denominator": rb_total,
        },
    }


def _breach(name: str, value: float | None, threshold: float, kind: str) -> str | None:
    if value is None:
        return None
    if kind == "max" and value > threshold:
        return f"{name}={value:.4f} exceeds max {threshold:.4f}"
    if kind == "min" and value < threshold:
        return f"{name}={value:.4f} below min {threshold:.4f}"
    return None


def main() -> int:
    p = argparse.ArgumentParser(description="SLO metrics report from events.jsonl")
    p.add_argument("--events-file", default="pnplog/events.jsonl")
    p.add_argument("--report-file", default="pnplog/slo_report.json")
    p.add_argument("--max-unknown-rate", type=float, default=0.20)
    p.add_argument("--max-mean-diagnosis-seconds", type=float, default=30.0)
    p.add_argument("--min-auto-remediation-success-rate", type=float, default=0.50)
    p.add_argument("--min-rollback-verification-success-rate", type=float, default=0.90)
    p.add_argument("--fail-on-thresholds", action="store_true")
    args = p.parse_args()

    events = _load_events(Path(args.events_file).expanduser())
    metrics = compute_slos(events)
    payload = {
        "schema": "pnp.slo_report.v1",
        "schema_version": 1,
        "events_file": str(Path(args.events_file).expanduser()),
        "metrics": metrics,
        "thresholds": {
            "max_unknown_rate": args.max_unknown_rate,
            "max_mean_diagnosis_seconds": args.max_mean_diagnosis_seconds,
            "min_auto_remediation_success_rate": args.min_auto_remediation_success_rate,
            "min_rollback_verification_success_rate": args.min_rollback_verification_success_rate,
        },
    }
    report_path = Path(args.report_file).expanduser()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(f"SLO report written: {report_path.resolve()}")
    breaches = [
        _breach(
            "unknown_unclassified_error_rate",
            metrics["unknown_unclassified_error_rate"]["value"],
            args.max_unknown_rate,
            "max",
        ),
        _breach(
            "mean_time_to_actionable_diagnosis_seconds",
            metrics["mean_time_to_actionable_diagnosis_seconds"]["value"],
            args.max_mean_diagnosis_seconds,
            "max",
        ),
        _breach(
            "successful_auto_remediation_rate",
            metrics["successful_auto_remediation_rate"]["value"],
            args.min_auto_remediation_success_rate,
            "min",
        ),
        _breach(
            "rollback_success_verification_rate",
            metrics["rollback_success_verification_rate"]["value"],
            args.min_rollback_verification_success_rate,
            "min",
        ),
    ]
    found = [b for b in breaches if b]
    if found:
        print("SLO threshold breaches:")
        for b in found:
            print(f" - {b}")
        if args.fail_on_thresholds:
            return 1
    else:
        print("SLO thresholds satisfied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
