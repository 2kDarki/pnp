"""Constants across pnp"""
import sys

from tuikit.textools import style_text as color
from tuikit.logictools import any_in


def expand_args() -> None:
    short = set()
    for argv in sys.argv[1:]:
        if argv.count("-") == 1: short.add(argv)

    args = {"a", "b", "i", "q", "v"}

    for argv in short:
        for arg in args:
            if arg in argv and f"-{arg}" not in sys.argv:
                sys.argv.append(f"-{arg}")


expand_args()
GITHUB  = "https://api.github.com"
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
DEBUG   = any_in("-d", "--debug", eq=sys.argv)
AUTOFIX = any_in("-a", "--auto-fix", "-b", "--batch-commit",
          eq=sys.argv)
CI_MODE = any_in("--ci", "-q", "--quiet", eq=sys.argv) \
       or not any_in("-i", "--interactive", eq=sys.argv)
