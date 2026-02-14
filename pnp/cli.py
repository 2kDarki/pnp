#!/usr/bin/env python3
"""
Primary CLI entry point for the `pnp` automation tool.

This module orchestrates the end-to-end workflow for
preparing and publishing a Python package or monorepo
component.

It handles:
  - Parsing command-line arguments
  - Detecting and initializing Git repositories
  - Running pre-push hooks (e.g., linting, tests)
  - Generating changelogs from Git history
  - Staging and committing changes
  - Tagging with semantic versioning
  - Optionally publishing GitHub releases with assets

Supports dry-run, interactive, auto-fix, and quiet modes for
safety and flexibility. All output is routed through a
utility transmission system for styling and formatting
consistency.

Uses `main` as the safe entry point to invoke the
CLI.
"""
from __future__ import annotations

# ======================= STANDARDS =======================
from datetime import datetime
from typing import Any, cast
from pathlib import Path
import subprocess
import argparse
try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]
import time
import sys
import os
import re
import shutil
import json
import tempfile

# ==================== THIRD-PARTIES ======================
from tuikit.textools import strip_ansi

# ======================== LOCALS =========================
from . import _constants as const
from . import __version__
from .help_menu import wrap, help_msg
from . import config
from .tui import tui_runner
from . import utils

DOCTOR_SCHEMA = "pnp.doctor.v1"
CHECK_SCHEMA = "pnp.check.v1"


def run_hook(cmd: str, cwd: str, dryrun: bool,
             no_transmission: bool = False) -> int:
    """
    Run a validated hook command safely with optional dry-run.

    NB: This function is not to be misunderstood as being
        "safe" against malicious hooks — that"s strictly none
        of my business. So the few guards that are present
        are just me guarding against my own absentmindedness.
    """
    # Reject unsafe shell characters
    if re.search(r"[$&;|><`()]", cmd):
        err = f"rejected potentially unsafe hook: {cmd!r}"
        raise ValueError(err)

    # Decide whether to capture output based on CLI flags and
    # exclusions
    exclude = "drace", "pytest"
    capture = not no_transmission \
          and not utils.any_in(exclude, eq=cmd)

    # Support optional prefix via "type::command" format
    # Parse and validate command
    parts  = cmd.split("::")
    prefix = "run"
    if len(parts) == 2: prefix, cmd = parts
    args = cmd.split()
    if not args:
        raise ValueError("hook command is empty")

    # Blacklist disallowed commands
    disallowed = {
        "rm", "mv", "dd", "shutdown", "reboot", "mkfs",
        "kill", "killall", ">:(", "sudo", "tsu", "chown",
        "chmod", "wget", "curl"
    }
    raw_cmd = os.path.basename(args[0]).lower()
    if raw_cmd in disallowed:
        err = f"hook command '{raw_cmd}' not allowed"
        raise ValueError(err)

    # Add [dry-run] status if in dry-run mode and exit early
    # to simulate success
    add = f" {const.DRYRUN}skips" if dryrun else ""
    m   = utils.wrap(f"[{prefix}] {cmd}{add}")
    utils.transmit(m, fg=const.GOOD)
    if dryrun: return 0

    if "pytest" in cmd: print()

    # Run the shell command
    # NB: DON"T REMOVE `shell=True`!!! HOOKS WILL NOT WORK!!!
    proc   = subprocess.run(cmd, cwd=cwd, shell=True,
             check=False, text=True, capture_output=capture)
    code   = proc.returncode
    stdout = proc.stdout
    stderr = proc.stderr
    if not capture or stderr: print()
    if code != 0:
        err = f"[{code}]: {cmd} {stderr}"
        raise RuntimeError(err)

    if capture:
        for line in stdout.splitlines():
            print(line); time.sleep(0.005)
        print()
    return code


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=help_msg())
    p.add_argument(
        "--version",
        action="version",
        version=f"pnp {__version__}",
    )
    p.add_argument("--doctor", action="store_true")
    p.add_argument("--doctor-json", action="store_true")
    p.add_argument("--doctor-report", default=None)
    p.add_argument("--check-only", action="store_true")
    p.add_argument("--check-json", action="store_true")
    p.add_argument("--strict", action="store_true")
    p.add_argument("--show-config", action="store_true")
    p.add_argument("--install-git-ext", action="store_true")
    p.add_argument("--uninstall-git-ext", action="store_true")
    p.add_argument("--git-ext-dir", default=None)
    p.add_argument("--status", "-s", dest="machete_status",
                   action="store_true")
    p.add_argument("--sync", "-S", dest="machete_sync",
                   action="store_true")
    p.add_argument("--traverse", "-t", dest="machete_traverse",
                   action="store_true")

    # Global arguments
    p.add_argument("path", nargs="?", default=".")
    p.add_argument("--batch-commit", "-b", action="store_true")
    p.add_argument("--hooks", default=None)
    p.add_argument("--changelog-file", default="changes.log")
    p.add_argument("--push", "-p", action="store_true")
    p.add_argument("--publish", "-P", action="store_true")
    p.add_argument("--remote", "-r", default=None)
    p.add_argument("--force", "-f", action="store_true")
    p.add_argument("--no-transmission", action="store_true")
    p.add_argument("--quiet", "-q", action="store_true")
    p.add_argument("--plain", action="store_true")
    p.add_argument("--verbose", "-v", action="store_true")
    p.add_argument("--debug", "-d", action="store_true")
    p.add_argument("--auto-fix", "-a", action="store_true")
    p.add_argument("--dry-run", "-n", action="store_true")
    p.add_argument("--ci", action="store_true")
    p.add_argument("--interactive", "-i", action="store_true")

    # Github arguments
    p.add_argument("--gh-release", action="store_true")
    p.add_argument("--gh-repo", default=None)
    p.add_argument("--gh-token", default=None)
    p.add_argument("--gh-draft", action="store_true")
    p.add_argument("--gh-prerelease", action="store_true")
    p.add_argument("--gh-assets", default=None)

    # Tagging arguments
    p.add_argument("--tag-prefix", default="v")
    p.add_argument("--tag-message", default=None)
    p.add_argument("--tag-sign", action="store_true")
    p.add_argument("--tag-bump", choices=["major", "minor",
                   "patch"], default="patch")
    return p


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Add and parse arguments."""
    p = _build_parser()
    parsed = p.parse_args(argv)
    return config.apply_layered_config(parsed, argv, p)


def _find_repo_noninteractive(path: str) -> str | None:
    """Find a git repo near path without prompting."""
    cur = os.path.abspath(path)
    while True:
        if os.path.isdir(os.path.join(cur, ".git")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent

    base = os.path.abspath(path)
    if not os.path.isdir(base):
        return None
    for child in os.listdir(base):
        cand = os.path.join(base, child)
        if os.path.isdir(os.path.join(cand, ".git")):
            return cand
    return None


def manage_git_extension_install(out: utils.Output,
                                 uninstall: bool = False,
                                 target_dir: str | None = None) -> int:
    """Install or remove a `git-pnp` shim for `git pnp` usage."""
    def in_path(dir_path: Path) -> bool:
        raw_path = os.environ.get("PATH", "")
        norm_target = os.path.normcase(str(dir_path.resolve()))
        for segment in raw_path.split(os.pathsep):
            if not segment.strip():
                continue
            try:
                norm_segment = os.path.normcase(str(Path(segment).expanduser().resolve()))
            except OSError:
                continue
            if norm_segment == norm_target:
                return True
        return False

    def shim_specs() -> list[tuple[Path, str, int | None]]:
        # Git command discovery differs across shells/platforms.
        # Create platform-appropriate shims so `git pnp` works
        # consistently in common environments.
        if os.name == "nt":
            return [
                (bin_dir / "git-pnp.cmd", "@echo off\r\npython -m pnp %*\r\n", None),
                (bin_dir / "git-pnp", "#!/usr/bin/env sh\nexec python -m pnp \"$@\"\n", 0o755),
            ]
        return [
            (bin_dir / "git-pnp", "#!/usr/bin/env sh\nexec python -m pnp \"$@\"\n", 0o755),
        ]

    home = Path.home()
    bin_dir = Path(target_dir).expanduser() if target_dir else \
        (home / ".local" / "bin")
    scripts = shim_specs()
    if uninstall:
        removed = 0
        for script, _, _ in scripts:
            if script.exists():
                script.unlink()
                removed += 1
                out.success(f"removed git extension shim: {utils.pathit(str(script))}")
        if removed == 0:
            out.warn(f"no shim found at {utils.pathit(str(bin_dir))}")
        else:
            out.success(f"removed {removed} shim(s) from {utils.pathit(str(bin_dir))}")
        return 0

    try:
        bin_dir.mkdir(parents=True, exist_ok=True)
        for script, content, mode in scripts:
            script.write_text(content, encoding="utf-8")
            if mode is not None:
                script.chmod(mode)
    except Exception as e:
        out.warn(f"failed to install git extension shim: {e}")
        return 1

    out.success(f"installed git extension shim(s) in: {utils.pathit(str(bin_dir))}")
    if not in_path(bin_dir):
        out.warn(f"add {utils.pathit(str(bin_dir))} to PATH to enable `git pnp`")
    return 0


def show_effective_config(args: argparse.Namespace,
                          out: utils.Output) -> int:
    """Print the effective merged runtime configuration."""
    keys = [
        "path", "batch_commit", "hooks", "changelog_file", "push",
        "publish", "remote", "force", "no_transmission", "quiet",
        "plain", "verbose", "debug", "auto_fix", "dry_run", "ci",
        "interactive", "gh_release", "gh_repo", "gh_token",
        "gh_draft", "gh_prerelease", "gh_assets", "check_only",
        "check_json",
        "strict",
        "tag_prefix",
        "tag_message", "tag_sign", "tag_bump", "doctor",
        "doctor_json", "doctor_report", "show_config",
        "install_git_ext", "uninstall_git_ext", "git_ext_dir", "machete_status",
        "machete_sync", "machete_traverse",
    ]
    effective = {k: getattr(args, k, None) for k in keys}
    sources = getattr(args, "_pnp_config_sources", None)
    if isinstance(sources, dict):
        effective["_sources"] = {
            k: sources.get(k, "default") for k in keys
        }
    files = getattr(args, "_pnp_config_files", None)
    if isinstance(files, dict):
        effective["_config_files"] = files
    diagnostics = getattr(args, "_pnp_config_diagnostics", None)
    if isinstance(diagnostics, list):
        effective["_config_diagnostics"] = diagnostics
    if isinstance(effective.get("gh_token"), str) and effective["gh_token"]:
        effective["gh_token"] = "***redacted***"
    out.raw(json.dumps(effective, indent=2, sort_keys=True))
    return 0


def run_doctor(path: str, out: utils.Output,
               json_mode: bool = False,
               report_file: str | None = None) -> int:
    """Run local environment audit checks."""
    original_quiet = out.quiet
    if json_mode:
        out.quiet = True
    failures = 0
    warnings = 0
    checks: list[dict[str, str]] = []
    step_delay = 0.25
    labels = [
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
        if use_ui:
            time.sleep(step_delay)

    def add_check(name: str, status: str, details: str) -> None:
        checks.append({"name": name, "status": status, "details": details})

    def git_run(repo: str, args: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", repo, *args],
            check=False,
            capture_output=True,
            text=True,
        )

    with tui_runner(labels, enabled=use_ui) as ui:
        if use_ui:
            utils.bind_console(ui)

        ui.start(0)
        py_ver = sys.version.split()[0]
        py_ok = sys.version_info >= (3, 10)
        py_detail = f"{py_ver} (>=3.10 required)"
        if py_ok:
            add_check("python", "ok", py_detail)
            out.success(f"Python: {py_detail}", step_idx=0)
            out.info(f"Executable: {sys.executable}", step_idx=0)
            pause_step()
            ui.finish(0, utils.StepResult.OK)
        else:
            failures += 1
            add_check("python", "fail", py_detail)
            out.warn(f"Python: {py_detail}", step_idx=0)
            pause_step()
            ui.finish(0, utils.StepResult.FAIL)

        ui.start(1)
        git_bin = shutil.which("git")
        git_ok = False
        if not git_bin:
            failures += 1
            add_check("git", "fail", "not found in PATH")
            out.warn("Git: not found in PATH", step_idx=1)
            pause_step()
            ui.finish(1, utils.StepResult.FAIL)
        else:
            cp = subprocess.run(
                [git_bin, "--version"],
                check=False,
                capture_output=True,
                text=True,
            )
            git_ok = cp.returncode == 0
            if git_ok:
                detail = cp.stdout.strip()
                add_check("git", "ok", detail)
                out.success(detail, step_idx=1)
                pause_step()
                ui.finish(1, utils.StepResult.OK)
            else:
                failures += 1
                add_check("git", "fail", "detected but unusable")
                out.warn("Git: detected but unusable", step_idx=1)
                pause_step()
                ui.finish(1, utils.StepResult.FAIL)

        ui.start(2)
        if git_ok:
            user = subprocess.run(
                ["git", "config", "--global", "user.name"],
                check=False,
                capture_output=True,
                text=True,
            ).stdout.strip()
            email = subprocess.run(
                ["git", "config", "--global", "user.email"],
                check=False,
                capture_output=True,
                text=True,
            ).stdout.strip()
            missing: list[str] = []
            if not user:
                missing.append("user.name")
            if not email:
                missing.append("user.email")
            if missing:
                warnings += 1
                detail = ", ".join(missing)
                add_check("git_identity", "warn", detail)
                out.warn("Missing global Git identity: " + detail,
                    step_idx=2)
                pause_step()
                ui.finish(2, utils.StepResult.ABORT)
            else:
                add_check("git_identity", "ok", "configured")
                out.success("Global Git identity configured", step_idx=2)
                pause_step()
                ui.finish(2, utils.StepResult.OK)
        else:
            warnings += 1
            add_check("git_identity", "warn", "skipped (Git unavailable)")
            out.warn("Skipped (Git unavailable)", step_idx=2)
            pause_step()
            ui.finish(2, utils.StepResult.ABORT)

        ui.start(3)
        repo = _find_repo_noninteractive(path) if git_ok else None
        if repo:
            add_check("repository", "ok", repo)
            out.success(f"Detected at {utils.pathit(repo)}", step_idx=3)
            pause_step()
            ui.finish(3, utils.StepResult.OK)
        else:
            warnings += 1
            add_check("repository", "warn", "not found near target path")
            out.warn("No repository detected near target path", step_idx=3)
            pause_step()
            ui.finish(3, utils.StepResult.ABORT)

        ui.start(4)
        if repo:
            cp = git_run(repo, ["status", "--porcelain"])
            if cp.returncode == 0:
                dirty = [line for line in cp.stdout.splitlines() if line.strip()]
                if dirty:
                    warnings += 1
                    add_check("working_tree", "warn",
                        f"{len(dirty)} pending change(s)")
                    out.warn(f"Working tree has {len(dirty)} pending change(s)",
                        step_idx=4)
                    preview = ", ".join(line[3:] for line in dirty[:4])
                    if preview:
                        out.info(f"Sample: {preview}", step_idx=4)
                    pause_step()
                    ui.finish(4, utils.StepResult.ABORT)
                else:
                    add_check("working_tree", "ok", "clean")
                    out.success("Working tree is clean", step_idx=4)
                    pause_step()
                    ui.finish(4, utils.StepResult.OK)
            else:
                warnings += 1
                add_check("working_tree", "warn", "unable to inspect")
                out.warn("Unable to inspect working tree", step_idx=4)
                pause_step()
                ui.finish(4, utils.StepResult.ABORT)
        else:
            warnings += 1
            add_check("working_tree", "warn", "skipped (no repository)")
            out.warn("Skipped (no repository)", step_idx=4)
            pause_step()
            ui.finish(4, utils.StepResult.ABORT)

        ui.start(5)
        if repo:
            branch_cp = git_run(repo, ["rev-parse", "--abbrev-ref", "HEAD"])
            branch = branch_cp.stdout.strip() if branch_cp.returncode == 0 else ""
            if not branch or branch == "HEAD":
                warnings += 1
                add_check("branch_tracking", "warn", "detached HEAD")
                out.warn("Detached HEAD; branch tracking unavailable", step_idx=5)
                pause_step()
                ui.finish(5, utils.StepResult.ABORT)
            else:
                upstream_cp = git_run(
                    repo, ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"]
                )
                if upstream_cp.returncode != 0:
                    warnings += 1
                    detail = f"branch '{branch}' has no upstream"
                    add_check("branch_tracking", "warn", detail)
                    out.warn(f"Branch '{branch}' has no upstream", step_idx=5)
                    pause_step()
                    ui.finish(5, utils.StepResult.ABORT)
                else:
                    upstream = upstream_cp.stdout.strip()
                    delta_cp = git_run(repo, ["rev-list", "--left-right", "--count", f"{upstream}...HEAD"])
                    if delta_cp.returncode == 0:
                        parts = delta_cp.stdout.strip().split()
                        behind = int(parts[0]) if parts else 0
                        ahead = int(parts[1]) if len(parts) > 1 else 0
                        if behind > 0:
                            warnings += 1
                            add_check("branch_tracking", "warn",
                                f"behind {upstream} by {behind} (ahead {ahead})")
                            out.warn(
                                f"Branch '{branch}' is behind {upstream} by {behind}",
                                step_idx=5,
                            )
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
                        add_check("branch_tracking", "warn",
                            "unable to compute ahead/behind status")
                        out.warn("Unable to compute ahead/behind status", step_idx=5)
                        pause_step()
                        ui.finish(5, utils.StepResult.ABORT)
        else:
            warnings += 1
            add_check("branch_tracking", "warn", "skipped (no repository)")
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
                add_check("remotes", "warn", "none configured")
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
            cp = git_run(repo, ["fsck", "--no-progress", "--no-dangling"])
            if cp.returncode == 0:
                add_check("repository_integrity", "ok", "git fsck passed")
                out.success("Git object database integrity looks good", step_idx=7)
                pause_step()
                ui.finish(7, utils.StepResult.OK)
            else:
                failures += 1
                detail = cp.stderr.strip() or cp.stdout.strip() or "git fsck failed"
                add_check("repository_integrity", "fail", detail)
                out.warn(detail, step_idx=7)
                pause_step()
                ui.finish(7, utils.StepResult.FAIL)
        else:
            warnings += 1
            add_check("repository_integrity", "warn", "skipped (no repository)")
            out.warn("Skipped (no repository)", step_idx=7)
            pause_step()
            ui.finish(7, utils.StepResult.ABORT)

        ui.start(8)
        pkg_root: str | None = repo
        if repo:
            detected = utils.detect_subpackage(path, repo)
            pkg_root = detected or repo
            pyproject = Path(pkg_root) / "pyproject.toml"
            if not pyproject.exists():
                warnings += 1
                add_check("project_metadata", "warn", "missing pyproject.toml")
                out.warn(f"Missing pyproject.toml in {utils.pathit(pkg_root)}",
                    step_idx=8)
                pause_step()
                ui.finish(8, utils.StepResult.ABORT)
            else:
                try:
                    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
                except Exception as e:
                    warnings += 1
                    add_check("project_metadata", "warn",
                        f"invalid pyproject.toml: {e}")
                    out.warn(f"Invalid pyproject.toml: {e}", step_idx=8)
                    pause_step()
                    ui.finish(8, utils.StepResult.ABORT)
                else:
                    project = data.get("project", {})
                    build_sys = data.get("build-system", {})
                    missing_meta: list[str] = []
                    if not project.get("name"):
                        missing_meta.append("project.name")
                    if not project.get("version"):
                        missing_meta.append("project.version")
                    if not build_sys.get("build-backend"):
                        missing_meta.append("build-system.build-backend")
                    if missing_meta:
                        warnings += 1
                        add_check("project_metadata", "warn",
                            "missing metadata: " + ", ".join(missing_meta))
                        out.warn("Missing metadata: "
                            + ", ".join(missing_meta), step_idx=8)
                        pause_step()
                        ui.finish(8, utils.StepResult.ABORT)
                    else:
                        meta_detail = f"{project.get('name')} {project.get('version')}"
                        add_check("project_metadata", "ok", meta_detail)
                        out.success(
                            f"Metadata OK ({meta_detail})",
                            step_idx=8,
                        )
                        pause_step()
                        ui.finish(8, utils.StepResult.OK)
        else:
            warnings += 1
            add_check("project_metadata", "warn", "skipped (no repository)")
            out.warn("Skipped (no repository)", step_idx=8)
            pause_step()
            ui.finish(8, utils.StepResult.ABORT)

        ui.start(9)
        if pkg_root:
            tests_dir = Path(pkg_root) / "tests"
            has_tests = tests_dir.is_dir()
            if not has_tests:
                for root, _, files in os.walk(pkg_root):
                    if any(f.startswith("test_") and f.endswith(".py")
                        for f in files):
                        has_tests = True
                        break
            if has_tests:
                add_check("test_footprint", "ok", "tests detected")
                out.success("Test footprint detected", step_idx=9)
                pause_step()
                ui.finish(9, utils.StepResult.OK)
            else:
                warnings += 1
                add_check("test_footprint", "warn", "no tests found")
                out.warn("No tests directory or test_*.py files found", step_idx=9)
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
    else:
        out.quiet = original_quiet

    if failures:
        out.warn("doctor summary: "
            + f"{failures} critical issue(s), {warnings} warning(s)")
        return 1
    if warnings:
        utils.transmit(
            utils.wrap("doctor summary: "
                + f"0 critical issue(s), {warnings} warning(s)"),
            fg=const.PROMPT,
            quiet=out.quiet,
        )
        return 0
    out.success("doctor summary: environment is healthy")
    return 0


def run_check_only(args: argparse.Namespace,
                   out: utils.Output) -> int:
    """Run non-mutating workflow preflight checks."""
    blockers = 0
    warnings_only = 0
    findings: list[dict[str, str]] = []
    emit = out if not args.check_json else utils.Output(quiet=True)

    def note(level: str, check: str, message: str) -> None:
        findings.append({"level": level, "check": check, "message": message})
        if level == "blocker":
            emit.warn(message)
        elif level == "warn":
            emit.warn(message)
        else:
            emit.success(message)

    emit.info("running check-only preflight")
    report_path: str | None = None
    with tempfile.NamedTemporaryFile(
        prefix="pnp_doctor_",
        suffix=".json",
        delete=False,
    ) as tf:
        report_path = tf.name
    doctor_code = run_doctor(args.path, emit, report_file=report_path)
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
            try:
                os.remove(report_path)
            except OSError:
                pass

    repo = _find_repo_noninteractive(args.path)
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
        if not repo:
            pass
        else:
            cp = subprocess.run(
                ["git", "-C", repo, "remote"],
                check=False,
                capture_output=True,
                text=True,
            )
            remotes = [r for r in cp.stdout.splitlines() if r.strip()]
            if cp.returncode != 0 or not remotes:
                note("blocker", "remotes",
                     "check-only: no git remotes configured")
                blockers += 1
            else:
                note("ok", "remotes", "check-only: remotes configured")

    if args.push and repo:
        cp = subprocess.run(
            ["git", "-C", repo, "rev-parse", "--abbrev-ref", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
        )
        branch = cp.stdout.strip() if cp.returncode == 0 else ""
        if not branch or branch == "HEAD":
            note("blocker", "branch",
                 "check-only: detached HEAD or no active branch")
            blockers += 1
        else:
            note("ok", "branch", f"check-only: active branch '{branch}'")

    if args.gh_release:
        token = args.gh_token or os.environ.get("GITHUB_TOKEN")
        if not args.gh_repo:
            note("blocker", "gh_release",
                 "check-only: --gh-repo is required for --gh-release")
            blockers += 1
        if not token:
            note("blocker", "gh_release",
                 "check-only: GitHub token required for --gh-release")
            blockers += 1

    if any((args.machete_status, args.machete_sync, args.machete_traverse)):
        if not shutil.which("git-machete"):
            note("blocker", "machete",
                 "check-only: git-machete not found in PATH")
            blockers += 1
        elif repo:
            cp = subprocess.run(
                ["git", "machete", "status"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )
            if cp.returncode != 0:
                detail = cp.stderr.strip() or cp.stdout.strip() \
                    or "git machete status failed"
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
        }
        out.raw(json.dumps(payload, indent=2))
    return code


class Orchestrator:
    """
    Main orchestrator for the pnp CLI tool.

    Orchestrates the full release workflow including:
      - Parsing CLI arguments and resolving paths
      - Locating or initializing a Git repository
      - Handling monorepo package detection
      - Executing pre-push hooks
      - Generating changelog between self.latest tag and HEAD
      - Optionally staging and committing uncommitted changes
      - Writing changelog to file if specified
      - Pushing changes and tags
      - Creating GitHub releases and uploading assets

    Supports dry-run and quiet modes for safe evaluation and
    silent execution.
    """

    def __init__(self, argv: list[str] | argparse.Namespace,
                 repo_path: str | None = None):
        """
        Initialize the orchestrator for the `pnp` CLI tool.

        Parses CLI arguments, resolves the working directory,
        sets up output behavior, and initializes key
        attributes used in the release process (e.g. Git repo
        path, changelog data, etc.).

        If `argv` is not provided (i.e. normal execution),
        the full workflow is immediately triggered via
        `self.orchestrate()`.

        Args:
            argv (list[str] | None): Optional CLI arguments
            for testing purposes. Defaults to `sys.argv[1:]`
            when not provided.
        """
        if isinstance(argv, list): argv = parse_args(argv)

        self.args: argparse.Namespace = argv
        const.sync_runtime_flags(self.args)
        self.path       = os.path.abspath(repo_path
                       or self.args.path)
        self.out        = utils.Output(quiet=self.args.quiet)
        self.repo: str | None = None
        self.subpkg: str | None = None
        self.gitutils: Any = None
        self.resolver: Any = None
        self.latest: str | None = None
        self.commit_msg: str | None = None
        self.tag: str | None = None
        self.log_dir: Path | None = None
        self.log_text: str | None = None

    def _git_head(self, path: str) -> str | None:
        cp = subprocess.run(
            ["git", "-C", path, "rev-parse", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
        )
        if cp.returncode != 0:
            return None
        head = cp.stdout.strip()
        return head or None

    def _rollback_unstage(self, path: str,
                          step_idx: int | None = None) -> None:
        cp = subprocess.run(
            ["git", "-C", path, "reset"],
            check=False,
            capture_output=True,
            text=True,
        )
        if cp.returncode == 0:
            self.out.warn("rollback: unstaged index after failure",
                          step_idx=step_idx)
        else:
            self.out.warn("rollback failed: unable to unstage index",
                          step_idx=step_idx)

    def _rollback_delete_tag(self, repo: str, tag: str,
                             step_idx: int | None = None) -> None:
        cp = subprocess.run(
            ["git", "-C", repo, "tag", "-d", tag],
            check=False,
            capture_output=True,
            text=True,
        )
        if cp.returncode == 0:
            self.out.warn(f"rollback: removed local tag {tag!r}",
                          step_idx=step_idx)
        else:
            self.out.warn(f"rollback failed: unable to remove local tag {tag!r}",
                          step_idx=step_idx)

    def orchestrate(self) -> None:
        """
        Execute the full release workflow.

        Runs a predefined series of steps in sequence,
        including:
          - Locating or initializing a Git repository
          - Running pre-push hooks
          - Staging and committing changes
          - Pushing to the remote repository
          - Publishing to package registries
          - Creating GitHub releases

        Each step returns a message and a `StepResult` enum
        that determines control flow:
          - SKIP: silently continues to the next step
          - FAIL: exits with code 1
          - ABORT: prints error and terminates

        If `--dry-run` is enabled, no actual changes are made
        and a reassuarance/confirmation message is shown.
        """
        steps = [
            self.find_repo,
            self.run_hooks,
            self.run_machete,
            self.stage_and_commit,
            self.push,
            self.publish,
            self.release,
        ]

        labels = [
            "Detect repository",
            "Run hooks",
            "Run git machete",
            "Stage and commit changes",
            "Push to remote",
            "Publish tag",
            "Create GitHub release"
        ]

        use_ui = bool(const.CI_MODE and not const.PLAIN
            and sys.stdout.isatty())

        with tui_runner(labels, enabled=use_ui) as ui:
            if use_ui: utils.bind_console(ui)

            for i, step in enumerate(steps):
                ui.start(i)
                msg, result = step(step_idx=i)
                ui.finish(i, result)
                if result is utils.StepResult.DONE: return None
                if result is utils.StepResult.SKIP: continue
                if result is utils.StepResult.FAIL: sys.exit(1)
                if result is utils.StepResult.ABORT:
                    if isinstance(msg, tuple): self.out.abort(*msg)
                    else: self.out.abort(msg)

        if self.args.dry_run:
            self.out.success(const.DRYRUN + "no changes made")

    def find_repo(self, step_idx: int | None = None
                 ) -> tuple[str | None, utils.StepResult]:
        """
        Locate the Git repository root and sets up project
        context.

        Attempts to find the repository starting from the
        provided path. If none is found and not in CI mode,
        prompts the user to initialize a new repository.

        Also:
          - Initializes logging directory
          - Dynamically imports Git-related modules
          - Detects monorepo subpackages if applicable

        Returns:
            tuple[str | None, StepResult]: An optional error
            message and a StepResult indicating whether to
            continue, fail, or abort.
        """
        try:
            found_repo = utils.find_repo(self.path)
            if not isinstance(found_repo, str):
                raise RuntimeError("unexpected repository resolution")
            self.repo = found_repo

            # Setup logging and import runtime-dependent
            # modules
            self.log_dir = utils.get_log_dir(self.repo)
            modules      = utils.import_deps(self.log_dir)
        except RuntimeError:
            if not const.CI_MODE:
                prompt = utils.wrap("no repo found. "
                       + "Initialize here? [y/n]")
                if utils.intent(prompt, "y", "return"):
                    self.log_dir = utils.get_log_dir(
                                   self.path)
                    modules = utils.import_deps(self.log_dir)
                    modules[0].git_init(self.path)
                    self.repo = self.path
                else:
                    result = utils.StepResult.ABORT
                    if self.args.batch_commit:
                        result = utils.StepResult.DONE
                    return None, result
            else:
                return "no git repository found", \
                       utils.StepResult.ABORT

        self.gitutils, self.resolver = modules
        assert self.repo is not None
        self.out.success(f"repo root: {utils.pathit(self.repo)}", step_idx)

        # monorepo detection: are we in a package folder?
        subpkg = utils.detect_subpackage(self.path, self.repo)
        if subpkg:
            self.subpkg = subpkg
            msg = "operating on detected package at: " \
                + f"{utils.pathit(self.subpkg)}\n"
            self.out.success(msg, step_idx)
        else: self.subpkg = self.repo
        assert self.subpkg is not None

        return None, utils.StepResult.OK

    def run_hooks(self, step_idx: int | None = None
                 ) -> tuple[str | None, utils.StepResult]:
        """
        Execute pre-push shell hooks defined via CLI
        arguments.

        Parses and runs each hook command, respecting dry-run
        mode.

        If a hook fails:
          - In CI mode: the process fails immediately.
          - Otherwise: user is prompted whether to continue
                       or abort.

        Skips execution entirely if no hooks are provided.

        Returns:
            tuple[str | None, StepResult]: An optional
            message and a StepResult indicating whether to
            continue, fail, or abort.
        """
        if not self.args.hooks:
            return None, utils.StepResult.SKIP

        hooks = [h.strip() for h in self.args.hooks.split(";"
                ) if h.strip()]
        assert self.subpkg is not None
        self.out.info("running hooks:\n" + utils
            .to_list(hooks), step_idx=step_idx)
        for i, cmd in enumerate(hooks):
            try:
                run_hook(
                    cmd,
                    self.subpkg,
                    self.args.dry_run,
                    no_transmission=self.args.no_transmission,
                )
            except (RuntimeError, ValueError) as e:
                msg = " ".join(e.args[0].split())
                if isinstance(e, RuntimeError):
                    msg = f"hook failed {msg}"
                self.out.warn(msg, step_idx=step_idx)
                prompt = "hook failed. Continue? [y/n]"
                if const.CI_MODE:
                    return None, utils.StepResult.FAIL
                if utils.intent(prompt, "n", "return"):
                    msg = "aborting due to hook failure"
                    return msg, utils.StepResult.ABORT

        if self.args.dry_run and const.PLAIN: print()

        return None, utils.StepResult.OK

    def run_machete(self, step_idx: int | None = None
                   ) -> tuple[str | None, utils.StepResult]:
        """Run optional git-machete checks/operations."""
        enabled = any((
            self.args.machete_status,
            self.args.machete_sync,
            self.args.machete_traverse,
        ))
        if not enabled:
            return None, utils.StepResult.SKIP
        assert self.repo is not None

        if not shutil.which("git-machete"):
            return "git-machete not found in PATH", utils.StepResult.ABORT

        commands: list[tuple[str, list[str]]] = []
        commands.append(("status", ["git", "machete", "status"]))
        if self.args.machete_sync:
            commands.append((
                "traverse --fetch --sync",
                ["git", "machete", "traverse", "--fetch", "--sync"],
            ))
        elif self.args.machete_traverse:
            commands.append((
                "traverse",
                ["git", "machete", "traverse"],
            ))

        for label, cmd in commands:
            if self.args.dry_run:
                self.out.info(const.DRYRUN + "would run: "
                    + " ".join(cmd), step_idx=step_idx)
                continue
            cp = subprocess.run(
                cmd,
                cwd=self.repo,
                check=False,
                capture_output=True,
                text=True,
            )
            if cp.returncode != 0:
                detail = cp.stderr.strip() or cp.stdout.strip() \
                    or f"git machete {label} failed"
                return detail, utils.StepResult.ABORT
            self.out.success(f"git machete {label}: ok", step_idx=step_idx)
        return None, utils.StepResult.OK

    def gen_changelog(self, get: bool = False) -> None\
                                                | Path:
        """
        Generate a changelog from the latest Git tag to HEAD.

        If `get` is True, returns the resolved changelog file
        path without generating the changelog. Otherwise,
        generates the changelog text, optionally writes it to
        a specified file, and prints it to the output stream.

        In dry-run mode:
          - No changes are written to disk.
          - A mock commit message can be passed to simulate
            output.

        Handles exceptions gracefully and displays contextual
        error messages, especially in dry-run mode where
        changelog generation may fail due to skipped
        operations.

        Args:
            get (bool): If True, returns the changelog file
                        path without running the generation
                        process.

        Returns:
            None | Path: Returns the changelog path if `get`
                         is True; otherwise, returns None.
        """
        assert self.repo is not None
        tags        = self.gitutils.tags_sorted(self.repo)
        self.latest = tags[0] if tags else None
        timestamp   = datetime.now().isoformat()[:-7]

        assert self.log_dir is not None
        log_file: Path = self.log_dir / Path("changes.log")
        if self.args.changelog_file:
            log_name = self.args.changelog_file
            if os.sep not in log_name:
                log_file = self.log_dir / Path(log_name)
            else:
                log_file = Path(log_name)

        if get: return log_file

        msg = self.commit_msg if self.args.dry_run else None
        hue = const.GOOD
        div = f"------| {timestamp} |------"
        try:
            self.log_text = utils.gen_changelog(
                            self.repo, since=self.latest,
                            dry_run=msg) + "\n"
        except Exception as e:
            hue = const.BAD
            add = ""
            if self.args.dry_run and "ambiguous" in e.args[0]:
                add = "NB: Potentially due to dry-run "\
                    + "skipping certain processes\n"
            self.log_text = utils.color("changelog "
                          + f"generation failed: {e}{add}\n",
                            hue)

        # log changes
        self.out.raw(const.PNP, end="")
        prompt = utils.color("changelog↴\n", hue)
        self.out.raw(wrap(prompt))
        self.out.raw(utils.Align().center(div, "-"))
        self.out.raw(wrap(self.log_text), end="")
        if not self.args.dry_run and self.args.changelog_file:
            os.makedirs(log_file.parent, exist_ok=True)
            with open(log_file, "a+", encoding="utf-8") as f:
                f.write(strip_ansi(f"{div}\n{self.log_text}"))

        return None

    def stage_and_commit(self, step_idx: int | None = None
                        ) -> tuple[tuple[str, bool] | None,
                             utils.StepResult]:
        """
        Stage and commit any uncommitted changes in the
        target directory.

        If no changes are found, the latest changelog is
        retrieved and the step is skipped. Otherwise, prompts
        the user (if not in CI mode) to confirm staging and
        committing. In dry-run mode, actions are logged but
        not executed.

        Generates a commit message either automatically or
        via user input, and stores it for later use. After
        committing, the changelog is regenerated to reflect
        the new commit.

        Returns:
            tuple[tuple[str, bool] | None, utils.StepResult]:
              - (error_msg, False), ABORT if an error occurs
              - None, SKIP if no changes are found
              - None, OK if commit is successful
        """
        assert self.subpkg is not None
        if not self.gitutils.has_uncommitted(self.subpkg):
            log_file      = self.gen_changelog(get=True)
            assert isinstance(log_file, Path)
            self.log_text = utils\
                .retrieve_latest_changelog(log_file)
            self.out.success("no changes to commit", step_idx)
            return None, utils.StepResult.SKIP

        if not const.CI_MODE:
            prompt = utils.wrap("uncommitted changes "
                   + "found. Stage and commit? [y/n]")
            if utils.intent(prompt, "n", "return"):
                return None, utils.StepResult.ABORT
        head_before = self._git_head(self.subpkg)
        staged = False
        try:
            msg = self.args.tag_message\
               or utils.gen_commit_message(self.subpkg)

            if not const.CI_MODE:
                m = "enter commit message. Type 'no' to " \
                  + "exclude commit message"
                self.out.prompt(m)
                m = input(const.CURSOR).strip() or "no"
                if const.PLAIN: self.out.raw()
                msg = msg if m.lower() == "no" else m

            self.commit_msg = msg

            if not self.args.dry_run:
                self.gitutils.stage_all(self.subpkg)
                staged = True
                self.gitutils.commit(self.subpkg, msg)
                staged = False
            else:
                msg = const.DRYRUN + f"would commit {msg!r}"
                self.out.info(msg, step_idx=step_idx)
        except Exception as e:
            if staged and not self.args.dry_run:
                head_after = self._git_head(self.subpkg)
                if head_before and head_after == head_before:
                    self._rollback_unstage(self.subpkg, step_idx=step_idx)
            e = self.resolver.normalize_stderr(e)
            return (f"{e}\n", False), utils.StepResult.ABORT

        # generate changelog between self.latest and HEAD
        self.gen_changelog()
        return None, utils.StepResult.OK

    def push(self, step_idx: int | None = None
            ) -> tuple[str | tuple[str, bool] | None,
                 utils.StepResult]:
        """
        Push local commits to a remote Git repository.

        Fetches all remotes and determines the current
        branch. If no branch is detected and not in dry-run
        mode, aborts. Otherwise, checks if the remote is
        ahead of the local branch. If so, prompts for force
        push (unless in CI mode or force is pre-specified).

        Handles push execution with optional force, excluding
        tags. Supports dry-run mode where actual push is
        skipped but flow continues with user prompts.

        Returns:
            tuple[str | tuple[str, bool] | None,
            utils.StepResult]
              - error_msg, ABORT if fetch fails or branchless
              - (error_msg, False), ABORT if push fails
              - None, SKIP if push flag is not set
              - None, OK if push succeeds
        """
        if not self.args.push:
            return None, utils.StepResult.SKIP
        assert self.subpkg is not None and self.repo is not None

        try: self.gitutils.fetch_all(self.repo)
        except Exception as e:
            self.out.warn(self.resolver.normalize_stderr(e),
                False, step_idx=step_idx)
            if const.CI_MODE and not self.args.dry_run:
                return None, utils.StepResult.ABORT
            self.out.prompt(const.DRYRUN + "continuing regardless",
                step_idx=step_idx)

        branchless = False
        branch     = self.gitutils.current_branch(self.subpkg)
        if not branch:
            self.out.warn("no branch detected",
                step_idx=step_idx)
            if not self.args.dry_run:
                return None, utils.StepResult.ABORT
            self.out.prompt(const.DRYRUN + "continuing regardless",
                step_idx=step_idx)
            branchless = True

        if not branchless:
            upstream = self.args.remote or self.gitutils\
                       .upstream_for_branch(self.subpkg,
                       branch)
            if upstream:
                remote_name = upstream.split("/")[0]
            else: remote_name = self.args.remote or "origin"
        else: upstream = None

        # check ahead/behind
        force = False
        if upstream:
            counts = self.gitutils.rev_list_counts(self.repo,
                     upstream, branch)
            if counts:
                remote_ahead, _ = counts
                if remote_ahead > 0:
                    m = f"remote ({upstream}) ahead by " \
                      + f"{remote_ahead} commit(s)"
                    self.out.warn(m, step_idx=step_idx)
                    if self.args.force: force = True
                    elif not const.CI_MODE:
                        msg   = utils.wrap("force push and "
                              + "overwrite remote? [y/n]")
                        force = bool(utils.intent(msg, "y",
                                "return"))
                    else: return None, utils.StepResult.ABORT

        if not branchless:
            try: self.gitutils.push(self.repo,
                    remote=remote_name,
                    branch=branch,
                    force=force,
                    push_tags=False)
            except Exception as e:
                return (self.resolver.normalize_stderr(e), False), \
                    utils.StepResult.ABORT

        return None, utils.StepResult.OK

    def publish(self, step_idx: int | None = None
               ) -> tuple[str | tuple[str, bool] | None,
                    utils.StepResult]:
        """
        Create and push a new Git tag based on the latest
        tag and version bump strategy.

        If `--publish` is not set, skips the step. Computes
        the new tag using the specified version bump and
        optional prefix, then creates the tag (signed or
        annotated) and pushes it to the remote.

        Handles dry-run mode by skipping actual tag creation
        and push but displaying the intended actions.

        Returns:
            tuple[str | tuple[str, bool] | None,
            utils.StepResult]:
              - Error message or (message, False), ABORT if
                tag creation or push fails.
              - None, SKIP if publishing is disabled.
              - None, OK if tag creation and push succeed.
        """
        if not self.args.publish:
            return None, utils.StepResult.SKIP

        self.tag = utils.bump_semver_from_tag(
                   self.latest or "", self.args.tag_bump,
                   prefix=self.args.tag_prefix)
        self.out.success(f"new tag: {self.tag}", step_idx)

        if self.args.dry_run:
            msg = const.DRYRUN + "would create tag " \
                + utils.color(self.tag, const.INFO)
            self.out.prompt(msg, step_idx=step_idx)
        else:
            assert self.repo is not None
            existing = self.gitutils.tags_sorted(self.repo, self.tag)
            tag_created = False
            try: self.gitutils.create_tag(self.repo, self.tag,
                 message=self.args.tag_message
                 or self.log_text, sign=self.args.tag_sign)
            except Exception as e:
                if self.tag in existing:
                    self.out.warn(f"tag {self.tag!r} already exists locally; reusing",
                                  step_idx=step_idx)
                else:
                    return f"tag creation failed: {e}", \
                           utils.StepResult.ABORT
            else:
                tag_created = True

            try: self.gitutils.push(self.repo,
                 remote=self.args.remote or "origin",
                 branch=None, force=self.args.force,
                 push_tags=True)
            except Exception as e:
                if tag_created:
                    self._rollback_delete_tag(self.repo, self.tag,
                                              step_idx=step_idx)
                e = self.resolver.normalize_stderr(e,
                    "failed to push tags:")
                return (e, False), utils.StepResult.ABORT

        return None, utils.StepResult.OK

    def release(self, step_idx: int | None = None
               ) -> tuple[tuple[str, bool] | None,
                    utils.StepResult]:
        """
        Create a GitHub release for the current tag and
        optionally uploads assets.

        Checks for required GitHub token (`--gh-token` or
        `GITHUB_TOKEN`) and repository (`--gh-repo`). If both
        are provided, creates a release with the changelog as
        the body, and optionally marks it as a draft or
        prerelease.

        If `--gh-assets` is specified, uploads the given file
        paths (comma-separated) as release assets.

        Supports dry-run mode by skipping actual API calls
        while displaying intended actions.

        Returns:
            tuple[tuple[str, bool] | None, utils.StepResult]:
              - (Error message, False), ABORT if GitHub
                release raises an error
              - None, FAIL if required inputs are missing.
              - None, SKIP if GitHub release is not enabled.
              - None, OK if the release (and assets) are
                successfully created or dry-run simulated.
        """
        if not self.args.gh_release:
            return None, utils.StepResult.SKIP

        if not self.tag:
            assert self.repo is not None
            tags = self.gitutils.tags_sorted(self.repo)
            if tags:
                self.tag = tags[0]
                self.out.warn(
                    "no publish step detected; using latest tag "
                    + f"{self.tag!r} for release",
                    step_idx=step_idx,
                )
            elif not self.args.dry_run:
                self.out.warn("cannot create GitHub release: no tag available",
                    step_idx=step_idx)
                return None, utils.StepResult.FAIL
            else:
                self.tag = "v0.0.0-dry-run"

        token = self.args.gh_token \
             or os.environ.get("GITHUB_TOKEN")
        if not token:
            m = "GitHub token required for release. Set " \
              + "--gh-token or GITHUB_TOKEN env var"
            self.out.warn(m, step_idx=step_idx)
            if not self.args.dry_run:
                return None, utils.StepResult.FAIL
        if not self.args.gh_repo:
            self.out.warn("--gh-repo required for GitHub release", step_idx=step_idx)
            if not self.args.dry_run:
                return None, utils.StepResult.FAIL

        from . import github as gh

        self.out.success(f"creating GitHub release for tag {self.tag}", step_idx)

        if self.args.dry_run:
            self.out.prompt(const.DRYRUN + "skipping process...",
                step_idx=step_idx)
        else:
            assert token is not None and self.tag is not None
            release_info = gh.create_release(token,
                           self.args.gh_repo, self.tag,
                           self.tag, self.log_text,
                           self.args.gh_draft,
                           self.args.gh_prerelease)

        if self.args.gh_assets:
            files = [f.strip() for f in self.args.gh_assets
                    .split(",") if f.strip()]
            for fpath in files:
                self.out.success(f"uploading asset: {fpath}",
                    step_idx=step_idx)
                if self.args.dry_run:
                    self.out.prompt(const.DRYRUN + "skipping process...",
                        step_idx=step_idx)
                else:
                    assert token is not None
                    try: gh.upload_asset(token,
                         self.args.gh_repo,
                         int(cast(int, release_info["id"])), fpath)
                    except RuntimeError as e:
                        e = self.resolver.normalize_stderr(e)
                        return (e, False), \
                               utils.StepResult.ABORT

        return None, utils.StepResult.OK


def main() -> None:
    """
    CLI entry point for the `pnp` tool.

    Handles CLI argument parsing, mode dispatch, and
    exception management for user-friendly execution.

    Features:
    - Supports normal and batch (`--batch-commit`) modes
    - Automatically applies default tag message and verbosity
      settings in batch mode
    - Discovers one or more repositories based on provided
      path
    - Delegates execution to `Orchestrator` per discovered
      repo
    - Gracefully handles unexpected exceptions, keyboard
      interrupts, and forced exits
    - Emits a final success message on completion

    This function is intended as the main launcher for CLI
    invocation of the tool.
    """
    args = parse_args(sys.argv[1:])
    if args.batch_commit and not args.verbose:
        args.quiet = True
    const.sync_runtime_flags(args)
    out  = utils.Output(quiet=args.quiet)
    code = 0
    try:
        if args.install_git_ext and args.uninstall_git_ext:
            out.warn("choose only one: --install-git-ext or --uninstall-git-ext")
            code = 1
            return None
        if args.show_config:
            code = show_effective_config(args, out)
            return None
        if args.check_only or args.check_json:
            code = run_check_only(args, out)
            return None
        if args.install_git_ext:
            code = manage_git_extension_install(out, uninstall=False,
                                                target_dir=args.git_ext_dir)
            return None
        if args.uninstall_git_ext:
            code = manage_git_extension_install(out, uninstall=True,
                                                target_dir=args.git_ext_dir)
            return None
        if args.doctor:
            code = run_doctor(
                args.path,
                out,
                json_mode=args.doctor_json,
                report_file=args.doctor_report,
            )
            return None
        if args.batch_commit:
            paths = utils.find_repo(
                args.path,
                batch=True,
                return_none=False,
            )
        else:
            paths = [None]
        for path in paths:
            orchestrator = Orchestrator(args, path)
            orchestrator.orchestrate()
    except BaseException as e:
        code = 1
        exit = (KeyboardInterrupt, EOFError, SystemExit)
        if const.DEBUG: raise e
        if isinstance(e, SystemExit):
            if isinstance(e.code, int): code = e.code
        if not isinstance(e, exit): out.warn(f"ERROR: {e}")
        elif not isinstance(e, exit[2]):
            i = 1 if not isinstance(e, EOFError) else 2
            out.raw("\n" * i + const.PNP, end="")
            out.raw(utils.color("forced exit", const.BAD))
    finally:
        status = out.success if code == 0 else out.warn
        status("done"); out.raw(); sys.exit(code)
