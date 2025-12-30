# pnp — Push and Publish

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

---

## Installation

Install via PyPI (once published):
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

---

## Command-line Options

path (positional): Path to the project/package (default .)

- `--push`: Push commits to remote

- `--publish`: Create and push a tag

- `--interactive / -i`: Prompt per step

- `--dry-run`: Show actions without executing

- `--force`: Force push remote if needed

- `--ci`: Non-interactive mode for CI pipelines

- `--remote`: Remote name to push (default: origin or upstream)

- `--tag-bump`: Type of version bump (major, minor, patch)

- `--tag-prefix`: Tag prefix (default v)

- `--tag-message`: Tag message

- `--tag-sign`: Sign the tag with GPG

- `--hooks`: Semicolon-separated pre-push commands

- `--changelog-file`: Save changelog to file

- `--gh-release`: Create a GitHub release for the tag

- `--gh-repo`: GitHub repository in owner/repo format

- `--gh-token`: GitHub personal access token (or env GITHUB_TOKEN)

- `--gh-draft`: Create release as draft

- `--gh-prerelease`: Mark release as prerelease

- `--gh-assets`: Comma-separated list of files to attach to release

---

## Contribution

1. Fork the repository
2. Create a feature branch
3. Run tests and linters (pytest, kitty)
4. Submit a pull request

---

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE)

---

# Disclaimer

**pnp automates Git and GitHub operations. Use with caution on important repositories. Always test with --dry-run if unsure.**
