# Resolver Error Codes

Stable resolver classifications for git stderr matching.

## Schema

```json
{
  "code": "PNP_RES_*",
  "severity": "info|warn|error|critical",
  "handler": "<resolver handler name>"
}
```

## Codes

- `PNP_RES_EMPTY_STDERR`
  - Severity: `warn`
  - Handler: `fallback`
  - Meaning: resolver was called without stderr content.

- `PNP_RES_NETWORK_CONNECTIVITY`
  - Severity: `error`
  - Handler: `internet_con_err`
  - Meaning: DNS/connection problems while contacting remote.

- `PNP_RES_DUBIOUS_OWNERSHIP`
  - Severity: `warn`
  - Handler: `dubious_ownership`
  - Meaning: git safe.directory ownership protection triggered.

- `PNP_RES_INVALID_OBJECT`
  - Severity: `error`
  - Handler: `invalid_object`
  - Meaning: object/index corruption signatures detected.

- `PNP_RES_REMOTE_URL_INVALID`
  - Severity: `error`
  - Handler: `internet_con_err`
  - Meaning: remote URL appears invalid or non-existent.

- `PNP_RES_REMOTE_UNREADABLE`
  - Severity: `error`
  - Handler: `missing_remote`
  - Meaning: remote cannot be read; often auth or permissions.

- `PNP_RES_UNCLASSIFIED`
  - Severity: `warn`
  - Handler: `fallback`
  - Meaning: stderr did not match known resolver patterns.

## Compatibility

- These codes are intended to be stable across minor releases.
- If a code must change, document it in `CHANGELOG.md`.
