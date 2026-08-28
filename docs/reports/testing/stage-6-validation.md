# Stage 6 Open-Source Security Validation

> Date: 2026-08-28
> Status: **REPOSITORY GATES IMPLEMENTED / LIVE SECURITY SCANS PENDING / RELEASE BLOCKER**

## Scope

Stage 6 covers repository privacy, Git-history secret scanning, dependency vulnerability review,
third-party provenance/license handling, and final release-artifact secret/runtime-state scanning.

The release is not allowed to treat implementation of a scanner as equivalent to a passing scan.

## Repository-side controls implemented

### Current tracked tree privacy guard

`bridge/tests/test_open_source_privacy.py` now fails when current non-historical tracked content contains
known operator-specific deployment markers or when runtime/secret material becomes tracked.

The historical evidence boundary is explicit:

- `docs/releases/`
- `docs/reports/`

Historical evidence may retain redacted or factual acceptance records, but current source, scripts, tests,
guides, architecture, and plans must remain reusable and operator-neutral.

### Fixed local security-audit workflow

`scripts/validate-open-source-security.ps1` implements one fixed release-security workflow:

1. `uv audit --project bridge --frozen`;
2. export `HEAD` with `git archive`;
3. Gitleaks scan of the exported current tracked tree;
4. Gitleaks full Git-history scan;
5. optional directory/ZIP artifact scan;
6. explicit rejection of runtime/secret artifact names such as `projects.toml`, `remote.toml`,
   `*.dpapi`, `*.sqlite3*`, and `*.log`.

Reports are written only under ignored `.local/security-audit/`.

The `codemcp-remote` built-in project profile contains a fixed `security-audit` command using this script.
It does not accept arbitrary shell, executable paths, or runtime argv.

### Gitleaks pin

Local Windows preparation is fixed to Gitleaks `8.30.0` Windows x64 with SHA-256:

`54fe94f644b832dd08e8c3a5915efb3bfa862386d59fb27ca0792cb687a83573`

Hosted Linux CI uses the same version with Linux x64 SHA-256:

`79a3ab579b53f71efd634f3aaf7e04a0fa0cf206b7ed434638d1547a2470a66e`

The pin is intentional. Gitleaks `8.30.1` had a published Windows x64 checksum inconsistency, so the
release gate does not silently move to that asset. Any scanner upgrade requires an explicit checksum
and behavior review.

### Hosted CI gate

`.github/workflows/ci.yml` now has an `Open-source security gates` job that:

- checks out full Git history with credentials persistence disabled;
- runs locked `uv audit`;
- downloads and verifies pinned Gitleaks;
- scans a `git archive HEAD` current-tree export;
- scans full Git history.

A workflow file in the repository is not hosted-CI evidence. The first real hosted execution remains
part of the Stage 5/6 release evidence.

## Dependency provenance and license review

### codemcp 0.3.0

The execution dependency remains `codemcp==0.3.0` from PyPI, pinned by `bridge/uv.lock`.

Verified PyPI artifact hashes:

- wheel: `a56123f6e1544aed55dbfd1b4946fc2583222b4104a82d8a2171d8c1621cd32a`
- sdist: `a28161aa86176cebd1861e7c134ac98ab1762849d75b46915e0a9fc4ef6efae7`

The `0.3.0` distribution contains inconsistent license metadata:

- distribution `METADATA`: `License: MIT`;
- bundled `License-File`: full Apache License 2.0 text;
- the source reference used for compatibility review also identifies Apache-2.0.

The release therefore does not collapse this into an unsupported single-license claim. Packaging keeps
the bundled license text and records the metadata discrepancy in third-party notices.

### Bundled transport components

The Windows packaging path already preserves third-party provenance/license evidence for:

- `cloudflared`: pinned version and SHA-256, Apache-2.0 license;
- OpenAI `tunnel-client`: upstream checksum manifest, SPDX sidecar, license, archive/binary hashes;
- `codemcp`: pinned PyPI artifact hashes plus bundled license and discrepancy notice.

The release-package contract uses generated `THIRD_PARTY_NOTICES.txt` plus component license files.
A separate root `THIRD_PARTY_NOTICES.md` is not required for `v0.1.0`.

## Validation evidence

Before the Stage 6 security-workflow additions, the privacy/supply-chain remediation baseline passed:

- format: `76 files already formatted`;
- tests: `335 passed, 7 skipped, 0 failed`.

After adding the fixed security workflow and hosted security job:

- format: `77 files already formatted`;
- full test result: **pending in this record until the active registered run completes**.

Do not replace the pending line with PASS unless the registered test operation is actually successful.

## Remaining mandatory evidence

Stage 6 remains a release blocker until all of the following are recorded:

- [ ] updated full regression PASS after the Stage 6 workflow changes;
- [ ] local `security-audit` dependency audit PASS or explicit accepted-risk record;
- [ ] local current tracked-tree Gitleaks scan PASS;
- [ ] local full Git-history Gitleaks scan PASS;
- [ ] first hosted CI security job PASS;
- [ ] final release staging directory or ZIP scanned with `-RequireArtifact`;
- [ ] final artifact contains no runtime/operator secret material;
- [ ] any discovered historical credential is revoked/rotated before history remediation;
- [ ] final dependency/license review is rechecked against the exact RC lockfile and payload.

## Execution boundary

The currently running pre-update Bridge exposes only its previously built fixed command catalog. Adding
`security-audit` to source does not hot-reload executable code into that running process.

Therefore this record intentionally does **not** claim a local history/dependency scan result yet.
The new fixed command must be executed through a rebuilt/updated Bridge or through the hosted CI gate.
