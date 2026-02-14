# Release Notes Template

Use this template when publishing a new `git-pnp` release.

## Summary

Short release overview (1-3 lines).

## Highlights

- Feature:
- UX:
- Reliability:

## Breaking Changes

- None.

If present, include:
- What changed
- Impact
- Migration command/example

## Fixes

- Bug fix:
- Regression fix:

## Upgrade

```bash
pip install -U git-pnp
```

## Checks

- [ ] `python -m compileall -q pnp tests`
- [ ] `python -m mypy`
- [ ] `python -m unittest discover -s tests -v`
- [ ] `python tools/schema_gate.py`

## Artifacts

- PyPI: `<version>`
- GitHub tag: `v<version>`
- Notes source: `CHANGELOG.md`
