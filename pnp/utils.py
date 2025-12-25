"""Module to keep communication with externals isolated"""

# ======================= STANDARDS ========================
from dataclasses import dataclass
from pathlib import Path
import subprocess
import sys

# ===================== THIRD-PARTIES ======================
from tuikit.textools import wrap_text, style_text as color
from tuikit.textools import transmit as _transmit, pathit
from tuikit.logictools import any_in
from tuikit.listools import choose

# ======================== LOCALS ==========================
from ._constants import *


def auto(text: str) -> str:
    sfx = color("[auto-fix]", GOOD)
    return f"{sfx} {text}"


def gen_changelog(path: str, since: str|None,
                  until: str|None = "HEAD") -> str:
    rng = f"{since}..{until}" if since else until
    cmd = ["git", "log", "--pretty=format:%h %s (%an)", rng]
    proc = subprocess.run(cmd, cwd=path, text=True, 
           capture_output=True)
    
    if proc.returncode != 0:
        raise RuntimeError(f"git log failed: {proc.stderr}")
    
    out = proc.stdout.strip()
    if not out: return f"- no notable changes\n"
    lines = ["- " + line for line in out.splitlines()]
    content = "\n".join(lines)
    return f"{content}\n"


def retrieve_latest_changelog(log_file: Path) -> str:
    if not log_file.exists(): return ""

    entries = log_file.read_text().split('------| ')
    if len(entries) < 2: return ""
    return '------| ' + entries[-1].strip()


def to_list(array: list) -> str:
    text = ""
    for i, item in enumerate(array):
        item   = item.split("::")[-1]
        pfx    = f"      {i + 1}."
        indent = len(pfx) + 2
        text  += pfx + " " + wrap_text(f"{item}\n", indent,
                inline=True, order=pfx)
    return text


def wrap(text:str) -> str:
    return wrap_text(text, I, inline=True, order=APP)


def transmit(*text: tuple[str], fg: str = PROMPT,
             quiet: bool = False) -> None:
    if quiet: return
    print(PNP, end="")
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

    def info(self, msg: str):
        transmit(msg, fg=INFO, quiet=self.quiet)

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
