"""Structured JSONL telemetry with run correlation and redaction."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import os
import re


_RUN_ID: str | None = None
_EVENTS_FILE: Path | None = None

_AUTH_URL_PATTERN = re.compile(r"(https?://)([^/\s@]+)@")
_TOKEN_KV_PATTERN = re.compile(r"(?i)\b(token|password|secret|passwd)\s*[:=]\s*([^\s,'\"]+)")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _new_run_id() -> str:
    seed = f"{os.getpid()}:{_now()}".encode("utf-8")
    return hashlib.sha1(seed).hexdigest()[:12]


def set_run_id(run_id: str | None = None) -> str:
    """Set and return active telemetry run id."""
    global _RUN_ID
    _RUN_ID = run_id.strip() if isinstance(run_id, str) and run_id.strip() else _new_run_id()
    return _RUN_ID


def run_id() -> str:
    """Get active run id, generating one if missing."""
    global _RUN_ID
    if not _RUN_ID: _RUN_ID = _new_run_id()
    return _RUN_ID


def init_event_stream(log_dir: str | Path) -> Path:
    """Initialize events stream file path under pnplog."""
    global _EVENTS_FILE
    path = Path(log_dir).expanduser().resolve()
    path.mkdir(parents=True, exist_ok=True)
    _EVENTS_FILE = path / "events.jsonl"
    return _EVENTS_FILE


def events_file() -> Path | None:
    """Return active events file path if initialized."""
    return _EVENTS_FILE


def _redact_text(text: str) -> str:
    s = text
    s = _AUTH_URL_PATTERN.sub(r"\1<redacted>@", s)
    s = _TOKEN_KV_PATTERN.sub(r"\1=<redacted>", s)
    return s


def redact(value: object) -> object:
    """Recursively redact secrets from telemetry payloads."""
    if isinstance(value, str): return _redact_text(value)
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, tuple):
        return [redact(v) for v in value]
    if isinstance(value, dict):
        return {str(k): redact(v) for k, v in value.items()}
    return value


def emit_event(event_type: str, step_id: str, payload: dict[str, object]) -> None:
    """Emit one JSONL telemetry event."""
    if _EVENTS_FILE is None: return
    event = {
        "ts": _now(),
        "run_id": run_id(),
        "event_type": event_type,
        "step_id": step_id,
        "payload": redact(payload),
    }
    try:
        _EVENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with _EVENTS_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, separators=(",", ":")) + "\n")
    # telemetry must never break core flow
    except Exception: return
