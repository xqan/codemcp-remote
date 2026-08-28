# Phase 7 Acceptance Test Plan — v0.1.0 Final Release Gate

> Status: **IN PROGRESS / FINAL RELEASE CANDIDATE PENDING**  
> Updated: 2026-08-28  
> Target: first stable `v0.1.0`

## 1. Purpose

This is the final functional, security, reliability, documentation, supply-chain and packaging gate for stable `v0.1.0`.

A feature is not PASS merely because:

- code exists;
- a lower-phase test exists;
- the current private Connector works;
- a historical release-candidate build succeeded.

Final approval requires evidence bound to the final release-candidate commit.

## 2. Mandatory release profile

The default `v0.1.0` acceptance profile is Profile A:

```text
Windows 11
  + packaged codemcp-remote.exe
  + Git for Windows
  + Native Windows local worker
  + Cloudflare Tunnel
  + ChatGPT Connector: Authentication = No authentication
  + Cloudflare WAF / Connector egress allowlist
  + Bridge network trust
```

Profile A security meaning:

```text
identity_level = network-only
```

Cloudflare network trust is not user authentication and cannot identify a ChatGPT user, account, Workspace or conversation.

Optional compatibility paths are tested only to the extent they remain advertised:

- WSL2 source-mode worker fallback;
- OpenAI Secure MCP Tunnel;
- OAuth Resource Server Profile B.

They do not redefine the mandatory installed-product baseline.

## 3. Release-candidate identity

The final acceptance record must capture:

- Git branch;
- exact release-candidate commit SHA;
- clean worktree state;
- `bridge/uv.lock` identity;
- `codemcp==0.3.0` identity;
- Python/uv/pwsh versions used for source/build CI;
- Windows version used for installed acceptance;
- Git for Windows version/path;
- packaged worker mode;
- Cloudflare client version/identity;
- Bridge configuration identity;
- project-registry configuration identity without exposing project roots publicly;
- auth/network-trust profile;
- installer SHA-256;
- release ZIP SHA-256;
- validation date.

If WSL2 is separately tested, record its distribution/version as compatibility evidence only.

No secret values may be copied into the release record.

## 4. Preconditions

Before final Phase 7 execution:

1. Phase 6 mandatory Windows operations gate is PASS.
2. Release-candidate worktree is clean.
3. The candidate is built from the exact commit being accepted.
4. Runtime secrets are injected/stored outside Git according to the documented protected path.
5. Profile A Cloudflare WAF/network trust is configured.
6. The final release artifact is available for clean-machine validation.
7. At least one dedicated real Java Git project is available for acceptance.
8. At least one project with a front-end build/test workflow is available for acceptance.
9. Destructive/recovery tests use disposable branches or fixture repositories.
10. Threat model has no untracked P0 threat.
11. Current normative documents agree on the default architecture.

## 5. Automated release-candidate gate

Run the complete registered repository workflow from the release-candidate commit.

Current full test scope:

```text
pytest -q bridge/tests tests/integration
```

Also run the release-required:

- Ruff lint;
- Ruff format check;
- package/build checks;
- configuration checks;
- compile/import checks used by CI;
- `git diff --check` equivalent;
- worktree cleanliness verification.

### Latest local development evidence

On 2026-08-28, after the open-source readiness/document alignment and transport-diagnostic fixes and before final release freeze, the registered test workflow reported:

```text
331 passed, 7 skipped
```

The skips are explicit environment/profile gates: unavailable symlink permissions, compatibility-only WSL coverage, opt-in real installer acceptance, and the Windows Phase 6 live-host smoke when no loopback Bridge is visible from the registered test process. A skip is not release PASS evidence; final RC acceptance must either exercise the mandatory case or document why it is outside the release profile.

This is useful development evidence only.

The final RC must re-run the complete gate and justify every remaining skip.

### Required result

- all mandatory tests PASS;
- no unexplained P0 security skip;
- lint/format/build PASS;
- worktree remains clean;
- test execution does not mutate release source state.

## 6. MCP contract gate

The expected public surface is exactly 22 tools:

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
- no generic caller-controlled argv;
- no arbitrary host path bypass;
- no MCP project add/remove/reload/reconfigure;
- mutation tools require canonical request identity/hash semantics;
- approval remains explicit where designed;
- schema differences from the accepted baseline are reviewed.

Status: **PENDING FINAL-RC RE-RUN.**

## 7. Functional acceptance

Use the real acceptance projects through the supported Profile A remote path.

| ID | Flow | Required result | Status |
|---|---|---|---|
| F-01 | open registered project | correct project/session/branch/HEAD metadata | PENDING |
| F-02 | project status | readiness and Git state accurate | PENDING |
| F-03 | list/read text | bounded correct content/metadata | PENDING |
| F-04 | code search | relevant results; sensitive paths omitted | PENDING |
| F-05 | create file | one intended committed change; replay idempotent | PENDING |
| F-06 | exact edit | only intended target change | PENDING |
| F-07 | whole-file write | matching SHA succeeds; stale SHA rejects | PENDING |
| F-08 | move tracked file | no clobber; correct tracked semantics | PENDING |
| F-09 | delete tracked file | intended tracked file only | PENDING |
| F-10 | create directory | intended `.gitkeep`/Git-trackable behavior | PENDING |
| F-11 | registered command | only configured command ID runs | PENDING |
| F-12 | format/test wrappers | only registered expected-kind command runs | PENDING |
| F-13 | git status/diff | bounded state corresponds to repository | PENDING |
| F-14 | manual checkpoint | explicit approval + registered ref | PENDING |
| F-15 | checkpoint restore | second approval + expected-HEAD CAS restore | PENDING |
| F-16 | operation status/audit | lifecycle reconstructable | PENDING |
| F-17 | cancel operation | only eligible owned operation cancelled | PENDING |
| F-18 | reconcile unknown | evidence-backed transition preserves safety | PENDING |
| F-19 | project add hot reload | local CLI add observed without Bridge/Tunnel/Connector restart | PENDING |
| F-20 | project remove revocation | local CLI removal blocks new access and affected active sessions | PENDING |

Project administration F-19/F-20 is executed locally, not through MCP.

## 8. Security negative acceptance

Every case must fail closed or enter the explicitly designed `unknown` state.

| ID | Attack / invalid state | Required behavior | Status |
|---|---|---|---|
| S-01 | unknown `project_id` | `PROJECT_NOT_ALLOWED` | PENDING |
| S-02 | arbitrary absolute path | reject before unauthorized filesystem access | PENDING |
| S-03 | `../` traversal | `PATH_ESCAPE` | PENDING |
| S-04 | symlink escape | fail closed | PENDING |
| S-05 | Windows junction/reparse escape | fail closed | PENDING REAL WINDOWS |
| S-06 | secret path | `SENSITIVE_PATH`/equivalent denial | PENDING |
| S-07 | secret through search | excluded before/after backend | PENDING |
| S-08 | sensitive content through diff | reject/redact | PENDING |
| S-09 | binary/oversized file | bounded rejection | PENDING |
| S-10 | unregistered command | `COMMAND_NOT_ALLOWED` | PENDING |
| S-11 | runtime argv/executable injection | impossible through public schema | PENDING |
| S-12 | dirty workspace mutation | fail according to policy | PENDING |
| S-13 | forged canonical request hash | reject before side effect | PENDING |
| S-14 | request ID reused with changed input/hash | idempotency conflict | PENDING |
| S-15 | wrong approval token | reject | PENDING |
| S-16 | expired approval | reject | PENDING |
| S-17 | reused approval | reject | PENDING |
| S-18 | cross-session operation/approval | hide/reject foreign scope | PENDING |
| S-19 | cross-project operation/approval | hide/reject foreign scope | PENDING |
| S-20 | external branch/HEAD change before restore | CAS conflict; no reset | PENDING |
| S-21 | dirty worktree before restore | reject; no reset | PENDING |
| S-22 | checkpoint ref tamper/missing | reject; no arbitrary reset | PENDING |
| S-23 | repository prompt injection | cannot widen Bridge authorization | PENDING RED-TEAM |
| S-24 | non-loopback Bridge config | invalid/fail closed | PENDING |
| S-25 | secret/log canary | absent/redacted from logs/evidence | PENDING PHASE 6 |
| S-26 | hidden model/provider egress | absent | PENDING |
| S-27 | wrong/missing Host | exact host boundary rejects | PENDING LIVE RECHECK |
| S-28 | invalid Origin when present | reject non-exact origin | PENDING LIVE RECHECK |
| S-29 | ordinary public source | Cloudflare blocks before Bridge | PENDING FINAL LIVE RECHECK |
| S-30 | forwarded-IP spoof | forwarded headers cannot authorize | PENDING |
| S-31 | project registry invalid update | last-known-good retained; fail closed | PENDING |
| S-32 | project root redirect | rejected; no silent authorization transfer | PENDING |
| S-33 | MCP project-admin attempt | no public admin tool exists | PENDING CONTRACT |

Any bypass that grants broader filesystem, command, approval, Git, identity, secret, network or project-administration capability is a release blocker.

## 9. Reliability and recovery acceptance

| ID | Fault | Required result | Status |
|---|---|---|---|
| R-01 | duplicate successful mutation | persisted result replay; no duplicate edit | PENDING |
| R-02 | same request ID / changed hash | conflict; no second side effect | PENDING |
| R-03 | Bridge restart before dispatch | operation fails safely | PENDING |
| R-04 | Bridge restart after uncertain backend boundary | operation becomes `unknown` | PENDING |
| R-05 | approval pending during restart | plaintext approval unavailable; fail closed | PENDING |
| R-06 | Cloudflare Tunnel disconnect | no transparent mutation replay | PENDING REAL TUNNEL |
| R-07 | Native Windows worker crash | failure/unknown preserves project safety block | PENDING REAL WORKER |
| R-08 | registered command timeout | bounded timeout + owned process-tree cleanup/unknown | PENDING |
| R-09 | external Git race | mutation/restore detects changed state | PENDING |
| R-10 | reconcile verified not-applied | releases block only with scoped evidence | PENDING |
| R-11 | reconcile verified applied | successor recovery follows designed constraints | PENDING |
| R-12 | 20 packaged start/doctor/status/stop cycles | 20/20 with no owned residue | PENDING PHASE 6 |
| R-13 | invalid project-registry generation | keep last-known-good | PENDING |
| R-14 | remove/re-add project ID | old sessions do not regain authorization | PENDING |

Prefer explicit unavailable/blocked/unknown results over guessing.

## 10. Real-project acceptance

Run at least ten complete remote modification tasks, not ten isolated tool calls.

Minimum distribution:

- five tasks against a real Java acceptance project;
- three tasks against a project with front-end workflow;
- two tasks exercising recovery/checkpoint/reconcile behavior.

For each task record:

- task ID/project ID;
- starting branch/HEAD;
- session ID;
- relevant operation IDs;
- change summary;
- command IDs executed;
- ending branch/HEAD;
- changed-file list;
- diff review result;
- approval usage;
- unknown/reconcile status;
- final project test/build result.

Do not copy proprietary source content into the public acceptance report.

Required:

```text
10/10 tasks
```

with explainable operation/audit/Git lineage and no unexplained side effect.

Status: **PENDING.**

## 11. ChatGPT-only reasoning boundary

Verify from final RC:

- Bridge has no configured model provider;
- Bridge has no hidden agent loop;
- codemcp remains an execution backend;
- repository content cannot authorize a privileged action;
- each multi-step user task is reconstructable from explicit ChatGPT MCP calls;
- network observation shows no prohibited model/provider egress from Bridge/codemcp.

Expected Tunnel/control-plane traffic is not model egress.

Status: **PENDING.**

## 12. Network-trust live boundary

Profile A Phase A-H already has successful live evidence, including:

- real ChatGPT Connector access;
- 22-tool discovery;
- project access;
- mutation;
- identical replay;
- explicit approval;
- checkpoint/CAS restore;
- exact baseline recovery;
- ordinary-source Cloudflare Block;
- ChatGPT-source Allow.

Final release acceptance must recheck that the current final RC has not invalidated:

- exact Host boundary;
- if-present Origin boundary;
- network-only principal semantics;
- ordinary public source Block;
- ChatGPT Connector access.

Do not reinterpret this as user authentication.

## 13. Documentation acceptance

Current public/normative documents:

- [x] `LICENSE` / `AGPL-3.0-only`
- [x] `SECURITY.md`
- [x] `docs/architecture/security-model.md`
- [x] `docs/architecture/threat-model.md`
- [x] `docs/architecture/architecture.md`
- [x] `docs/implementation-plan.md`
- [x] `docs/acceptance/phase-6-validation.md`
- [x] `docs/acceptance/acceptance-test-plan.md`
- [x] public README
- [x] Windows build/install/use guide
- [x] operations runbook
- [x] codemcp pinned-baseline guide
- [x] Cloudflare network-trust guide
- [x] `CONTRIBUTING.md`
- [x] `CODE_OF_CONDUCT.md`
- [x] `CHANGELOG.md`
- [x] `.github` CI / issue / PR / Dependabot configuration
- [ ] final third-party notices decision
- [ ] clean-machine README execution PASS
- [ ] final known-limitations cross-check
- [ ] final release notes/checksum verification against final RC

Documentation must not claim:

- WSL2 is required for normal installed mutation;
- Native Windows mutation is unsupported;
- Secure MCP Tunnel is the mandatory default remote path;
- Profile A provides human user identity.

## 14. Secrets and supply-chain acceptance

Before tag:

- [ ] scan tracked working tree;
- [ ] scan complete Git history;
- [ ] scan `.github/`, scripts, configs, docs, tests and fixtures;
- [ ] scan final release artifact;
- [ ] audit locked dependencies for known vulnerabilities;
- [ ] review dependency license compatibility/notices;
- [ ] confirm local project registry/runtime logs/SQLite/secret data are not packaged;
- [ ] verify `codemcp==0.3.0` provenance remains intentional.

If a real secret is discovered:

1. revoke/rotate;
2. clean history;
3. rescan;
4. rebuild candidate;
5. rerun affected gates.

Status: **PENDING.**

## 15. Packaging and clean-machine acceptance

The final release workflow must produce from the exact accepted commit:

- Windows EXE payload;
- `codemcp-remote-setup.exe`;
- release ZIP;
- SHA-256 checksum/manifest;
- release notes;
- known limitations;
- exact Git identity.

On a clean Windows 11 host:

1. verify installer SHA-256;
2. install;
3. isolate product runtime PATH;
4. verify Python/uv/pwsh are not required/visible;
5. verify Git prerequisite;
6. verify `worker_mode=local`;
7. initialize Profile A;
8. verify DPAPI-backed transport secret;
9. create/register disposable `phase5-clean` project;
10. start Bridge + Cloudflare Tunnel;
11. connect real ChatGPT Connector;
12. read acceptance file;
13. perform deterministic mutation;
14. verify identical replay;
15. restore via approval/checkpoint CAS;
16. prove exact original baseline and clean worktree;
17. stop;
18. cleanup/uninstall;
19. verify expected preserved user data contract;
20. scan artifact/evidence for secrets.

The previous live Phase H use of a temporary file in the real `codemcp-remote` repository does not replace this strict disposable-project clean-machine gate.

Status: **PENDING STRICT PASS.**

## 16. GitHub hosted acceptance

Repository-side governance is already implemented.

Before stable release:

- [ ] first hosted CI run passes on Ubuntu and Windows;
- [ ] pull requests automatically receive required checks;
- [ ] Dependabot recognizes uv and GitHub Actions;
- [ ] branch/ruleset protects the release branch using required checks;
- [ ] issue forms render;
- [ ] PR template renders;
- [ ] workflow permissions remain least-privilege.

Local workflow files alone do not establish hosted PASS.

## 17. Signing decision

Current historical candidate evidence records Authenticode as:

```text
NotSigned
```

Before final release, explicitly choose and document one:

- sign the installer/release executable with an appropriate code-signing certificate; or
- publish unsigned artifacts with the limitation and expected Windows/SmartScreen trust impact clearly disclosed.

Do not imply signed provenance when the artifact is unsigned.

## 18. Final Release Gate

Stable `v0.1.0` requires:

| Gate | Required state |
|---|---|
| Release identity | VERIFIED |
| Phase 6 Windows operations | PASS |
| Automated suite/lint/format/build | PASS |
| 22-tool MCP contract | PASS |
| Functional matrix | PASS |
| Security negative matrix | PASS |
| Reliability/recovery matrix | PASS |
| 10 real remote tasks | PASS |
| ChatGPT-only boundary | PASS |
| Profile A live boundary | PASS |
| Documentation | PASS |
| Secrets | PASS |
| Dependency/license supply chain | PASS |
| Strict clean-machine packaging | PASS |
| Hosted GitHub CI/ruleset | PASS |
| SHA-256 integrity | PASS |
| Signing decision | RECORDED |
| Worktree/tag identity | CLEAN / VERIFIED |

Any P0 blocker, unexplained skip, unresolved secret exposure, unsafe mutation ambiguity, documentation/implementation mismatch or artifact identity mismatch keeps the decision:

```text
BLOCKED
```

## 19. Final sign-off record

Fill only from the final release candidate:

```text
release_candidate_commit:
release_candidate_branch:
phase_6_status:
automated_suite:
mcp_contract:
functional_matrix:
security_matrix:
reliability_matrix:
real_task_count:
chatgpt_only_boundary:
network_trust_live:
documentation:
secret_scan:
dependency_audit:
license_review:
clean_machine_install:
cleanup_uninstall:
hosted_ci:
artifact_installer_sha256:
artifact_zip_sha256:
authenticode:
known_blockers:
release_decision: BLOCKED | APPROVED
validated_at:
```

Default decision is `BLOCKED` until every mandatory field is backed by evidence.
