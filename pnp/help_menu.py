"""Custom help output for pnp."""

# ====================== STANDARDS ========================
from typing import NoReturn
import sys

# ==================== THIRD-PARTIES ======================
from tuikit.textools import wrap_text as wrap, Align
from tuikit.textools import style_text as color
from tuikit import console

# ======================== LOCALS =========================
from ._constants import GOOD
from . import utils


INDENT          = 23  # Indented spaces for options
ALLOWED_OPTIONS = {
     "global": ["--push", "-p", "--publish", "-P",
                "--interactive", "-i", "--dry-run", "-n",
                "--ci", "--hooks", "--remote", "-r",
                "--changelog-file", "--no-transmission",
                "--auto-fix", "-a", "--quiet", "-q",
                "--force", "-f", "--debug", "-d", "-v",
                "--verbose", "--batch-commit", "-b",
                "--plain", "--doctor", "--version",
                "--check-only", "--strict",
                "--check-json",
                "--show-config", "--doctor-json",
                "--doctor-report",
                "--install-git-ext", "--uninstall-git-ext",
                "--git-ext-dir", "--status", "-s",
                "--sync", "-S", "--traverse", "-t"],
     "github": ["--gh-release", "--gh-repo",
                "--gh-token", "--gh-draft",
                "--gh-prerelease", "--gh-assets"],
    "tagging": ["--tag-bump", "--tag-prefix",
                "--tag-message", "--edit-message",
                "--editor", "--tag-sign"]}
H_FLAGS     = ["-h", "--h", "-help", "--help"]


def get_option(h_arg: str) -> str:
    if isinstance(h_arg, list): h_arg = h_arg[0]
    idx = sys.argv.index(h_arg)
    if idx == 0: return ""
    arg = sys.argv[idx - 1]
    if "=" in arg: return arg.split("=")[0]
    if arg.startswith("-"): return arg
    return ""


def help_msg(found: bool = False,
             option: str | None = None) -> str | NoReturn:
    """
    Conditionally prints help description.

    Behavior:
      - If no help flag present -> returns parser description
      - If help requested and a known option is present in
        argv -> show only its section
      - Otherwise, print full help and exit
    """
    _help = any(h in sys.argv for h in H_FLAGS)

    if not _help: return "pnp git automation CLI"

    location = None
    if _help:
        h_arg    = next(a for a in sys.argv if a in H_FLAGS)
        h_option = get_option(h_arg)
        for idx, (sect_name, opts) in enumerate(
                 ALLOWED_OPTIONS.items(), start=1):
            if h_option in opts: location = idx; break

    hue    = "magenta"
    header = Align().center("《 PNP HELP 》", "=", hue, GOOD)
    print(f"\n{header}\n")

    # Section 1: Usage examples
    section = color("Usage examples:", "", "", True, True)
    print(f"{section}")
    print("    pnp --push --publish\n")
    print(wrap("pnp . --push --publish --gh-"
         + "release --gh-repo username/repo\n", 8, 4))
    print(wrap('pnp path/to/package --push --publish --'
        'hooks "pytest -q; flake8" --interactive', 8, 4))
    print(wrap("pnp --doctor", 8, 4))
    print(wrap("pnp . --check-only --strict --push --publish", 8, 4))
    print(wrap("pnp . --check-only --check-json", 8, 4))
    print(wrap("pnp --doctor --doctor-json", 8, 4))
    print(wrap("pnp --show-config", 8, 4))
    print(wrap("pnp --install-git-ext", 8, 4))
    print(wrap("pnp . --push --publish --sync", 8, 4))

    # Section 2: Options & Commands
    section = color("Options & Commands:", bold=True,
              underline=True)
    print(f"\n{section}\n")
    if option: print(f"Invalid option: {option!r}\n")
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
    print(wrap("• Use --doctor to preflight your environment",
               4, 2))
    print(wrap("• Use --version to verify installed build",
               4, 2))
    print(wrap("• Set defaults via git config (pnp.<key>) "
               "or env vars (PNP_<KEY>)", 4, 2))
    print(wrap("• Use git-machete flags to validate/sync branch"
               " stacks before push/publish", 4, 2))
    print(wrap("• By default, pnp uses fail-fast mode. "
               "The workflow will exit on first failure "
               "unless --interactive is set", 4, 2))

    console.underline(hue=GOOD, alone=True)
    sys.exit(0)


def desc(text: str) -> str:
    return wrap("use " + text, INDENT, inline=True,
           order="   darkian standard   ")


def print_help(section: int = 0) -> None:
    """Prints options (Global, GitHub, or Tagging)"""
    if section == 0:  # Global options
        options = f"""{color(" 1. Global", GOOD)}
    Path (positional)  {desc("path/to/package (default: "
                       + "'.')")}
    Batch commits      {desc("-b / --batch-commit to commit "
                       + "all local repos in the current "
                       + "directory")}
    Pre-push hooks     {desc('--hooks "command1; command2" '
                       + "to run pre-push hooks. A command "
                       + "can include type hint, e.g., "
                       + '"lint::drace lint ." or '
                       + '"test::pytest ."')}
    Hook output        {desc("--no-transmission to print "
                       + "output without effects")}
    Changelog          {desc("--changelog-file FILE for "
                       + "writing generated changelog to "
                       + "file (default: changes.log). "
                       + "Writes 'repo_root/pnplog/"
                       + "changelog_file' unless FILE is a "
                       + "path, of which it then writes to "
                       + "that path")}
    Push               {desc("-p / --push to push commits")}
    Publish            {desc("-P / --publish to bump tags "
                       + "and push them. Assumes your "
                       + "workflows' `*.yml` responsible "
                       + "for publishing triggers when a "
                       + "tag is pushed")}
    Remote push        {desc("-r / --remote NAME for remote "
                       + "name to push to (default: origin "
                       + "or branch upstream)")}
    Force push         {desc("-f / --force for pushing "
                       + "forcefully. Usually, git push will"
                       + " refuse to update a branch that is"
                       + " not an ancestor of the commit "
                       + "being pushed. This flag disables "
                       + "that check. NB: it can cause the "
                       + "remote repository to lose commits;"
                       + " use it with care")}
    Auto fix           {desc("-a / --auto-fix to "
                       + "automatically fix all errors "
                       + "encountered using the most sure "
                       + "fire method. NB: when an error "
                       + "that requires user input is "
                       + "encountered, the user will be "
                       + "asked for input if in interactive "
                       + "mode, otherwise it will abort "
                       + "workflow")}
    Verbose mode       {desc("-v / --verbose to show output "
                       + "when running batch commits ")}
    Quiet mode         {desc("-q / --quiet for silent "
                       + "workflows. NB: since this disables"
                       + " all output, this mode is a "
                       + "fail-fast-type mode — it will exit"
                       + " on first issue unless auto-fix is"
                       + " set, which will exit on input-"
                       + "dependent errors")}
    Interactive mode   {desc("-i / --interactive to be "
                       + "prompted when an issue occurs. "
                       + "Useful for handling mid-workflow "
                       + "issues. NB: flag ignored if in CI "
                       + "mode")}
    CI mode            {desc("--ci for non-interactive "
                       + "workflow")}
    Dry run mode       {desc("-n / --dry-run to simulate "
                       + "actions")}
    Debug mode         {desc("-d / --debug to show full "
                       + "traceback when an error occurs")}
    Doctor mode        {desc("--doctor to run local "
                       + "preflight audit checks (runtime, "
                       + "repo hygiene, metadata, release "
                       + "readiness)")}
    Doctor JSON        {desc("--doctor-json to print doctor "
                       + "results in machine-readable JSON")}
    Doctor report      {desc("--doctor-report FILE to save "
                       + "doctor JSON report to a file")}
    Check-only         {desc("--check-only to run "
                       + "non-mutating workflow preflight "
                       + "and exit")}
    Strict mode        {desc("--strict to treat warnings as "
                       + "blockers (useful with "
                       + "--check-only in CI)")}
    Check JSON         {desc("--check-json to emit "
                       + "machine-readable JSON summary/"
                       + "findings for --check-only")}
    Check-only codes   {desc("--check-only returns 0 "
                       + "(clean), 10 (warnings), 20 "
                       + "(blockers)")}
    Version            {desc("--version to print installed "
                       + "pnp version")}
    Show config        {desc("--show-config to print "
                       + "effective runtime configuration "
                       + "after applying defaults, pyproject"
                       + ", git config, env, and CLI")}
    Install extension  {desc("--install-git-ext to install "
                       + "a git-pnp shim for `git pnp`")}
    Remove extension   {desc("--uninstall-git-ext to remove "
                       + "the installed git-pnp shim")}
    Extension dir      {desc("--git-ext-dir PATH to set "
                       + "where the git-pnp shim is "
                       + "installed")}
    Machete status     {desc("-s / --status to run `git "
                       + "machete status` and fail on"
                       + "issues")}
    Machete sync       {desc("-S / --sync to run `git "
                       + "machete traverse --fetch --sync`")}
    Machete traverse   {desc("-t / --traverse to run `git "
                       + "machete traverse`")}
        """
    elif section == 1:  # GitHub options
        options = f"""{color(" 2. Github", GOOD)}
    Release            {desc("--gh-release to create a "
                       + "release from tag")}
    Repo target        {desc("--gh-repo OWNER/REPO for "
                       + "setting repo. Useful when "
                       + "initializing a new repo or when "
                       + "fixing errors that require you "
                       + "to set a connection with a repo "
                       + "and in auto-fix mode")}
    Token source       {desc("--gh-token TOKEN or set "
                       + "GITHUB_TOKEN env variable")}
    Draft              {desc("--gh-draft for draft release")}
    Mark prerelease    {desc("--gh-prerelease to mark "
                       + "release as prerelease")}
    Attach files       {desc('--gh-assets "file1, file2, ...'
                       + '" for including files such as .whl'
                       + " files (also supports wildcards, "
                       + "e.g., *.whl)")}
        """
    else:  # Tagging options
        options = f"""{color(" 3. Tagging", GOOD)}
    Tag prefix         {desc("--tag-prefix PREFIX to set tag"
                       + " prefix (default: v)")}
    Tag bump           {desc("--tag-bump major|minor|patch "
                       + "(default: patch)")}
    Tag message        {desc("--tag-message <message> to "
                       + "to add a message to a tag. It can "
                       + "also be used add a commit message."
                       + " In Interactive mode you can type "
                       + "'no' or press enter/return for it "
                       + "to use that message, otherwise it "
                       + "would be overriden")}
    Edit message       {desc("--edit-message to open your "
                       + "editor for commit message editing "
                       + "via a temp file")}
    Editor             {desc("--editor '<cmd>' to set "
                       + "editor command (default inherits "
                       + "git core.editor / env vars)")}
    Sign tag           {desc("--tag-sign for GPG signing")}
        """
    print(options)
