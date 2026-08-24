# Phase 6 Validation — Windows 11 Operations

> Status: IN PROGRESS
> Date: 2026-08-24
> Release target: `v0.1.0`

## Goal

Validate that codemcp-remote can be started, diagnosed, stopped, recovered, and upgraded predictably on its supported Windows 11 + WSL2 operating path.

This document is a Release Gate record. A documented test case is not considered passed until its evidence is captured from a real supported host.

## Supported validation environment

- Windows 11 host.
- PowerShell 7 (`pwsh`).
- WSL2 Ubuntu mutation worker.
- Python 3.12+.
- Git.
- `uv`.
- pinned `codemcp==0.3.0`.
- configured OpenAI Secure MCP Tunnel for Tunnel-dependent cases.
- Bridge bound to loopback only.

## Evidence handling

Validation output belongs under `.local/validation/` and MUST remain Git-ignored.

Evidence may contain local paths, process IDs, Git metadata, and diagnostic details. The lifecycle runner applies the same diagnostic redaction helpers used by the Tunnel scripts before persisting captured stdout/stderr. Even redacted evidence must be treated as local operational data and reviewed before sharing externally.

Never place `CONTROL_PLANE_API_KEY` in command-line parameters, config files, the Tunnel profile, or validation artifacts.

## A. Repeatable lifecycle validation

The automated lifecycle runner executes:

`start-all.ps1 → doctor.ps1 → stop-all.ps1`

and requires every step to exit successfully. `stop-all.ps1` also verifies that project-owned processes and the loopback listeners it manages are not left behind.

Default release run:

```powershell
pwsh -File .\scripts\validate-lifecycle.ps1 -Iterations 20
```

For a clean host whose local Tunnel profile has not yet been materialized:

```powershell
pwsh -File .\scripts\validate-lifecycle.ps1 -Iterations 20 -InitializeFirst
```

`-InitializeFirst` applies only to the first iteration and does not imply `-Force`. The validator intentionally provides no force-overwrite option for a Tunnel profile.

Expected result:

- process exit code `0`;
- `status = "ok"`;
- `requested_iterations = 20`;
- `completed_iterations = 20`;
- every `start`, `doctor`, and `stop` step reports exit code `0`;
- no unrecognized listener is reported after stop;
- evidence is stored in `.local/validation/phase6-lifecycle-<UTC timestamp>/`.

If any iteration fails, the validator stops the sequence, attempts `stop-all.ps1` cleanup, records redacted evidence, and exits non-zero.

### Current status

**PENDING REAL-HOST EXECUTION.**

The script has been added to the repository, but this Release Gate is not marked PASS until the 20-cycle run is executed on the supported Windows 11 host.

## B. Failure and recovery matrix

Each case must be run from a known healthy baseline and must record the observed diagnostic/recovery result.

| Case | Injection / setup | Required outcome | Status |
|---|---|---|---|
| Bridge exits unexpectedly | terminate the repository-owned Bridge process while Tunnel remains present | `doctor.ps1` identifies Bridge failure; restart restores health; no mutation is silently replayed | PENDING |
| tunnel-client exits unexpectedly | terminate the repository-owned Tunnel process | Bridge remains local; remote readiness fails; restart Tunnel restores readiness without replay | PENDING |
| codemcp worker exits unexpectedly | terminate active WSL2 codemcp worker during a controlled test | worker failure is surfaced; uncertain mutation is `unknown`; subsequent unsafe mutation remains blocked pending reconcile | PENDING |
| Bridge startup port occupied | bind Bridge port with an unrelated process | `start-all.ps1` refuses to reuse the unrecognized process and exits non-zero | PENDING |
| Tunnel health port occupied | bind Tunnel health port with an unrelated process | startup/stop validation does not kill the unrelated process; state is reported for operator action | PENDING |
| stale process metadata / stale state | simulate recoverable stale local runtime state without altering trusted code/config | startup/doctor reports or safely replaces only state it owns; unrelated processes are untouched | PENDING |
| WSL unavailable | stop/disable target WSL distribution for the test | doctor fails with actionable WSL/worker diagnostic; no mutation dispatch | PENDING |
| Git unavailable | temporarily remove Git from the validation process PATH | doctor/start prerequisite check fails clearly; no mutation dispatch | PENDING |
| Tunnel unauthenticated | omit/invalid runtime Tunnel credential in isolated test environment | Tunnel readiness fails without printing credential; Bridge can still be diagnosed locally with `-SkipTunnel` | PENDING |
| Tunnel disconnect during mutation | controlled disconnect at backend-boundary test point | operation must not be transparently replayed; uncertain outcome is reconciled explicitly | PENDING |
| timeout / process tree | run a registered bounded test fixture that spawns a child and exceeds timeout | timeout is reported and the owned process tree is terminated, or uncertainty is surfaced fail-closed | PENDING |

Destructive fault injection must use a disposable fixture repository or a dedicated test project, never an uncommitted production workspace.

## C. Log and secret validation

Use synthetic canaries, never real credentials.

Required canary classes:

- `CONTROL_PLANE_API_KEY=<synthetic value>`;
- `Authorization: Bearer <synthetic value>`;
- an `sk-...` shaped synthetic key;
- approval token-shaped text;
- a synthetic secret file under a denied filename.

Inspect:

- `.local/logs/bridge.log*`;
- `.local/logs/tunnel-client.log*`;
- `.local/logs/workers/*.stderr.log*`;
- `.local/validation/**`;
- doctor output captured for the validation.

Release requirement:

- runtime/Tunnel canaries are absent or redacted;
- approval plaintext is not persisted;
- denied secret-file contents do not appear in unrestricted diagnostics;
- useful error context remains after redaction.

Status: **PENDING**.

## D. Encoding and path matrix

Run representative registered fixture projects with:

| Case | Required outcome | Status |
|---|---|---|
| ASCII path | normal start/read/mutation/test flow | PENDING |
| path containing spaces | same behavior as ASCII | PENDING |
| Chinese path / filename | correct UTF-8 read, worker path mapping, logging, and Git status | PENDING |
| CRLF source file | exact edit/write preserves intended line-ending behavior | PENDING |
| LF source file | exact edit/write preserves intended line-ending behavior | PENDING |
| long Windows path within supported OS limits | actionable success or explicit supported-limit failure; no silent truncation | PENDING |

## E. Dependency upgrade and rollback

Before changing `codemcp`, MCP SDK, or other execution-path dependencies:

1. create a clean Git checkpoint/tag for the known-good dependency set;
2. preserve the existing lock file;
3. update one dependency scope at a time;
4. run doctor, the full automated test suite, compatibility tests, Phase 6 lifecycle validation, and Phase 7 security acceptance;
5. compare exposed MCP tool schemas and codemcp behavior against `docs/codemcp-compatibility-matrix.md`;
6. reject the upgrade if mutation/Git/process semantics change without an explicit design review.

Rollback:

1. stop Bridge/Tunnel/worker trees with `stop-all.ps1`;
2. restore the known-good dependency metadata and lock file from Git;
3. rebuild/sync the environment from the restored lock;
4. run doctor;
5. run the full test suite;
6. run at least one lifecycle cycle before reconnecting ChatGPT;
7. do not reuse an `unknown` mutation as evidence that rollback succeeded—reconcile the repository state separately.

Status: **DOCUMENTED; EXECUTION PENDING FOR NEXT REAL UPGRADE.**

## F. Release exit criteria

Phase 6 is PASS only when all of the following are true:

- [ ] 20/20 automated lifecycle iterations pass on a supported Windows 11 host.
- [ ] Bridge, Tunnel, and worker abnormal-exit cases pass.
- [ ] unrelated port/listener cases fail safely.
- [ ] WSL, Git, and Tunnel dependency failures produce actionable diagnostics.
- [ ] timeout/process-tree cleanup passes.
- [ ] synthetic log/credential canary scan passes.
- [ ] spaces, Chinese paths, line endings, and supported long paths are validated.
- [ ] upgrade and rollback procedure is reviewed against the pinned dependency baseline.
- [ ] no Phase 6 P0/P1 blocker remains open.

Until every checkbox above has evidence, Phase 6 remains **IN PROGRESS** and stable `v0.1.0` remains blocked.
