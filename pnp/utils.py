"""Module to keep communication with externals isolated."""
# ======================= STANDARDS ========================
from enum import Enum, auto as auto_enum
from typing import NoReturn, Protocol
from dataclasses import dataclass
from types import ModuleType
from pathlib import Path
import subprocess
import shutil
import sys
import os
import re

# ===================== THIRD-PARTIES ======================
from tuikit.textools import wrap_text, style_text as color
from tuikit.textools import transmit as _transmit, pathit
from tuikit.logictools import any_in


# ======================== LOCALS ==========================
from . import _constants as const
from ._constants import *

PROJECT_MARKERS = (
    "pyproject.toml",
    "package.json",
    "go.mod",
    "Cargo.toml",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "composer.json",
    "Gemfile",
    "mix.exs",
    "Project.toml",
)


class MessageSink(Protocol):
    def add_message(self, idx: int | None, msg: str,
                    fg: str = PROMPT, prfx: bool = True
                   ) -> None: ...


_active_console: MessageSink | None = None
_console_stack: list[MessageSink | None] = []


def bind_console(console: MessageSink | None) -> None:
    global _active_console
    _active_console = console


def suspend_console() -> None:
    """Pause active sink when external apps need terminal control."""
    global _active_console
    current = _active_console
    _console_stack.append(current)
    if current is None: return
    suspend = getattr(current, "suspend", None)
    if callable(suspend): suspend()
    else: bind_console(None)


def resume_console() -> None:
    """Restore previously suspended sink."""
    if not _console_stack: return

    previous = _console_stack.pop()
    if previous is None: bind_console(None); return

    resume = getattr(previous, "resume", None)
    if callable(resume): resume()
    else: bind_console(previous)


def get_shell() -> str | None:
    return shutil.which("bash") \
        or shutil.which("zsh") \
        or shutil.which("sh")


def find_repo(path: str, batch: bool = False,
              return_none: bool = False
             ) -> str | list[str | None] | NoReturn:
    """Walks until .git present else raises RuntimeError"""
    def found(path: str) -> str:
        path = pathit(path)
        return wrap(f"found repository in {path!r}. "
             + "Is it the correct repository? [y/n]")

    if batch: curs = []
    elif return_none: return [None]

    Output(quiet=const.QUIET).raw()

    # walk up
    cur = os.path.abspath(path)
    while True:
        if os.path.isdir(os.path.join(cur, '.git')):
            if batch: curs.append(cur); break
            if const.CI_MODE: return cur
            if intent(found(cur), "y", "return"): return cur
        parent = os.path.dirname(cur)
        if parent == cur: break
        cur = parent

    # walk down one level for performance reasons
    cur   = os.path.abspath(path)
    paths = [f"{cur}{os.sep}{c}" for c in os.listdir(cur)]

    for cur in paths:
        if os.path.isdir(os.path.join(cur, '.git')):
            if batch: curs.append(cur); continue
            if const.CI_MODE: return cur
            if intent(found(cur), "y", "return"): return cur

    if batch and curs:
        # Preserve discovery order while removing duplicates.
        return list(dict.fromkeys(curs))
    raise RuntimeError("[404] repo not found")


def has_project_marker(path: str) -> bool:
    """Return True when `path` contains a known project manifest file."""
    return any(
        os.path.exists(os.path.join(path, marker))
        for marker in PROJECT_MARKERS
    )


def detect_subpackage(path: str, monorepo_path: str) -> str | None:
    """Find subpackage by checking common project marker files."""
    # if path contains a project marker, treat it as package root
    candidate = os.path.abspath(path)
    if has_project_marker(candidate):
        if candidate != monorepo_path: return candidate

    # else, try to find nearest folder with project marker
    # relative to monorepo root
    for root, _, files in os.walk(monorepo_path):
        if any(marker in files for marker in PROJECT_MARKERS):
            if candidate.startswith(root):
                if root != monorepo_path: return root
    return None


def import_deps(log_dir: Path) -> tuple[ModuleType, ModuleType]:
    """
    Dynamically import modules that rely on runtime state

    These imports depend on runtime setup (e.g. log directory).
    Deferring them ensures setup-dependent operations do not
    break at import time.

    Returns:
        tuple: (gitutils, resolver) modules
    """
    from . import resolver
    from . import gitutils

    resolver.configure_logger(log_dir)
    return gitutils, resolver


def bump_semver_from_tag(tag: str, bump: str,
                         prefix: str = 'v') -> str:
    """Bumps tag"""
    sem    = tag
    suffix = ""
    if tag.startswith(prefix): sem = tag[len(prefix):]
    if "-" in sem:
        sem, suffix = sem.split("-")
        suffix      = f"-{suffix}"

    m = re.match(r'(\d+)\.(\d+)\.(\d+)$', sem)
    if not m:  # start fresh
        if bump == 'patch': return f"{prefix}0.0.1{suffix}"
        if bump == 'minor': return f"{prefix}0.1.0{suffix}"
        if bump == 'major': return f"{prefix}1.0.0{suffix}"

    if m is not None:
        major, minor, patch = map(int, m.groups())

    if bump == 'patch': patch += 1
    if bump == 'minor': minor += 1; patch = 0
    if bump == 'major': major += 1; minor = 0; patch = 0
    return f"{prefix}{major}.{minor}.{patch}{suffix}"


def auto(text: str) -> str:
    sfx = color("[auto-fix]", GOOD)
    return f"{sfx} {text}"


def lines(cmd: list[str], cwd: str) -> list | list[str]:
    return subprocess.run(cmd, cwd=cwd, capture_output=True,
           text=True, check=True).stdout.strip().splitlines()


def get_changes(cwd: str) -> dict[str, list | list[str]]:
    changes: dict[str, list | list[str]] = {
        "added": [], "updated": [], "removed": []
    }
    try:
        cmd = ["git", "diff", "--name-status", "--cached"]
        cp = lines(cmd[:-1], cwd) or lines(cmd, cwd)
        for line in cp:
            marker, file = line.split()
            if marker == "A": action = "added"
            if marker == "M": action = "updated"
            if marker == "D": action = "removed"
            changes[action] += [file]
    except Exception: pass

    return changes


def classify_files(files: list[str]) -> list[str]:
    types = {
          "code": [".py", ".js", ".ts", ".go", ".sh",
                   ".java", ".c", ".cpp"],
          "docs": [".md", ".txt", ".rst"],
         "tests": ["test", "tests"],
        "config": [".toml", ".json", ".yaml", ".yml", ".ini"]
    }
    tags = set()

    for f in files:
        path = Path(f.lower())
        sfx  = path.suffix
        if any(part in str(path) for part in types["tests"]):
            tags.add("tests")
        elif sfx in types["code"]: tags.add("code")
        elif sfx in types["docs"]: tags.add("docs")
        elif sfx in types["config"]: tags.add("config")
        else: tags.add("misc")

    return list(tags)


def gen_commit_message(repo_root: str) -> str:
    message = f"{APP} auto commit — "
    changes = get_changes(repo_root)
    files: list[str] = []
    for group in changes.values(): files.extend(group)

    # Fallback if no files found (maybe blob recovery just
    # occurred)
    if not files: return message + "general update"

    if len(changes["added"]) < 4 and len(files) < 7:
        mapped = [
            ("added", changes["added"]),
            ("updated", changes["updated"]),
            ("removed", changes["removed"])
        ]

        msg = ""
        for (action, files) in mapped:
            if not files: continue
            sfx = "; " if msg else ""
            if len(files) > 1:
                sep = ", and " if len(files) > 2 else " and "
                text = ", ".join(files[:-1])
                text += sep + files[-1]
            else: text = files[0]
            msg += f"{sfx}{action}: {text}"

        return message + msg

    tags = classify_files(files)
    if not tags: return message + "misc changes"

    if len(tags) > 1:
        sep = ", and" if len(tags) > 2 else " and"
        text = ", ".join(sorted(tags[:-1]))
        text += f"{sep} {tags[-1]}"
    else: text = tags[0]

    return message + "updated " + text


def gen_changelog(path: str, since: str | None,
                  dry_run: str | None,
                  until: str = "HEAD") -> str:
    rng  = f"{since}..{until}" if since else until
    out = ""
    if const.DRY_RUN:
        cmd = ["git", "log", "--pretty=format:%h %s (%an)", rng]
        proc = subprocess.run(
            cmd,
            cwd=path,
            text=True,
            capture_output=True,
        )
        rc = int(proc.returncode)
        out = (proc.stdout or "").strip()
        err = (proc.stderr or "").strip()
    else:
        from . import gitutils
        rc, out = gitutils.run_git(
            ["log", "--pretty=format:%h %s (%an)", rng],
            cwd=path,
        )
        err = out.strip()
    if rc != 0:
        raise RuntimeError(f"git log failed: {err}")

    out = out.strip()
    if not out: return "- no notable changes\n"
    text = out.splitlines()[0].split()
    if not dry_run:
        code    = color(text[0], PROMPT)
        message = color(' '.join(text[1:-1]), GOOD)
    else:
        code    = color("dry0run", PROMPT)
        message = color(dry_run, GOOD)
    author = color(text[-1], INFO)
    return f"{code} {message} {author}\n"


def retrieve_latest_changelog(log_file: Path) -> str:
    if not log_file.exists(): return ""

    entries = log_file.read_text().split("------| ")
    if len(entries) < 2: return ""
    return "------| " + entries[-1].strip()


def to_list(array: list) -> str:
    text = ""
    for i, item in enumerate(array):
        item   = item.split("::")[-1]
        pfx    = f"      {i + 1}."
        indent = len(pfx) + 2
        text  += pfx + " " + wrap_text(f"{item}\n", indent,
                inline=True, order=pfx)
    return text


def wrap(text: str) -> str:
    return wrap_text(text, I, inline=True, order=APP)


def transmit(*text: str | tuple[str], fg: str = PROMPT,
             quiet: bool = False, prfx: bool = True,
             step_idx: int | None = None) -> None:
    if quiet: return

    msg    = " ".join(map(str, text))
    # --- TUI ACTIVE: Rich owns the terminal ---
    if _active_console is not None:
        # Pass raw text + style hints; let Rich render styling.
        _active_console.add_message(step_idx, msg, fg=fg, prfx=prfx)
        return

    # --- Plain terminal path (legacy behavior) ---
    if prfx: print(PNP, end="")

    _transmit(msg, speed=SPEED, hold=HOLD, hue=fg)


def intent(prompt: str, condition: str, action: str = "exit",
           space: bool = True) -> bool | None:
    transmit(prompt)
    _intent = input(CURSOR).strip().lower()
    if space: print()
    _intent = _intent[0] if _intent else "n"
    if action == "return": return _intent == condition
    if _intent != condition: sys.exit(1)
    return None


def get_log_dir(path: str) -> Path:
    log_dir = Path(path) / "pnplog"
    os.makedirs(log_dir, exist_ok=True)
    return log_dir


@dataclass
class Output:
    quiet: bool = False

    def success(self, msg: str, step_idx: int | None = None
               ) -> None:
        msg = msg if _active_console is not None else wrap(msg)
        transmit(msg, fg=GOOD, quiet=self.quiet,
            step_idx=step_idx)

    def info(self, msg: str, prefix: bool = True,
             step_idx: int | None = None) -> None:
        msg = wrap(msg) if const.PLAIN else msg
        transmit(msg, fg=INFO, quiet=self.quiet, prfx=prefix,
            step_idx=step_idx)

    def prompt(self, msg: str, fit: bool = True,
               step_idx: int | None = None) -> None:
        if fit and _active_console is None:
            msg = wrap(msg)
        transmit(msg, quiet=self.quiet, step_idx=step_idx)

    def warn(self, msg: str, fit: bool = True,
             step_idx: int | None = None) -> None:
        if fit and _active_console is None:
            msg = wrap(msg)
        transmit(msg, fg=BAD, step_idx=step_idx)

    def abort(self, msg: str | None = None, fit: bool = True,
              step_idx: int | None = None) -> NoReturn:
        if not msg: msg = "exiting..."
        self.warn(msg, fit, step_idx); sys.exit(1)

    def raw(self, *args: object, **kwargs: object) -> None:
        if not self.quiet: print(*args, **kwargs)  # type: ignore[call-overload]


class StepResult(Enum):
    OK    = auto_enum()
    DONE  = auto_enum()
    SKIP  = auto_enum()
    FAIL  = auto_enum()
    RETRY = auto_enum()
    ABORT = auto_enum()
