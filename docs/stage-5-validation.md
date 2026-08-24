# Stage 5 Validation — GitHub Governance and CI

Date: 2026-08-24

## Status

Repository-side implementation: **COMPLETE**

GitHub-hosted activation/first-run verification: **PENDING until the repository is hosted on GitHub**

This distinction is intentional. The repository contains the complete governance and CI configuration, but a local checkout cannot prove GitHub branch protection, Dependabot scheduling, or the first hosted Actions run.

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

After the repository is created/pushed to GitHub, verify:

1. the first `CI` workflow run succeeds on `ubuntu-latest` and `windows-latest`;
2. pull requests automatically receive the CI checks;
3. Dependabot accepts both `uv` and `github-actions` ecosystems;
4. repository branch/ruleset settings require the chosen CI checks before merging to the protected release branch;
5. issue forms and the pull-request template render correctly.

These are activation checks, not permission to move the release gate to PASS without evidence.

## Conclusion

Stage 5 repository implementation is complete. Stable `v0.1.0` remains blocked by the pending hosted activation check and by the other P0 release gates defined in `docs/open-source-readiness-plan.md`.
