"""Outputs help message when invalid args are passed"""

# ====================== STANDARDS ========================
from typing import NoReturn
import sys
import os

# ==================== THIRD-PARTIES ======================
from tuikit.textools import style_text as color, transmit
from tuikit.textools import wrap_text as wrap, Align
from tuikit.logictools import any_in
from tuikit import console

# ======================== LOCALS =========================
from ._constants import SPEED, HOLD, BAD, GOOD as g
from . import utils


I               = 23  # Indented spaces for options
ALLOWED_OPTIONS = {
     "global": ["--push", "-p", "--publish", "-P",
                "--interactive", "-i", "--dry-run", "-d",
                "--ci", "--hooks", "--remote", "-r",
                "--changelog-file", "--no-transmission",
                "--auto-fix", "-a", "--quiet", "-q",
                "--force", "-f"],
     "github": ["--gh-release", "--gh-repo",
                "--gh-token", "--gh-draft", 
                "--gh-prerelease", "--gh-assets"],
    "tagging": ["--tag-bump", "--tag-prefix",
                "--tag-message", "--tag-sign"]}
H_FLAGS     = ["-h", "--h", "-help", "--help"]
ALL_ALLOWED = sum(ALLOWED_OPTIONS.values(), []) + H_FLAGS


def get_option(h_arg: str) -> str:
    if isinstance(h_arg, list): h_arg = h_arg[0]
    idx = sys.argv.index(h_arg)
    arg = sys.argv[idx - 1]
    if "=" in arg: return arg.split("=")[0]
    if arg.startswith("-"): return arg


def validate_options(get: bool = False) -> bool | NoReturn:
    """
Check if arguments provided are valid

Args:
    get: if True, returns a boolean of argument(s) validity
         else if an argument is invalid, prints help 
         message and exit, otherwise returns True
    """
    raw_args = sys.argv[1:]

    for arg in raw_args:
        if "=" in arg: base = arg.split("=", 1)[0]
        else: base = arg

        if base.startswith("-") and base not in \
                                     ALL_ALLOWED:
            if get: return False
            help_msg(found=True, option=arg)
    return True


def help_msg(found: bool = False,
             option: str | None = None) -> str | NoReturn:
    """
Conditionally prints help description

Behavior:
  - If no help flag present and options are valid -> 
    returns "" (no help)
  - If help requested and a known option is present in 
    argv -> show only its section
  - Otherwise, print full help and exit
    """
    argv    = sys.argv[1:]
    _help   = any(h in sys.argv for h in H_FLAGS)
 
    if not found and validate_options():
        if not _help:return ""

    location = None
    if _help:
        h_arg = next(a for a in sys.argv if a in H_FLAGS)
        h_option = get_option(h_arg)        
        for idx, (sect_name, opts) in enumerate(
                 ALLOWED_OPTIONS.items(), start=1):
            if h_option in opts:
                location = idx
                break

    h = "magenta"
    header = Align().center("《 PNP HELP 》", "=", h, g)
    print(f"\n{header}\n")

    # Section 1: Usage examples
    section = color("Usage examples:", "", "", True, True)
    print(f"{section}")
    print("    pnp --push --publish\n")
    print(wrap("pnp . --push --publish --gh-"
         + "release --gh-repo username/repo\n", 8, 4))
    print(wrap('pnp path/to/package --push --publish --'
         + 'hooks "pytest -q; flake8" --interactive',8, 4))

    # Section 2: Options & Commands
    section = color("Options & Commands:", bold=True, 
              underline=True)
    print(f"\n{section}\n")
    if option:
        utils.transmit(f"Invalid option: {option!r}\n", 
            fg=BAD)
    if location and h_option: print_help(location - 1)
    else:
        for _ in range(3): print_help(_)

    # Section 3: Tips
    section = color("Tips:", "", "", True, True)
    print(f"{section}")
    print(wrap("• Use --dry-run to see what would happen "
               "without making changes", 4, 2))
    print(wrap("• Use --interactive to confirm each step",
               4, 2))
    print(wrap("• Use --gh-prerelease or --gh-draft to "
               "control release visibility", 4, 2))
    print(wrap("• Ensure GITHUB_TOKEN is set for GitHub "
               "releases", 4, 2))
    print(wrap("• By default, pnp uses fail-fast mode. "
               "The workflow will exit on first failure "
               "unless --interactive is set", 4, 2))

    console.underline(hue=g, alone=True)
    sys.exit(0)


def desc(text: str) -> str:
    return wrap("use " + text, I, inline=True,
           order="   darkian standard   ")


def print_help(section:int = 0) -> None:
    """Prints options (Global, GitHub, or Tagging)"""
    if section == 0:  # Global options
        options = f"""{color(" 1. Global", "green")}
    Path (positional)  {desc("path/to/package (default: "
                       +"'.')")}
    Push               {desc("-p / --push to push "
                       +"commits")}
    Publish            {desc("-P / --publish to bump "
                       +"tags and push")}
    Remote push        {desc("-r / --remote NAME for "
                       +"remote name to push to (default: "
                       +"origin or branch upstream)")}
    Auto fix           {desc("-a / --auto-fix to "
                       +"automatically fix all errors "
                       +"encountered using the most sure "
                       +"fire method. NB: when an error "
                       +"that requires user input is "
                       +"encountered, the user will be "
                       +"asked for input if in interactive "
                       +"mode, otherwise it will abort "
                       +"workflow")}
    Changelog          {desc("--changelog-file path/to/"
                       +"file for writing generated "
                       +"changelog to file (default: "
                       +"changelog)")}
    Interactivity      {desc("-i / --interactive to be"
                       +" prompted when an issue occurs. "
                       +"Useful for handling mid-workflow"
                       +" issues. (NB: flag ignored if in"
                       +" CI mode)")}
    CI mode            {desc("--ci for non-interactive"
                       +" workflow")}
    Quiet mode         {desc("-q / --quiet for silent "
                       +"workflows. NB: since this disables "
                       +"all output, this mode is a "
                       +"fail-fast-type mode — it will exit "
                       +"on first issue unless auto-fix is "
                       +"set, which will exit on input-"
                       +"dependent errors")}
    Dry run mode       {desc("-d / --dry-run to simulate "
                       +"actions")}
    Pre-push hooks     {desc('--hooks "command1; command2"'
                       +'to run pre-push hooks. A '
                       +'command can include type hint, '
                       +'e.g., "lint::drace lint ." or '
                       +'"test::pytest ."')}
    Hook output        {desc("--no-transmission to "
                       +"print output without effects")}
        """ 
    elif section == 1:  # GitHub options
        options = f"""{color(" 2. Github", "green")}
    Release            {desc("--gh-release to create a"
                       +" release from tag")}
    Repo target        {desc("--gh-repo OWNER/REPO for "
                       +"setting repo. Useful when "
                       +"initializing a new repo or when "
                       +"fixing errors that require you "
                       +"to set a connection with a repo "
                       +"but you don't want to be asked "
                       +"to provide username and repo "
                       +"name when required by the error "
                       +"handler")}
    Token source       {desc("--gh-token TOKEN or set "
                       +"GITHUB_TOKEN env variable")}
    Draft              {desc("--gh-draft for draft release")}
    Mark prerelease    {desc("--gh-prerelease to mark "
                       +"release as prerelease")}
    Attach files       {desc('--gh-assets "file1, file2'
                       +', ..." for including files such as '
                       +'.whl files (also supports '
                       +'wildcards, e.g., *.whl)')}
        """
    else:  # Tagging options
        options = f"""{color(" 3. Tagging", "green")}
    Tag prefix         {desc("--tag-prefix PREFIX to set tag"
                       +" prefix (default: 'v')")}
    Tag bump           {desc("--tag-bump major|minor|patch "
                       +"(default: patch)")}
    Tag message        {desc("--tag-message <message>")}
    Sign tag           {desc("--tag-sign for GPG signing")}
        """
    print(options)
