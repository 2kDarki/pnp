"""Deterministic helpers for local git integration tests."""
from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile


class GitFixture:
    def __init__(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def close(self) -> None:
        self._tmp.cleanup()

    def run(self, args: list[str], cwd: Path | None = None,
            check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=str(cwd) if cwd else None,
            check=check,
            capture_output=True,
            text=True,
        )

    def init_bare(self, name: str = "remote.git") -> Path:
        path = self.root / name
        self.run(["init", "--bare", str(path)])
        return path

    def init_repo(self, name: str) -> Path:
        path = self.root / name
        path.mkdir(parents=True, exist_ok=True)
        self.run(["init", str(path)])
        return path

    def clone(self, src: Path, name: str) -> Path:
        dst = self.root / name
        self.run(["clone", str(src), str(dst)])
        return dst

    def set_identity(self, repo: Path, user: str, email: str) -> None:
        self.run(["config", "user.name", user], cwd=repo)
        self.run(["config", "user.email", email], cwd=repo)

    def add_remote(self, repo: Path, name: str, remote_path: Path) -> None:
        self.run(["remote", "add", name, str(remote_path)], cwd=repo)

    def write_file(self, repo: Path, rel: str, text: str) -> None:
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def commit_all(self, repo: Path, message: str) -> None:
        self.run(["add", "-A"], cwd=repo)
        self.run(["commit", "-m", message], cwd=repo)

    def branch(self, repo: Path) -> str:
        cp = self.run(["rev-parse", "--abbrev-ref", "HEAD"], cwd=repo)
        return cp.stdout.strip()

    def push_upstream(self, repo: Path, remote: str, branch: str) -> None:
        self.run(["push", "-u", remote, branch], cwd=repo)
