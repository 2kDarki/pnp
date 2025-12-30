"""Module to keep communication with externals isolated"""

# ======================= STANDARDS ========================
from dataclasses import dataclass
from typing import NoReturn
from pathlib import Path
import subprocess
import sys
import os
import re

# ===================== THIRD-PARTIES ======================
from tuikit.textools import wrap_text, style_text as color
from tuikit.textools import transmit as _transmit, pathit
from tuikit.logictools import any_in

# ======================== LOCALS ==========================
from ._constants import *


def find_repo(path: str) -> str | NoReturn:
    """Walks until .git present else raises RuntimeError"""
    # Walking is relative to current working directory
    def found(path):
        path = pathit(path)
        return wrap(f"found repository in {path!r}. "
             + "Is it the correct repository? [y/n]")

    print()
    # walk up
    cur = os.path.abspath(path)
    while True:
        if os.path.isdir(os.path.join(cur, '.git')):
            if CI_MODE: return path
            yes = intent(found(cur), "y", "return")
            if yes: return cur
        parent = os.path.dirname(cur)
        if parent == cur: break
        cur = parent

    # walk down one level for performance reasons
    cur   = os.path.abspath(path)
    paths = [f"{cur}{os.sep}{c}" for c in os.listdir(cur)]

    for path in paths:
        if os.path.isdir(os.path.join(path, '.git')):
            if CI_MODE: return path
            yes = intent(found(path), "y", "return")
            if yes: return path

    raise RuntimeError


def detect_subpackage(path: str, monorepo_path: str) -> str:
    """Find subpackage by checking if pyproject.toml is present"""
    # if path contains pyproject.toml, treat it as package
    # root
    candidate = os.path.abspath(path)
    if os.path.exists(os.path.join(candidate, 'pyproject.toml')):
        if candidate != monorepo_path: return candidate

    # else, try to find nearest folder with pyproject
    # relative to monorepo root
    for root, _, files in os.walk(monorepo_path):
        if 'pyproject.toml' in files:
            if candidate.startswith(root):
                if root != monorepo_path: return root


def import_deps():
    """
    Dynamically import modules that rely on runtime state

    These imports depend on `log_dir` being initialized, as
    the modules internally use it for logging or error
    handling. Deferring them ensures that setup-dependent
    operations don't break on initial load

    Returns:
        tuple: (gitutils, giterr) modules
    """
    from .handlers import giterr
    from . import gitutils
    return gitutils, giterr


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
    changes = {"added": [], "updated": [], "removed": []}
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


def classify_files(files):
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


def gen_commit_message(repo_root):
    message = f"{APP} auto commit — "
    changes = get_changes(repo_root)
    files   = []
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
                text  = ", ".join(files[:-1])
                text += sep + files[-1]
            else: text = files[0]
            msg += f"{sfx}{action}: {text}"

        return message + msg

    tags = classify_files(files)
    if not tags: return message + "misc changes"

    if len(tags) > 1:
        sep = ", and" if len(files) > 2 else " and"
        text = ", ".join(sorted(tags[:-1]))
        text += f"{sep} {tags[-1]}"
    else: text = tags[0]

    return message + text + " updated"


def gen_changelog(path: str, since: str | None,
                  until: str | None = "HEAD") -> str:
    rng  = f"{since}..{until}" if since else until
    cmd  = ["git", "log", "--pretty=format:%h %s (%an)", rng]
    proc = subprocess.run(cmd, cwd=path, text=True,
           capture_output=True)

    if proc.returncode != 0:
        raise RuntimeError(f"git log failed: {proc.stderr}")

    out = proc.stdout.strip()
    if not out: return "- no notable changes\n"
    log_text = out.splitlines()[0].split()
    code     = color(log_text[0], PROMPT)
    msg      = color(' '.join(log_text[1:-1]), GOOD)
    author   = color(log_text[-1], INFO)
    return f"{code} {msg} {author}\n"


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


def transmit(*text: tuple[str], fg: str = PROMPT,
             quiet: bool = False, prfx: bool = True) -> None:
    if quiet: return
    if prfx: print(PNP, end="")
    _transmit(*text, speed=SPEED, hold=HOLD, hue=fg)


def intent(prompt, condition, action="exit", space=True):
    transmit(prompt)
    _intent = input(CURSOR).strip().lower()
    if space: print()
    _intent = _intent[0] if _intent else "n"
    if action == "return": return _intent == condition
    if _intent != condition: sys.exit(1)


def get_log_dir(path: str) -> Path:
    log_dir = Path(path) / "pnplog"

    with open(Path().cwd() / "log_dir", "w") as f:
        f.write(str(log_dir))

    return log_dir


@dataclass
class Output:
    quiet: bool = False

    def success(self, msg: str):
        transmit(wrap(msg), fg=GOOD, quiet=self.quiet)

    def info(self, msg: str, prefix: bool = True):
        transmit(msg, fg=INFO, quiet=self.quiet, prfx=prefix)

    def prompt(self, msg: str, fit=True):
        if fit: msg = wrap(msg)
        transmit(msg, quiet=self.quiet)

    def warn(self, msg: str, fit=True):
        if fit: msg = wrap(msg)
        transmit(msg, fg=BAD)

    def abort(self, msg: str | None = None, fit=True):
        if not msg: msg = "exiting..."
        self.warn(msg, fit); sys.exit(1)

    def raw(self, *args, **kwargs):
        if not self.quiet:
            print(*args, **kwargs)
