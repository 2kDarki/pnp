"""Regression tests for machine-readable JSON contracts."""


import subprocess
import unittest
import json
import sys


def _extract_json(stdout: str) -> dict[str, object]:
    start = stdout.find("{")
    end = stdout.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise AssertionError("no JSON object found in output")
    blob = stdout[start:end + 1]
    return json.loads(blob)


def _assert_error_envelope(payload: dict[str, object]) -> None:
    envelope = payload.get("error_envelope")
    if not isinstance(envelope, dict):
        raise AssertionError("error_envelope is missing or not an object")
    for key in (
        "code",
        "severity",
        "category",
        "actionable",
        "message",
        "operation",
        "step",
        "stderr_excerpt",
        "raw_ref",
        "retryable",
        "user_action_required",
        "suggested_fix",
        "context",
    ):
        if key not in envelope:
            raise AssertionError(f"missing error_envelope key: {key}")


class JsonContractTests(unittest.TestCase):
    def test_doctor_json_contract_v1(self) -> None:
        cp = subprocess.run(
            [sys.executable, "-m", "pnp", "--doctor", "--doctor-json", "--ci"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(cp.returncode, 0, cp.stderr)
        payload = _extract_json(cp.stdout)
        self.assertEqual(payload.get("schema"), "pnp.doctor.v1")
        self.assertEqual(payload.get("schema_version"), 1)
        self.assertIn("generated_at", payload)
        self.assertIn("path", payload)
        summary = payload.get("summary")
        self.assertIsInstance(summary, dict)
        if isinstance(summary, dict):
            self.assertIn("critical", summary)
            self.assertIn("warnings", summary)
            self.assertIn("healthy", summary)
        checks = payload.get("checks")
        self.assertIsInstance(checks, list)
        _assert_error_envelope(payload)

    def test_check_json_contract_v1(self) -> None:
        cp = subprocess.run(
            [sys.executable, "-m", "pnp", ".", "--check-json", "--ci"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(cp.returncode, 0)
        payload = _extract_json(cp.stdout)
        self.assertEqual(payload.get("schema"), "pnp.check.v1")
        self.assertEqual(payload.get("schema_version"), 1)
        self.assertIn("generated_at", payload)
        self.assertIn("path", payload)
        self.assertIn("strict", payload)
        summary = payload.get("summary")
        self.assertIsInstance(summary, dict)
        if isinstance(summary, dict):
            self.assertIn("exit_code", summary)
            self.assertIn("blockers", summary)
            self.assertIn("warnings", summary)
        findings = payload.get("findings")
        self.assertIsInstance(findings, list)
        _assert_error_envelope(payload)


if __name__ == "__main__":
    unittest.main()
