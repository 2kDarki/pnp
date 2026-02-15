"""Helper functions extracted from cli entrypoint."""
from __future__ import annotations

from pathlib import Path
import argparse
import json
import os
import re
import shutil
import subprocess
import time

from . import _constants as const
from . import utils


def run_hook(cmd: str, cwd: str, dryrun: bool,
             no_transmission: bool = False) -> int:
    """Run a validated hook command safely with optional dry-run."""
    if re.search(r"[$&;|><`()]", cmd):
        err = f"rejected potentially unsafe hook: {cmd!r}"
        raise ValueError(err)

    exclude = "drace", "pytest"
    capture = not no_transmission \
          and not utils.any_in(exclude, eq=cmd)

    parts = cmd.split("::")
    prefix = "run"
    if len(parts) == 2:
        prefix, cmd = parts
    args = cmd.split()
    if not args:
        raise ValueError("hook command is empty")

    disallowed = {
        "rm", "mv", "dd", "shutdown", "reboot", "mkfs",
        "kill", "killall", ">:(", "sudo", "tsu", "chown",
        "chmod", "wget", "curl",
    }
    raw_cmd = os.path.basename(args[0]).lower()
    if raw_cmd in disallowed:
        err = f"hook command '{raw_cmd}' not allowed"
        raise ValueError(err)

    add = f" {const.DRYRUN}skips" if dryrun else ""
    m = utils.wrap(f"[{prefix}] {cmd}{add}")
    utils.transmit(m, fg=const.GOOD)
    if dryrun:
        return 0

    if "pytest" in cmd:
        print()

    proc = subprocess.run(cmd, cwd=cwd, shell=True,
             check=False, text=True, capture_output=capture)
    code = proc.returncode
    stdout = proc.stdout
    stderr = proc.stderr
    if not capture or stderr:
        print()
    if code != 0:
        err = f"[{code}]: {cmd} {stderr}"
        raise RuntimeError(err)

    if capture:
        for line in stdout.splitlines():
            print(line)
            time.sleep(0.005)
        print()
    return code


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

    home = Path.home()
    bin_dir = Path(target_dir).expanduser() if target_dir else \
        (home / ".local" / "bin")

    def shim_specs() -> list[tuple[Path, str, int | None]]:
        if os.name == "nt":
            return [
                (bin_dir / "git-pnp.cmd", "@echo off\r\npython -m pnp %*\r\n", None),
                (bin_dir / "git-pnp", "#!/usr/bin/env sh\nexec python -m pnp \"$@\"\n", 0o755),
            ]
        return [
            (bin_dir / "git-pnp", "#!/usr/bin/env sh\nexec python -m pnp \"$@\"\n", 0o755),
        ]

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
        "check_json", "strict", "tag_prefix", "tag_message",
        "edit_message", "editor", "tag_sign", "tag_bump", "doctor",
        "doctor_json", "doctor_report", "show_config", "install_git_ext",
        "uninstall_git_ext", "git_ext_dir", "machete_status",
        "machete_sync", "machete_traverse",
    ]
    effective = {k: getattr(args, k, None) for k in keys}
    sources = getattr(args, "_pnp_config_sources", None)
    if isinstance(sources, dict):
        effective["_sources"] = {k: sources.get(k, "default") for k in keys}
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
