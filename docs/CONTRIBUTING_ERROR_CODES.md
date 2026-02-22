# Contributing: Resolver Rules and Error Codes

This guide defines the safe process for adding or changing resolver classifications and stable error codes.

## Non-Negotiable Rules

- Do not silently repurpose existing stable codes.
- Additive code/rule changes are preferred.
- Any breaking code contract change requires:
  - migration notes (`docs/ERROR_CODE_MIGRATION_TEMPLATE.md`)
  - explicit approval override for CI gate

## Safe Change Workflow

1. Update classifier logic:
   - `pnp/resolver_classifier.py`
   - keep matching deterministic and side-effect free
2. Update canonical policy mapping:
   - `pnp/error_model.py`
   - add/update `ERROR_CODE_POLICY` and related mappings
3. If renaming/deprecating:
   - add alias mapping in `DEPRECATED_ERROR_CODE_ALIASES`
   - keep canonical output stable
4. Update lock and docs:
   - `docs/error_code_lock.json`
   - `docs/ERROR_CODES.md`
5. Add/refresh tests:
   - golden corpus: `tests/fixtures/resolver_classifier_golden.json`
   - snapshot: `tests/fixtures/resolver_classifier_snapshot_v1.json`
   - tests: `tests/test_resolver_classifier_golden.py`
6. Run gates:
   - `python tools/error_code_gate.py`
   - `python tools/schema_gate.py`
   - `pytest -q`

## Rule Authoring Guidance

- Prefer explicit substring/pattern rules with clear precedence.
- Avoid locale-sensitive or brittle message fragments.
- Normalize stderr before classification (already enforced by classifier).
- Keep unknown fallback behavior intact (`PNP_GIT_UNCLASSIFIED`).
- Add ambiguity samples to golden corpus when multiple rules may match.

## Breaking Change Procedure

If you must break compatibility:

1. Fill migration notes using:
   - `docs/ERROR_CODE_MIGRATION_TEMPLATE.md`
2. Add explicit CI override:
   - env: `PNP_ALLOW_ERROR_CODE_BREAK=1`, or
   - file: `.error_code_breaking_change_approved`
3. Ensure review includes downstream consumer impact and rollout plan.

## Pull Request Checklist

- [ ] New/changed rules have deterministic tests.
- [ ] Golden corpus and snapshot are updated intentionally.
- [ ] `docs/ERROR_CODES.md` is updated.
- [ ] `docs/error_code_lock.json` matches intended contract.
- [ ] `tools/error_code_gate.py` passes without override (unless approved break).
