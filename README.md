# pnp — Push and Publish

[![CI](https://github.com/2kDarki/pnp/actions/workflows/ci.yml/badge.svg)](https://github.com/2kDarki/pnp/actions/workflows/ci.yml)
[![Publish to PyPI](https://github.com/2kDarki/pnp/actions/workflows/publish.yml/badge.svg)](https://github.com/2kDarki/pnp/actions/workflows/publish.yml)

**pnp** is a lightweight Python CLI tool to automate the common developer workflow of:

1. Staging and committing changes  
2. Pushing to Git remotes  
3. Automatically bumping semantic version tags  
4. Publishing releases (including GitHub releases)  

It's designed for fast iteration, CI integration, and monorepo-aware projects.

---

## Features

- Initialize Git repo if not present  
- Detect uncommitted changes and auto-commit  
- Push commits to a remote branch (with optional forced push)  
- Bump semantic version tags (`major`, `minor`, `patch`) automatically  
- Generate changelog from commit messages between tags  
- Optional GPG signing of tags  
- Pre-push hooks for tests, linters, or build steps  
- CI mode: non-interactive, fail-fast for automation pipelines  
- Monorepo support: operate on sub-packages  
- GitHub releases: create releases from tags with optional asset uploads  
- Dry-run mode for safe testing  
- Optional git-machete checks/sync before push/publish  

---

## Support Matrix

| Area | Supported |
|---|---|
| Python | 3.10, 3.11, 3.12 |
| OS | Linux, macOS, Windows |
| Git | 2.30+ |
| Shells | POSIX sh, Bash/Zsh/Fish, PowerShell/CMD |

---

## Installation

Install via PyPI:
```bash
 pip install git-pnp
```

---

## Usage

### Basic push and publish

```bash
# Stage, commit, push, bump tag, and push tag
git pnp . --push --publish
```

### Interactive mode

```bash
git pnp . --push --publish --interactive
```

### Compose commit message in editor

```bash
git pnp . --push --publish --edit-message
```

### GitHub release with assets

```bash
git pnp . --push --publish --gh-release \
    --gh-repo "username/pkg" \
    --gh-assets "dist/pkg-0.1.0-py3-none-any.whl" \
    --interactive
```

### Run pre-push hooks

```bash
git pnp . --push --publish --hooks "pytest -q; flake8"
```

### Dry-run mode

```bash
git pnp . --push --publish --dry-run
```

### Check-only preflight (no mutation)

```bash
git pnp . --check-only --push --publish
git pnp . --check-only --strict --push --publish
git pnp . --check-only --check-json
```

`--check-only` exit codes:
- `0`: clean
- `10`: warnings only
- `20`: blockers found

### Git-machete integration

```bash
git pnp . --push --publish --status
git pnp . --push --publish --sync
```

### Environment doctor

```bash
pnp --doctor
```

Machine-readable doctor output:
```bash
pnp --doctor --doctor-json
pnp --doctor --doctor-report pnplog/doctor.json
```

### Show effective config

```bash
pnp --show-config
```

### Install git extension shim

```bash
pnp --install-git-ext
```

Optional custom install directory:
```bash
pnp --install-git-ext --git-ext-dir ~/bin
```

PATH setup examples:

- Bash/Zsh (Linux/macOS):
  ```bash
  echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
  # or ~/.zshrc
  ```

- Fish (Linux/macOS):
  ```fish
  fish_add_path $HOME/.local/bin
  ```

- PowerShell (Windows):
  ```powershell
  [Environment]::SetEnvironmentVariable(
    "Path",
    "$HOME\.local\bin;" + $env:Path,
    "User"
  )
  ```

- CMD (Windows):
  ```bat
  setx PATH "%USERPROFILE%\.local\bin;%PATH%"
  ```

After updating PATH, start a new shell and verify:
```bash
git pnp --version
```

---

## Command-line Options

path (positional): Path to the project/package (default .)

- `--push`: Push commits to remote

- `--publish`: Create and push a tag

- `--interactive / -i`: Prompt per step

- `--dry-run`: Show actions without executing

- `--version`: Show installed `pnp` version

- `--doctor`: Run local preflight checks

- `--doctor-json`: Emit doctor results as JSON

- `--doctor-report`: Write doctor JSON report to a file

- `--check-only`: Run non-mutating workflow preflight and exit

- `--check-json`: Emit machine-readable JSON for `--check-only`

- `--strict`: Treat warnings as blockers (recommended with `--check-only` in CI)

JSON schema contracts:
- `docs/JSON_CONTRACTS.md`
- Resolver taxonomy and codes: `docs/ERROR_CODES.md`
- CI gate script: `tools/schema_gate.py`

- `--show-config`: Print effective merged runtime configuration

- `--install-git-ext`: Install `git-pnp` shim (enables `git pnp`)

- `--uninstall-git-ext`: Remove installed `git-pnp` shim

- `--git-ext-dir`: Directory for extension shim install/remove

- `--status`: Run `git machete status` before workflow mutating steps

- `--sync`: Run `git machete status` and `git machete traverse --fetch --sync`

- `--traverse`: Run `git machete status` and `git machete traverse`

- `--force`: Force push remote if needed

- `--ci`: Non-interactive mode for CI pipelines

- `--remote`: Remote name to push (default: origin or upstream)

- `--tag-bump`: Type of version bump (major, minor, patch)

- `--tag-prefix`: Tag prefix (default v)

- `--tag-message`: Tag message

- `--edit-message`: Open editor to compose commit message via temp file
  (temp file is auto-deleted after workflow completion)

- `--editor`: Editor command override for `--edit-message` (otherwise inherits Git/editor env)

- `--tag-sign`: Sign the tag with GPG

- `--hooks`: Semicolon-separated pre-push commands

- `--changelog-file`: Save changelog to file

- `--gh-release`: Create a GitHub release for the tag

- `--gh-repo`: GitHub repository in owner/repo format

- `--gh-token`: GitHub personal access token (or env GITHUB_TOKEN)

- `--gh-draft`: Create release as draft

- `--gh-prerelease`: Mark release as prerelease

- `--gh-assets`: Comma-separated list of files to attach to release

## Configuration precedence

Runtime options can be set from:
1. Defaults in CLI
2. Project config (`[tool.pnp]` in nearest `pyproject.toml`)
3. Git config (`pnp.<key>`), global then local repo
4. Environment variables (`PNP_<KEY>`)
5. Explicit CLI flags (highest priority)

Examples:
```bash
# pyproject.toml
[tool.pnp]
push = true
publish = true
tag-bump = "minor"
machete-status = true

# git/env overrides
git config --global pnp.push true
git config --global pnp.publish true
git config --global pnp.tag-bump minor
git config --global pnp.machete-status true
git config --global pnp.check-only true
git config --global pnp.check-json true
git config --global pnp.strict true
export PNP_REMOTE=origin
```

---

## Contribution

1. Fork the repository
2. Create a feature branch
3. Install dev tooling:
   ```bash
   pip install -e ".[dev]"
   ```
4. Run checks locally:
   ```bash
   make check
   ```
5. Submit a pull request

Release process references:
- `CHANGELOG.md`
- `docs/release-notes-template.md`
- `docs/HANDOFF.md`

## Internal Layout

- `pnp/cli.py`: CLI argument parsing and dispatch
- `pnp/workflow_engine.py`: orchestration and workflow step sequencing
- `pnp/ops.py`: shared process/git/editor utility operations
- `pnp/audit.py`: doctor and check-only audit flows

## CI Workflows

- `Publish to PyPI` workflow runs on `v*` tags via `.github/workflows/publish.yml`.
- Recommended local gate before tagging: `make check`.

---

## Compatibility Policy

- Runtime support targets Python `3.10+`.
- CI validates Python `3.10`, `3.11`, `3.12` on Linux/macOS/Windows.
- Git `2.30+` is required for expected workflow behavior.
- `git pnp` extension shims target:
  - POSIX shells via `git-pnp`
  - Windows shells via `git-pnp.cmd` (and POSIX shim for Git Bash)
- Interactive TUI output assumes a TTY; CI/non-interactive paths remain plain and deterministic.

---

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE)

---

# Disclaimer

**pnp automates Git and GitHub operations. Use with caution on important repositories. Always test with --dry-run if unsure.**
