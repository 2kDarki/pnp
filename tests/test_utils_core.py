"""Unit tests for core pure utility behavior."""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from pnp import utils


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


if __name__ == "__main__":
    unittest.main()
