# Stage 6 Open-Source Security Validation

> Date: 2026-08-28
> Status: **LOCAL AUTOMATED SECURITY GATES PASS / MANUAL LICENSE REVIEW + HOSTED CI + CLEAN-MACHINE PRODUCTION INSTALLER PENDING / RELEASE BLOCKER**

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
3. Gitleaks scan of the exported current tracked tree plus operator-specific deployment/path checks;
4. Gitleaks Git-history scan across all refs with `--log-opts=--all`;
5. optional directory/ZIP artifact scan;
6. explicit rejection of runtime/secret artifact names such as `projects.toml`, `remote.toml`,
   `*.dpapi`, `*.sqlite3*`, and `*.log`;
7. explicit rejection of operator-specific deployment/path data from final artifacts.

Reports are written only under ignored `.local/security-audit/`.

The `codemcp-remote` built-in project profile contains two fixed commands using this script:

- `security-audit`: source/dependency/current-tree/history gate;
- `artifact-audit`: the same gate plus mandatory scan of the standard
  `.local/release-candidate/codemcp-remote-v0.1.0-windows-x64.zip`.

Both commands are mirrored in root `codemcp.toml`. They do not accept arbitrary shell, executable paths,
or runtime argv through the Bridge.

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

### Windows build-tool provenance

The Windows EXE build no longer resolves PyInstaller from a floating transitive dependency graph.
`scripts/build-windows-exe.ps1` and `scripts/prepare-pypi-wheel.ps1` pin and SHA-256 verify the complete
PyInstaller build-tool wheel closure used by the `v0.1.0` Windows x64 path:

- `pyinstaller==6.22.2`;
- `pyinstaller-hooks-contrib==2026.6`;
- `altgraph==0.17.5`;
- `pefile==2024.8.26`;
- `pywin32-ctypes==0.2.3`;
- `packaging==26.3`;
- `setuptools==84.0.0`.

The helper verifies both the repository-pinned digest and the digest published in PyPI JSON before a
wheel can be consumed. Cached/downloaded bytes are then verified again.

The build extracts the verified PyInstaller wheel's upstream `COPYING.txt`, requires the bootloader
exception to be present, preserves it at `THIRD_PARTY/pyinstaller/COPYING.txt`, and writes a matching
`NOTICE.txt`. `BUILD_PROVENANCE.json` records the exact build-tool filenames, versions, and SHA-256
digests. The remote-transport staging step and installer smoke both fail closed if this evidence is missing.

### Bundled transport components

The Windows packaging path already preserves third-party provenance/license evidence for:

- `cloudflared`: pinned version and SHA-256, Apache-2.0 license;
- OpenAI `tunnel-client`: upstream checksum manifest, SPDX sidecar, license, archive/binary hashes;
- `codemcp`: pinned PyPI artifact hashes plus bundled license and discrepancy notice;
- PyInstaller bootloader/build output: verified wheel provenance plus upstream `COPYING.txt` and explicit
  `GPL-2.0-or-later WITH Bootloader-exception` notice.

The release-package contract uses generated `THIRD_PARTY_NOTICES.txt`, `BUILD_PROVENANCE.json`, and
component license files. A separate root `THIRD_PARTY_NOTICES.md` is not required for `v0.1.0`.

## Validation evidence

Before the Stage 6 security-workflow additions, the privacy/supply-chain remediation baseline passed:

- format: `76 files already formatted`;
- tests: `335 passed, 7 skipped, 0 failed`.

After adding the fixed security workflow, all-ref history scan, fixed artifact gate, dependency-license
inventory, immutable CI action pins, verified PyInstaller build-tool closure, build provenance, release
license-evidence contracts, and the pytest security-baseline upgrade:

- format: **`77 files already formatted`**;
- full regression: **`342 passed, 7 skipped, 0 failed`**;
- warnings: **`2`** non-blocking warnings;
- `uv audit`: **PASS** — `47 packages`, `0 known vulnerabilities`, `0 adverse project statuses`;
- current tracked-tree Gitleaks: **PASS** — no findings;
- full Git-history Gitleaks: **PASS** — no findings;
- final RC artifact Gitleaks: **PASS** — no findings;
- dependency-license inventory: **47/47 installed locked packages accounted for**, `missing_license_evidence=[]`;
- exact installer SHA-256: `902e15205aee3d585fafa0248c89419171f5a14d6bb249655820318d4fd8e7c6`;
- exact RC ZIP SHA-256: `0ce11c91e5735808ffa1260755ba4030adbed220f5d2f9fe5ca9818b3a39fed1`;
- staging payload audit: **PASS**;
- final RC audit: **PASS**.

This proves the repository-side implementation and local automated Stage 6 release-security gates are
regression-clean for the exact RC above. The dependency-license inventory still explicitly reports
`manual_compatibility_review_required=true`; automated evidence collection is not a legal compatibility
signoff.

## Remaining mandatory evidence

Stage 6 remains a release blocker until the remaining non-local-automation gates are recorded:

- [x] updated full regression PASS after the Stage 6 workflow changes (`342 passed, 7 skipped`);
- [x] local dependency vulnerability audit PASS;
- [x] local current tracked-tree Gitleaks scan PASS;
- [x] local full Git-history Gitleaks scan PASS;
- [x] final release staging payload audit PASS;
- [x] final RC ZIP audit PASS;
- [x] final artifact contains no detected runtime/operator secret material;
- [x] no historical credential finding requiring revoke/rotate/history remediation was detected;
- [ ] manual dependency/license compatibility review is signed off against the exact RC lockfile and payload;
- [ ] first hosted CI security job PASS;
- [ ] production installer clean-machine validation PASS.

## Execution boundary

The local one-click release workflow has now executed the dependency, tracked-tree, full-history, staging
payload, and final RC scans successfully and preserved evidence under `.local/release-evidence/`.

The developer-machine installer smoke used `isolated-existing-production-install`, so it validates the
payload/install/upgrade/uninstall mechanics without modifying the existing production installation. It does
**not** replace the final clean-machine validation of the production AppId installer.
