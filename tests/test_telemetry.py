"""Telemetry redaction and event-shape tests."""


from pathlib import Path
import tempfile
import unittest
import json

from pnp import telemetry


class TelemetryTests(unittest.TestCase):
    def test_emit_event_includes_run_and_step(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            telemetry.set_run_id("testrun01")
            path = telemetry.init_event_stream(Path(tmp))
            telemetry.emit_event(
                event_type="runtime_error",
                step_id="publish",
                payload={"message": "failed"},
            )
            rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(rows), 1)
            row = rows[0]
            self.assertEqual(row["run_id"], "testrun01")
            self.assertEqual(row["event_type"], "runtime_error")
            self.assertEqual(row["step_id"], "publish")
            self.assertIn("payload", row)

    def test_redaction_masks_auth_url_and_token_fields(self) -> None:
        payload = {
            "url": "https://ghp_1234@github.com/u/r.git",
            "token": "token=ghp_5678",
            "nested": {"password": "password: secret123"},
        }
        redacted = telemetry.redact(payload)
        text = json.dumps(redacted)
        self.assertNotIn("ghp_1234", text)
        self.assertNotIn("ghp_5678", text)
        self.assertNotIn("secret123", text)
        self.assertIn("<redacted>", text)


if __name__ == "__main__":
    unittest.main()
