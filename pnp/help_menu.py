"""Outputs help message when invalid args are passed"""

# ==================== THIRD-PARTIES ======================
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
                "--interactive", "-i", "--dry-run",
                "--ci", "--hooks", "--remote",
                "--changelog-file", "--no-transmission"],
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

def print_help(section:int = 0) -> None:
    """Prints options (Global, GitHub, or Tagging)"""
    if section == 0:  # Global options
        options = f"""{color(" 1. Global", "green")}
    Path (positional)  {wrap("path/to/package (default: "
                       +"'.')", I, inline=True, 
                       order="    Path (positional) ")}
    Push               {wrap("use -p / --push to push "
                       +"commits", I, inline=True, 
                       order="    Push              ")}
    Publish            {wrap("use -P / --publish to bump "
                       +"tags and push", I, inline=True, 
                       order="    Publish           ")}
    Remote push        {wrap("--remote NAME for remote "
                       +"name to push to (default: origin "
                       +"or branch upstream)", I, 
                       inline=True, 
                       order="    Publish           ")}
    Changelog          {wrap("--changelog-file path/to/"
                       +"file for writing generated "
                       +"changelog to file (default: "
                       +"chlog)", I, inline=True, 
                       order="    Publish           ")}
    Interactivity      {wrap("use -i / --interactive to be"
                       +" prompted when an issue occurs. "
                       +"Useful for handling mid-workflow"
                       +" issues. (NB: flag ignored if in"
                       +" CI mode)", I, inline=True, 
                       order="    Interactivity     ")}
    CI mode            {wrap("use --ci for non-interactive"
                       +" automation", I, inline=True, 
                       order="    CI mode           ")}
    Dry run mode       {wrap("use --dry-run to simulate "
                       +"actions", I, inline=True, 
                       order="    Dry run mode      ")}
    Pre-push hooks     {wrap('use --hooks "command1; '
                       +'command2"', I, inline=True, 
                       order="    Pre-push hooks    ")}
    Hook output        {wrap("use --no-transmission to "
                       +"print output at once", I, 
                       inline=True, 
                       order="    hook output       ")}
        """ 
    elif section == 1:  # GitHub options
        options = f"""{color(" 2. Github", "green")}
    Release            {wrap("use --gh-release to create a"
                       +" release from tag",I, inline=True, 
                       order="    Release           ")}
    Repo target        {wrap("use --gh-repo OWNER/REPO", I, 
                       inline=True, 
                       order="    Repo target       ")}
    Token source       {wrap("use --gh-token or set "
                       +"GITHUB_TOKEN env variable", I, 
                       inline=True,
                       order="    Token source      ")}
    Draft              {wrap("use --gh-draft for draft "
                       +"release", I, inline=True, 
                       order="    Draft             ")}
    Mark prerelease    {wrap("use --gh-prerelease", I, 
                       inline=True, 
                       order="    Mark prerelease   ")}
    Attach files       {wrap('use --gh-assets "file1,file2'
                       +',..."', I, inline=True, 
                       order="    Attach files      ")}
        """
    else:  # Tagging options
        options = f"""{color(" 3. Tagging", "green")}
    Tag prefix         {wrap("--tag-prefix (default: 'v')", 
                       I, inline=True, 
                       order="    Tag prefix        ")}
    Tag bump           {wrap("--tag-bump major|minor|"
                       +"patch (default: patch)", I, 
                       inline=True, 
                       order="    Tag bump          ")}
    Tag message        {wrap("--tag-message <message>", I, 
                       inline=True, 
                       order="    Tag message       ")}
    Sign tag           {wrap("--tag-sign for GPG signing", 
                       I, inline=True,
                       order="    Sign tag          ")}
        """
    print(options)
