"""Top-level package metadata for pnp."""


from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
import re


def _read_local_version() -> str | None:
    """Read version from local pyproject.toml when available."""
    root      = Path(__file__).resolve().parent.parent
    pyproject = root / "pyproject.toml"
    if not pyproject.exists(): return None

    try: text = pyproject.read_text(encoding="utf-8")
    except OSError: return None

    match = re.search(r'^\s*version\s*=\s*"([^"]+)"', text,
            re.MULTILINE)
    if match: return match.group(1)
    return None


try: __version__ = _read_local_version() or version("git-pnp")
except PackageNotFoundError:
    __version__ = _read_local_version() or "0+local"
