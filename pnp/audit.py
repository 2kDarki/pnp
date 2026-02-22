"""Health and preflight checks extracted from CLI module."""


import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Callable
from pathlib import Path
import subprocess
import argparse
import tempfile
import time
import json
import sys
import os

try: import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]

from .error_model import build_error_envelope
from . import _constants as const
from .tui import tui_runner
from .ops import run_hook
from . import utils
from . import ops

DOCTOR_SCHEMA = "pnp.doctor.v1"
CHECK_SCHEMA  = "pnp.check.v1"

_JS_TEST_CONFIG_MARKERS = (
    "jest.config.js",
    "jest.config.cjs",
    "jest.config.mjs",
    "vitest.config.js",
    "vitest.config.ts",
    "mocha.opts",
    ".mocharc",
)

_GENERAL_TEST_DIR_NAMES = (
    "tests",
    "test",
    "__tests__",
    "spec",
    "specs",
)

_GENERAL_TEST_FILE_PATTERNS = (
    "test_*.py",
    "*_test.py",
    "*.spec.js",
    "*.test.js",
    "*.spec.ts",
    "*.test.ts",
    "*_test.go",
    "*Test.java",
    "*Tests.java",
    "*_spec.rb",
)


def _build_error_envelope(
    code: str,
    severity: str,
    category: str,
    message: str,
    operation: str,
    step: str,
    context: dict[str, object],
    actionable: bool = True,
    retryable: bool = False,
    user_action_required: bool = True,
    suggested_fix: str | None = None,
    stderr_excerpt: str = "",
    raw_ref: str = "",
) -> dict[str, object]:
    """Construct a stable machine-readable error envelope."""
    envelope = build_error_envelope(
        code=code,
        severity=severity,
        category=category,
        message=message,
        operation=operation,
        step=step,
        context=context,
        actionable=actionable,
        retryable=retryable,
        user_action_required=user_action_required,
        suggested_fix=suggested_fix or "",
        stderr_excerpt=stderr_excerpt,
        raw_ref=raw_ref,
    )
    return envelope.as_dict()


def _doctor_error_envelope(
    path: str,
    checks: list[dict[str, str]],
    failures: int,
    warnings: int,
) -> dict[str, object]:
    """Build envelope for doctor JSON/report output."""
    repo = ""
    first_fail = next((c for c in checks if c["status"] == "fail"), None)
    first_warn = next((c for c in checks if c["status"] == "warn"), None)
    repo_check = next((c for c in checks if c["name"] == "repository"), None)
    if repo_check and repo_check["status"] == "ok":
        repo = repo_check["details"]

    context = {
        "path": os.path.abspath(path),
        "repo": repo,
        "ci_mode": bool(const.CI_MODE),
        "dry_run": bool(const.DRY_RUN),
    }
    if failures > 0:
        assert first_fail is not None
        msg = f"doctor reported {failures} critical issue(s)"
        return _build_error_envelope(
            code="PNP_DOCTOR_CRITICAL",
            severity="error",
            category="preflight",
            message=msg,
            operation="doctor",
            step=first_fail["name"],
            stderr_excerpt=first_fail["details"],
            suggested_fix="Resolve failing doctor checks and rerun --doctor.",
            context=context,
        )
    if warnings > 0:
        assert first_warn is not None
        msg = f"doctor reported {warnings} warning(s)"
        return _build_error_envelope(
            code="PNP_DOCTOR_WARNINGS",
            severity="warn",
            category="preflight",
            message=msg,
            operation="doctor",
            step=first_warn["name"],
            stderr_excerpt=first_warn["details"],
            suggested_fix="Review warning checks and resolve if required.",
            context=context,
        )
    return _build_error_envelope(
        code="PNP_DOCTOR_HEALTHY",
        severity="info",
        category="preflight",
        message="doctor reported a healthy environment",
        operation="doctor",
        step="summary",
        actionable=False,
        retryable=False,
        user_action_required=False,
        suggested_fix="No action required.",
        context=context,
    )


def _check_error_envelope(
    args: argparse.Namespace,
    findings: list[dict[str, str]],
    blockers: int,
    warnings_only: int,
    exit_code: int,
    repo: str | None,
) -> dict[str, object]:
    """Build envelope for check-only JSON output."""
    first_blocker = next((f for f in findings if f["level"] == "blocker"), None)
    first_warn = next((f for f in findings if f["level"] == "warn"), None)
    context = {
        "path": os.path.abspath(args.path),
        "repo": repo or "",
        "strict": bool(args.strict),
        "ci_mode": bool(const.CI_MODE),
        "dry_run": bool(const.DRY_RUN),
    }
    if exit_code == 20 and first_blocker:
        return _build_error_envelope(
            code="PNP_CHECK_BLOCKERS",
            severity="error",
            category="preflight",
            message=f"check-only found {blockers} blocker(s)",
            operation="check_only",
            step=first_blocker["check"],
            stderr_excerpt=first_blocker["message"],
            suggested_fix="Resolve blockers and rerun --check-only.",
            context=context,
        )
    if exit_code == 10 and first_warn:
        return _build_error_envelope(
            code="PNP_CHECK_WARNINGS",
            severity="warn",
            category="preflight",
            message=f"check-only found {warnings_only} warning(s)",
            operation="check_only",
            step=first_warn["check"],
            stderr_excerpt=first_warn["message"],
            suggested_fix="Review warnings or run with --strict to enforce.",
            context=context,
        )
    return _build_error_envelope(
        code="PNP_CHECK_CLEAN",
        severity="info",
        category="preflight",
        message="check-only found no blockers",
        operation="check_only",
        step="summary",
        actionable=False,
        retryable=False,
        user_action_required=False,
        suggested_fix="No action required.",
        context=context,
    )


def _check_pyproject(path: Path) -> tuple[str, str]:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return "warn", f"invalid pyproject.toml: {e}"

    project = data.get("project", {})
    if isinstance(project, dict):
        name = project.get("name")
        version = project.get("version")
        if name and version:
            return "ok", f"pyproject project metadata: {name} {version}"
        if name:
            return "ok", f"pyproject project metadata: {name}"
    return "ok", "pyproject.toml detected"


def _check_package_json(path: Path) -> tuple[str, str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return "warn", f"invalid package.json: {e}"

    if not isinstance(data, dict):
        return "warn", "invalid package.json: expected JSON object"

    name = data.get("name")
    version = data.get("version")
    if isinstance(name, str) and name.strip():
        if isinstance(version, str) and version.strip():
            return "ok", f"package.json metadata: {name} {version}"
        return "ok", f"package.json metadata: {name}"
    return "warn", "package.json missing required key: name"


def _check_go_mod(path: Path) -> tuple[str, str]:
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as e:
        return "warn", f"unable to read go.mod: {e}"

    for line in text.splitlines():
        raw = line.strip()
        if not raw or raw.startswith("//"):
            continue
        if raw.startswith("module "):
            module = raw.removeprefix("module ").strip()
            if module:
                return "ok", f"go module: {module}"
            return "warn", "go.mod has empty module directive"
        break
    return "warn", "go.mod missing module directive"


def _check_cargo_toml(path: Path) -> tuple[str, str]:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return "warn", f"invalid Cargo.toml: {e}"

    package = data.get("package")
    workspace = data.get("workspace")
    if isinstance(package, dict):
        name = package.get("name")
        version = package.get("version")
        if name and version:
            return "ok", f"cargo package metadata: {name} {version}"
        if name:
            return "ok", f"cargo package metadata: {name}"
        return "warn", "Cargo.toml [package] missing key: name"

    if isinstance(workspace, dict):
        return "ok", "cargo workspace manifest detected"
    return "ok", "Cargo.toml detected"


def _check_pom_xml(path: Path) -> tuple[str, str]:
    try:
        root = ET.fromstring(path.read_text(encoding="utf-8"))
    except Exception as e:
        return "warn", f"invalid pom.xml: {e}"

    def text(tag: str) -> str:
        namespaces = (
            f".//{{http://maven.apache.org/POM/4.0.0}}{tag}",
            f".//{tag}",
        )
        for query in namespaces:
            node = root.find(query)
            if node is not None and node.text and node.text.strip():
                return node.text.strip()
        return ""

    artifact = text("artifactId")
    version = text("version")
    if not artifact:
        return "warn", "pom.xml missing required key: artifactId"
    if version:
        return "ok", f"maven metadata: {artifact} {version}"
    return "ok", f"maven metadata: {artifact}"


def _check_composer_json(path: Path) -> tuple[str, str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return "warn", f"invalid composer.json: {e}"

    if not isinstance(data, dict):
        return "warn", "invalid composer.json: expected JSON object"
    name = data.get("name")
    if isinstance(name, str) and name.strip():
        return "ok", f"composer metadata: {name}"
    return "ok", "composer.json detected"


def _check_project_toml(path: Path) -> tuple[str, str]:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return "warn", f"invalid Project.toml: {e}"

    name = data.get("name")
    version = data.get("version")
    if isinstance(name, str) and name.strip():
        if isinstance(version, str) and version.strip():
            return "ok", f"Project.toml metadata: {name} {version}"
        return "ok", f"Project.toml metadata: {name}"
    return "ok", "Project.toml detected"


_METADATA_CHECKERS: dict[str, Callable[[Path], tuple[str, str]]] = {
    "pyproject.toml": _check_pyproject,
    "package.json": _check_package_json,
    "go.mod": _check_go_mod,
    "Cargo.toml": _check_cargo_toml,
    "pom.xml": _check_pom_xml,
    "composer.json": _check_composer_json,
    "Project.toml": _check_project_toml,
}


def _metadata_check(pkg_root: str) -> tuple[str, str]:
    """Return (status, details) for project metadata detection."""
    root = Path(pkg_root)
    markers = [
        marker
        for marker in utils.PROJECT_MARKERS
        if (root / marker).exists()
    ]
    if not markers:
        return "warn", "no known project manifest detected"

    warnings: list[str] = []
    details: list[str] = []

    for marker in markers:
        checker = _METADATA_CHECKERS.get(marker)
        if checker is None:
            details.append(f"{marker} detected")
            continue
        status, detail = checker(root / marker)
        if status == "warn":
            warnings.append(detail)
        else:
            details.append(detail)

    if warnings:
        return "warn", "; ".join(warnings)
    return "ok", "; ".join(details)


def _has_test_footprint(pkg_root: str) -> bool:
    """Detect test footprint using cross-language conventions."""
    root = Path(pkg_root)
    if any((root / d).is_dir() for d in _GENERAL_TEST_DIR_NAMES):
        return True

    if any((root / name).exists() for name in _JS_TEST_CONFIG_MARKERS):
        return True

    for pattern in _GENERAL_TEST_FILE_PATTERNS:
        if list(root.rglob(pattern)):
            return True
    return False


def _find_repo_noninteractive(path: str) -> str | None:
    """Find a git repo near path without prompting."""
    cur = os.path.abspath(path)
    while True:
        if os.path.isdir(os.path.join(cur, ".git")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur: break
        cur = parent

    base = os.path.abspath(path)
    if not os.path.isdir(base): return None
    for child in os.listdir(base):
        cand = os.path.join(base, child)
        if os.path.isdir(os.path.join(cand, ".git")):
            return cand
    return None


def run_doctor(path: str, out: utils.Output,
               json_mode: bool = False,
               report_file: str | None = None,
               repo_finder: Callable[[str], str | None] |
                            None = None) -> int:
    """Run local environment audit checks."""
    if repo_finder is None:
        repo_finder = _find_repo_noninteractive
    original_quiet = out.quiet
    if json_mode: out.quiet = True
    failures = 0
    warnings = 0
    checks: list[dict[str, str]] = []
    step_delay = 0.25
    labels     = [
        "Python runtime",
        "Git availability",
        "Git identity",
        "Repository detection",
        "Working tree hygiene",
        "Branch tracking",
        "Git remotes",
        "Repository integrity",
        "Project metadata",
        "Test footprint",
        "GitHub token",
    ]
    use_ui = bool(const.CI_MODE and not const.PLAIN
         and sys.stdout.isatty())

    def pause_step() -> None:
        if use_ui: time.sleep(step_delay)

    def add_check(name: str, status: str, details: str) -> None:
        checks.append({
            "name": name,
            "status": status,
            "details": details
        })

    def git_run(repo: str, args: list[str]
               ) -> subprocess.CompletedProcess[str]:
        return ops.run_git(repo, args)

    with tui_runner(labels, enabled=use_ui) as ui:
        if use_ui: utils.bind_console(ui)

        ui.start(0)
        py_ver    = sys.version.split()[0]
        py_ok     = sys.version_info >= (3, 10)
        py_detail = f"{py_ver} (>=3.10 required)"
        if py_ok:
            add_check("python", "ok", py_detail)
            out.success(f"Python: {py_detail}", step_idx=0)
            out.info(f"Executable: {sys.executable}",
                step_idx=0)
            pause_step()
            ui.finish(0, utils.StepResult.OK)
        else:
            failures += 1
            add_check("python", "fail", py_detail)
            out.warn(f"Python: {py_detail}", step_idx=0)
            pause_step()
            ui.finish(0, utils.StepResult.FAIL)

        ui.start(1)
        git_bin = "git" if ops.command_exists("git") \
             else None
        git_ok  = False
        if not git_bin:
            failures += 1
            add_check("git", "fail", "not found in PATH")
            out.warn("Git: not found in PATH", step_idx=1)
            pause_step()
            ui.finish(1, utils.StepResult.FAIL)
        else:
            cp     = ops.run_command([git_bin, "--version"])
            git_ok = cp.returncode == 0
            if git_ok:
                detail = cp.stdout.strip()
                add_check("git", "ok", detail)
                out.success(detail, step_idx=1)
                pause_step()
                ui.finish(1, utils.StepResult.OK)
            else:
                failures += 1
                add_check("git", "fail",
                    "detected but unusable")
                out.warn("Git: detected but unusable",
                    step_idx=1)
                pause_step()
                ui.finish(1, utils.StepResult.FAIL)

        ui.start(2)
        if git_ok:
            user = ops.run_command(
                ["git", "config", "--global", "user.name"],
            ).stdout.strip()
            email = ops.run_command(
                ["git", "config", "--global", "user.email"],
            ).stdout.strip()
            missing: list[str] = []
            if not user: missing.append("user.name")
            if not email: missing.append("user.email")
            if missing:
                warnings += 1
                detail = ", ".join(missing)
                add_check("git_identity", "warn", detail)
                out.warn("Missing global Git identity: "
                   + detail, step_idx=2)
                pause_step()
                ui.finish(2, utils.StepResult.ABORT)
            else:
                add_check("git_identity", "ok", "configured")
                out.success("Global Git identity configured",
                    step_idx=2)
                pause_step()
                ui.finish(2, utils.StepResult.OK)
        else:
            warnings += 1
            add_check("git_identity", "warn",
                "skipped (Git unavailable)")
            out.warn("Skipped (Git unavailable)", step_idx=2)
            pause_step()
            ui.finish(2, utils.StepResult.ABORT)

        ui.start(3)
        repo = repo_finder(path) if git_ok else None
        if repo:
            add_check("repository", "ok", repo)
            out.success(f"Detected at {utils.pathit(repo)}",
                step_idx=3)
            pause_step()
            ui.finish(3, utils.StepResult.OK)
        else:
            warnings += 1
            add_check("repository", "warn",
                "not found near target path")
            out.warn(
                "No repository detected near target path",
                step_idx=3
            )
            pause_step()
            ui.finish(3, utils.StepResult.ABORT)

        ui.start(4)
        if repo:
            cp = git_run(repo, ["status", "--porcelain"])
            if cp.returncode == 0:
                dirty = [line for line in cp.stdout
                        .splitlines() if line.strip()]
                if dirty:
                    warnings += 1
                    add_check("working_tree", "warn",
                        f"{len(dirty)} pending change(s)")
                    out.warn("Working tree has "
                        f"{len(dirty)} pending change(s)",
                        step_idx=4)
                    preview = ", ".join(line[3:] for line in
                              dirty[:4])
                    if preview:
                        out.info(f"Sample: {preview}",
                            step_idx=4)
                    pause_step()
                    ui.finish(4, utils.StepResult.ABORT)
                else:
                    add_check("working_tree", "ok", "clean")
                    out.success("Working tree is clean",
                        step_idx=4)
                    pause_step()
                    ui.finish(4, utils.StepResult.OK)
            else:
                warnings += 1
                add_check("working_tree", "warn",
                    "unable to inspect")
                out.warn("Unable to inspect working tree",
                    step_idx=4)
                pause_step()
                ui.finish(4, utils.StepResult.ABORT)
        else:
            warnings += 1
            add_check("working_tree", "warn",
                "skipped (no repository)")
            out.warn("Skipped (no repository)", step_idx=4)
            pause_step()
            ui.finish(4, utils.StepResult.ABORT)

        ui.start(5)
        if repo:
            branch_cp = git_run(repo, ["rev-parse",
                        "--abbrev-ref", "HEAD"])
            branch = branch_cp.stdout.strip() \
                  if branch_cp.returncode == 0 else ""
            if not branch or branch == "HEAD":
                warnings += 1
                add_check("branch_tracking", "warn",
                    "detached HEAD")
                out.warn("Detached HEAD; branch tracking "
                    "unavailable", step_idx=5)
                pause_step()
                ui.finish(5, utils.StepResult.ABORT)
            else:
                upstream_cp = git_run(
                    repo, ["rev-parse", "--abbrev-ref",
                    "--symbolic-full-name", "@{u}"]
                )
                if upstream_cp.returncode != 0:
                    warnings += 1
                    detail = f"branch '{branch}' has no " \
                           + "upstream"
                    add_check("branch_tracking", "warn",
                        detail)
                    out.warn(f"Branch '{branch}' has no "
                        "upstream", step_idx=5)
                    pause_step()
                    ui.finish(5, utils.StepResult.ABORT)
                else:
                    upstream = upstream_cp.stdout.strip()
                    delta_cp = git_run(repo, ["rev-list",
                               "--left-right", "--count",
                               f"{upstream}...HEAD"])
                    if delta_cp.returncode == 0:
                        parts = delta_cp.stdout.strip().split()
                        behind = int(parts[0]) if parts else 0
                        ahead = int(parts[1]) if len(parts) > 1 else 0
                        if behind > 0:
                            warnings += 1
                            add_check("branch_tracking", "warn",
                                f"behind {upstream} by {behind} (ahead {ahead})")
                            out.warn(f"Branch '{branch}' is behind {upstream} by {behind}", step_idx=5)
                            if ahead > 0:
                                out.info(f"And ahead by {ahead}", step_idx=5)
                            pause_step()
                            ui.finish(5, utils.StepResult.ABORT)
                        else:
                            add_check("branch_tracking", "ok",
                                f"tracks {upstream} (ahead {ahead}, behind {behind})")
                            out.success(
                                f"Branch '{branch}' tracks {upstream} (ahead {ahead}, behind {behind})",
                                step_idx=5,
                            )
                            pause_step()
                            ui.finish(5, utils.StepResult.OK)
                    else:
                        warnings += 1
                        add_check("branch_tracking", "warn", "unable to compute ahead/behind status")
                        out.warn("Unable to compute ahead/behind status", step_idx=5)
                        pause_step()
                        ui.finish(5, utils.StepResult.ABORT)
        else:
            warnings += 1
            add_check("branch_tracking", "warn", "skipped "
                "(no repository)")
            out.warn("Skipped (no repository)", step_idx=5)
            pause_step()
            ui.finish(5, utils.StepResult.ABORT)

        ui.start(6)
        if repo:
            cp = git_run(repo, ["remote", "-v"])
            raw = [line for line in cp.stdout.splitlines() if line.strip()]
            remotes = sorted({line.split()[0] for line in raw})
            if cp.returncode == 0 and remotes:
                detail = ", ".join(remotes)
                add_check("remotes", "ok", detail)
                out.success(detail, step_idx=6)
                pause_step()
                ui.finish(6, utils.StepResult.OK)
            elif cp.returncode == 0:
                warnings += 1
                add_check("remotes", "warn",
                    "none configured")
                out.warn("No remotes configured", step_idx=6)
                pause_step()
                ui.finish(6, utils.StepResult.ABORT)
            else:
                warnings += 1
                add_check("remotes", "warn", "unable to read")
                out.warn("Unable to read remotes", step_idx=6)
                pause_step()
                ui.finish(6, utils.StepResult.ABORT)
        else:
            warnings += 1
            add_check("remotes", "warn", "skipped (no repository)")
            out.warn("Skipped (no repository)", step_idx=6)
            pause_step()
            ui.finish(6, utils.StepResult.ABORT)

        ui.start(7)
        if repo:
            cp = git_run(repo, ["fsck", "--no-progress",
                 "--no-dangling"])
            if cp.returncode == 0:
                add_check("repository_integrity", "ok",
                    "git fsck passed")
                out.success("Git object database integrity "
                    "looks good", step_idx=7)
                pause_step()
                ui.finish(7, utils.StepResult.OK)
            else:
                failures += 1
                detail = cp.stderr.strip() or cp.stdout.strip() or "git fsck failed"
                add_check("repository_integrity", "fail",
                    detail)
                out.warn(detail, step_idx=7)
                pause_step()
                ui.finish(7, utils.StepResult.FAIL)
        else:
            warnings += 1
            add_check("repository_integrity", "warn",
                "skipped (no repository)")
            out.warn("Skipped (no repository)", step_idx=7)
            pause_step()
            ui.finish(7, utils.StepResult.ABORT)

        ui.start(8)
        pkg_root: str | None = repo
        if repo:
            detected = utils.detect_subpackage(path, repo)
            pkg_root = detected or repo
            status, detail = _metadata_check(pkg_root)
            add_check("project_metadata", status, detail)
            if status == "warn":
                warnings += 1
                out.warn(detail, step_idx=8)
                pause_step()
                ui.finish(8, utils.StepResult.ABORT)
            else:
                out.success(f"Metadata OK ({detail})", step_idx=8)
                pause_step()
                ui.finish(8, utils.StepResult.OK)
        else:
            warnings += 1
            add_check("project_metadata", "warn",
                "skipped (no repository)")
            out.warn("Skipped (no repository)", step_idx=8)
            pause_step()
            ui.finish(8, utils.StepResult.ABORT)

        ui.start(9)
        if pkg_root:
            has_tests = _has_test_footprint(pkg_root)
            if has_tests:
                add_check("test_footprint", "ok", "tests detected")
                out.success("Test footprint detected", step_idx=9)
                pause_step()
                ui.finish(9, utils.StepResult.OK)
            else:
                warnings += 1
                add_check("test_footprint", "warn",
                    "no tests found")
                out.warn("No conventional test footprint found", step_idx=9)
                pause_step()
                ui.finish(9, utils.StepResult.ABORT)
        else:
            warnings += 1
            add_check("test_footprint", "warn", "skipped (no project root)")
            out.warn("Skipped (no project root)", step_idx=9)
            pause_step()
            ui.finish(9, utils.StepResult.ABORT)

        ui.start(10)
        token = os.environ.get("GITHUB_TOKEN")
        if token:
            add_check("github_token", "ok", "set")
            out.success("Set (GITHUB_TOKEN)", step_idx=10)
            pause_step()
            ui.finish(10, utils.StepResult.OK)
        else:
            warnings += 1
            add_check("github_token", "warn", "missing")
            out.warn("Missing (set GITHUB_TOKEN for releases)", step_idx=10)
            pause_step()
            ui.finish(10, utils.StepResult.ABORT)

    report = {
        "schema": DOCTOR_SCHEMA,
        "schema_version": 1,
        "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "path": os.path.abspath(path),
        "summary": {
            "critical": failures,
            "warnings": warnings,
            "healthy": failures == 0 and warnings == 0,
        },
        "checks": checks,
        "error_envelope": _doctor_error_envelope(path, checks, failures, warnings),
    }
    if report_file:
        try:
            rpath = Path(report_file)
            rpath.parent.mkdir(parents=True, exist_ok=True)
            rpath.write_text(json.dumps(report, indent=2), encoding="utf-8")
            out.success(f"doctor report written: {utils.pathit(str(rpath))}")
        except Exception as e:
            out.warn(f"failed to write doctor report: {e}")
    if json_mode:
        out.quiet = original_quiet
        out.raw(json.dumps(report, indent=2))
    else: out.quiet = original_quiet

    if failures:
        out.warn("doctor summary: " + f"{failures} critical issue(s), {warnings} warning(s)")
        return 1
    if warnings:
        utils.transmit(
            utils.wrap("doctor summary: " + f"0 critical issue(s), {warnings} warning(s)"),
            fg=const.PROMPT,
            quiet=out.quiet,
        )
        return 0
    out.success("doctor summary: environment is healthy")
    return 0


def run_check_only(args: argparse.Namespace,
                   out: utils.Output,
                   doctor_fn: Callable[..., int] | None = None,
                   repo_finder: Callable[[str], str | None] | None = None) -> int:
    """Run non-mutating workflow preflight checks."""
    if doctor_fn is None: doctor_fn = run_doctor
    if repo_finder is None:
        repo_finder = _find_repo_noninteractive

    blockers = 0
    warnings_only = 0
    findings: list[dict[str, str]] = []
    emit = out if not args.check_json else utils.Output(quiet=True)

    def note(level: str, check: str, message: str) -> None:
        findings.append({"level": level, "check": check, "message": message})
        if level == "blocker": emit.warn(message)
        elif level == "warn": emit.warn(message)
        else: emit.success(message)

    emit.info("running check-only preflight")
    report_path: str | None = None
    with tempfile.NamedTemporaryFile(
        prefix="pnp_doctor_",
        suffix=".json",
        delete=False,
    ) as tf:
        report_path = tf.name
    doctor_code = doctor_fn(args.path, emit, report_file=report_path)
    if doctor_code != 0:
        blockers += 1
        note("blocker", "doctor", "check-only: doctor reported critical issue(s)")
    if report_path:
        try:
            parsed = json.loads(Path(report_path).read_text(encoding="utf-8"))
            warn_count = int(parsed.get("summary", {}).get("warnings", 0))
            warnings_only += warn_count
            if args.strict and warn_count > 0:
                blockers += warn_count
                note("blocker", "doctor",
                     f"check-only strict: doctor reported {warn_count} warning(s)")
            elif warn_count > 0:
                note("warn", "doctor",
                     f"check-only: doctor reported {warn_count} warning(s)")
        except Exception as e:
            blockers += 1
            note("blocker", "doctor_report_parse",
                 f"check-only: failed to parse doctor report: {e}")
        finally:
            try: os.remove(report_path)
            except OSError: pass

    repo = repo_finder(args.path)
    if not repo:
        note("blocker", "repository",
             "check-only: no repository detected near target path")
        blockers += 1
    else:
        note("ok", "repository",
             f"check-only: repo detected at {utils.pathit(repo)}")

    if args.hooks:
        hooks = [h.strip() for h in args.hooks.split(";") if h.strip()]
        for cmd in hooks:
            try:
                run_hook(cmd, repo or ".", dryrun=True,
                         no_transmission=args.no_transmission)
            except (RuntimeError, ValueError) as e:
                note("blocker", "hooks",
                     f"check-only: invalid hook {cmd!r}: {e}")
                blockers += 1

    if args.push or args.publish:
        if repo:
            cp = ops.run_git(repo, ["remote"])
            remotes = [r for r in cp.stdout.splitlines() if r.strip()]
            if cp.returncode != 0 or not remotes:
                note("blocker", "remotes", "check-only: no git remotes configured")
                blockers += 1
            else:
                note("ok", "remotes", "check-only: remotes configured")

    if args.push and repo:
        cp = ops.run_git(repo, ["rev-parse", "--abbrev-ref", "HEAD"])
        branch = cp.stdout.strip() if cp.returncode == 0 else ""
        if not branch or branch == "HEAD":
            note("blocker", "branch", "check-only: detached HEAD or no active branch")
            blockers += 1
        else:
            note("ok", "branch", f"check-only: active branch '{branch}'")

    if args.gh_release:
        token = args.gh_token or os.environ.get("GITHUB_TOKEN")
        if not args.gh_repo:
            note("blocker", "gh_release", "check-only: --gh-repo is required for --gh-release")
            blockers += 1
        if not token:
            note("blocker", "gh_release", "check-only: GitHub token required for --gh-release")
            blockers += 1

    if any((args.machete_status, args.machete_sync, args.machete_traverse)):
        if not ops.command_exists("git-machete"):
            note("blocker", "machete", "check-only: git-machete not found in PATH")
            blockers += 1
        elif repo:
            cp = ops.run_command(["git", "machete", "status"], cwd=repo)
            if cp.returncode != 0:
                detail = cp.stderr.strip() or cp.stdout.strip() or "git machete status failed"
                note("blocker", "machete", f"check-only: {detail}")
                blockers += 1
            else:
                note("ok", "machete", "check-only: git machete status passed")

    code = 0
    if blockers:
        code = 20
        emit.warn(f"check-only summary: {blockers} blocker(s) found")
    elif warnings_only > 0:
        code = 10
        emit.warn(f"check-only summary: {warnings_only} warning(s), 0 blocker(s)")
    else:
        emit.success("check-only summary: no blockers found")

    if args.check_json:
        envelope = _check_error_envelope(
            args=args,
            findings=findings,
            blockers=blockers,
            warnings_only=warnings_only,
            exit_code=code,
            repo=repo,
        )
        payload = {
            "schema": CHECK_SCHEMA,
            "schema_version": 1,
            "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "path": os.path.abspath(args.path),
            "strict": bool(args.strict),
            "summary": {
                "exit_code": code,
                "blockers": blockers,
                "warnings": warnings_only,
            },
            "findings": findings,
            "error_envelope": envelope,
        }
        out.raw(json.dumps(payload, indent=2))
    return code
