"""
Generate a simple changelog from commits between two refs. Uses git log --pretty=format.
"""

# ======================= STANDARDS =======================
from datetime import datetime
import subprocess
import sys

# ==================== THIRD-PARTIES ======================
from tuikit.logictools import any_in

# ======================== LOCALS =========================
from .handlers import giterr


def gen_changelog(path: str, since: str|None,
                  until: str|None = "HEAD") -> str:
    rng = f"{since}..{until}" if since else until
    cmd = ["git", "log", "--pretty=format:%h %s (%an)", rng]
    proc = subprocess.run(cmd, cwd=path, text=True, 
           capture_output=True)
    
    if proc.returncode != 0:
        if any_in("-i", "--interactive", eq=sys.argv):
            info = [path, gen_changelog, path, since, until]
            out = giterr(proc.stderr, info)
            if out != 1: return out               
        err = proc.stderr or ""
        raise RuntimeError(f"git log failed: {err}")
    
    timestamp = datetime.now().isoformat()[:-7]
    entry = f"Changelog - [{timestamp}]"
    out = proc.stdout.strip()
    if not out: return f"{entry}\n- no notable changes\n"
    lines = ["- " + line for line in out.splitlines()]
    content = "\n".join(lines)
    return f"{entry}\n{content}\n"
