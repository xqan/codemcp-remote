# Development State — codemcp-remote

Updated: 2026-08-30
Plan: `docs/plans/v0.1.0/open-source-readiness-plan.md`
Branch: `codex/open-source-readiness`
Session restore baseline HEAD: `a8fdb0139dc6ab21662ed41d8e72aa969b43f1a1`

## Current Phase

`v0.1.0` Open Source Readiness — **Final Release Gate IN PROGRESS**.

The Live Acceptance Ledger in the plan and the acceptance reports are authoritative for completed release evidence. Completed Phase/Stage gates must not be repeated unless a later code/artifact change invalidates their evidence.

## Completed

- Phase 6 / Stage 2 mandatory Windows real-host matrix: PASS / COMPLETE.
- Phase 7 functional F-01..F-20: PASS.
- Reliability R-01..R-14: PASS.
- Security acceptance: accounted for through S-33, with the documented Windows symlink privilege environment limitation.
- 10/10 real-project remote tasks: PASS / COMPLETE.
- Stage 6 secrets/dependency/license/supply-chain audit: PASS with documented `codemcp==0.3.0` license-metadata discrepancy.
- Hosted CI billing/spending-limit condition: WAIVED / ACCEPTED RISK; never record as CI PASS.
- Final automated source gate: PASS / COMPLETE.
- Documentation consistency: PASS.
- Acceptance-record synchronization completed on 2026-08-30 without rerunning completed phases: Phase 6 top-level/exit status, Phase 7 22-tool contract/F-01..F-20/R-01..R-14/ChatGPT-only/network-trust status, and the plan's Stage 2/3/4/5/7 summaries now match the Live Acceptance Ledger.
- The fourth audited RC production clean-machine `Prepare -> Start -> remote contract -> Cleanup` using disposable `phase5-clean` is historical PASS evidence; the old Phase H temporary-real-repository/Cleanup-deferred deviation is no longer a current packaging blocker.
- Draft release notes exist at `docs/releases/v0.1.0/release-notes.md`.

## Remaining

1. Record final GitHub governance state: ruleset / merge policy, Dependabot `uv` + `github-actions` hosted activation, and Issue forms / PR template hosted rendering. Hosted CI remains waived, not PASS.
2. Create final release-only commit after the governance record is closed.
3. Rebuild installer + ZIP from that exact commit.
4. Recompute SHA-256, run artifact/security scan, and prove exact source/artifact identity.
5. Complete final clean-machine package / README onboarding / disposable-repo / cleanup / uninstall sign-off.
6. Bind final CHANGELOG / known limitations / release notes / checksum record to the exact final commit and artifacts.
7. Final Release Gate sign-off.
8. Tag `v0.1.0` and publish the GitHub Release.

## Decisions

- Signing decision is **FINAL for `v0.1.0`: `NotSigned` / ACCEPTED LIMITATION**. No Authenticode certificate will be used; Windows SmartScreen / reputation / user-trust warnings are an explicitly accepted first-release limitation.
- GitHub hosted CI remains explicitly waived because billing blocked execution before runner/job start.
- Do not add required CI checks that cannot execute under the accepted hosted-CI waiver.
- `codemcp-remote-3243` is a separate parallel worktree/task and is out of scope for this release-gate session.

## Blockers

- GitHub-side ruleset/merge policy, Dependabot hosted activation, and Issue forms / PR template hosted rendering cannot be proven from repository files alone. The currently connected GitHub source exposes no accessible `codemcp-remote` repository/installation, so hosted governance remains pending external verification/record.
- Final release-only artifact work must not start until the GitHub final governance record is closed, because the final commit/artifact identity must be immutable for the remaining release evidence.

## Tests

Revalidated on the restore baseline `a8fdb0139dc6ab21662ed41d8e72aa969b43f1a1`:

- Registered full test recheck: **PASS** — `353 passed, 7 skipped, 2 warnings` in 160.15s.
- Registered Ruff format check: **PASS** — `79 files already formatted`.
- Registered security audit: **PASS** for dependency audit, dependency-license evidence, current tracked-tree secret scan, and all-ref Git-history secret scan; `1339 commits scanned`, no leaks.
- Artifact scan: intentionally not rerun yet; final artifact must be rebuilt after the final release-only commit.
- A preceding full-test attempt hit transient Windows `WinError 32` while PyInstaller removed an old shared `.local/dist/codemcp-remote` tree. An immediate exact-HEAD recheck passed 353/7; no source change was made for that transient lock.
- Worktree remained clean after the revalidation commands.

## Next

1. Close the GitHub final governance record: ruleset / merge policy, Dependabot hosted activation, and hosted Issue forms / PR template rendering.
2. Freeze the final release-only commit.
3. Rebuild installer + ZIP and revalidate SHA-256, artifact/security scan, and exact source/artifact identity.
4. Complete final clean-machine README/package/disposable-repo/cleanup/uninstall sign-off.
5. Bind final release notes/checksums, sign off the Final Release Gate, then tag/publish `v0.1.0`.
