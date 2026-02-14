# Changelog

All notable changes to this project are documented in this file.

The format is based on Keep a Changelog and follows semantic versioning.

## Release Policy

- Add changes under `## [Unreleased]` as they are merged.
- Group entries under:
  - `Added`
  - `Changed`
  - `Fixed`
  - `Removed`
  - `Security`
- On release:
  - Move `Unreleased` entries into a new `## [X.Y.Z] - YYYY-MM-DD` section.
  - Keep the newest release at the top.
  - Link the tag in release notes and include migration notes for breaking changes.

## [Unreleased]

### Added
- Add `--edit-message` to compose commit messages in the user editor via a temporary file.
- Add `--editor` to override editor command selection (`git core.editor` / env fallback still supported).

### Fixed
- Fix terminal rendering conflict where Rich live spinners continued updating while external editors (for example `nano`) were open, causing jumbled/flickering editor screens.
