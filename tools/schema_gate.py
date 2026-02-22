#!/usr/bin/env python3
"""CI gate for JSON schema contract compatibility."""


from pathlib import Path
import subprocess
import json
import sys
import os


ROOT          = Path(__file__).resolve().parents[1]
LOCK_FILE     = ROOT / "docs" / "schema_lock.json"
APPROVAL_FILE = ROOT / ".schema_breaking_change_approved"


def _extract_json_blob(text: str) -> dict[str, object]:
    start = text.find("{")
    end   = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError(
            "could not locate JSON object in command output")
    return json.loads(text[start:end + 1])


def _run(cmd: list[str]) -> dict[str, object]:
    cp = subprocess.run(cmd, cwd=ROOT, check=False, capture_output=True, text=True)
    if cp.returncode not in (0, 10, 20):
        err = cp.stderr.strip() or cp.stdout.strip() \
           or f"exit={cp.returncode}"
        raise RuntimeError(
              f"command failed ({' '.join(cmd)}): {err}")
    return _extract_json_blob(cp.stdout)


def _validate_payload(name: str, payload: dict[str, object], lock: dict[str, object]) -> list[str]:
    issues: list[str] = []
    required_top = [str(k) for k in lock[
        "required_top_level"]]  # type: ignore[index]
    required_summary = [str(k) for k in lock[
        "required_summary"]]  # type: ignore[index]
    required_item = [str(k) for k in lock[
        "required_item"]]  # type: ignore[index]
    required_envelope = [str(k) for k in lock.get(
        "required_envelope", [])]  # type: ignore[arg-type]
    expected_schema = str(lock["schema"])  # type: ignore[index]
    expected_schema_version = int(lock["schema_version"])  # type: ignore[index]

    if payload.get("schema") != expected_schema:
        issues.append(f"{name}: schema mismatch ({payload.get('schema')} != {expected_schema})")
    if payload.get("schema_version") != expected_schema_version:
        issues.append(
            f"{name}: schema_version mismatch "
            + f"({payload.get('schema_version')} != {expected_schema_version})"
        )

    for key in required_top:
        if key not in payload:
            issues.append(f"{name}: missing top-level key '{key}'")

    summary = payload.get("summary")
    if not isinstance(summary, dict):
        issues.append(f"{name}: summary is not an object")
    else:
        for key in required_summary:
            if key not in summary:
                issues.append(f"{name}: missing summary key '{key}'")

    items_key = "checks" if name == "doctor" else "findings"
    items     = payload.get(items_key)
    if not isinstance(items, list):
        issues.append(f"{name}: {items_key} is not an array")
    else:
        for i, item in enumerate(items):
            if not isinstance(item, dict):
                issues.append(f"{name}: {items_key}[{i}] is not an object")
                continue
            for key in required_item:
                if key not in item:
                    issues.append(f"{name}: {items_key}[{i}] missing key '{key}'")

    envelope = payload.get("error_envelope")
    if required_envelope:
        if not isinstance(envelope, dict):
            issues.append(f"{name}: error_envelope is not an object")
        else:
            for key in required_envelope:
                if key not in envelope:
                    issues.append(f"{name}: error_envelope missing key '{key}'")
    return issues


def main() -> int:
    lock = json.loads(LOCK_FILE.read_text(encoding="utf-8"))
    doctor = _run([sys.executable, "-m", "pnp", "--doctor", "--doctor-json", "--ci"])
    check = _run([sys.executable, "-m", "pnp", ".", "--check-json", "--ci"])

    issues: list[str] = []
    issues.extend(_validate_payload("doctor", doctor, lock["doctor"]))  # type: ignore[index]
    issues.extend(_validate_payload("check", check, lock["check"]))  # type: ignore[index]

    approved = (
        os.environ.get("PNP_ALLOW_SCHEMA_BREAK", "").strip() in {"1", "true", "yes"}
        or APPROVAL_FILE.exists()
    )

    if issues and not approved:
        print("Schema gate failed:")
        for issue in issues: print(f" - {issue}")
        print("Set PNP_ALLOW_SCHEMA_BREAK=1 or add .schema_breaking_change_approved to override.")
        return 1

    if issues and approved:
        print("Schema gate override active; continuing despite detected issues:")
        for issue in issues: print(f" - {issue}")
        return 0

    print("Schema gate passed.")
    return 0


if __name__ == "__main__": raise SystemExit(main())
