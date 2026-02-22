"""Unit tests for core pure utility behavior."""


from pathlib import Path
import tempfile
import unittest

from pnp import utils


class _Sink:
    def __init__(self) -> None:
        self.calls: list[tuple[int | None, str, str, bool]] = []

    def add_message(self, idx: int | None, msg: str,
                    fg: str = "yellow", prfx: bool = True) -> None:
        self.calls.append((idx, msg, fg, prfx))


class UtilsCoreTests(unittest.TestCase):
    def test_bump_semver_patch_from_standard_tag(self) -> None:
        self.assertEqual(utils.bump_semver_from_tag("v1.2.3", "patch"), "v1.2.4")

    def test_bump_semver_minor_with_custom_prefix(self) -> None:
        self.assertEqual(utils.bump_semver_from_tag("rel-2.4.9", "minor", "rel-"), "rel-2.5.0")

    def test_bump_semver_bootstrap_on_invalid_input(self) -> None:
        self.assertEqual(utils.bump_semver_from_tag("nonsense", "major"), "v1.0.0")

    def test_bump_semver_preserves_suffix(self) -> None:
        self.assertEqual(utils.bump_semver_from_tag("v1.2.3-beta", "patch"), "v1.2.4-beta")

    def test_retrieve_latest_changelog_returns_last_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "changes.log"
            path.write_text(
                "------| 2026-01-01T10:00:00 |------\none\n"
                "------| 2026-01-02T10:00:00 |------\ntwo\n",
                encoding="utf-8",
            )
            last = utils.retrieve_latest_changelog(path)
            self.assertIn("2026-01-02T10:00:00", last)
            self.assertTrue(last.startswith("------| "))

    def test_output_does_not_prewrap_when_tui_sink_is_active(self) -> None:
        sink = _Sink()
        utils.bind_console(sink)
        try:
            out = utils.Output(quiet=False)
            msg = ("long-message " * 20).strip()
            out.success(msg, step_idx=3)
            self.assertEqual(len(sink.calls), 1)
            idx, captured, fg, prfx = sink.calls[0]
            self.assertEqual(idx, 3)
            self.assertEqual(captured, msg)
            self.assertEqual(fg, "green")
            self.assertTrue(prfx)
        finally:
            utils.bind_console(None)

    def test_detect_subpackage_accepts_non_python_project_marker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pkg = root / "frontend"
            pkg.mkdir(parents=True, exist_ok=True)
            (pkg / "package.json").write_text("{}", encoding="utf-8")
            detected = utils.detect_subpackage(str(pkg), str(root))
            self.assertEqual(detected, str(pkg))

    def test_detect_subpackage_returns_none_without_known_markers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pkg = root / "misc"
            pkg.mkdir(parents=True, exist_ok=True)
            detected = utils.detect_subpackage(str(pkg), str(root))
            self.assertIsNone(detected)


if __name__ == "__main__":
    unittest.main()
