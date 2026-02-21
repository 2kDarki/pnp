"""CLI smoke tests for stable user-facing behavior."""


from pathlib import Path
import subprocess
import tempfile
import unittest
import json
import sys
import os


class CliSmokeTests(unittest.TestCase):
    def test_help_exits_zero(self) -> None:
        cp = subprocess.run(
            [sys.executable, "-m", "pnp", "--help"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(cp.returncode, 0, cp.stderr)
        self.assertIn("--doctor", cp.stdout)
        self.assertIn("--version", cp.stdout)
        self.assertIn("--sync", cp.stdout)
        self.assertIn("--show-config", cp.stdout)
        self.assertIn("--check-only", cp.stdout)
        self.assertIn("--check-json", cp.stdout)
        self.assertIn("--edit-message", cp.stdout)
        self.assertIn("--editor", cp.stdout)

    def test_ci_dry_run_without_repo_exits_non_zero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cp = subprocess.run(
                [sys.executable, "-m", "pnp", ".", "--dry-run", "--ci"],
                check=False,
                capture_output=True,
                text=True,
                cwd=tmp,
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
        self.assertIn("doctor summary", cp.stdout.lower())

    def test_show_config_runs(self) -> None:
        cp = subprocess.run(
            [sys.executable, "-m", "pnp", "--show-config"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(cp.returncode, 0, cp.stderr)
        self.assertIn("\"path\":", cp.stdout)
        self.assertIn("\"_sources\":", cp.stdout)
        self.assertIn("\"_config_diagnostics\":", cp.stdout)
        self.assertIn("\"_config_files\":", cp.stdout)

    def test_show_config_reports_pyproject_layer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "pyproject.toml").write_text(
                "[tool.pnp]\nremote = 'upstream'\n",
                encoding="utf-8",
            )
            cp = subprocess.run(
                [sys.executable, "-m", "pnp", str(root), "--show-config"],
                check=False,
                capture_output=True,
                text=True,
            )
        self.assertEqual(cp.returncode, 0, cp.stderr)
        end = cp.stdout.rfind("}")
        payload = json.loads(cp.stdout[:end + 1])
        self.assertEqual(payload["remote"], "upstream")
        self.assertEqual(payload["_sources"]["remote"], "pyproject")

    def test_doctor_json_runs(self) -> None:
        cp = subprocess.run(
            [sys.executable, "-m", "pnp", "--doctor", "--doctor-json", "--ci"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(cp.returncode, 0, cp.stderr)
        self.assertIn("\"summary\":", cp.stdout)
        self.assertIn("\"checks\":", cp.stdout)

    def test_check_only_without_repo_exits_non_zero(self) -> None:
        cp = subprocess.run(
            [sys.executable, "-m", "pnp", ".", "--check-only", "--ci"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(cp.returncode, 0)
        self.assertIn("check-only", cp.stdout.lower())

    def test_check_json_runs(self) -> None:
        cp = subprocess.run(
            [sys.executable, "-m", "pnp", ".", "--check-json", "--ci"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(cp.returncode, 0)
        self.assertIn("\"summary\":", cp.stdout)
        self.assertIn("\"exit_code\":", cp.stdout)

    def test_unknown_flag_is_rejected_by_argparse(self) -> None:
        cp = subprocess.run(
            [sys.executable, "-m", "pnp", "--nope-flag"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(cp.returncode, 0)
        self.assertIn("unrecognized arguments", cp.stderr.lower())

    def test_install_and_uninstall_git_extension_shim(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bin_dir = Path(tmp)
            shim = bin_dir / "git-pnp"
            cp_install = subprocess.run(
                [
                    sys.executable, "-m", "pnp",
                    "--install-git-ext",
                    "--git-ext-dir", str(bin_dir),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(cp_install.returncode, 0, cp_install.stderr)
            self.assertTrue(shim.exists())

            cp_uninstall = subprocess.run(
                [
                    sys.executable, "-m", "pnp",
                    "--uninstall-git-ext",
                    "--git-ext-dir", str(bin_dir),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(cp_uninstall.returncode, 0, cp_uninstall.stderr)
            self.assertFalse(shim.exists())

    def test_install_git_extension_warns_if_dir_not_in_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ)
            env["PATH"] = ""
            cp = subprocess.run(
                [
                    sys.executable, "-m", "pnp",
                    "--install-git-ext",
                    "--git-ext-dir", tmp,
                ],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )
        self.assertEqual(cp.returncode, 0, cp.stderr)
        self.assertIn("to PATH", cp.stdout)

    def test_install_git_extension_no_path_warning_when_dir_in_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ)
            env["PATH"] = tmp
            cp = subprocess.run(
                [
                    sys.executable, "-m", "pnp",
                    "--install-git-ext",
                    "--git-ext-dir", tmp,
                ],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )
        self.assertEqual(cp.returncode, 0, cp.stderr)
        self.assertNotIn("to PATH", cp.stdout)


if __name__ == "__main__":
    unittest.main()
