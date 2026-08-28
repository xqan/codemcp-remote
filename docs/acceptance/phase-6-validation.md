# Phase 6 Validation — Windows 11 Operations

> Status: **IN PROGRESS — RELEASE BLOCKER**  
> Updated: 2026-08-28  
> Release target: `v0.1.0`

## 1. Goal

Validate that the **current packaged Windows release path** can be started, diagnosed, stopped, recovered and operated predictably on Windows 11.

The mandatory `v0.1.0` Phase 6 profile is:

```text
Windows 11
  + packaged codemcp-remote.exe
  + Git for Windows
  + Native Windows local worker
  + Cloudflare Tunnel
  + Profile A: auth.mode=none
  + network_trust.mode=cloudflare-chatgpt
```

WSL2 and OpenAI Secure MCP Tunnel remain compatibility paths. Their existence must not make WSL2, Python, `uv`, PowerShell 7 or `CONTROL_PLANE_API_KEY` a mandatory installed-runtime requirement.

A documented case is not PASS until real-host evidence is captured.

## 2. Mandatory validation environment

Use the final or current release-candidate artifact on a supported Windows 11 x64-compatible host/VM.

Required:

- Windows 11;
- installed `codemcp-remote.exe`;
- Git for Windows;
- Native Windows `worker_mode=local`;
- bundled `cloudflared`;
- configured Cloudflare Tunnel;
- Profile A network trust;
- Bridge bound to loopback;
- a disposable registered Git project;
- no dependency on source checkout for normal product execution.

The installed runtime must continue to work when these development tools are absent from the product runtime `PATH`:

- Python;
- `uv`;
- PowerShell 7;
- WSL2 worker environment.

Source-development validation may still use Python/uv/pwsh and the repository scripts, but that is supporting evidence rather than the mandatory packaged-runtime contract.

## 3. Evidence handling

Acceptance evidence must not contain real credentials.

Use synthetic canaries and redact:

- Cloudflare `TUNNEL_TOKEN`;
- OAuth Resource Server verification secret when Profile B is separately tested;
- `CONTROL_PLANE_API_KEY` when the optional Secure MCP compatibility transport is tested;
- Bearer tokens;
- approval tokens;
- private-key or secret-file contents.

Evidence may contain local paths, process IDs and Git metadata. Treat it as sensitive operational data even after redaction.

Do not commit runtime logs, SQLite databases, DPAPI secret blobs, local project registry values or acceptance credentials.

## 4. A — Repeatable packaged lifecycle

### 4.1 Mandatory 20-cycle gate

From the installed release candidate, execute at least 20 complete cycles:

```text
codemcp-remote.exe start
  -> codemcp-remote.exe doctor
  -> codemcp-remote.exe status
  -> codemcp-remote.exe stop
```

Each iteration must prove:

- start exits successfully;
- Bridge becomes healthy;
- Cloudflare Tunnel becomes healthy/ready;
- `doctor` reports the configured Profile A contract;
- `worker_mode = local`;
- Git prerequisite is available;
- stop terminates only product-owned process trees;
- no owned Bridge/Tunnel/worker process is left behind;
- unrelated listeners/processes are not killed;
- the next iteration starts from a known state.

Required release result:

```text
requested_iterations = 20
completed_iterations = 20
failed_iterations = 0
```

Status: **PENDING REAL-HOST EXECUTION.**

### 4.2 Source-mode lifecycle runner

The existing source-development runner remains useful:

```powershell
pwsh -File .\scripts\validate-lifecycle.ps1 -Iterations 20
```

It validates the repository PowerShell lifecycle path and stores local evidence under `.local/validation/`.

This runner does **not** replace the mandatory packaged-runtime 20-cycle gate.

### 4.3 Non-destructive live-host smoke

`tests/integration/test_phase6_live_host.py` provides a bounded Windows-only smoke that can reuse an already healthy loopback Bridge without stopping it. When `http://127.0.0.1:46200/healthz` is reachable from the registered test process, it executes:

- `scripts/doctor.ps1 -SkipTunnel`;
- `scripts/stop-all.ps1 -WhatIf`.

The smoke never performs an actual stop. If no live Bridge is visible from the test process, it skips rather than pretending that live-host evidence exists.

Current evidence on 2026-08-28:

```text
331 passed, 7 skipped
Phase 6 live-host smoke: SKIPPED
reason: no live loopback Bridge is available on the Phase 6 baseline port
```

This confirms that the current `codemcp-557` control path cannot be counted as same-process/same-port source-mode Phase 6 evidence merely because remote MCP calls are working. The mandatory packaged-runtime 20-cycle gate remains PENDING and must run in an isolated acceptance lifecycle where stopping the candidate cannot terminate the control channel used to conduct the test.

## 5. B — Failure and recovery matrix

Every case starts from a known healthy packaged Profile A baseline.

| Case | Injection / setup | Required outcome | Status |
|---|---|---|---|
| Bridge exits unexpectedly | terminate the product-owned Bridge process | `doctor` identifies Bridge failure; restart restores health; no mutation is silently replayed | PENDING |
| `cloudflared` exits unexpectedly | terminate the product-owned Cloudflare Tunnel process | Bridge remains loopback-local; remote readiness fails; restart restores transport without mutation replay | PENDING |
| Native codemcp worker exits unexpectedly | terminate active local worker during a controlled operation | failure/uncertainty is surfaced; uncertain mutation becomes `unknown`; unsafe follow-up mutation remains blocked pending reconcile | PENDING |
| Bridge port occupied | bind Bridge port with unrelated process | product refuses to adopt/kill unrelated listener and fails safely | PENDING |
| Tunnel health/control port occupied | bind relevant local transport port with unrelated process | startup/stop does not kill unrelated process; actionable state is reported | PENDING |
| stale runtime/process metadata | simulate recoverable stale owned state | product replaces/cleans only state it can prove it owns | PENDING |
| Git unavailable | isolate product PATH without Git | `doctor`/start fails with actionable Git prerequisite error; no mutation dispatch | PENDING |
| Cloudflare token missing/invalid | isolated Profile A with absent/invalid transport credential | Tunnel readiness fails without credential disclosure; local Bridge remains diagnosable | PENDING |
| Tunnel disconnect during mutation | controlled transport interruption at backend boundary | operation is not transparently replayed; uncertainty is reconciled explicitly | PENDING |
| command timeout/process tree | registered bounded fixture spawns child and exceeds timeout | owned process tree terminates or outcome becomes explicitly unknown/fail-closed | PENDING |
| restart with pending approval | restart while operation awaits approval | stale plaintext approval is unavailable; operation/session recovery follows defined fail-closed semantics | PENDING |
| restart around backend boundary | restart before and after dispatch boundary | pre-dispatch operation fails safely; uncertain post-boundary mutation is `unknown` | PENDING |

Destructive fault injection must use a disposable fixture repository or dedicated acceptance project.

## 6. C — Log and credential canary validation

Use synthetic values only.

Mandatory Profile A canaries:

- `TUNNEL_TOKEN=<synthetic value>`;
- `Authorization: Bearer <synthetic value>`;
- an `sk-...` shaped synthetic key;
- approval-token-shaped text;
- a synthetic denied secret file.

When optional compatibility profiles are tested, also include:

- `CONTROL_PLANE_API_KEY=<synthetic value>`;
- Profile B Resource Server verification-secret canary.

Inspect:

- Bridge logs;
- Cloudflare Tunnel logs;
- worker stderr logs;
- lifecycle/validation evidence;
- `doctor`/status output;
- crash/recovery diagnostics.

Release requirement:

- credential canaries are absent or redacted;
- plaintext approval tokens are not persisted;
- denied secret-file contents do not appear in unrestricted diagnostics;
- useful error context remains after redaction.

Status: **PENDING.**

## 7. D — Encoding and Windows path matrix

Run representative registered fixture projects with Native Windows worker mode.

| Case | Required outcome | Status |
|---|---|---|
| ASCII path | normal read/mutation/test/Git flow | PENDING |
| path containing spaces | same security and mutation behavior as ASCII | PENDING |
| Chinese path / filename | correct UTF-8 read/write/search/log/Git behavior | PENDING |
| CRLF source file | exact edit/write preserves intended line-ending semantics | PENDING |
| LF source file | exact edit/write preserves intended line-ending semantics | PENDING |
| supported long Windows path | success or explicit supported-limit failure; no silent truncation | PENDING |
| mixed command output encoding | output remains bounded/diagnosable without secret disclosure | PENDING |

WSL path mapping is a separate compatibility test when `worker_mode=wsl2` is intentionally advertised; it is not part of the mandatory Native Windows installed-runtime matrix.

## 8. E — Dependency upgrade and rollback

Before changing `codemcp`, MCP SDK or another execution-path dependency:

1. record the known-good dependency lock and release-candidate commit;
2. preserve the existing lock file;
3. change one dependency scope at a time;
4. run `doctor`;
5. run the complete automated suite;
6. run the codemcp compatibility matrix;
7. rerun affected Phase 6 lifecycle/recovery cases;
8. rerun Phase 7 security acceptance;
9. compare the exposed 22-tool MCP schema;
10. reject the upgrade if mutation/Git/process/replay semantics change without an explicit design review.

Rollback:

1. stop all product-owned Bridge/Tunnel/worker trees;
2. restore known-good dependency metadata and lock;
3. rebuild the release candidate from the known-good commit;
4. run `doctor`;
5. run the complete automated suite;
6. run at least one packaged lifecycle cycle;
7. reconcile any pre-existing `unknown` mutation separately;
8. do not treat dependency rollback as proof that an uncertain repository mutation was reverted.

Status: **DOCUMENTED; FINAL RELEASE-BASELINE REVIEW PENDING.**

## 9. Compatibility-only checks

These are not mandatory default-runtime dependencies, but must remain truthful if advertised:

### WSL2 fallback

When explicitly configuring `worker_mode=wsl2`:

- missing/unavailable WSL produces an actionable diagnostic;
- no mutation dispatch occurs when worker preparation is invalid;
- path mapping and worker stderr remain bounded and correct.

### OpenAI Secure MCP Tunnel

When explicitly selecting the compatibility transport:

- loopback target constraints remain enforced;
- plaintext `CONTROL_PLANE_API_KEY` is not persisted in repo/profile/logs;
- transport failure does not grant broader Bridge authorization.

### OAuth Profile B

When explicitly testing Profile B:

- its verification secret uses the documented protected source;
- subject/client/scope identity remains separate from Profile A `network-only` identity.

A failure in an advertised compatibility feature must either be fixed or documented by narrowing the `v0.1.0` support claim.

## 10. Release exit criteria

Phase 6 is PASS only when all mandatory items below have real evidence from the current release candidate:

- [ ] 20/20 packaged lifecycle iterations PASS;
- [ ] Bridge, Cloudflare Tunnel and Native Windows worker abnormal-exit cases PASS;
- [ ] unrelated port/listener cases fail safely;
- [ ] Git and transport-credential dependency failures produce actionable diagnostics;
- [ ] restart/backend-boundary recovery follows `failed`/`unknown` semantics;
- [ ] timeout/process-tree cleanup PASS;
- [ ] synthetic log/credential canary scan PASS;
- [ ] spaces, Chinese paths, line endings and supported long paths PASS;
- [ ] dependency upgrade/rollback procedure reviewed against current pinned baseline;
- [ ] no Phase 6 P0/P1 blocker remains open.

Until every mandatory checkbox has evidence, Phase 6 remains:

```text
IN PROGRESS
```

and stable `v0.1.0` remains blocked.
