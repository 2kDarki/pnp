"""Project-type adapter registry for workflow-specific behavior."""


from dataclasses import dataclass
from typing import Protocol
import json
import os
import re
import xml.etree.ElementTree as ET

try: import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]

from . import utils

SUPPORTED_PROJECT_TYPES: tuple[str, ...] = (
    "auto",
    "generic",
    "python",
    "node",
    "rust",
    "go",
    "java",
    "php",
    "ruby",
    "elixir",
    "julia",
)

PROJECT_TYPE_MARKERS: dict[str, tuple[str, ...]] = {
    "python": ("pyproject.toml",),
    "node": ("package.json",),
    "rust": ("Cargo.toml",),
    "go": ("go.mod",),
    "java": ("pom.xml", "build.gradle", "build.gradle.kts"),
    "php": ("composer.json",),
    "ruby": ("Gemfile",),
    "elixir": ("mix.exs",),
    "julia": ("Project.toml",),
}

DETECTION_ORDER: tuple[str, ...] = (
    "python",
    "node",
    "rust",
    "go",
    "java",
    "php",
    "ruby",
    "elixir",
    "julia",
)


class ProjectAdapter(Protocol):
    """Typed behavior contract for per-project adapters."""

    @property
    def project_type(self) -> str:
        """Canonical project type name."""

    def compute_next_tag(
        self,
        latest_tag: str,
        bump: str,
        prefix: str,
        project_root: str,
    ) -> str:
        """Return next release tag for this project type."""

    def pre_publish_commands(self, adapter_config: dict[str, object] | None = None) -> list[str]:
        """Return adapter-specific pre-publish commands."""

    def publish_commands(self, adapter_config: dict[str, object] | None = None) -> list[str]:
        """Return adapter-specific publish commands."""


@dataclass(frozen=True)
class GenericAdapter:
    """Fallback adapter for unknown or non-package repositories."""

    project_type: str = "generic"

    def compute_next_tag(
        self,
        latest_tag: str,
        bump: str,
        prefix: str,
        project_root: str,
    ) -> str:
        del project_root
        return utils.bump_semver_from_tag(latest_tag, bump, prefix=prefix)

    def pre_publish_commands(self, adapter_config: dict[str, object] | None = None) -> list[str]:
        return _generic_pre_publish_commands(adapter_config)

    def publish_commands(self, adapter_config: dict[str, object] | None = None) -> list[str]:
        return _generic_publish_commands(adapter_config)


@dataclass(frozen=True)
class ManifestSeedAdapter(GenericAdapter):
    """Generic adapter that can seed first tag from manifest metadata."""

    project_type: str = "generic"

    def manifest_version(self, project_root: str) -> str | None:
        del project_root
        return None

    def compute_next_tag(
        self,
        latest_tag: str,
        bump: str,
        prefix: str,
        project_root: str,
    ) -> str:
        if latest_tag.strip():
            return super().compute_next_tag(
                latest_tag=latest_tag,
                bump=bump,
                prefix=prefix,
                project_root=project_root,
            )
        seed = self.manifest_version(project_root)
        if seed:
            return f"{prefix}{seed}"
        return super().compute_next_tag(
            latest_tag=latest_tag,
            bump=bump,
            prefix=prefix,
            project_root=project_root,
        )


def _semver_core(value: object) -> str | None:
    if not isinstance(value, str): return None
    text = value.strip()
    if not text: return None
    text = text.removeprefix("v")
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)", text)
    if not match: return None
    major, minor, patch = match.groups()
    return f"{int(major)}.{int(minor)}.{int(patch)}"


@dataclass(frozen=True)
class NodeAdapter(ManifestSeedAdapter):
    project_type: str = "node"

    def manifest_version(self, project_root: str) -> str | None:
        path = os.path.join(project_root, "package.json")
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return None
        if not isinstance(data, dict): return None
        return _semver_core(data.get("version"))

    def pre_publish_commands(self, adapter_config: dict[str, object] | None = None) -> list[str]:
        commands = _generic_pre_publish_commands(adapter_config)
        if not isinstance(adapter_config, dict): return commands
        build = adapter_config.get("build-script")
        test = adapter_config.get("test-script")
        if isinstance(build, str) and build.strip():
            commands.append(f"npm run {build.strip()}")
        if isinstance(test, str) and test.strip():
            commands.append(f"npm run {test.strip()}")
        return commands

    def publish_commands(self, adapter_config: dict[str, object] | None = None) -> list[str]:
        commands = _generic_publish_commands(adapter_config)
        if not isinstance(adapter_config, dict): return commands
        publish_script = adapter_config.get("publish-script")
        if isinstance(publish_script, str) and publish_script.strip():
            commands.append(f"npm run {publish_script.strip()}")
        return commands


@dataclass(frozen=True)
class RustAdapter(ManifestSeedAdapter):
    project_type: str = "rust"

    def manifest_version(self, project_root: str) -> str | None:
        path = os.path.join(project_root, "Cargo.toml")
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = tomllib.loads(f.read())
        except Exception:
            return None
        if not isinstance(data, dict): return None
        pkg = data.get("package")
        if not isinstance(pkg, dict): return None
        return _semver_core(pkg.get("version"))

    def pre_publish_commands(self, adapter_config: dict[str, object] | None = None) -> list[str]:
        commands = _generic_pre_publish_commands(adapter_config)
        if not isinstance(adapter_config, dict): return commands
        for key in ("build-command", "test-command"):
            value = adapter_config.get(key)
            if isinstance(value, str) and value.strip():
                commands.append(value.strip())
        return commands

    def publish_commands(self, adapter_config: dict[str, object] | None = None) -> list[str]:
        return _generic_publish_commands(adapter_config)


@dataclass(frozen=True)
class JavaAdapter(ManifestSeedAdapter):
    project_type: str = "java"

    def manifest_version(self, project_root: str) -> str | None:
        path = os.path.join(project_root, "pom.xml")
        if not os.path.exists(path): return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                root = ET.fromstring(f.read())
        except Exception:
            return None
        queries = (
            ".//{http://maven.apache.org/POM/4.0.0}version",
            ".//version",
        )
        for query in queries:
            node = root.find(query)
            if node is not None and node.text:
                version = _semver_core(node.text)
                if version: return version
        return None


@dataclass(frozen=True)
class PhpAdapter(ManifestSeedAdapter):
    project_type: str = "php"

    def manifest_version(self, project_root: str) -> str | None:
        path = os.path.join(project_root, "composer.json")
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return None
        if not isinstance(data, dict): return None
        return _semver_core(data.get("version"))


@dataclass(frozen=True)
class JuliaAdapter(ManifestSeedAdapter):
    project_type: str = "julia"

    def manifest_version(self, project_root: str) -> str | None:
        path = os.path.join(project_root, "Project.toml")
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = tomllib.loads(f.read())
        except Exception:
            return None
        if not isinstance(data, dict): return None
        return _semver_core(data.get("version"))


@dataclass(frozen=True)
class PythonAdapter(ManifestSeedAdapter):
    """Python project adapter."""

    project_type: str = "python"

    def manifest_version(self, project_root: str) -> str | None:
        path = os.path.join(project_root, "pyproject.toml")
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = tomllib.loads(f.read())
        except Exception:
            return None
        if not isinstance(data, dict): return None
        project = data.get("project")
        if not isinstance(project, dict): return None
        return _semver_core(project.get("version"))


ADAPTERS: dict[str, ProjectAdapter] = {
    "generic": GenericAdapter(),
    "python": PythonAdapter(),
    "node": NodeAdapter(),
    "rust": RustAdapter(),
    "java": JavaAdapter(),
    "php": PhpAdapter(),
    "julia": JuliaAdapter(),
}


def _generic_pre_publish_commands(adapter_config: dict[str, object] | None = None) -> list[str]:
    if not isinstance(adapter_config, dict): return []

    commands: list[str] = []
    singles = ("pre-publish-hook", "pre-publish-command")
    lists = ("pre-publish-hooks", "pre-publish-commands")
    for key in singles:
        value = adapter_config.get(key)
        if isinstance(value, str) and value.strip():
            commands.append(value.strip())
    for key in lists:
        value = adapter_config.get(key)
        if not isinstance(value, list): continue
        for item in value:
            if isinstance(item, str) and item.strip():
                commands.append(item.strip())
    return commands


def _generic_publish_commands(adapter_config: dict[str, object] | None = None) -> list[str]:
    if not isinstance(adapter_config, dict): return []
    commands: list[str] = []
    singles = ("publish-command", "registry-publish-command")
    lists = ("publish-commands", "registry-publish-commands")
    for key in singles:
        value = adapter_config.get(key)
        if isinstance(value, str) and value.strip():
            commands.append(value.strip())
    for key in lists:
        value = adapter_config.get(key)
        if not isinstance(value, list): continue
        for item in value:
            if isinstance(item, str) and item.strip():
                commands.append(item.strip())
    return commands


def detect_project_type(project_root: str) -> str:
    """Infer project type from well-known manifest files."""
    root = os.path.abspath(project_root)
    for kind in DETECTION_ORDER:
        markers = PROJECT_TYPE_MARKERS.get(kind, ())
        if any(os.path.exists(os.path.join(root, marker)) for marker in markers):
            return kind
    return "generic"


def resolve_project_adapter(project_root: str, override: str | None = None) -> ProjectAdapter:
    """Resolve adapter from explicit override or marker-based detection."""
    choice = (override or "auto").strip().lower()
    if choice and choice != "auto":
        return ADAPTERS.get(choice, GenericAdapter(project_type=choice))
    detected = detect_project_type(project_root)
    return ADAPTERS.get(detected, GenericAdapter(project_type=detected))
