# Stage 5 Validation — GitHub Governance and CI

Date: 2026-08-24

## Status

Repository-side implementation: **COMPLETE**

GitHub-hosted CI execution: **WAIVED / ACCEPTED RISK** — the hosted run was blocked by the recorded billing/spending-limit condition before runner/job execution and is not counted as PASS.

Hosted governance activation: **PARTIAL / PENDING FINAL RECORD** — repository-side Dependabot/CI/templates are present, but branch/ruleset state and hosted Dependabot activation still require GitHub-side verification.

This distinction is intentional. Local repository configuration proves the intended governance files, but it cannot prove GitHub ruleset enforcement or hosted Dependabot scheduling. The hosted CI waiver does not convert an unexecuted Actions job into PASS.

## Delivered

- `CONTRIBUTING.md`
- `CODE_OF_CONDUCT.md`
- `CHANGELOG.md`
- `.github/workflows/ci.yml`
- `.github/ISSUE_TEMPLATE/bug_report.yml`
- `.github/ISSUE_TEMPLATE/feature_request.yml`
- `.github/pull_request_template.md`
- `.github/dependabot.yml`
- README links to the governance documents

The CI workflow uses read-only repository permissions, disables persisted checkout credentials, runs on both Ubuntu and Windows for the Python 3.12 core checks, validates the locked environment, Ruff lint/format, pytest, example configuration, package build, and Git whitespace/cleanliness.

GitHub Actions dependencies are pinned to an exact immutable release or commit. Dependabot monitors both `/bridge` uv dependencies and GitHub Actions weekly.

## Local validation evidence

### Ruff format

Command: registered project workflow `format`

Result: **PASS**

```text
49 files already formatted
```

The first format run exposed two pre-existing formatting defects in `bridge/tests/test_phase2_integration.py` and `bridge/tests/test_phase2_worker.py`. Only Ruff-equivalent whitespace/layout changes were applied, then the check passed.

### Tests

Command: registered project workflow `test`

Result: **PASS**

```text
127 passed, 390 warnings in 56.00s
```

Warnings are not treated as hidden success criteria. The observed warnings include Python 3.14 asyncio deprecations, a Pydantic incomplete forward-reference warning, and a pytest cache permission warning. They remain visible technical debt for later release review.

### Git state

Result: **PASS**

- branch: `codex/20260824`
- working tree: clean

## Hosted checks still required

Before stable release, record the remaining GitHub-side governance state:

1. hosted CI remains **WAIVED / ACCEPTED RISK** for `v0.1.0` unless the billing condition is resolved and a real Ubuntu/Windows run actually executes;
2. verify Dependabot accepts both `uv` and `github-actions` ecosystems;
3. verify the repository branch/ruleset protects the intended release branch with the chosen merge policy; do not require a CI check that cannot execute under the accepted waiver unless the billing blocker is resolved;
4. verify issue forms and the pull-request template render correctly;
5. capture the final governance decision in the release record.

These are activation/governance checks. Local files alone do not establish hosted PASS, and the CI waiver must remain visible.

## Conclusion

Stage 5 repository implementation is complete. The hosted CI billing blocker is explicitly waived for `v0.1.0` and is not a PASS. Stable release remains blocked on the final GitHub governance record (ruleset / Dependabot hosted activation) and the other remaining release gates in `docs/plans/v0.1.0/open-source-readiness-plan.md`.
