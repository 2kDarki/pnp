"""Constants across pnp"""
import sys

from tuikit.textools import style_text as color
from tuikit.logictools import any_in


DRYRUN  = color("[dry-run] ", "gray")
CURSOR  = color("  >>> ", "magenta")
GOOD    = "green"
BAD     = "red"
PROMPT  = "yellow"
INFO    = "cyan"
SPEED   = 0.0075
HOLD    = 0.01
APP     = "[pnp]"
PNP     = color(f"{APP} ", "magenta")
I       = 6
AUTOFIX = any_in("-a", "--auto-fix", eq=sys.argv)
CI_MODE = any_in("--ci", "-q", "--quiet", eq=sys.argv) \
       or not any_in("-i", "--interactive", eq=sys.argv)
