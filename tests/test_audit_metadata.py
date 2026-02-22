"""Tests for project-type-specific metadata checks in audit."""


from pathlib import Path
import tempfile
import unittest

from pnp.audit import _metadata_check


class AuditMetadataTests(unittest.TestCase):
    def test_metadata_check_accepts_package_json_with_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "package.json").write_text(
                '{"name":"web-app","version":"0.1.0"}',
                encoding="utf-8",
            )
            status, detail = _metadata_check(str(root))
        self.assertEqual(status, "ok")
        self.assertIn("package.json metadata: web-app 0.1.0", detail)

    def test_metadata_check_warns_on_invalid_package_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "package.json").write_text("{", encoding="utf-8")
            status, detail = _metadata_check(str(root))
        self.assertEqual(status, "warn")
        self.assertIn("invalid package.json", detail)

    def test_metadata_check_warns_when_go_mod_lacks_module(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "go.mod").write_text(
                "go 1.24\n",
                encoding="utf-8",
            )
            status, detail = _metadata_check(str(root))
        self.assertEqual(status, "warn")
        self.assertIn("go.mod missing module directive", detail)

    def test_metadata_check_accepts_cargo_workspace_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Cargo.toml").write_text(
                "[workspace]\nmembers = [\"crate-a\"]\n",
                encoding="utf-8",
            )
            status, detail = _metadata_check(str(root))
        self.assertEqual(status, "ok")
        self.assertIn("cargo workspace manifest detected", detail)


if __name__ == "__main__":
    unittest.main()
