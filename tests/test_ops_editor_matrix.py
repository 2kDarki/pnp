"""Editor resolution matrix tests for shell/environment combinations."""


from unittest.mock import patch
import unittest

from pnp import ops


class OpsEditorMatrixTests(unittest.TestCase):
    def test_preferred_editor_takes_precedence(self) -> None:
        with patch.dict("pnp.ops.os.environ", {}, clear=True):
            with patch("pnp.ops.git_core_editor", return_value="vim"):
                with patch("pnp.ops.shutil.which", side_effect=lambda b: f"/usr/bin/{b}"):
                    cmd = ops.resolve_editor_command("code --wait", repo=".")
        self.assertEqual(cmd, ["code", "--wait"])

    def test_fallback_order_uses_pnp_editor_before_git_editor(self) -> None:
        env = {
            "PNP_EDITOR": "nano",
            "GIT_EDITOR": "vim",
            "VISUAL": "emacs",
            "EDITOR": "vi",
        }
        with patch.dict("pnp.ops.os.environ", env, clear=True):
            with patch("pnp.ops.git_core_editor", return_value="code --wait"):
                with patch("pnp.ops.shutil.which", return_value="/usr/bin/nano"):
                    cmd = ops.resolve_editor_command(None, repo=".")
        self.assertEqual(cmd, ["nano"])

    def test_git_core_editor_used_when_env_missing(self) -> None:
        with patch.dict("pnp.ops.os.environ", {}, clear=True):
            with patch("pnp.ops.git_core_editor", return_value="code --wait"):
                with patch("pnp.ops.shutil.which", side_effect=lambda b: "/usr/bin/code" if b == "code" else None):
                    cmd = ops.resolve_editor_command(None, repo=".")
        self.assertEqual(cmd, ["code", "--wait"])

    def test_visual_then_editor_fallback_when_git_config_missing(self) -> None:
        env = {"VISUAL": "hx", "EDITOR": "vi"}
        with patch.dict("pnp.ops.os.environ", env, clear=True):
            with patch("pnp.ops.git_core_editor", return_value=None):
                with patch("pnp.ops.shutil.which", side_effect=lambda b: "/usr/bin/hx" if b == "hx" else None):
                    cmd = ops.resolve_editor_command(None, repo=".")
        self.assertEqual(cmd, ["hx"])

    def test_posix_default_falls_back_to_nano(self) -> None:
        with patch.dict("pnp.ops.os.environ", {}, clear=True):
            with patch("pnp.ops.git_core_editor", return_value=None):
                with patch("pnp.ops.os.name", "posix"):
                    with patch(
                        "pnp.ops.shutil.which",
                        side_effect=lambda b: "/usr/bin/nano" if b == "nano" else None,
                    ):
                        cmd = ops.resolve_editor_command(None, repo=".")
        self.assertEqual(cmd, ["nano"])

    def test_windows_default_falls_back_to_notepad(self) -> None:
        with patch.dict("pnp.ops.os.environ", {}, clear=True):
            with patch("pnp.ops.git_core_editor", return_value=None):
                with patch("pnp.ops.os.name", "nt"):
                    with patch(
                        "pnp.ops.shutil.which",
                        side_effect=lambda b: r"C:\\Windows\\System32\\notepad.exe" if b == "notepad" else None,
                    ):
                        cmd = ops.resolve_editor_command(None, repo=".")
        self.assertEqual(cmd, ["notepad"])

    def test_raises_when_no_editor_available(self) -> None:
        with patch.dict("pnp.ops.os.environ", {}, clear=True):
            with patch("pnp.ops.git_core_editor", return_value=None):
                with patch("pnp.ops.shutil.which", return_value=None):
                    with self.assertRaises(RuntimeError):
                        ops.resolve_editor_command(None, repo=".")


if __name__ == "__main__":
    unittest.main()
