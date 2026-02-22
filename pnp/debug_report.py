"""Build sanitized debug support bundles for postmortems."""


from datetime import datetime, timezone
from argparse import Namespace
from collections import deque
from pathlib import Path
from typing import Any
import subprocess
import platform
import json
import sys
import os

from . import __version__
from . import telemetry


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _tail_lines(path: Path, max_lines: int = 200) -> list[str]:
    try:
        with path.open("r", encoding="utf-8") as f:
            return list(deque((line.rstrip("\n") for line in f), maxlen=max_lines))
    except Exception:
        return []


def _tail_jsonl(path: Path, max_rows: int = 400) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in _tail_lines(path, max_lines=max_rows):
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if isinstance(obj, dict):
            rows.append(obj)
    return rows


def _safe_git(path: str, args: list[str]) -> str:
    try:
        cp = subprocess.run(
            ["git"] + args,
            cwd=path,
            check=False,
            capture_output=True,
            text=True,
            timeout=4,
        )
    except Exception:
        return ""
    out = (cp.stdout or cp.stderr or "").strip()
    return out[:5000]


def _git_snapshot(target: str) -> dict[str, Any]:
    inside = _safe_git(target, ["rev-parse", "--is-inside-work-tree"]).lower()
    is_repo = inside == "true"
    if not is_repo:
        return {"is_repo": False}
    return {
        "is_repo": True,
        "top_level": _safe_git(target, ["rev-parse", "--show-toplevel"]),
        "branch": _safe_git(target, ["rev-parse", "--abbrev-ref", "HEAD"]),
        "head": _safe_git(target, ["rev-parse", "HEAD"]),
        "status": _safe_git(target, ["status", "--short", "--branch"]),
        "remote_v": _safe_git(target, ["remote", "-v"]),
        "tags_at_head": _safe_git(target, ["tag", "--points-at", "HEAD"]),
    }


def _env_snapshot() -> dict[str, str]:
    allow = [
        "CI",
        "GITHUB_ACTIONS",
        "GITHUB_REF",
        "GITHUB_SHA",
        "TERM",
        "SHELL",
        "LANG",
        "LC_ALL",
    ]
    return {k: os.environ.get(k, "") for k in allow if os.environ.get(k) is not None}


def _report_path(args: Namespace, target: str, run_id: str) -> Path:
    override = str(getattr(args, "debug_report_file", "") or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return (Path(target) / "pnplog" / f"debug-report-{run_id}.json").resolve()


def build_debug_report(args: Namespace) -> Path:
    """Build and persist a sanitized debug support bundle."""
    target = os.path.abspath(getattr(args, "path", "."))
    if os.path.isfile(target):
        target = os.path.dirname(target)
    run_id = telemetry.run_id()
    log_dir = Path(target) / "pnplog"
    events_file = log_dir / "events.jsonl"
    events = _tail_jsonl(events_file, max_rows=400)
    decisions = [e for e in events if e.get("event_type") == "resolver_decision"]
    retries = [e for e in events if e.get("event_type") == "retry"]
    envelope = _read_json(log_dir / "last_error_envelope.json")
    payload: dict[str, Any] = {
        "report_version": "1",
        "tool": "pnp",
        "tool_version": __version__,
        "generated_at": _now(),
        "run_id": run_id,
        "target_path": target,
        "argv": list(sys.argv[1:]),
        "effective_flags": dict(vars(args)),
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "env": _env_snapshot(),
        },
        "git_snapshot": _git_snapshot(target),
        "failure_envelope": envelope,
        "resolver": {
            "decisions": decisions,
            "retries": retries,
        },
        "events_tail": events[-120:],
        "debug_log_tail": _tail_lines(log_dir / "debug.log", max_lines=200),
    }
    sanitized = telemetry.redact(payload)
    report_path = _report_path(args, target, run_id)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(sanitized, indent=2), encoding="utf-8")
    return report_path
