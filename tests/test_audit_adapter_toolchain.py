"""Unit tests for adapter-aware doctor toolchain checks."""

from pathlib import Path
from unittest.mock import patch
import tempfile
import unittest

from pnp import audit


class AuditAdapterToolchainTests(unittest.TestCase):
    def test_toolchain_check_reports_ok_when_no_adapter_commands_configured(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "package.json").write_text(
                '{"name":"app","version":"1.0.0"}',
                encoding="utf-8",
            )
            status, detail = audit._adapter_toolchain_check(str(root))
        self.assertEqual(status, "ok")
        self.assertIn("no adapter commands configured", detail)

    def test_toolchain_check_warns_when_required_binary_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "package.json").write_text(
                '{"name":"app","version":"1.0.0"}',
                encoding="utf-8",
            )
            (root / "pyproject.toml").write_text(
                (
                    "[tool.pnp]\nproject-type='node'\n\n"
                    "[tool.pnp.node]\npublish-command='npm publish --access public'\n"
                ),
                encoding="utf-8",
            )
            with patch("pnp.audit.ops.command_exists", return_value=False):
                status, detail = audit._adapter_toolchain_check(str(root))
        self.assertEqual(status, "warn")
        self.assertIn("missing command(s): npm", detail)

    def test_toolchain_check_reports_ok_when_binaries_exist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Cargo.toml").write_text(
                "[package]\nname='app'\nversion='0.4.0'\n",
                encoding="utf-8",
            )
            (root / "pyproject.toml").write_text(
                (
                    "[tool.pnp]\nproject-type='rust'\n\n"
                    "[tool.pnp.rust]\n"
                    "pre-publish-command='cargo fmt --check'\n"
                    "publish-command='cargo publish'\n"
                ),
                encoding="utf-8",
            )
            with patch("pnp.audit.ops.command_exists", return_value=True):
                status, detail = audit._adapter_toolchain_check(str(root))
        self.assertEqual(status, "ok")
        self.assertIn("rust: toolchain ready (cargo)", detail)


if __name__ == "__main__":
    unittest.main()
