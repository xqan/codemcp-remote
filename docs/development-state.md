# Development State

Last updated: 2026-08-31

This file is the durable repository checkpoint for active development work. Repository code, Git state, tests, and acceptance records remain authoritative over chat history.

## Completed workstream: documentation i18n

### Current state

- Branch: `codex/docs-i18n`
- Branch starting point for this work: `5523b0923b186fbac2ec0d6df112be7c51d8f1cf`
- Validated content HEAD before this state-only checkpoint update: `c9a2a69269bb12f02145783d8984c8e88af8effb`
- Scope: documentation organization and documentation tests only.
- Runtime/product source code was not modified by this workstream.
- Worktree remained clean after Bridge-owned mutations.
- Status: **COMPLETE / GATE PASS**.

### Completed

- Established English as the default and canonical documentation language.
- Added the repository-level Simplified Chinese entry point: `README.zh-CN.md`.
- Added the Bridge Simplified Chinese entry point: `bridge/README.zh-CN.md`.
- Added the independent Simplified Chinese documentation tree under `docs/zh-CN/`.
- Rebuilt `docs/README.md` as the English documentation center.
- Rebuilt `docs/implementation-plan.md` as the English canonical macOS plan.
- Rebuilt `bridge/README.md` in English and removed the obsolete statement that Native Windows mutation is unsupported.
- Preserved the original Chinese macOS implementation plan under `docs/zh-CN/implementation-plan.md`.
- Preserved the original Chinese open-source readiness plan under `docs/zh-CN/open-source-readiness-plan.md` while rebuilding the canonical path in English.
- Preserved the original Chinese codemcp compatibility matrix under `docs/zh-CN/codemcp-compatibility-matrix.md` while rebuilding the canonical path in English.
- Removed the remaining Chinese continuation markers from the canonical Cloudflare/OAuth plan.
- Added explicit English-canonical links from the deep Chinese plan/compatibility documents.
- Removed the temporary `docs/zh-CN/.gitkeep` marker after real Chinese documents existed.
- Added `bridge/tests/test_docs_i18n.py` to prevent default documentation from silently returning to mixed-language prose and to verify required language entry points.

### Remaining

- No implementation work remains in the documentation-i18n workstream.
- Review/merge/push of `codex/docs-i18n` is a repository integration step, not unfinished implementation.

### Decisions

- English is canonical for repository-default, current, normative, acceptance, release, and historical documentation paths.
- Simplified Chinese is independently maintained in `README.zh-CN.md`, `bridge/README.zh-CN.md`, and `docs/zh-CN/`.
- Chinese documentation prioritizes installation, operation, architecture/security understanding, and high-value release/compatibility material; it does not mechanically duplicate every historical report.
- When English and Chinese differ on protocol, security, release gates, version status, or support claims, the English canonical document wins.
- Historical release/report evidence remains historical evidence and must not override current architecture, guide, or acceptance documents.
- Existing directory taxonomy (`architecture/`, `guides/`, `acceptance/`, `plans/`, `releases/`, `reports/`) is retained to avoid unnecessary link churn.

### Blockers

- None for this workstream.

### Tests

- Initial i18n-guard regression: `390 passed, 1 failed, 8 skipped`; the single failure identified three pre-existing Chinese canonical documents/markers.
- Those findings were fixed without changing runtime code.
- Post-fix full regression: `392 passed, 8 skipped, 2 warnings`.
- Final regression after removing the obsolete `.gitkeep`: `392 passed, 8 skipped, 2 warnings` on HEAD `c9a2a69269bb12f02145783d8984c8e88af8effb`.
- Registered format gate after final tree cleanup: **PASS — 85 files already formatted**.
- The two warnings are existing environment/dependency warnings: one unresolved Pydantic forward-reference warning and one pytest cache-path warning on Windows; neither is introduced by the documentation changes.
- Final validated worktree at `c9a2a69269bb12f02145783d8984c8e88af8effb`: clean, with no test/format side effects.

### Next

Review and merge `codex/docs-i18n` when desired. Do not repeat this workstream unless the English/Chinese documentation contract changes or a regression is found.

## Parallel workstream: macOS v0.1.0 packaging and acceptance

This is independent from the completed documentation-i18n branch and must not be treated as completed by the documentation changes above.

### Current source state

- Implementation branch recorded by the macOS track: `codex/macos-cli-packaging`.
- Native GitHub candidate matrix includes `macos-arm64` and `macos-intel64`.
- Phase 3 GitHub-hosted native dual-architecture candidate gate is recorded as PASS.
- Phase 4 real clean-host acceptance remains the release boundary in the current macOS acceptance ledger.

### Completed

- Remote MCP connection to an Intel Mac was verified.
- `project_open`, branch enforcement, `git_status`, `file_list`, `file_read`, `file_create`, bounded checkpoint diff, and cleanup were exercised successfully on the Intel acceptance project.
- The packaged-runtime `BridgeError` zero-argument `super()` failure was fixed by directly initializing `Exception`.

### Remaining

- Complete the remaining Phase 4 clean-host acceptance items required by `docs/acceptance/macos-v0.1.0-validation.md`.
- Do not infer Apple Silicon or final macOS support from Intel-only evidence.
- Do not declare the ad-hoc-signed, non-notarized macOS candidates Apple-trusted.

### Decisions

- macOS artifacts are ad-hoc signed.
- No Developer ID certificate is used.
- Notarization is not performed.
- Final support claims must follow real clean-host evidence, not CI build success alone.

### Blockers

- The macOS release remains blocked until its current Phase 4/final release gates are satisfied.

### Tests

- Detailed current macOS evidence belongs in:
  - `docs/acceptance/macos-v0.1.0-validation.md`
  - `docs/guides/macos-build-install-use.md`
  - `docs/implementation-plan.md`

### Next

Continue the macOS workstream only from its repository-recorded first incomplete gate; do not repeat completed phases.
