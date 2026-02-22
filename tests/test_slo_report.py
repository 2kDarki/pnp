"""Tests for SLO report metric computation."""


from pathlib import Path
import tempfile
import unittest
import json

from tools.slo_report import compute_slos, main as slo_main


class SloReportTests(unittest.TestCase):
    def test_compute_slos_from_synthetic_events(self) -> None:
        events = [
            {
                "ts": "2026-02-22T01:00:00Z",
                "run_id": "r1",
                "event_type": "resolver_decision",
                "step_id": "git",
                "payload": {"code": "PNP_GIT_UNCLASSIFIED"},
            },
            {
                "ts": "2026-02-22T01:00:01Z",
                "run_id": "r1",
                "event_type": "resolver_decision",
                "step_id": "git",
                "payload": {"code": "PNP_NET_CONNECTIVITY"},
            },
            {
                "ts": "2026-02-22T01:00:02Z",
                "run_id": "r1",
                "event_type": "error_signal",
                "step_id": "push",
                "payload": {"code": "PNP_NET_PUSH_FAIL"},
            },
            {
                "ts": "2026-02-22T01:00:05Z",
                "run_id": "r1",
                "event_type": "actionable_diagnosis",
                "step_id": "push",
                "payload": {"code": "PNP_NET_PUSH_FAIL"},
            },
            {
                "ts": "2026-02-22T01:00:06Z",
                "run_id": "r1",
                "event_type": "remediation",
                "step_id": "git_safe_directory",
                "payload": {"outcome": "success"},
            },
            {
                "ts": "2026-02-22T01:00:07Z",
                "run_id": "r1",
                "event_type": "remediation",
                "step_id": "destructive_reset",
                "payload": {"outcome": "failed"},
            },
            {
                "ts": "2026-02-22T01:00:08Z",
                "run_id": "r1",
                "event_type": "rollback_verification",
                "step_id": "publish",
                "payload": {"verified": True},
            },
            {
                "ts": "2026-02-22T01:00:09Z",
                "run_id": "r1",
                "event_type": "rollback_verification",
                "step_id": "publish",
                "payload": {"verified": False},
            },
        ]
        metrics = compute_slos(events)
        self.assertEqual(metrics["unknown_unclassified_error_rate"]["denominator"], 2)
        self.assertEqual(metrics["unknown_unclassified_error_rate"]["numerator"], 1)
        self.assertAlmostEqual(metrics["unknown_unclassified_error_rate"]["value"], 0.5)
        self.assertEqual(metrics["mean_time_to_actionable_diagnosis_seconds"]["samples"], 1)
        self.assertAlmostEqual(
            metrics["mean_time_to_actionable_diagnosis_seconds"]["value"], 3.0
        )
        self.assertEqual(metrics["successful_auto_remediation_rate"]["denominator"], 2)
        self.assertEqual(metrics["successful_auto_remediation_rate"]["numerator"], 1)
        self.assertAlmostEqual(metrics["successful_auto_remediation_rate"]["value"], 0.5)
        self.assertEqual(metrics["rollback_success_verification_rate"]["denominator"], 2)
        self.assertEqual(metrics["rollback_success_verification_rate"]["numerator"], 1)
        self.assertAlmostEqual(metrics["rollback_success_verification_rate"]["value"], 0.5)

    def test_cli_writes_report_and_respects_fail_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            events_path = Path(tmp) / "events.jsonl"
            report_path = Path(tmp) / "slo.json"
            rows = [
                {
                    "ts": "2026-02-22T01:00:00Z",
                    "run_id": "r1",
                    "event_type": "resolver_decision",
                    "step_id": "git",
                    "payload": {"code": "PNP_GIT_UNCLASSIFIED"},
                }
            ]
            events_path.write_text(
                "\n".join(json.dumps(r) for r in rows) + "\n",
                encoding="utf-8",
            )
            argv = [
                "slo_report.py",
                "--events-file",
                str(events_path),
                "--report-file",
                str(report_path),
                "--max-unknown-rate",
                "0.0",
                "--fail-on-thresholds",
            ]
            with unittest.mock.patch("sys.argv", argv):
                code = slo_main()
            self.assertEqual(code, 1)
            self.assertTrue(report_path.exists())


if __name__ == "__main__":
    unittest.main()
