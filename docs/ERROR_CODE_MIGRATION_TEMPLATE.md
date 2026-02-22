# Error Code Migration Notes Template

Use this template whenever introducing a breaking error-code contract change.

## Summary
- Date:
- Author:
- Related PR/issue:

## Breaking Change Type
- [ ] Removed stable error code
- [ ] Changed stable code meaning/severity/category
- [ ] Changed workflow step -> code mapping
- [ ] Removed/changed deprecated alias mapping

## Before
- Affected code(s):
- Previous behavior:
- Previous payload examples:

## After
- New code(s) / mapping:
- New behavior:
- New payload examples:

## Compatibility Plan
- Deprecated aliases kept until version:
- Fallback/canonicalization behavior:
- Contract version impact:

## Consumer Impact
- Known downstream consumers:
- Required consumer updates:
- Rollout guidance:

## Validation
- Tests added/updated:
- CI gates run:
- Manual verification notes:
