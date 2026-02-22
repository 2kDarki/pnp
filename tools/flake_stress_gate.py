#!/usr/bin/env python3
"""Run seeded stress tests repeatedly and enforce flake-rate threshold."""


from datetime import UTC, datetime
from pathlib import Path
import subprocess
import argparse
import random
import json
import sys
import os


ROOT = Path(__file__).resolve().parents[1]


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _run_once(seed: int, retries: int, timeout_s: int) -> tuple[bool, str]:
    env = dict(os.environ)
    env["PNP_STRESS_SEED"] = str(seed)
    env["PNP_STRESS_ITERATIONS"] = str(retries)
    env["PNP_STRESS_RETRY_SAMPLES"] = "64"
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "tests/test_fault_injection_stress.py",
    ]
    try:
        cp = subprocess.run(
            cmd,
            cwd=ROOT,
            env=env,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired:
        return False, "timeout"
    out = (cp.stdout or cp.stderr or "").strip()
    return cp.returncode == 0, out


def main() -> int:
    parser = argparse.ArgumentParser(description="seeded stress/flake gate")
    parser.add_argument("--runs", type=int, default=20)
    parser.add_argument("--seed-base", type=int, default=1000)
    parser.add_argument("--seed-span", type=int, default=20000)
    parser.add_argument("--retries-per-run", type=int, default=35)
    parser.add_argument("--timeout-s", type=int, default=180)
    parser.add_argument("--flake-threshold", type=float, default=0.05)
    parser.add_argument(
        "--report-file",
        default="pnplog/stress_flake_report.json",
    )
    args = parser.parse_args()

    if args.runs <= 0:
        print("--runs must be > 0")
        return 2
    rng = random.Random(args.seed_base)
    samples: list[dict[str, object]] = []
    failures = 0
    for i in range(args.runs):
        seed = rng.randint(args.seed_base, args.seed_base + args.seed_span)
        ok, summary = _run_once(
            seed=seed,
            retries=args.retries_per_run,
            timeout_s=args.timeout_s,
        )
        samples.append(
            {
                "run": i + 1,
                "seed": seed,
                "ok": ok,
                "summary": summary.splitlines()[-1] if summary else "",
            }
        )
        if not ok:
            failures += 1
            print(f"[fail] run={i + 1} seed={seed} summary={samples[-1]['summary']}")
        else:
            print(f"[ok] run={i + 1} seed={seed} summary={samples[-1]['summary']}")

    rate = failures / args.runs
    payload = {
        "schema": "pnp.stress_flake.v1",
        "schema_version": 1,
        "generated_at": _now(),
        "runs": args.runs,
        "failures": failures,
        "flake_rate": rate,
        "flake_threshold": args.flake_threshold,
        "retries_per_run": args.retries_per_run,
        "samples": samples,
    }
    report_path = (ROOT / args.report_file).resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"stress report written: {report_path}")
    print(f"flake rate: {rate:.4f} (threshold {args.flake_threshold:.4f})")
    if rate > args.flake_threshold:
        print("flake gate failed")
        return 1
    print("flake gate passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
