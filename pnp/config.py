"""Layered runtime configuration for pnp.

Precedence order (low -> high):
1) argparse defaults
2) pyproject.toml ([tool.pnp])
3) git config (global, then local repository)
4) environment variables
5) explicit CLI options
"""
from __future__ import annotations

from argparse import Namespace, ArgumentParser
from dataclasses import dataclass
from pathlib import Path
import subprocess
import os

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]


@dataclass(frozen=True)
class OptionSpec:
    dest: str
    git_key: str
    env_key: str
    kind: str  # "bool" | "str"
    choices: tuple[str, ...] | None = None


SPECS: tuple[OptionSpec, ...] = (
    OptionSpec("hooks", "hooks", "PNP_HOOKS", "str"),
    OptionSpec("changelog_file", "changelog-file", "PNP_CHANGELOG_FILE", "str"),
    OptionSpec("push", "push", "PNP_PUSH", "bool"),
    OptionSpec("publish", "publish", "PNP_PUBLISH", "bool"),
    OptionSpec("remote", "remote", "PNP_REMOTE", "str"),
    OptionSpec("force", "force", "PNP_FORCE", "bool"),
    OptionSpec("no_transmission", "no-transmission", "PNP_NO_TRANSMISSION", "bool"),
    OptionSpec("quiet", "quiet", "PNP_QUIET", "bool"),
    OptionSpec("plain", "plain", "PNP_PLAIN", "bool"),
    OptionSpec("verbose", "verbose", "PNP_VERBOSE", "bool"),
    OptionSpec("debug", "debug", "PNP_DEBUG", "bool"),
    OptionSpec("auto_fix", "auto-fix", "PNP_AUTO_FIX", "bool"),
    OptionSpec("dry_run", "dry-run", "PNP_DRY_RUN", "bool"),
    OptionSpec("ci", "ci", "PNP_CI", "bool"),
    OptionSpec("interactive", "interactive", "PNP_INTERACTIVE", "bool"),
    OptionSpec("gh_release", "gh-release", "PNP_GH_RELEASE", "bool"),
    OptionSpec("gh_repo", "gh-repo", "PNP_GH_REPO", "str"),
    OptionSpec("gh_token", "gh-token", "PNP_GH_TOKEN", "str"),
    OptionSpec("gh_draft", "gh-draft", "PNP_GH_DRAFT", "bool"),
    OptionSpec("gh_prerelease", "gh-prerelease", "PNP_GH_PRERELEASE", "bool"),
    OptionSpec("gh_assets", "gh-assets", "PNP_GH_ASSETS", "str"),
    OptionSpec("check_only", "check-only", "PNP_CHECK_ONLY", "bool"),
    OptionSpec("check_json", "check-json", "PNP_CHECK_JSON", "bool"),
    OptionSpec("strict", "strict", "PNP_STRICT", "bool"),
    OptionSpec("tag_prefix", "tag-prefix", "PNP_TAG_PREFIX", "str"),
    OptionSpec("tag_message", "tag-message", "PNP_TAG_MESSAGE", "str"),
    OptionSpec("tag_sign", "tag-sign", "PNP_TAG_SIGN", "bool"),
    OptionSpec("tag_bump", "tag-bump", "PNP_TAG_BUMP", "str",
               choices=("major", "minor", "patch")),
    OptionSpec("machete_status", "machete-status", "PNP_MACHETE_STATUS", "bool"),
    OptionSpec("machete_sync", "machete-sync", "PNP_MACHETE_SYNC", "bool"),
    OptionSpec("machete_traverse", "machete-traverse", "PNP_MACHETE_TRAVERSE", "bool"),
)


def _parse_bool(raw: str) -> bool | None:
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    return None


def _parse_bool_like(raw: object) -> bool | None:
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        return _parse_bool(raw)
    return None


def _repo_root(path: str) -> str | None:
    cur = os.path.abspath(path)
    while True:
        if os.path.isdir(os.path.join(cur, ".git")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return None
        cur = parent


def _resolve_scan_root(path: str) -> Path:
    target = Path(path).expanduser()
    if not target.is_absolute():
        target = (Path.cwd() / target).resolve()
    else:
        target = target.resolve()
    if target.is_file():
        return target.parent
    return target


def _find_pyproject(path: str) -> Path | None:
    cur = _resolve_scan_root(path)
    while True:
        candidate = cur / "pyproject.toml"
        if candidate.is_file():
            return candidate
        if cur.parent == cur:
            return None
        cur = cur.parent


def _diag(level: str, source: str, key: str, raw: object,
          message: str) -> dict[str, str]:
    return {
        "level": level,
        "source": source,
        "key": key,
        "raw": str(raw),
        "message": message,
    }


def _load_pyproject_overrides(path: str) -> tuple[dict[str, object],
                                                   list[dict[str, str]],
                                                   str | None]:
    pyproject = _find_pyproject(path)
    if pyproject is None:
        return {}, [], None
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        msg = f"failed to parse pyproject.toml: {exc}"
        return {}, [_diag("error", "pyproject", "tool.pnp", "", msg)], str(pyproject)

    table = data.get("tool", {}).get("pnp")
    if table is None:
        return {}, [], str(pyproject)
    if not isinstance(table, dict):
        msg = "tool.pnp must be a TOML table, e.g. [tool.pnp]"
        return {}, [_diag("error", "pyproject", "tool.pnp", type(table).__name__, msg)], str(pyproject)

    key_to_spec = {spec.git_key: spec for spec in SPECS}
    values: dict[str, object] = {}
    diagnostics: list[dict[str, str]] = []
    for raw_key, raw_val in table.items():
        key = str(raw_key).strip().lower().replace("_", "-")
        spec = key_to_spec.get(key)
        if spec is None:
            msg = "unknown key in [tool.pnp]; use one of documented pnp keys"
            diagnostics.append(_diag("warning", "pyproject", str(raw_key), raw_val, msg))
            continue
        values[spec.dest] = raw_val
    return values, diagnostics, str(pyproject)


def _read_git_scope(scope_args: list[str], repo: str | None = None) -> dict[str, str]:
    cmd = ["git"]
    if repo:
        cmd += ["-C", repo]
    cmd += ["config", *scope_args, "--get-regexp", r"^pnp\."]
    try:
        cp = subprocess.run(cmd, check=False, capture_output=True, text=True)
    except FileNotFoundError:
        return {}
    if cp.returncode != 0:
        return {}
    out: dict[str, str] = {}
    for line in cp.stdout.splitlines():
        if not line.strip():
            continue
        key, _, value = line.partition(" ")
        out[key.strip()] = value.strip()
    return out


def _load_git_overrides(path: str) -> dict[str, str]:
    values = _read_git_scope(["--global"])
    repo = _repo_root(path)
    if repo:
        values.update(_read_git_scope(["--local"], repo=repo))
    mapped: dict[str, str] = {}
    for spec in SPECS:
        key = f"pnp.{spec.git_key}"
        if key in values:
            mapped[spec.dest] = values[key]
    return mapped


def _load_env_overrides() -> dict[str, str]:
    out: dict[str, str] = {}
    for spec in SPECS:
        raw = os.environ.get(spec.env_key)
        if raw is not None:
            out[spec.dest] = raw
    return out


def _coerce(dest: str, raw: object, source: str,
            diagnostics: list[dict[str, str]]) -> object | None:
    spec = next((s for s in SPECS if s.dest == dest), None)
    if spec is None:
        return None
    if spec.kind == "bool":
        value = _parse_bool_like(raw)
        if value is None:
            msg = f"invalid boolean value for {dest}; use true/false"
            diagnostics.append(_diag("warning", source, dest, raw, msg))
        return value
    if spec.kind == "str":
        if not isinstance(raw, str):
            msg = f"invalid value type for {dest}; expected string"
            diagnostics.append(_diag("warning", source, dest, raw, msg))
            return None
        if spec.choices and raw not in spec.choices:
            choices = ", ".join(spec.choices)
            msg = f"invalid value for {dest}; expected one of: {choices}"
            diagnostics.append(_diag("warning", source, dest, raw, msg))
            return None
        return raw
    return None


def _explicit_cli_dests(argv: list[str], parser: ArgumentParser) -> set[str]:
    mapping = parser._option_string_actions
    explicit: set[str] = set()
    i = 0
    while i < len(argv):
        token = argv[i]
        if token == "--":
            break
        if not token.startswith("-"):
            i += 1
            continue
        opt = token.split("=", 1)[0]
        action = mapping.get(opt)
        if action is None:
            i += 1
            continue
        explicit.add(action.dest)
        takes_value = action.nargs not in (0, None) or action.option_strings and action.default is not False
        if "=" not in token and takes_value and i + 1 < len(argv):
            i += 2
            continue
        i += 1
    return explicit


def apply_layered_config(args: Namespace, argv: list[str], parser: ArgumentParser) -> Namespace:
    """Apply git/env overrides unless destination was set explicitly by CLI."""
    merged = Namespace(**vars(args))
    explicit = _explicit_cli_dests(argv, parser)
    py_vals, py_diags, pyproject_path = _load_pyproject_overrides(
        getattr(merged, "path", "."))
    git_vals = _load_git_overrides(getattr(merged, "path", "."))
    env_vals = _load_env_overrides()
    sources: dict[str, str] = {}
    diagnostics: list[dict[str, str]] = list(py_diags)

    for k in vars(merged):
        sources[k] = "default"
    for dest in explicit:
        sources[dest] = "cli"

    for spec in SPECS:
        if spec.dest in explicit:
            continue
        if spec.dest in py_vals:
            value = _coerce(spec.dest, py_vals[spec.dest], "pyproject", diagnostics)
            if value is not None:
                setattr(merged, spec.dest, value)
                sources[spec.dest] = "pyproject"
        if spec.dest in git_vals:
            value = _coerce(spec.dest, git_vals[spec.dest], "git", diagnostics)
            if value is not None:
                setattr(merged, spec.dest, value)
                sources[spec.dest] = "git"
        if spec.dest in env_vals:
            value = _coerce(spec.dest, env_vals[spec.dest], "env", diagnostics)
            if value is not None:
                setattr(merged, spec.dest, value)
                sources[spec.dest] = "env"
    setattr(merged, "_pnp_config_sources", sources)
    setattr(merged, "_pnp_config_diagnostics", diagnostics)
    setattr(merged, "_pnp_config_files", {"pyproject": pyproject_path})
    return merged
