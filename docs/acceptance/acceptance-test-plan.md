# Phase 7 Acceptance Test Plan — v0.1.0 Release Gate

> Status: DRAFT / EXECUTION PENDING
> Date: 2026-08-26
> Target: first stable `v0.1.0`

## 1. Purpose

This plan is the final functional, security, reliability, documentation, and packaging gate for the first stable codemcp-remote release.

A test listed here is not PASS merely because an implementation or lower-phase automated test exists. Stable release requires the applicable automated suites to pass from the release candidate commit and the real-host cases to have recorded evidence.

## 2. Release candidate identity

The final execution record MUST capture:

- Git branch;
- release candidate commit SHA;
- working-tree status;
- Python version;
- `uv` version;
- Git version;
- PowerShell version;
- Windows version;
- WSL distribution/version;
- pinned codemcp release/commit;
- MCP SDK/package lock state;
- Tunnel client version;
- Bridge configuration path;
- project-registry configuration path;
- validation date.

No secret values may be copied into the acceptance record.

## 3. Preconditions

Before Phase 7 execution:

1. Stage 0 baseline checks are complete.
2. Phase 6 validation is PASS.
3. the release candidate worktree is clean.
4. local runtime secrets are injected outside Git.
5. `config/projects.toml` contains only test/acceptance projects appropriate for the run.
6. at least:
   - one real Java Git project; and
   - one project with a front-end build/test command
   are available as dedicated acceptance projects.
7. destructive/recovery tests use disposable branches or fixture repositories.
8. the threat model has no untracked P0 threat.

### Phase 5.5.7 profile selection

The recommended personal acceptance profile is **5.5.7A**:

```text
ChatGPT Connector (Authentication = No authentication)
  -> OpenAI Connector egress network
  -> Cloudflare WAF IP List/rule
  -> Cloudflare Tunnel
  -> 127.0.0.1:46200
  -> network-trust Bridge + existing project/security policies
```

Profile A requires `auth.mode = "none"`, `network_trust.mode =
"cloudflare-chatgpt"`, and non-empty exact `allowed_hosts`; it does not require
`CODEMCP_RS_VERIFICATION_SECRET`. The Cloudflare allowlist is a network trust
boundary, not authentication or user identity, and cannot identify a ChatGPT
user, Workspace, account, or conversation. Profile B remains the optional
advanced OAuth Resource Server profile with `mcp-rs-verification-v1`.

The local Phase A–G implementation and regression gates do not replace the live
Phase H checks. The release record must separately prove Cloudflare WAF
`BLOCK` for an ordinary public source, Connector `ALLOW`, stopped-tunnel
behavior, the selected Connector contract, and cleanup.

## 4. Automated suite gate

Run the repository's complete registered test workflow from the release candidate.

Current registered suite:

```text
pytest -q bridge/tests tests/integration
```

Also run the configured formatting/lint/build checks required by the release workflow and:

```text
git diff --check
```

Required result:

- all tests PASS;
- no unexpected skips for a P0 security case;
- formatting/lint/build checks PASS;
- `git diff --check` PASS;
- worktree remains clean after read-only checks.

### Current status

**LOCAL REGRESSION PASS (2026-08-26):** `312 passed, 6 skipped` from
`bridge/tests` and `tests/integration`, with the project virtual environment
available on PATH for tests that intentionally invoke a `python` command.
The skipped cases are environment/profile-specific (symlink permission,
non-applicable WSL host, or opt-in real installer acceptance). This local PASS
does not close the live Phase H or final release gate.

The full repository Ruff check and format validation pass after mechanical
cleanup of the existing findings. This is a lint result only and does not
prove the Phase H live Cloudflare or ChatGPT Connector boundary.

## 5. MCP contract gate

The exposed tool set for the current release candidate must match the intentional public contract.

Expected tools:

1. `project_open`
2. `project_status`
3. `file_read`
4. `code_search`
5. `file_list`
6. `file_edit`
7. `file_create`
8. `file_write`
9. `file_move`
10. `file_delete`
11. `directory_create`
12. `registered_command_run`
13. `format_run`
14. `test_run`
15. `git_status`
16. `git_diff`
17. `checkpoint_create`
18. `checkpoint_restore`
19. `operation_status`
20. `approval_confirm`
21. `operation_cancel`
22. `operation_reconcile`

Required checks:

- no arbitrary shell tool;
- no caller-controlled executable path;
- no generic runtime argv surface for registered commands;
- no arbitrary absolute host path input that bypasses project registration;
- mutation tools expose `client_request_id` / request-hash semantics;
- high-risk operations preserve explicit approval where designed;
- schema changes from the previous validated baseline are reviewed, not silently accepted.

Existing automated evidence includes the local MCP contract test in `bridge/tests/test_phase2_server.py`.

Status: **PENDING RELEASE-CANDIDATE RE-RUN.**

## 6. Functional acceptance

Use the real acceptance projects and verify the normal workflow from ChatGPT through the supported Tunnel path.

| ID | Flow | Required result | Status |
|---|---|---|---|
| F-01 | open registered project | correct project/session, branch/HEAD metadata | PENDING |
| F-02 | project status | readiness and Git state are accurate | PENDING |
| F-03 | list/read text files | content/metadata correct and bounded | PENDING |
| F-04 | search code | relevant results returned; sensitive paths omitted | PENDING |
| F-05 | create file | tracked change created once; replay is idempotent | PENDING |
| F-06 | exact edit | only intended target change is committed | PENDING |
| F-07 | whole-file write with SHA | matching baseline succeeds; stale baseline rejects | PENDING |
| F-08 | move tracked file | source/destination semantics correct; no clobber | PENDING |
| F-09 | delete tracked file | intended tracked file removed; untracked/sensitive targets reject | PENDING |
| F-10 | create directory | Git-trackable marker behavior correct | PENDING |
| F-11 | registered test/format/build | only configured command ID executes; output bounded | PENDING |
| F-12 | git status/diff | changed paths and bounded diff correspond to actual Git state | PENDING |
| F-13 | manual checkpoint | approval required and registered checkpoint created | PENDING |
| F-14 | restore checkpoint | second approval + CAS restore succeeds only at expected HEAD | PENDING |
| F-15 | operation status/audit | lifecycle and audit events reconstruct the operation | PENDING |
| F-16 | cancel pending operation | cancellation applies only to eligible owned operation | PENDING |
| F-17 | reconcile unknown | evidence-backed reconcile releases or preserves project block correctly | PENDING |

## 7. Security negative acceptance

Every case below must fail closed or produce the explicitly designed `unknown`/reconcile state.

| ID | Attack / invalid state | Required behavior | Existing evidence | Release status |
|---|---|---|---|---|
| S-01 | unknown `project_id` | `PROJECT_NOT_ALLOWED` | Phase 2 policy/server tests | PENDING RE-RUN |
| S-02 | absolute/arbitrary path | reject before filesystem access | path-policy tests | PENDING |
| S-03 | `../` traversal | `PATH_ESCAPE` | Phase 2 policy/server tests | PENDING RE-RUN |
| S-04 | symlink escape | `PATH_ESCAPE` | symlink policy test | PENDING RE-RUN |
| S-05 | Windows junction/reparse escape | `PATH_ESCAPE` | implementation path check | PENDING REAL WINDOWS |
| S-06 | `.env` / private key / token path | `SENSITIVE_PATH` | policy/server tests | PENDING RE-RUN |
| S-07 | sensitive path through search | excluded before backend and after result | search regression test | PENDING RE-RUN |
| S-08 | sensitive path through diff | reject/redact before return | policy Git diff test | PENDING RE-RUN |
| S-09 | binary/oversized file | bounded rejection | server contract tests | PENDING RE-RUN |
| S-10 | unregistered command | `COMMAND_NOT_ALLOWED` | server contract test | PENDING RE-RUN |
| S-11 | command drift / injected runtime args | cannot execute outside configured argv | policy contract | PENDING |
| S-12 | dirty workspace mutation | `WORKSPACE_DIRTY` unless both policy layers intentionally opt out | policy/server tests | PENDING RE-RUN |
| S-13 | forged request hash | reject before operation side effect | canonical-hash test | PENDING RE-RUN |
| S-14 | request ID reused with different hash | `IDEMPOTENCY_CONFLICT` | persistence test | PENDING RE-RUN |
| S-15 | wrong approval token | reject | persistence test | PENDING RE-RUN |
| S-16 | expired approval | reject | approval service/test coverage | PENDING |
| S-17 | approval reuse | `APPROVAL_ALREADY_USED` | persistence test | PENDING RE-RUN |
| S-18 | cross-session operation/approval | hide/reject foreign operation | server reconciliation tests | PENDING RE-RUN |
| S-19 | cross-project operation/approval | hide/reject foreign project scope | scope tests + Phase 7 case | PENDING |
| S-20 | external branch/HEAD change before rollback | CAS conflict; no reset | Phase 4 suite | PENDING RE-RUN |
| S-21 | dirty worktree before rollback | reject; no reset | Phase 4 suite | PENDING RE-RUN |
| S-22 | checkpoint ref tampering/missing ref | reject; no unregistered reset | Phase 4 suite | PENDING RE-RUN |
| S-23 | repository prompt injection | cannot widen Bridge authorization | architectural boundary | PENDING RED-TEAM |
| S-24 | non-loopback server configuration | invalid/fail closed according to config validation | server/settings checks | PENDING RE-RUN |
| S-25 | runtime/model credential canary | absent/redacted from logs and evidence | Phase 6 matrix | PENDING |
| S-26 | hidden model/provider egress | no Bridge/codemcp model provider traffic | dependency/source/runtime review | PENDING |
| S-27 | wrong/missing Host or forwarded-host bypass | exact Host boundary rejects; forwarded headers cannot authorize | Phase C runtime matrix | PASS LOCAL / PENDING LIVE |
| S-28 | invalid/present Origin | missing accepted; present non-exact origin rejected | Phase C runtime matrix | PASS LOCAL / PENDING LIVE |
| S-29 | ordinary public source reaches Bridge | Cloudflare WAF blocks before Tunnel/Bridge with `403` | deployment runbook | PENDING PHASE H |

Any bypass of S-01 through S-29 that grants broader filesystem, command, approval, identity, secret, network, or destructive Git capability is a release blocker.

## 8. Reliability and recovery acceptance

| ID | Fault | Required result | Status |
|---|---|---|---|
| R-01 | duplicate successful mutation request | persisted result replayed; no duplicate edit | PENDING |
| R-02 | same request ID / changed hash | conflict, no second side effect | PENDING |
| R-03 | Bridge restart before dispatch | operation classified failed; session recovery explicit | PENDING |
| R-04 | Bridge restart after backend boundary | operation classified `unknown` when outcome uncertain | PENDING |
| R-05 | approval pending during restart | approval cancelled; plaintext token absent | PENDING |
| R-06 | Tunnel disconnect | no transparent mutation replay | PENDING REAL TUNNEL |
| R-07 | worker crash | failure/unknown state preserves safe project block | PENDING REAL WORKER |
| R-08 | registered command timeout | bounded timeout; owned process tree terminated or outcome marked uncertain | PENDING |
| R-09 | external Git race | mutation/rollback detects changed state | PENDING |
| R-10 | reconcile verified not-applied mutation | transition releases lock only with scoped evidence flow | PENDING |
| R-11 | reconcile verified applied mutation after restart | successor-session recovery follows designed constraints | PENDING |
| R-12 | 20 start/doctor/stop cycles | 20/20 with no owned process/listener residue | PENDING PHASE 6 |

The implementation must prefer an explicit unavailable/blocked/unknown result over guessing that a mutation did or did not occur.

## 9. Real-project acceptance

Run at least ten complete remote modification tasks, not ten isolated tool calls.

Minimum distribution:

- five tasks against the Java acceptance project;
- three tasks against the project containing a front-end workflow;
- two tasks exercising recovery/checkpoint/reconcile behavior.

For each task record:

- task ID and project ID;
- starting branch/HEAD;
- session ID;
- relevant operation IDs;
- requested change summary;
- commands executed by registered ID;
- ending branch/HEAD;
- changed-file list;
- diff review result;
- whether approval was used;
- whether any `unknown` state occurred;
- final test result.

Do not copy proprietary source contents into the public acceptance record.

Required result:

- 10/10 tasks have explainable operation/audit/Git lineage;
- no unexplained side effect;
- no unexpected file outside the intended scope;
- all project-specific verification commands pass.

Status: **PENDING.**

## 10. ChatGPT-only reasoning boundary

Verify from the release candidate:

- Bridge source/dependencies contain no configured model provider or hidden agent loop;
- runtime Bridge configuration denies model calls/model egress as designed;
- codemcp remains an execution backend rather than a second reasoning agent;
- one user task is reconstructable as explicit ChatGPT MCP calls and Bridge operations;
- repository prompt text cannot authorize a privileged Bridge action by itself.

Network observation should distinguish expected Tunnel control-plane traffic from prohibited model/provider traffic.

Status: **PENDING.**

## 11. Documentation acceptance

Required public documents:

- [x] `LICENSE` — GNU AGPL v3, project SPDX `AGPL-3.0-only`
- [x] `SECURITY.md`
- [x] `docs/architecture/security-model.md`
- [x] `docs/architecture/threat-model.md`
- [x] `docs/acceptance/phase-6-validation.md`
- [x] `docs/acceptance/acceptance-test-plan.md`
- [x] public-user README and Cloudflare network-trust runbook restructured
- [ ] public-user documentation clean-machine verified
- [ ] `CONTRIBUTING.md`
- [ ] `CODE_OF_CONDUCT.md`
- [ ] `CHANGELOG.md`
- [ ] final third-party license/notices decision
- [ ] final known-limitations section matches implementation
- [ ] release instructions + SHA-256 verification documented

Documentation commands must be copied and executed on a clean supported machine before PASS.

## 12. Secrets and supply-chain acceptance

Before the release tag:

- scan tracked working tree for credentials;
- scan complete Git history for credentials;
- scan `.github/`, scripts, configs, docs, examples, tests, fixtures;
- inspect release artifact after packaging;
- audit locked dependencies for known vulnerabilities;
- review third-party license compatibility/notices;
- confirm no local `config/projects.toml`, Tunnel profile, `.local/`, logs, SQLite database, or runtime key is packaged;
- verify `codemcp==0.3.0` baseline provenance remains intentional.

Status: **PENDING STAGE 6.**

## 13. Packaging and integrity acceptance

The release workflow must produce:

- source/release artifact appropriate to the published installation path;
- deterministic or documented build procedure;
- SHA-256 checksum file;
- release notes;
- known limitations;
- exact Git tag/commit identity.

From the produced artifact on a clean Windows 11 + WSL2 environment:

1. follow README only;
2. install/sync dependencies;
3. create local project configuration from example;
4. initialize local Tunnel profile without storing its runtime key;
5. run doctor;
6. start services;
7. discover the intended MCP tools;
8. complete a safe read and one controlled mutation;
9. stop services;
10. verify checksum and no unexpected runtime residue.

Status: **PENDING STAGE 7.**

## 14. Final Release Gate

Stable `v0.1.0` is allowed only when:

| Gate | Required state |
|---|---|
| Automated suite | PASS |
| MCP contract | PASS |
| Functional | PASS |
| Security negative matrix | PASS |
| Reliability / recovery | PASS |
| Phase 6 operations | PASS |
| 10 real remote tasks | PASS |
| ChatGPT-only boundary | PASS |
| Documentation | PASS |
| Secrets / supply chain | PASS |
| Packaging / clean machine | PASS |
| SHA-256 integrity | PASS |
| Working tree / release commit | CLEAN / VERIFIED |

Any P0 blocker, unexplained skip, unresolved secret exposure, unsafe mutation ambiguity, or mismatch between documentation and executable behavior blocks the stable tag.

## 15. Sign-off record

Fill this only from the final release candidate:

```text
release_candidate_commit:
phase_6_status:
automated_suite:
security_matrix:
reliability_matrix:
real_task_count:
secret_scan:
dependency_audit:
clean_machine_install:
artifact_sha256:
known_blockers:
release_decision: BLOCKED | APPROVED
validated_at:
```

The default decision is `BLOCKED` until every mandatory field is backed by evidence.
