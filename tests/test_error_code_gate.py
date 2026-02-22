"""Tests for error-code contract compatibility gate."""


import unittest

from tools import error_code_gate


class ErrorCodeGateTests(unittest.TestCase):
    def test_current_contract_matches_lock(self) -> None:
        lock = error_code_gate.json.loads(
            error_code_gate.LOCK_FILE.read_text(encoding="utf-8")
        )
        curr = error_code_gate.current_contract()
        issues, _ = error_code_gate.compare_contracts(lock, curr)
        self.assertEqual(issues, [])

    def test_detects_removed_stable_code_as_breaking(self) -> None:
        lock = {
            "workflow_step_codes": {"push": "PNP_NET_PUSH_FAIL"},
            "deprecated_aliases": {},
            "error_code_policy": {"PNP_NET_PUSH_FAIL": {"severity": "error", "category": "network"}},
        }
        curr = {
            "workflow_step_codes": {"push": "PNP_NET_PUSH_FAIL"},
            "deprecated_aliases": {},
            "error_code_policy": {},
        }
        issues, notes = error_code_gate.compare_contracts(lock, curr)
        self.assertTrue(any("stable error code removed" in i for i in issues))
        self.assertEqual(notes, [])

    def test_additive_code_is_non_breaking_note(self) -> None:
        lock = {
            "workflow_step_codes": {"push": "PNP_NET_PUSH_FAIL"},
            "deprecated_aliases": {},
            "error_code_policy": {"PNP_NET_PUSH_FAIL": {"severity": "error", "category": "network"}},
        }
        curr = {
            "workflow_step_codes": {"push": "PNP_NET_PUSH_FAIL"},
            "deprecated_aliases": {},
            "error_code_policy": {
                "PNP_NET_PUSH_FAIL": {"severity": "error", "category": "network"},
                "PNP_NEW_CODE": {"severity": "warn", "category": "internal"},
            },
        }
        issues, notes = error_code_gate.compare_contracts(lock, curr)
        self.assertEqual(issues, [])
        self.assertTrue(any("new stable error code added" in n for n in notes))


if __name__ == "__main__":
    unittest.main()
