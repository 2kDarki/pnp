"""Constants across pnp."""
from __future__ import annotations

from argparse import Namespace

from tuikit.textools import style_text as color


GITHUB         = "https://api.github.com"
GITHUB_UPLOADS = "https://uploads.github.com"
DRYRUN         = color("[dry-run] ", "gray")
CURSOR         = color("  >>> ", "magenta")
GOOD           = "green"
BAD            = "red"
PROMPT         = "yellow"
INFO           = "cyan"
SPEED          = 0.0075
HOLD           = 0.01
APP            = "[pnp]"
PNP            = color(f"{APP} ", "magenta")
I              = 6

# Runtime flags: initialized once per invocation by CLI.
PLAIN           = False
DEBUG           = False
AUTOFIX         = False
CI_MODE         = True
DRY_RUN         = False
QUIET           = False
NO_TRANSMISSION = False
GH_REPO         = None


def sync_runtime_flags(args: Namespace) -> None:
    """Synchronize runtime flags from parsed CLI args."""
    global PLAIN, DEBUG, AUTOFIX, CI_MODE, DRY_RUN, QUIET
    global NO_TRANSMISSION, GH_REPO

    PLAIN           = bool(args.plain)
    DEBUG           = bool(args.debug)
    AUTOFIX         = bool(args.auto_fix or args.batch_commit)
    DRY_RUN         = bool(args.dry_run)
    QUIET           = bool(args.quiet)
    NO_TRANSMISSION = bool(args.no_transmission)
    GH_REPO         = args.gh_repo
    CI_MODE         = bool(args.ci or args.quiet or args.plain
                   or not args.interactive)
