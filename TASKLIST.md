# PNP Production Task List

## Completed
- [x] Remove import-time runtime side effects (argv mutation, resolver log bootstrap file dependency).
- [x] Fix batch repo discovery infinite loop.
- [x] Fix hook failure handling (`RuntimeError` path is now reachable and tested).
- [x] Add explicit runtime dependency for `rich`.
- [x] Guard GitHub release flow when no publish step/tag is available.
- [x] Add PR/push CI workflow with matrix testing.
- [x] Gate publish workflow on tests.
- [x] Add package metadata validation (`twine check`).
- [x] Add `--version` command and stabilize version output.
- [x] Add `--doctor` preflight command.
- [x] Add local integration tests for git push + tag push via bare remote.
- [x] Add local mock-server integration tests for GitHub release + asset upload.
- [x] Add strict mypy gate and expand strict-typed module set to core runtime files.
- [x] Remove committed bytecode/cache artifacts.

## Current Quality Gates
- [x] `python -m compileall -q pnp tests`
- [x] `python -m mypy`
- [x] `python -m unittest discover -s tests -v`
- [x] CI matrix: Linux/macOS/Windows + Python 3.10/3.11/3.12
- [x] Publish workflow requires type-check + tests + packaging checks

## Next High-Impact Work
- [ ] Expand strict typing to remaining non-core modules and remove any temporary ignores.
- [ ] Add dedicated end-to-end CLI scenario tests covering interactive and CI/autofix branches.
- [ ] Add workflow badges + status section in `README.md`.
- [ ] Add a changelog/release notes policy (`CHANGELOG.md` + release template).
- [ ] Add contributor automation targets (e.g. `make check` or `just check`) to standardize local commands.

## Large-Scale Initiatives (Optional)
- [ ] Redesign resolver into smaller strategy handlers with explicit error taxonomy.
- [ ] Introduce hermetic integration test harness for remote behaviors beyond local bare repos.
- [ ] Add telemetry-free diagnostics report mode (`--doctor --json`) for CI systems.

## Definition of Done (Production Baseline)
- [ ] All required checks pass locally and in CI for every PR.
- [ ] No release tag can publish unless type-check, tests, and package checks pass.
- [ ] Core commands (`--help`, `--version`, `--doctor`, push/publish/release paths) are covered by automated tests.
- [ ] README contributor flow exactly matches enforced CI behavior.
