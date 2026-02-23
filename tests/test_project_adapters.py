"""Tests for project adapter detection and resolution."""

from pathlib import Path
import tempfile
import unittest

from pnp.project_adapters import resolve_project_adapter
from pnp.project_adapters import detect_project_type


class ProjectAdapterTests(unittest.TestCase):
    def test_detect_python_from_pyproject(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "pyproject.toml").write_text(
                "[project]\nname='pkg'\n",
                encoding="utf-8",
            )
            self.assertEqual(detect_project_type(str(root)), "python")

    def test_detect_node_from_package_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "package.json").write_text(
                "{\"name\": \"app\"}",
                encoding="utf-8",
            )
            self.assertEqual(detect_project_type(str(root)), "node")

    def test_resolve_unknown_override_falls_back_to_generic_adapter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            adapter = resolve_project_adapter(tmp, override="dotnet")
            self.assertEqual(adapter.project_type, "dotnet")
            tag = adapter.compute_next_tag("v1.2.3", "patch", "v", tmp)
            self.assertEqual(tag, "v1.2.4")

    def test_auto_detect_unknown_returns_generic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            adapter = resolve_project_adapter(tmp, override="auto")
            self.assertEqual(adapter.project_type, "generic")

    def test_node_adapter_seeds_first_tag_from_package_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "package.json").write_text(
                "{\"name\": \"app\", \"version\": \"1.4.0\"}",
                encoding="utf-8",
            )
            adapter = resolve_project_adapter(str(root), override="auto")
            tag = adapter.compute_next_tag("", "patch", "v", str(root))
            self.assertEqual(tag, "v1.4.0")

    def test_rust_adapter_seeds_first_tag_from_cargo_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Cargo.toml").write_text(
                "[package]\nname='app'\nversion='0.9.3'\n",
                encoding="utf-8",
            )
            adapter = resolve_project_adapter(str(root), override="auto")
            tag = adapter.compute_next_tag("", "minor", "v", str(root))
            self.assertEqual(tag, "v0.9.3")

    def test_node_adapter_collects_pre_publish_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "package.json").write_text(
                "{\"name\": \"app\", \"version\": \"1.4.0\"}",
                encoding="utf-8",
            )
            adapter = resolve_project_adapter(str(root), override="auto")
            commands = adapter.pre_publish_commands(
                {
                    "pre-publish-hook": "drace lint .",
                    "pre-publish-hooks": ["python -m unittest -q"],
                    "build-script": "build",
                    "test-script": "test",
                }
            )
            self.assertEqual(
                commands,
                [
                    "drace lint .",
                    "python -m unittest -q",
                    "npm run build",
                    "npm run test",
                ],
            )

    def test_rust_adapter_collects_build_and_test_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Cargo.toml").write_text(
                "[package]\nname='app'\nversion='0.9.3'\n",
                encoding="utf-8",
            )
            adapter = resolve_project_adapter(str(root), override="auto")
            commands = adapter.pre_publish_commands(
                {
                    "pre-publish-command": "cargo fmt --check",
                    "build-command": "cargo build --locked",
                    "test-command": "cargo test --locked",
                }
            )
            self.assertEqual(
                commands,
                [
                    "cargo fmt --check",
                    "cargo build --locked",
                    "cargo test --locked",
                ],
            )

    def test_node_adapter_collects_publish_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "package.json").write_text(
                "{\"name\": \"app\", \"version\": \"1.4.0\"}",
                encoding="utf-8",
            )
            adapter = resolve_project_adapter(str(root), override="auto")
            commands = adapter.publish_commands(
                {
                    "publish-command": "npm publish --access public",
                    "publish-script": "publish:prod",
                }
            )
            self.assertEqual(
                commands,
                [
                    "npm publish --access public",
                    "npm run publish:prod",
                ],
            )


if __name__ == "__main__":
    unittest.main()
