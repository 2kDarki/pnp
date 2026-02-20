"""Helper functions extracted from cli entrypoint."""
from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
import argparse
import shutil
import shlex
import time
import json
import os
import re

from . import _constants as const
from . import utils


def command_exists(name: str) -> bool:
    """Return True if executable is available in PATH."""
    return shutil.which(name) is not None


def run_command(args: list[str], cwd: str | None = None
               ) -> subprocess.CompletedProcess[str]:
    """Run a command and capture text output."""
    return subprocess.run(args, cwd=cwd, check=False,
           capture_output=True, text=True)


def run_git(repo: str, args: list[str]) -> subprocess.CompletedProcess[str]:
    """Run `git -C <repo> ...` and capture output."""
    return run_command(["git", "-C", repo, *args])


def run_machete(repo: str, dry_run: bool,
                machete_sync: bool,
                machete_traverse: bool,
                out: utils.Output,
                step_idx: int | None = None
               ) -> tuple[str | None, utils.StepResult]:
    """Run git-machete status/traverse operations."""
    if not command_exists("git-machete"):
        return "git-machete not found in PATH", \
               utils.StepResult.ABORT

    commands: list[tuple[str, list[str]]] = []
    commands.append(("status", ["git", "machete", "status"]))
    if machete_sync:
        commands.append(("traverse --fetch --sync",
            ["git", "machete", "traverse", "--fetch",
            "--sync"]))
    elif machete_traverse:
        commands.append(("traverse",
            ["git", "machete", "traverse"]))

    for label, cmd in commands:
        if dry_run:
            out.info(const.DRYRUN + "would run: "
               + " ".join(cmd), step_idx=step_idx)
            continue
        cp = run_command(cmd, cwd=repo)
        if cp.returncode != 0:
            detail = cp.stderr.strip() or cp.stdout.strip() \
                  or f"git machete {label} failed"
            return detail, utils.StepResult.ABORT
        out.success(f"git machete {label}: ok",
            step_idx=step_idx)
    return None, utils.StepResult.OK


def run_hook(cmd: str, cwd: str, dryrun: bool,
             no_transmission: bool = False) -> int:
    """Run a validated hook command safely with optional dry-run."""
    if re.search(r"[$&;|><`()]", cmd):
        err = f"rejected potentially unsafe hook: {cmd!r}"
        raise ValueError(err)

    exclude = "drace", "pytest"
    capture = not no_transmission \
          and not utils.any_in(exclude, eq=cmd)

    parts  = cmd.split("::")
    prefix = "run"
    if len(parts) == 2: prefix, cmd = parts
    args = cmd.split()
    if not args: raise ValueError("hook command is empty")

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
    m   = utils.wrap(f"[{prefix}] {cmd}{add}")
    utils.transmit(m, fg=const.GOOD)
    if dryrun: return 0

    if "pytest" in cmd: print()

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
            if not segment.strip(): continue
            try:
                norm_segment = os.path.normcase(str(Path(segment).expanduser().resolve()))
            except OSError: continue
            if norm_segment == norm_target: return True
        return False

    home    = Path.home()
    bin_dir = Path(target_dir).expanduser() if target_dir \
         else (home / ".local" / "bin")

    def shim_specs() -> list[tuple[Path, str, int | None]]:
        if os.name == "nt":
            return [
                (bin_dir / "git-pnp.cmd",
                "@echo off\r\npython -m pnp %*\r\n", None),
                (bin_dir / "git-pnp", 
                "#!/usr/bin/env sh\nexec python -m "
                "pnp \"$@\"\n", 0o755),
            ]
        return [
            (bin_dir / "git-pnp", "#!/usr/bin/env sh\nexec "
            "python -m pnp \"$@\"\n", 0o755),
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
        "path", "batch_commit", "hooks", "changelog_file",
        "push", "publish", "remote", "force",
        "no_transmission", "quiet", "plain", "verbose",
        "debug", "auto_fix", "dry_run", "ci", "interactive",
        "gh_release", "gh_repo", "gh_token", "gh_draft",
        "gh_prerelease", "gh_assets", "check_only",
        "check_json", "strict", "tag_prefix", "tag_message",
        "edit_message", "editor", "tag_sign", "tag_bump",
        "doctor", "doctor_json", "doctor_report",
        "show_config", "install_git_ext",
        "uninstall_git_ext", "git_ext_dir", "machete_status",
        "machete_sync", "machete_traverse",
    ]
    effective = {k: getattr(args, k, None) for k in keys}
    sources   = getattr(args, "_pnp_config_sources", None)
    if isinstance(sources, dict):
        effective["_sources"] = {
            k: sources.get(k, "default") for k in keys
        }
    files = getattr(args, "_pnp_config_files", None)
    if isinstance(files, dict):
        effective["_config_files"] = files
    diagnostics = getattr(args, "_pnp_config_diagnostics",
                  None)
    if isinstance(diagnostics, list):
        effective["_config_diagnostics"] = diagnostics
    if isinstance(effective.get("gh_token"), str) and effective["gh_token"]:
        effective["gh_token"] = "***redacted***"
    out.raw(json.dumps(effective, indent=2, sort_keys=True))
    return 0


def cleanup_temp_files(paths: list[str]) -> None:
    """Best-effort cleanup of temporary files."""
    for path in paths:
        try: os.unlink(path)
        except OSError: continue


def git_core_editor(repo: str | None) -> str | None:
    """Resolve `git config core.editor` for a repository."""
    if not repo: return None
    cp = subprocess.run(
        ["git", "-C", repo, "config", "--get", "core.editor"],
        check=False,
        capture_output=True,
        text=True,
    )
    if cp.returncode != 0: return None
    editor = cp.stdout.strip()
    return editor or None


def resolve_editor_command(preferred: str | None,
                           repo: str | None = None) -> list[str]:
    """Return editor command honoring CLI/env/git fallbacks."""
    candidates = [
        preferred,
        os.environ.get("PNP_EDITOR"),
        os.environ.get("GIT_EDITOR"),
        git_core_editor(repo),
        os.environ.get("VISUAL"),
        os.environ.get("EDITOR"),
    ]
    if os.name == "nt": candidates.append("notepad")
    else: candidates.extend(("nano", "vi"))

    seen: set[str] = set()
    for candidate in candidates:
        if not candidate: continue
        value = candidate.strip()
        if not value or value in seen: continue
        seen.add(value)
        try:
            parts = shlex.split(value, posix=(os.name != "nt"))
        except ValueError: parts = [value]
        if not parts: continue
        binary = parts[0]
        if os.path.isabs(binary) or shutil.which(binary):
            return parts
    raise RuntimeError(
        "no editor found; set --editor, PNP_EDITOR, GIT_EDITOR, VISUAL, or EDITOR"
    )


def edit_message_in_editor(initial: str, kind: str,
                           editor: list[str],
                           out: utils.Output,
                           step_idx: int | None = None
                           ) -> tuple[str, str]:
    """Open editor using a temp file and return (message, temp_path)."""
    fd, path = tempfile.mkstemp(prefix="pnp-msg-", suffix=".txt")
    os.close(fd)
    header = [
        initial.strip(),
        "",
        f"# pnp {kind} message editor",
        "# Lines starting with '#' are ignored.",
        "# Save and close to continue.",
    ]
    Path(path).write_text("\n".join(header) + "\n", encoding="utf-8")
    out.info(f"opening editor: {' '.join(editor)}", step_idx=step_idx)
    utils.suspend_console()
    try: cp = subprocess.run([*editor, path], check=False)
    finally: utils.resume_console()
    if cp.returncode != 0:
        raise RuntimeError(f"editor exited with status {cp.returncode}")
    raw  = Path(path).read_text(encoding="utf-8")
    text = "\n".join(
        line for line in raw.splitlines()
        if not line.lstrip().startswith("#")
    ).strip()
    if not text:
        out.warn("empty editor message; using generated message", step_idx=step_idx)
        return initial, path
    return text, path


def git_head(path: str) -> str | None:
    """Return HEAD sha or None."""
    cp = subprocess.run(
        ["git", "-C", path, "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    if cp.returncode != 0: return None
    head = cp.stdout.strip()
    return head or None


def rollback_unstage(path: str, out: utils.Output,
                     step_idx: int | None = None) -> None:
    """Attempt to unstage index after a failed commit sequence."""
    cp = subprocess.run(
        ["git", "-C", path, "reset"],
        check=False,
        capture_output=True,
        text=True,
    )
    if cp.returncode == 0:
        out.warn("rollback: unstaged index after failure", step_idx=step_idx)
    else:
        out.warn("rollback failed: unable to unstage index", step_idx=step_idx)


def rollback_delete_tag(repo: str, tag: str, out: utils.Output,
                        step_idx: int | None = None) -> None:
    """Attempt to delete a local tag after failed remote push."""
    cp = subprocess.run(
        ["git", "-C", repo, "tag", "-d", tag],
        check=False,
        capture_output=True,
        text=True,
    )
    if cp.returncode == 0:
        out.warn(f"rollback: removed local tag {tag!r}", step_idx=step_idx)
    else:
        out.warn(
            f"rollback failed: unable to remove local tag {tag!r}",
            step_idx=step_idx,
        )
