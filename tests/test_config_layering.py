"""Tests for layered config precedence (default < pyproject < git < env < cli)."""


from unittest.mock import patch

from pathlib import Path
import tempfile
import unittest
import os

from pnp.cli import _build_parser
from pnp import config


class ConfigLayeringTests(unittest.TestCase):
    def test_pyproject_overrides_defaults(self) -> None:
        parser = _build_parser()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "pyproject.toml").write_text(
                "[tool.pnp]\nremote = 'pyproj'\n",
                encoding="utf-8",
            )
            args = parser.parse_args([str(root)])
            with patch("pnp.config._load_git_overrides", return_value={}):
                with patch.dict(os.environ, {}, clear=True):
                    merged = config.apply_layered_config(args, [str(root)], parser)
        self.assertEqual(merged.remote, "pyproj")
        self.assertEqual(merged._pnp_config_sources["remote"], "pyproject")

    def test_git_overrides_pyproject(self) -> None:
        parser = _build_parser()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "pyproject.toml").write_text(
                "[tool.pnp]\nremote = 'pyproj'\n",
                encoding="utf-8",
            )
            args = parser.parse_args([str(root)])
            with patch("pnp.config._load_git_overrides",
                       return_value={"remote": "origin"}):
                with patch.dict(os.environ, {}, clear=True):
                    merged = config.apply_layered_config(args, [str(root)], parser)
        self.assertEqual(merged.remote, "origin")
        self.assertEqual(merged._pnp_config_sources["remote"], "git")

    def test_env_overrides_git(self) -> None:
        parser = _build_parser()
        args = parser.parse_args([])
        with patch("pnp.config._load_pyproject_overrides",
                   return_value=({"remote": "pyproj"}, [], None)):
            with patch("pnp.config._load_git_overrides",
                       return_value={"remote": "origin"}):
                with patch.dict(os.environ, {"PNP_REMOTE": "upstream"}, clear=False):
                    merged = config.apply_layered_config(args, [], parser)
        self.assertEqual(merged.remote, "upstream")
        self.assertEqual(merged._pnp_config_sources["remote"], "env")

    def test_cli_overrides_env(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["--remote", "fork"])
        with patch("pnp.config._load_pyproject_overrides",
                   return_value=({"remote": "pyproj"}, [], None)):
            with patch("pnp.config._load_git_overrides",
                       return_value={"remote": "origin"}):
                with patch.dict(os.environ, {"PNP_REMOTE": "upstream"}, clear=False):
                    merged = config.apply_layered_config(
                        args,
                        ["--remote", "fork"],
                        parser,
                    )
        self.assertEqual(merged.remote, "fork")
        self.assertEqual(merged._pnp_config_sources["remote"], "cli")

    def test_invalid_bool_is_ignored(self) -> None:
        parser = _build_parser()
        args = parser.parse_args([])
        with patch("pnp.config._load_pyproject_overrides",
                   return_value=({}, [], None)):
            with patch("pnp.config._load_git_overrides",
                       return_value={"push": "false"}):
                with patch.dict(os.environ, {"PNP_PUSH": "maybe"}, clear=False):
                    merged = config.apply_layered_config(args, [], parser)
        self.assertIs(merged.push, False)
        diagnostics = merged._pnp_config_diagnostics
        self.assertTrue(any(d["source"] == "env" and d["key"] == "push"
                            for d in diagnostics))

    def test_pyproject_invalid_types_are_reported(self) -> None:
        parser = _build_parser()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "pyproject.toml").write_text(
                "[tool.pnp]\npush = 'maybe'\nunknown_key = true\n",
                encoding="utf-8",
            )
            args = parser.parse_args([str(root)])
            with patch("pnp.config._load_git_overrides", return_value={}):
                merged = config.apply_layered_config(args, [str(root)], parser)
        self.assertIs(merged.push, False)
        diags = merged._pnp_config_diagnostics
        self.assertTrue(any(d["key"] == "push" for d in diags))
        self.assertTrue(any(d["key"] == "unknown_key" for d in diags))

    def test_pyproject_parse_error_is_reported(self) -> None:
        parser = _build_parser()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "pyproject.toml").write_text(
                "[tool.pnp\npush = true\n",
                encoding="utf-8",
            )
            args = parser.parse_args([str(root)])
            with patch("pnp.config._load_git_overrides", return_value={}):
                merged = config.apply_layered_config(args, [], parser)
        self.assertTrue(any(d["level"] == "error" and d["source"] == "pyproject"
                            for d in merged._pnp_config_diagnostics))

    def test_machete_flag_can_come_from_env(self) -> None:
        parser = _build_parser()
        args = parser.parse_args([])
        with patch("pnp.config._load_pyproject_overrides",
                   return_value=({}, [], None)):
            with patch("pnp.config._load_git_overrides",
                       return_value={}):
                with patch.dict(os.environ, {"PNP_MACHETE_STATUS": "true"}, clear=False):
                    merged = config.apply_layered_config(args, [], parser)
        self.assertIs(merged.machete_status, True)

    def test_check_only_can_come_from_env(self) -> None:
        parser = _build_parser()
        args = parser.parse_args([])
        with patch("pnp.config._load_pyproject_overrides",
                   return_value=({}, [], None)):
            with patch("pnp.config._load_git_overrides",
                       return_value={}):
                with patch.dict(os.environ, {"PNP_CHECK_ONLY": "true"}, clear=False):
                    merged = config.apply_layered_config(args, [], parser)
        self.assertIs(merged.check_only, True)

    def test_check_json_can_come_from_env(self) -> None:
        parser = _build_parser()
        args = parser.parse_args([])
        with patch("pnp.config._load_pyproject_overrides",
                   return_value=({}, [], None)):
            with patch("pnp.config._load_git_overrides",
                       return_value={}):
                with patch.dict(os.environ, {"PNP_CHECK_JSON": "true"}, clear=False):
                    merged = config.apply_layered_config(args, [], parser)
        self.assertIs(merged.check_json, True)

    def test_strict_can_come_from_env(self) -> None:
        parser = _build_parser()
        args = parser.parse_args([])
        with patch("pnp.config._load_pyproject_overrides",
                   return_value=({}, [], None)):
            with patch("pnp.config._load_git_overrides",
                       return_value={}):
                with patch.dict(os.environ, {"PNP_STRICT": "true"}, clear=False):
                    merged = config.apply_layered_config(args, [], parser)
        self.assertIs(merged.strict, True)

    def test_project_type_can_come_from_pyproject(self) -> None:
        parser = _build_parser()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "pyproject.toml").write_text(
                "[tool.pnp]\nproject-type = 'node'\n",
                encoding="utf-8",
            )
            args = parser.parse_args([str(root)])
            with patch("pnp.config._load_git_overrides", return_value={}):
                with patch.dict(os.environ, {}, clear=True):
                    merged = config.apply_layered_config(args, [str(root)], parser)
        self.assertEqual(merged.project_type, "node")
        self.assertEqual(merged._pnp_config_sources["project_type"], "pyproject")

    def test_adapter_subtable_is_loaded_from_pyproject(self) -> None:
        parser = _build_parser()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "pyproject.toml").write_text(
                (
                    "[tool.pnp]\nproject-type = 'node'\n\n"
                    "[tool.pnp.node]\nregistry = 'https://registry.npmjs.org'\n"
                    "build_script = 'build'\n"
                ),
                encoding="utf-8",
            )
            args = parser.parse_args([str(root)])
            with patch("pnp.config._load_git_overrides", return_value={}):
                merged = config.apply_layered_config(args, [str(root)], parser)
        adapter_cfg = merged._pnp_adapter_config
        self.assertIn("node", adapter_cfg)
        self.assertEqual(adapter_cfg["node"]["registry"], "https://registry.npmjs.org")
        self.assertEqual(adapter_cfg["node"]["build-script"], "build")


if __name__ == "__main__":
    unittest.main()
