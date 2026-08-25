# Phase 5.5 — Cloudflare Transport + External MCP Auth Integration Execution Plan

Status: **IN PROGRESS — 5.5.1, 5.5.2 and 5.5.4A complete; 5.5.3 waits on the mcp-auth-server Phase 4 verification contract**

Target release: `v0.1.0`

Repository: `codemcp-remote`

External dependency: a separately developed, general-purpose `mcp-auth-server` project.

Dependency status: `mcp-auth-server` Phase 3 — Cloudflare OAuth Provider Integration is complete. `codemcp-remote` Phase 5.5.3 remains gated on the auth-server Phase 4 Resource Server Verification Contract freeze.

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

The authentication architecture is now deliberately separated from the transport architecture. Cloudflare is responsible only for publishing the loopback MCP endpoint over HTTPS. OAuth authorization-server responsibilities belong to an independent, reusable `mcp-auth-server` project rather than to Cloudflare Access or to `codemcp-remote`.

Phase 5.5 therefore inserts a transport abstraction plus generic OAuth resource-server integration before the final clean-machine freeze.

## 2. Goal

Make remote transport replaceable, add a production-quality Cloudflare path, and integrate `codemcp-remote` with an external standards-based MCP authorization server:

```text
ChatGPT
  |
  | OAuth 2.0 / PKCE / DCR as negotiated
  v
Independent mcp-auth-server
  |
  | access token
  v
HTTPS MCP endpoint
  |
  v
Cloudflare Tunnel
  |
  v
127.0.0.1:46200/mcp
  |
  | generic OAuth resource-server validation
  v
codemcp-remote Bridge
  |
  v
native codemcp worker + Git/checkpoint policy
```

Cloudflare becomes the recommended/default remote transport for self-hosted users.

The independent `mcp-auth-server` owns OAuth protocol state and user/client authorization. `codemcp-remote` acts only as an OAuth-protected MCP resource server and keeps its existing project/tool/Git policy as the authoritative operation-authorization layer unless a later phase explicitly adds verified scope mapping.

The existing OpenAI Secure MCP Tunnel implementation remains available as an optional compatibility provider until a later explicit removal decision.

## 3. Non-goals

Phase 5.5 must not:

- redesign MCP tools;
- redesign Git/checkpoint semantics;
- weaken mutation approval, CAS rollback, idempotency, project isolation, or audit behavior;
- expose the Bridge on `0.0.0.0`;
- implement login UI, DCR persistence, authorization-code issuance, refresh-token issuance, consent storage, user management, or an OAuth authorization server inside `codemcp-remote`;
- couple `codemcp-remote` to the internal database, runtime, or source code of `mcp-auth-server`;
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
ChatGPT
  -> independent mcp-auth-server
  -> Bearer access token
  -> Cloudflare Tunnel
  -> codemcp-remote Bridge resource-server validation
```

`mcp-auth-server` is the OAuth authorization layer and uses `@cloudflare/workers-oauth-provider` as its generic OAuth 2.1 protocol engine. The auth-server project owns MCP-specific Resource Registry / issuer / scope / audience policy, while the Provider owns the standards OAuth state machine such as Authorization Code + PKCE, client/grant lifecycle, token issuance, refresh and revoke.

`codemcp-remote` is an OAuth Resource Server only. It accepts MCP requests after validating the externally issued access token according to the **versioned Resource Server Verification Contract** frozen by `mcp-auth-server` Phase 4. Cloudflare Tunnel remains transport only and is not an identity authority.

Minimum Bridge semantics, independent of token representation:

- extract the standard Bearer token from the HTTP Authorization header;
- validate token authenticity/active state using only the frozen Resource Server Verification Contract;
- require the configured authorization-server issuer/binding;
- require exact canonical MCP resource/audience matching;
- enforce expiry/revocation semantics defined by the contract;
- extract only documented caller/client identity fields;
- consume only documented scopes and never infer authorization from token presence;
- fail closed on missing, malformed, expired, revoked, unverifiable, wrong-resource, or wrong-issuer credentials;
- never trust Cloudflare-specific identity headers as an authorization source.

If the final contract selects signed/self-contained tokens, Phase 5.5.3 may implement JWKS/key discovery, bounded key caching, signature validation and time-claim checks. If it selects Provider-native opaque tokens, Phase 5.5.3 must instead implement the reviewed online validation/introspection contract, including Resource Server authentication, strict timeout, bounded positive caching, revocation semantics and fail-closed network behavior.

`mcp-auth-server` Phase 3 is now complete. The remaining production integration gate is its Phase 4 Resource Server Verification Contract; Phase 5.5.3 must not guess the token representation or validation endpoint before that contract is frozen.

### 4.4 Scope handling

OAuth scope enforcement is not assumed before interoperability evidence.

Phase 5.5.0 must determine whether ChatGPT and the independent `mcp-auth-server` can negotiate stable scopes suitable for MCP authorization.

If verified, a minimal mapping may be designed, for example:

```text
codemcp:read
codemcp:write
codemcp:execute
codemcp:checkpoint
```

If scope semantics are not proven end-to-end, OAuth is used for authentication/identity only and the existing Bridge policy remains the authoritative tool authorization layer.

Do not invent unsupported scope semantics or infer authorization from token presence alone.

### 4.5 Cross-project boundary

`mcp-auth-server` is a separate project and release lifecycle.

The integration contract must be protocol-based, not source-based:

```text
codemcp-remote
  -> authorization-server issuer / metadata
  -> canonical MCP resource identifier
  -> versioned Resource Server Verification Contract
       -> JWT/JWKS verification, OR
       -> authenticated online validation/introspection
  -> documented identity/scopes/error semantics
```

`codemcp-remote` must not:

- import auth-server or Provider packages;
- read the auth-server D1/KV/provider storage directly;
- depend on auth-server filesystem/runtime state;
- share Provider storage secrets or private signing keys;
- require the auth server to run on the same machine;
- proxy login/consent pages.

The token representation is not selected in this repository. `codemcp-remote` consumes the contract frozen by `mcp-auth-server` Phase 4 and implements only the selected Resource Server verification mode.

Cross-project execution gate:

```text
mcp-auth-server Phase 3  Cloudflare OAuth Provider integration       COMPLETE
codemcp-remote 5.5.1     transport abstraction                      COMPLETE
codemcp-remote 5.5.2     Cloudflare transport provider              COMPLETE
codemcp-remote 5.5.4A    transport CLI/config                       COMPLETE

mcp-auth-server Phase 4.0  characterize Provider token behavior
mcp-auth-server Phase 4.1  freeze Resource Server Verification Contract v1
                              |
                              +--> unlock codemcp-remote 5.5.3
                              +--> unlock codemcp-remote 5.5.4B

mcp-auth-server Phase 5/6 and codemcp-remote 5.5.3/5.5.4B may then proceed in parallel.
mcp-auth-server Phase 7 is the hardened integration guide/reference layer, not the first contract-definition gate.
```

Phase 5.5.3 must not begin from assumptions about `@cloudflare/workers-oauth-provider` token internals. It begins only after the auth-server Phase 4.1 handoff is versioned and testable.

### 4.6 Cloudflare tunnel credential

The Cloudflare tunnel credential/token is a local machine secret.

Requirements:

- never commit it;
- never write it to plaintext TOML/env files;
- never print it in logs or JSON status output;
- store it using the existing Windows DPAPI secret mechanism or a generalized DPAPI secret store;
- child `cloudflared.exe` receives it only through the process environment or another supported ephemeral mechanism.

### 4.7 Packaged cloudflared

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

## Phase 5.5.0 — External MCP Auth + HTTP MCP compatibility spike

**Status: PARTIAL — preliminary protocol evidence recorded; final token-verification/interoperability acceptance waits on `mcp-auth-server` Phase 4.1.**

### Objective

Prove the standards contract among ChatGPT, the independent `mcp-auth-server`, Cloudflare transport, and the MCP Resource Server before starting auth-dependent production integration.

This phase is an interoperability gate, not an implementation phase for either project.

### Preconditions

A disposable/testable `mcp-auth-server` deployment must exist with enough functionality to exercise the intended ChatGPT flow. Its internal implementation is out of scope for this repository.

### Work

Create a disposable test path and verify:

1. ChatGPT can connect to an HTTPS `/mcp` endpoint through Cloudflare Tunnel.
2. Streamable HTTP MCP tool discovery works.
3. The MCP resource server can advertise or trigger the OAuth discovery flow ChatGPT expects.
4. ChatGPT can discover the independent auth server through the final metadata contract.
5. CIMD/client metadata behavior is recorded.
6. Dynamic Client Registration behavior is recorded when used.
7. Exact redirect URI registration/matching behavior is recorded.
8. Authorization Code + PKCE S256 compatibility is proven when that flow is used.
9. Token issuance succeeds.
10. Refresh-token/session renewal behavior is recorded when supported.
11. Exact access-token presentation to the MCP resource server is captured with secrets redacted.
12. Token format is classified as signed/self-contained or opaque.
13. For signed tokens, issuer, audience/resource, JWKS, subject/identity and expiry claims are recorded.
14. For opaque tokens, the required introspection contract is recorded before any Bridge implementation.
15. 401 vs 403 behavior for unauthenticated/unauthorized calls is recorded.
16. A read tool call succeeds through the authenticated path.
17. A write tool call succeeds through the authenticated path.
18. Reconnect after token refresh/session expiration is exercised.
19. Whether meaningful custom OAuth scopes can be negotiated and enforced end-to-end is recorded.
20. Cloudflare is confirmed to act only as HTTPS transport; no Cloudflare identity header is required for authorization.

### Deliverables

- `docs/reports/compatibility/mcp-auth-server-chatgpt-spike.md`;
- a redacted standards contract covering discovery, DCR/CIMD, redirect URIs, PKCE, token presentation, issuer/audience/resource, JWKS or introspection, refresh behavior and error semantics;
- explicit PASS/FAIL matrix;
- explicit list of assumptions that remain unproven;
- reference to the independent auth-server build/version/commit used for the spike when available.

The existing `docs/reports/compatibility/cloudflare-chatgpt-oauth-spike.md` remains historical evidence from the pre-pivot Cloudflare-Access design and must not be treated as the final auth contract.

### Stop conditions

Stop Phase 5.5 before production refactoring if any of these cannot be proven:

- ChatGPT cannot use the Cloudflare-published Streamable HTTP MCP endpoint;
- OAuth cannot complete reliably against the independent auth server;
- the MCP resource server cannot cryptographically validate or safely introspect the issued access token;
- issuer/audience/resource semantics cannot prevent token reuse against the wrong MCP resource;
- write-tool calls cannot work through the selected ChatGPT OAuth flow.

Do not fall back to a shared static bearer secret merely to pass the spike.

Transport-only work that does not depend on the auth contract (`5.5.1`, `5.5.2`, `5.5.4A`) is explicitly allowed to proceed in parallel and is already complete. **No auth production integration (`5.5.3` or `5.5.4B`) starts until `mcp-auth-server` Phase 4.1 freezes a testable Resource Server Verification Contract and the relevant Phase 5.5.0 interoperability checks pass.**

---

## Phase 5.5.1 — Transport provider abstraction

**Status: COMPLETE — 2026-08-25.**

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

**Status: COMPLETE — 2026-08-25.**

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

## Phase 5.5.3 — MCP OAuth Resource Server verification integration

**Status: BLOCKED — starts only after `mcp-auth-server` Phase 4.1 freezes Resource Server Verification Contract v1.**

### Objective

Make credentials issued by the independent `mcp-auth-server` enforceable at the Bridge without coupling `codemcp-remote` to Cloudflare OAuth Provider internals, D1/KV storage, or auth-server source code.

### Input contract

Phase 5.5.3 consumes exactly one versioned handoff from `mcp-auth-server` Phase 4.1. The handoff must define at least:

- canonical authorization-server issuer;
- canonical MCP resource identifier and exact audience semantics;
- token representation;
- verification mode: local signed-token verification or authenticated online validation/introspection;
- token lifetime and revocation semantics;
- Resource Server authentication requirements for online verification, if any;
- stable identity fields;
- stable scope representation;
- 401/403 behavior;
- cache and failure semantics;
- test vectors for wrong-resource and revoked/invalid credentials.

Do not implement from Provider internals that are not part of this frozen contract.

### Configuration model

Configuration contains only the Resource Server-side settings required by the selected contract. Conceptually:

```toml
[auth]
mode = "oauth-resource-server"
issuer = "https://auth.example.com/"
resource = "https://mcp.example.com/mcp"
verification = "<frozen-contract-mode>"
```

Provider-specific fields such as `jwks_url` or an online validation/introspection endpoint are added only if selected by the Phase 4.1 contract.

### Common implementation

Regardless of representation:

- extract the standard Bearer token;
- reject duplicate/conflicting credentials;
- validate issuer/resource/audience exactly;
- enforce active/expiry/revocation semantics;
- propagate documented identity into request/audit context;
- extract only documented scopes;
- keep Cloudflare identity headers non-authoritative;
- fail closed when verification cannot establish an active credential for this exact MCP resource.

### Signed-token path, only if selected

Implement:

- bounded JWKS/key discovery cache;
- approved algorithm/key validation;
- signature validation;
- issuer/audience/resource validation;
- expiry/not-before validation;
- unknown/stale key rejection;
- key-rotation negative tests.

### Provider-native opaque-token path, only if selected

Implement the reviewed online verification/introspection contract:

- authenticate `codemcp-remote` as a Resource Server using the mechanism defined by the auth server;
- strict connect/read timeout;
- fail closed on network/auth-server failure;
- bounded positive-result cache only when allowed by the contract;
- no unsafe long-lived negative cache;
- immediate or contract-defined revocation behavior;
- never send the MCP bearer token anywhere except the designated auth-server verification endpoint;
- redact the credential from logs/errors/traces.

### Health endpoint rule

Local lifecycle health checks must keep working without making `/healthz` a public privileged path.

The public tunnel exposes only the MCP/auth-discovery surface required by the final contract; local lifecycle diagnostics remain loopback-safe.

### Negative tests

Must include representation-independent cases:

- no Authorization header;
- malformed/duplicate Bearer header;
- malformed/invalid credential;
- expired credential;
- revoked/inactive credential;
- wrong issuer;
- wrong canonical audience/resource;
- token/credential issued for a different MCP resource;
- spoofed Cloudflare identity headers having no authorization effect;
- verification dependency unavailable -> fail closed.

Additionally:

- signed mode: forged signature, unknown/stale key, invalid time claims;
- opaque mode: invalid introspection/validation response, Resource Server authentication failure, timeout, revoked token and cache-expiry behavior.

### Scope gate

If the frozen contract proves stable scopes, add explicit scope-to-operation enforcement with tests for read/write/execute/checkpoint boundaries.

If scope semantics are not yet frozen, OAuth establishes caller identity/resource validity while existing Bridge policy remains authoritative for operation authorization. Do not invent scope meanings locally.

Then STOP.

---

## Phase 5.5.4 — CLI, configuration, migration, and doctor

### Objective

Make transport selection and external OAuth resource-server validation supported product configuration rather than code-path switches.

### Parallel execution split

Because the independent `mcp-auth-server` protocol contract is not yet frozen, Phase 5.5.4 is executed in two gated parts:

- **Phase 5.5.4A — transport-only CLI/config**: versioned transport selection, backward-compatible OpenAI fallback/migration behavior, Cloudflare CLI parameters, provider-specific DPAPI transport secrets, provider-aware start/status/stop/doctor. This part may proceed before Phase 5.5.3.
- **Phase 5.5.4B — auth-aware configuration**: OAuth Resource Server metadata, issuer/resource plus the selected verification-mode settings, auth-aware doctor/status and structural validation. This part remains blocked until `mcp-auth-server` Phase 4.1 freezes Resource Server Verification Contract v1; after that it may proceed alongside 5.5.3 when the config schema can be derived without guessing.

Phase 5.5.4A implementation completed on 2026-08-25. Completion of 5.5.4A does **not** mark Phase 5.5.4 as fully complete.

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

- versioned transport-provider configuration;
- versioned generic OAuth resource-server configuration;
- backward-compatible migration for current OpenAI runtime state;
- generalized local secret storage only for transport credentials that actually require secrecy;
- public auth metadata configuration for issuer, audience/resource and JWKS/introspection fields proven by Phase 5.5.0;
- provider-aware and auth-aware `doctor`;
- provider-aware and auth-aware JSON status;
- provider-aware startup errors;
- provider-specific transport validation;
- auth-specific structural validation;
- no provider secret leakage;
- no auth-server private signing material or user/client database copied into the local runtime.

### Doctor requirements for Cloudflare + external auth

At minimum report:

- transport = cloudflare;
- Bridge loopback configuration valid;
- cloudflared binary found;
- tunnel credential available from DPAPI;
- public MCP URL structurally valid;
- auth mode = oauth-resource-server;
- issuer/discovery metadata structurally valid;
- audience/resource identifier structurally valid;
- JWKS or introspection configuration structurally valid according to the Phase 5.5.0 contract;
- no auth-server private signing material is present locally;
- Git prerequisite available;
- native worker mode = local.

Do not make successful public internet access, live auth-server reachability, or successful token issuance a prerequisite for an offline configuration check unless the command explicitly performs a network diagnostic.

Then STOP.

---

## Phase 5.5.5 — Windows installer integration

### Objective

Ship Cloudflare transport and generic OAuth resource-server support without bundling the independent auth server or reintroducing local runtime dependencies.

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

The installed Windows payload still requires locally only:

- Windows 11 x64;
- Git for Windows;
- user-owned Cloudflare account/domain/tunnel configuration for the Cloudflare path.

To use the authenticated ChatGPT path, the user must additionally have access to a compatible external `mcp-auth-server` deployment implementing the versioned Resource Server Verification Contract frozen in auth-server Phase 4.1. That auth server is a network dependency, not a bundled local runtime dependency.

Installed release must still not require or bundle:

- Python;
- uv;
- pwsh;
- WSL2;
- source checkout;
- `mcp-auth-server` source/runtime;
- auth-server private signing keys;
- auth-server user/client/grant databases.

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

#### Cloudflare transport-specific

- tunnel-token storage/redaction;
- origin remains loopback;
- no arbitrary cloudflared args;
- public URL validation;
- provider process ownership;
- provider health;
- tunnel restart behavior;
- no Cloudflare identity header is trusted for authorization.

#### Generic OAuth Resource Server-specific

- Bearer token extraction;
- verification mode exactly matches `mcp-auth-server` Resource Server Verification Contract v1;
- issuer validation;
- exact canonical audience/resource validation;
- expiry/revocation/active-state validation defined by the contract;
- auth fail closed;
- wrong-resource credential rejection;
- JWKS or online-validation dependency outage behavior defined by the contract;
- identity propagation into request/audit context;
- scope enforcement only when frozen and proven end-to-end;
- no dependency on auth-server Provider packages, private keys, D1/KV, filesystem or source code.

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

## Phase 5.5.7 — Final ChatGPT + external OAuth + clean Windows acceptance

### Objective

Replace the interrupted Phase 5 acceptance with the final proof of Cloudflare transport plus independent MCP OAuth authentication.

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
- Bridge remains loopback-only;
- generic OAuth resource-server configuration is structurally valid;
- no auth-server private signing key, user database, client database or refresh-token state exists in the codemcp-remote runtime.

### ChatGPT + independent auth-server contract

Create/connect the ChatGPT custom MCP/plugin using the final OAuth configuration backed by the independent `mcp-auth-server`.

Prove:

1. ChatGPT discovers the intended auth server/resource metadata.
2. OAuth authorization succeeds.
3. DCR/CIMD/redirect-URI behavior matches the Phase 5.5.0 contract.
4. PKCE behavior matches the Phase 5.5.0 contract when required.
5. a credential issued under the exact `mcp-auth-server` Resource Server Verification Contract version used for acceptance is accepted for this MCP resource.
6. a credential for the wrong canonical audience/resource is rejected.
7. expired, revoked, inactive or otherwise invalid authorization is rejected without Git state change.
8. refresh/session renewal behavior works as specified by the auth-server interoperability contract and does not weaken Resource Server validation.
9. tool discovery succeeds.
10. `project_open phase5-clean` succeeds.
11. `project_status.development_ready == true`.
12. `file_read PHASE5_ACCEPTANCE.txt` returns the expected marker.
13. initial Git state is baseline + clean.
14. deterministic remote mutation succeeds.
15. resulting checkpoint is inspected.
16. identical replay returns the original operation/checkpoint without second execution.
17. `checkpoint_restore` uses the canonical request hash over:

```text
project_id
session_id
checkpoint_id
expected_head
```

18. approval flow is completed normally.
19. CAS restore returns to the original baseline.
20. final `git_status` exactly matches baseline HEAD and clean worktree.
21. if scopes were proven in Phase 5.5.0, at least one allowed and one denied scope boundary is exercised.
22. Cloudflare identity headers are not required for the authenticated MCP path.
23. cleanup/uninstall succeeds.

### Completion criteria

Phase 5.5 is PASS only when all local, external OAuth, remote mutation, idempotency, rollback, negative-auth, and cleanup evidence is recorded.

The acceptance record must identify the exact `mcp-auth-server` build/version/commit used, without making that project part of this repository's packaged payload.

After PASS:

- update Phase 5 release evidence;
- mark Cloudflare as the recommended transport;
- document `mcp-auth-server` as a compatible external authorization-server dependency rather than an embedded component;
- keep OpenAI Tunnel as optional/compatibility transport;
- freeze `v0.1.0` packaging only after explicit user approval.

Then STOP.

## 6. Expected file impact

Likely additions:

```text
bridge/src/codemcp_bridge/transports/
bridge/src/codemcp_bridge/auth/
bridge/tests/test_cloudflare_transport.py
bridge/tests/test_oauth_resource_auth.py
docs/reports/compatibility/mcp-auth-server-chatgpt-spike.md
docs/guides/cloudflare-tunnel-setup.md
docs/guides/external-mcp-auth-setup.md
```

Likely modifications:

```text
bridge/src/codemcp_bridge/lifecycle.py
bridge/src/codemcp_bridge/main.py
bridge/src/codemcp_bridge/mcp_server.py
bridge/src/codemcp_bridge/mcp_transport.py
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

The independent `mcp-auth-server` repository is not part of this file-impact list. Its implementation plan, tests, storage model and release artifacts belong to that project.

This list is planning guidance, not authorization to modify all listed files.

## 7. Risk register

### High — access token is accepted without binding it to the intended MCP resource

Mitigation:

- `mcp-auth-server` Phase 4.1 freezes issuer/resource/audience semantics and reusable wrong-resource test vectors;
- Phase 5.5.0 verifies those semantics through the ChatGPT interoperability path;
- Bridge validates the exact canonical resource binding before any tool dispatch;
- negative tests cover credentials issued for a different MCP server;
- no fallback to token-presence-only authentication.

### High — authorization-server internals leak into codemcp-remote

Mitigation:

- protocol-only integration boundary;
- no shared database/filesystem/private signing keys;
- no auth-server package imports;
- acceptance runs the auth server as an independently versioned external dependency.

### High — public MCP endpoint bypasses authentication

Mitigation:

- Bridge resource-server auth is enforced independently of Cloudflare;
- Cloudflare is treated only as transport;
- direct requests without a valid token fail closed;
- Bridge remains loopback-only behind the outbound tunnel.

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

### Medium — OAuth/DCR/CIMD behavior differs between ChatGPT and mcp-auth-server

Mitigation:

- Phase 5.5.0 is a mandatory live interoperability spike;
- exact redirect URI, PKCE, DCR/CIMD, token and refresh contracts are captured;
- no production auth integration before the contract is proven.

### Medium — auth-server signing-key rotation or outage breaks MCP access

Mitigation:

- bounded JWKS cache and rotation tests for signed tokens;
- explicit timeout/fail-closed design for opaque-token introspection if used;
- doctor separates offline structural checks from live network diagnostics;
- no insecure fail-open path.

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
- installer uninstall continues to preserve user data/secrets by default;
- the external auth server remains independently deployable and removable.

If the independent auth-server interoperability spike fails in Phase 5.5.0, stop the generic OAuth integration work. Do not embed a one-off OAuth server into `codemcp-remote` and do not weaken authentication to a static shared secret merely to continue.

If Cloudflare transport itself is sound but OAuth interoperability is not, Cloudflare may remain a future transport option, but it must not become the recommended authenticated release path until the auth contract is proven.

## 9. Estimated engineering size

Relative size inside `codemcp-remote`:

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

The independent `mcp-auth-server` has its own engineering estimate and phase plan and must not be counted as hidden work inside these estimates.

The highest-risk work in this repository is correct OAuth resource-server validation and interoperability, not the Cloudflare Tunnel process itself.

The Bridge, native worker, Git safety, checkpoint, idempotency, and approval architecture should remain largely unchanged.

## 10. Execution rule

Implementation order is fixed:

```text
5.5.0 external MCP auth + HTTP interoperability spike
  ->
5.5.1 transport abstraction
  ->
5.5.2 Cloudflare provider
  ->
5.5.3 generic OAuth resource-server integration
  ->
5.5.4 CLI/config/migration/doctor
  ->
5.5.5 installer integration
  ->
5.5.6 security/regression gate
  ->
5.5.7 final ChatGPT + external OAuth + clean-machine acceptance
```

Cross-project dependency rule:

```text
mcp-auth-server may develop in parallel
          |
          v
Phase 5.5.0 requires a testable auth-server endpoint
          |
          v
No production auth integration before 5.5.0 PASS
```

Do not skip forward.

After completing each phase:

1. report changed files;
2. report tests/evidence;
3. report commit;
4. report remaining blockers;
5. STOP and wait for explicit `继续`.
