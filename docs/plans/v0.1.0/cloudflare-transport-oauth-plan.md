# Phase 5.5 — Cloudflare Transport + OAuth Execution Plan

Status: **PLANNED — implementation not started**

Target release: `v0.1.0`

Repository: `codemcp-remote`

## 1. Context

Packaging Phase 5 already proved most of the Windows distribution path:

- native Windows worker works without WSL2;
- the PyInstaller executable works without Python/uv/pwsh on the isolated runtime PATH;
- the Inno Setup installer works as a per-user install;
- DPAPI-backed secret persistence works across processes;
- Bridge and tunnel lifecycle health checks work;
- remote `project_open`, `file_read`, Git mutation, Bridge-owned checkpoint creation, and idempotent replay were exercised against the disposable clean-machine project.

The remaining Phase 5 acceptance work exposed two things:

1. the clean-machine disposable project template needs a deterministic profile marker so `development_ready=true` can be validated;
2. the current OpenAI Secure MCP Tunnel path is not the best long-term default for a self-hosted/open-source distribution.

A ChatGPT custom MCP/plugin flow was also verified to support a public HTTP MCP URL with OAuth configuration, including client metadata/DCR-related settings, scopes, authorization URL, token URL, and registration URL.

Phase 5.5 therefore inserts a transport/authentication refactor before the final clean-machine freeze.

## 2. Goal

Make remote transport a replaceable subsystem and add a production-quality Cloudflare path:

```text
ChatGPT
  |
  | OAuth
  v
Cloudflare Access
  |
  | HTTPS
  v
Cloudflare Tunnel
  |
  v
127.0.0.1:46200/mcp
  |
  v
codemcp-remote Bridge
  |
  v
native codemcp worker + Git/checkpoint policy
```

Cloudflare becomes the recommended/default remote transport for self-hosted users.

The existing OpenAI Secure MCP Tunnel implementation remains available as an optional compatibility provider until a later explicit removal decision.

## 3. Non-goals

Phase 5.5 must not:

- redesign MCP tools;
- redesign Git/checkpoint semantics;
- weaken mutation approval, CAS rollback, idempotency, project isolation, or audit behavior;
- expose the Bridge on `0.0.0.0`;
- implement a custom OAuth authorization server unless the provider spike proves it is unavoidable;
- make arbitrary shell execution available;
- require Python, uv, pwsh, or WSL2 in the packaged runtime;
- remove the existing OpenAI Tunnel provider in the same phase;
- begin Phase 6 automatically.

## 4. Architectural decisions

### 4.1 Transport abstraction

Introduce one provider boundary for lifecycle operations.

Conceptual contract:

```text
RemoteTransportProvider
- initialize(...)
- validate_config(...)
- start(...)
- status(...)
- stop(...)
- doctor(...)
- redact(...)
```

Initial implementations:

```text
cloudflare
openai-tunnel
```

Bridge/MCP/Git/checkpoint code must not know which remote transport is active.

### 4.2 Loopback-only Bridge remains mandatory

The Bridge continues to listen only on:

```text
127.0.0.1:46200
```

The remote provider establishes the outbound/public path.

No firewall port opening and no direct public Bridge bind are allowed.

### 4.3 Authentication model

Preferred authentication chain:

```text
ChatGPT OAuth
  -> Cloudflare Access Managed OAuth
  -> Cloudflare Tunnel
  -> Bridge JWT verification
```

Cloudflare Access is responsible for the user-facing OAuth authorization flow.

The Bridge adds defense-in-depth by validating the Cloudflare Access JWT forwarded with MCP requests.

Minimum validation requirements:

- signature verification;
- issuer validation;
- audience/application validation;
- expiration/not-before validation;
- required identity claims;
- fail closed on missing, malformed, expired, forged, or wrong-audience tokens.

The exact discovery/DCR/CIMD behavior and exact forwarded JWT/header contract must be confirmed in Phase 5.5.0 before implementation.

### 4.4 Scope handling

OAuth scope enforcement is not assumed before verification.

Phase 5.5.0 must determine whether the selected Cloudflare/ChatGPT flow can carry stable application scopes suitable for tool authorization.

If verified, design a minimal mapping such as:

```text
codemcp:read
codemcp:write
codemcp:execute
codemcp:checkpoint
```

If not verified, OAuth is used for authentication/identity only and the existing Bridge policy remains the authoritative tool authorization layer.

Do not invent unsupported scope semantics.

### 4.5 Cloudflare tunnel credential

The Cloudflare tunnel credential/token is a local machine secret.

Requirements:

- never commit it;
- never write it to plaintext TOML/env files;
- never print it in logs or JSON status output;
- store it using the existing Windows DPAPI secret mechanism or a generalized DPAPI secret store;
- child `cloudflared.exe` receives it only through the process environment or another supported ephemeral mechanism.

### 4.6 Packaged cloudflared

The Windows installer may bundle a pinned `cloudflared.exe`.

Release provenance must record:

- exact version;
- upstream download URL;
- upstream license;
- SHA-256;
- local packaged SHA-256;
- source/provenance record.

The build must fail closed on checksum mismatch.

## 5. Phase breakdown

Each sub-phase is independently gated.

**Complete one sub-phase, report evidence, then stop and wait for explicit authorization before starting the next one.**

---

## Phase 5.5.0 — OAuth + HTTP MCP compatibility spike

### Objective

Prove the external protocol contract before changing production code.

### Work

Create a disposable test path and verify:

1. ChatGPT can connect to an HTTPS `/mcp` endpoint through Cloudflare.
2. Streamable HTTP MCP tool discovery works.
3. OAuth discovery behavior expected by ChatGPT.
4. CIMD/client metadata behavior.
5. Dynamic client registration behavior, if used.
6. Authorization callback compatibility.
7. Token issuance and refresh behavior.
8. Exact Cloudflare headers/JWT delivered to the origin.
9. JWT issuer/audience values.
10. 401 vs 403 behavior for unauthenticated/unauthorized calls.
11. Read tool call.
12. Write tool call.
13. Reconnect after token refresh/session expiration.
14. Whether meaningful custom OAuth scopes can be enforced.

### Deliverables

- `docs/reports/compatibility/cloudflare-chatgpt-oauth-spike.md`
- captured configuration contract with secrets redacted;
- explicit PASS/FAIL matrix.

### Stop conditions

Stop Phase 5.5 entirely if any of these cannot be proven:

- ChatGPT cannot use the Cloudflare-protected Streamable HTTP MCP endpoint;
- OAuth cannot complete reliably;
- Cloudflare does not provide an origin-verifiable identity token/header;
- write-tool calls cannot work through the selected ChatGPT flow.

No production refactor starts before this spike is PASS.

---

## Phase 5.5.1 — Transport provider abstraction

### Objective

Refactor the current tunnel lifecycle behind a provider interface without behavior change.

### Work

Expected code areas:

- `bridge/src/codemcp_bridge/lifecycle.py`
- new `bridge/src/codemcp_bridge/transports/`
- `bridge/src/codemcp_bridge/main.py`
- lifecycle tests.

Suggested layout:

```text
transports/
  __init__.py
  base.py
  openai_tunnel.py
```

Move OpenAI-specific responsibilities out of generic lifecycle code:

- tunnel profile validation;
- OpenAI control-plane environment;
- `tunnel-client` discovery;
- tunnel-client process startup;
- provider health;
- provider log redaction.

Generic lifecycle retains:

- process ownership;
- PID + process creation-time validation;
- start/status/stop orchestration;
- atomic state files;
- log rotation helpers;
- Bridge lifecycle.

### Compatibility requirement

Existing OpenAI Tunnel behavior must remain regression-compatible at the end of this phase.

### Validation

- existing lifecycle tests pass;
- existing OpenAI Tunnel profile tests pass;
- packaged source-mode behavior unchanged;
- no Cloudflare implementation yet.

### Completion criteria

The Bridge can select an `openai-tunnel` provider through the new abstraction with no externally observable regression.

Then STOP.

---

## Phase 5.5.2 — Cloudflare transport provider

### Objective

Add `cloudflare` as a second remote transport.

### Configuration model

Target conceptual configuration:

```toml
[remote]
transport = "cloudflare"

[remote.cloudflare]
public_url = "https://mcp.example.com/mcp"
origin_url = "http://127.0.0.1:46200/mcp"
```

Tunnel credential is not stored in this TOML.

### Work

Implement:

- `cloudflared.exe` discovery;
- pinned bundled binary support;
- DPAPI-backed tunnel token storage;
- cloudflared process startup;
- provider status;
- provider health;
- process ownership protection;
- safe stop;
- redacted logs;
- startup timeout;
- fail-closed config validation.

### Security constraints

Reject:

- non-HTTPS public MCP URLs;
- origin host other than loopback;
- origin path other than configured MCP path;
- plaintext tunnel token in config;
- arbitrary cloudflared argv injection;
- user-provided executable paths outside approved discovery rules unless explicitly designed and tested.

### Validation

- unit tests for config parsing;
- token redaction tests;
- stale PID/PID reuse tests;
- cloudflared missing/bad-version behavior;
- mocked provider health;
- real local smoke when available.

Then STOP.

---

## Phase 5.5.3 — Cloudflare Access JWT enforcement

### Objective

Make Cloudflare OAuth identity cryptographically enforceable at the Bridge.

### Work

Add an authentication layer for MCP requests when Cloudflare auth mode is enabled.

Configuration should identify only public/non-secret validation metadata, for example:

```toml
[auth]
mode = "cloudflare-access"
issuer = "..."
audience = "..."
```

Exact field names are decided from Phase 5.5.0 evidence.

Implement:

- Access JWT extraction;
- key discovery/cache;
- signature validation;
- issuer validation;
- audience validation;
- expiry/not-before validation;
- identity extraction;
- request context propagation;
- structured authentication failures;
- audit event identity attachment where appropriate.

### Health endpoint rule

Local lifecycle health checks must keep working without making `/healthz` a public privileged path.

The public tunnel should expose only what is required for MCP operation.

### Negative tests

Must include:

- no token;
- malformed token;
- expired token;
- wrong issuer;
- wrong audience;
- forged signature;
- stale key;
- duplicate/conflicting identity headers;
- direct origin request attempting to spoof Cloudflare headers.

### Scope gate

If Phase 5.5.0 proves stable scopes, add scope-to-operation enforcement here.

If not, explicitly document that Access authenticates identity while Bridge policy authorizes operations.

Then STOP.

---

## Phase 5.5.4 — CLI, configuration, migration, and doctor

### Objective

Make provider selection a supported product configuration rather than a code-path switch.

### CLI target

Conceptually:

```text
codemcp-remote init --transport cloudflare
codemcp-remote start
codemcp-remote status
codemcp-remote stop
codemcp-remote doctor
```

OpenAI compatibility remains selectable:

```text
codemcp-remote init --transport openai-tunnel
```

### Work

- versioned provider configuration;
- backward-compatible migration for current OpenAI runtime state;
- generalized secret storage if required;
- provider-aware `doctor`;
- provider-aware JSON status;
- provider-aware startup errors;
- provider-specific config validation;
- no provider secret leakage.

### Doctor requirements for Cloudflare

At minimum report:

- transport = cloudflare;
- Bridge loopback configuration valid;
- cloudflared binary found;
- tunnel credential available from DPAPI;
- public MCP URL structurally valid;
- Access/JWT validation metadata structurally valid;
- Git prerequisite available;
- native worker mode = local.

Do not make successful public internet access a prerequisite for an offline configuration check unless the command explicitly performs a network diagnostic.

Then STOP.

---

## Phase 5.5.5 — Windows installer integration

### Objective

Ship Cloudflare support without reintroducing external runtime dependencies.

### Work

Update:

- `scripts/prepare-tunnel-client.ps1` or replace with provider-neutral preparation scripts;
- Inno Setup payload;
- installer build script;
- release manifest;
- SHA256SUMS;
- license/provenance notices.

Recommended rename:

```text
prepare-remote-transport.ps1
```

or provider-specific:

```text
prepare-cloudflared.ps1
prepare-openai-tunnel-client.ps1
```

### Installer contract

Installed release still requires only:

- Windows 11 x64;
- Git for Windows;
- user-owned Cloudflare account/domain/tunnel configuration for the Cloudflare path.

Installed release must still not require:

- Python;
- uv;
- pwsh;
- WSL2;
- source checkout.

### Validation

- build from clean tree;
- exact cloudflared checksum;
- version smoke;
- installer install/upgrade/uninstall smoke;
- no secret in installer;
- no user runtime data deletion on normal uninstall.

Then STOP.

---

## Phase 5.5.6 — Security and regression gate

### Objective

Prove the transport refactor did not weaken core safety properties.

### Required regression groups

#### Core unchanged

- project path isolation;
- sensitive-path filtering;
- mutation lock;
- clean-worktree preconditions;
- branch policy;
- checkpoint creation;
- checkpoint finalization CAS;
- idempotency;
- operation audit;
- approval tokens;
- rollback CAS;
- unknown-side-effect handling;
- PID reuse protection.

#### Cloudflare-specific

- token storage/redaction;
- JWT validation;
- auth fail closed;
- origin remains loopback;
- no arbitrary cloudflared args;
- public URL validation;
- provider process ownership;
- provider health;
- tunnel restart behavior.

#### OpenAI provider compatibility

Existing OpenAI provider tests continue to pass unless an explicit deprecation decision is made later.

### Quality gate

- targeted tests pass;
- full regression passes;
- `compileall` passes;
- `git diff --check` passes;
- packaging smoke passes;
- working tree clean.

Then STOP.

---

## Phase 5.5.7 — Final ChatGPT + clean Windows acceptance

### Objective

Replace the interrupted Phase 5 acceptance with the final Cloudflare/OAuth release proof.

### Disposable project template

The harness should create:

```text
README.md
PHASE5_ACCEPTANCE.txt
pyproject.toml
```

Do **not** create `codemcp.toml`.

`pyproject.toml` is only a static marker allowing the Bridge to resolve the built-in Python project profile and generated fixed command catalog.

The clean-machine acceptance does not execute Python and does not require Python to be installed.

### Local clean-machine contract

Prove:

- exact installer SHA-256;
- install succeeds;
- worker mode = local;
- Python invisible on isolated PATH;
- uv invisible;
- pwsh invisible;
- Git available;
- cloudflared bundled and found;
- Cloudflare tunnel secret recovered from DPAPI;
- Bridge health OK;
- Cloudflare provider health OK;
- Bridge remains loopback-only.

### ChatGPT OAuth contract

Create/connect the ChatGPT custom MCP/plugin using the final OAuth configuration.

Prove:

1. OAuth authorization succeeds.
2. tool discovery succeeds.
3. `project_open phase5-clean` succeeds.
4. `project_status.development_ready == true`.
5. `file_read PHASE5_ACCEPTANCE.txt` returns the expected marker.
6. initial Git state is baseline + clean.
7. deterministic remote mutation succeeds.
8. resulting checkpoint is inspected.
9. identical replay returns the original operation/checkpoint without second execution.
10. `checkpoint_restore` uses the canonical request hash over:

```text
project_id
session_id
checkpoint_id
expected_head
```

11. approval flow is completed normally.
12. CAS restore returns to the original baseline.
13. final `git_status` exactly matches baseline HEAD and clean worktree.
14. OAuth denial/expiry behavior is tested without changing Git state.
15. cleanup/uninstall succeeds.

### Completion criteria

Phase 5.5 is PASS only when all local, OAuth, remote mutation, idempotency, rollback, and cleanup evidence is recorded.

After PASS:

- update Phase 5 release evidence;
- mark the Cloudflare path as the recommended transport;
- keep OpenAI Tunnel as optional/compatibility transport;
- freeze `v0.1.0` packaging only after explicit user approval.

Then STOP.

## 6. Expected file impact

Likely additions:

```text
bridge/src/codemcp_bridge/transports/
bridge/src/codemcp_bridge/auth/
bridge/tests/test_cloudflare_transport.py
bridge/tests/test_cloudflare_access_auth.py
docs/reports/compatibility/cloudflare-chatgpt-oauth-spike.md
docs/guides/cloudflare-tunnel-setup.md
```

Likely modifications:

```text
bridge/src/codemcp_bridge/lifecycle.py
bridge/src/codemcp_bridge/main.py
bridge/src/codemcp_bridge/mcp_server.py
bridge/src/codemcp_bridge/settings.py
scripts/build-windows-exe.ps1
scripts/build-windows-installer.ps1
scripts/codemcp-remote.iss
scripts/validate-clean-windows-release.ps1
docs/architecture/architecture.md
docs/architecture/security-model.md
docs/architecture/threat-model.md
docs/guides/operations-runbook.md
README.md
```

This list is planning guidance, not authorization to modify all listed files.

## 7. Risk register

### High — auth configuration looks valid but origin identity is not actually verified

Mitigation:

- Phase 5.5.0 captures the exact origin token/header;
- Bridge verifies JWT cryptographically;
- negative tests cover spoofed origin headers.

### High — public MCP endpoint bypasses Access

Mitigation:

- Tunnel/Access configuration must protect the MCP hostname/path;
- Bridge requires valid Access JWT in Cloudflare auth mode;
- Bridge remains loopback-only.

### Medium — transport refactor regresses OpenAI Tunnel

Mitigation:

- provider abstraction first;
- existing OpenAI behavior frozen by regression tests;
- no removal during Phase 5.5.

### Medium — cloudflared credential leakage

Mitigation:

- DPAPI storage;
- explicit log redaction;
- no plaintext config;
- packaging scan;
- negative tests.

### Medium — OAuth/DCR behavior differs from assumptions

Mitigation:

- Phase 5.5.0 is a mandatory spike;
- no production implementation before the contract is proven.

### Low — Python profile marker is misunderstood as a Python runtime dependency

Mitigation:

- acceptance documentation explicitly states it is static detection metadata only;
- clean-machine PATH gate still proves Python is absent.

## 8. Rollback strategy

At every sub-phase:

- code changes are isolated in Git commits;
- existing OpenAI transport remains available;
- do not migrate user runtime state destructively;
- config migration must preserve or back up the previous provider config;
- installer uninstall continues to preserve user data/secrets by default.

If Cloudflare OAuth compatibility fails in Phase 5.5.0, abort the Cloudflare default decision and resume the existing Phase 5 OpenAI Tunnel acceptance path.

## 9. Estimated engineering size

Relative size:

```text
Phase 5.5.0  small/medium
Phase 5.5.1  medium
Phase 5.5.2  medium
Phase 5.5.3  medium/high
Phase 5.5.4  medium
Phase 5.5.5  small/medium
Phase 5.5.6  medium
Phase 5.5.7  medium
```

The highest-risk work is OAuth/JWT correctness, not the Cloudflare Tunnel process itself.

The Bridge, native worker, Git safety, checkpoint, idempotency, and approval architecture should remain largely unchanged.

## 10. Execution rule

Implementation order is fixed:

```text
5.5.0 OAuth/HTTP compatibility spike
  ->
5.5.1 transport abstraction
  ->
5.5.2 Cloudflare provider
  ->
5.5.3 Access JWT enforcement
  ->
5.5.4 CLI/config/migration
  ->
5.5.5 installer integration
  ->
5.5.6 security/regression gate
  ->
5.5.7 final clean-machine acceptance
```

Do not skip forward.

After completing each phase:

1. report changed files;
2. report tests/evidence;
3. report commit;
4. report remaining blockers;
5. STOP and wait for explicit `继续`.
