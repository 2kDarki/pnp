"""Constants across pnp."""


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
PLAIN                   = False
DEBUG                   = False
AUTOFIX                 = False
CI_MODE                 = True
DRY_RUN                 = False
QUIET                   = False
NO_TRANSMISSION         = False
GH_REPO                 = None
ALLOW_SAFE_RESET        = False
ALLOW_DESTRUCTIVE_RESET = False


def sync_runtime_flags(args: Namespace) -> None:
    """Synchronize runtime flags from parsed CLI args."""
    global PLAIN, DEBUG, AUTOFIX, CI_MODE, DRY_RUN, QUIET
    global NO_TRANSMISSION, GH_REPO, ALLOW_SAFE_RESET
    global ALLOW_DESTRUCTIVE_RESET

    PLAIN           = bool(getattr(args, "plain", False))
    DEBUG           = bool(getattr(args, "debug", False))
    AUTOFIX         = bool(getattr(args, "auto_fix", False)
                    or getattr(args, "batch_commit", False))
    DRY_RUN         = bool(getattr(args, "dry_run", False))
    QUIET           = bool(getattr(args, "quiet", False))
    NO_TRANSMISSION = bool(getattr(args, "no_transmission", False))
    GH_REPO         = getattr(args, "gh_repo", None)
    CI_MODE         = bool(getattr(args, "ci", False)
                    or getattr(args, "quiet", False)
                    or getattr(args, "plain", False)
                    or not getattr(args, "interactive", False))
    ALLOW_SAFE_RESET = bool(getattr(args, "safe_reset", False))
    ALLOW_DESTRUCTIVE_RESET = bool(
        getattr(args, "destructive_reset", False)
    )
