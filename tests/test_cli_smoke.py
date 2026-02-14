"""CLI smoke tests for stable user-facing behavior."""
from __future__ import annotations

import subprocess
import sys
import unittest


class CliSmokeTests(unittest.TestCase):
    def test_help_exits_zero(self) -> None:
        cp = subprocess.run(
            [sys.executable, "-m", "pnp", "--help"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(cp.returncode, 0, cp.stderr)

    def test_ci_dry_run_without_repo_exits_non_zero(self) -> None:
        cp = subprocess.run(
            [sys.executable, "-m", "pnp", ".", "--dry-run", "--ci"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(cp.returncode, 0)
        self.assertIn("no git repository found", cp.stdout)

    def test_version_exits_zero(self) -> None:
        cp = subprocess.run(
            [sys.executable, "-m", "pnp", "--version"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(cp.returncode, 0, cp.stderr)
        self.assertIn("pnp", cp.stdout.lower())

    def test_doctor_runs(self) -> None:
        cp = subprocess.run(
            [sys.executable, "-m", "pnp", "--doctor", "--ci"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(cp.returncode, 0, cp.stderr)
        self.assertIn("doctor report", cp.stdout.lower())


if __name__ == "__main__":
    unittest.main()
