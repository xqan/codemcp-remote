# Project Registry Hot Reload — Implementation Plan

> Branch: `codex/project-registry-hot-reload`
>
> Goal: allow projects added or removed through the **local CLI only** to become effective in a running Bridge without restarting the Bridge, Tunnel, or ChatGPT Connector.
>
> Security invariant: **local CLI is the project-authorization control plane; ChatGPT/MCP is only the execution plane for projects that were already authorized locally.**

## 1. Scope

This change is intentionally narrow.

In scope:

- hot reload of `<CODEMCP_HOME>/config/projects.toml`;
- local CLI `project add` / `project remove` as the only project-registration mutation path;
- automatic, fail-closed refresh of the running Bridge project registry;
- immediate visibility of newly added projects;
- immediate revocation of removed projects;
- safe handling of project policy/command changes;
- observability and regression coverage;
- documentation updates.

Out of scope:

- MCP tools for project administration;
- remote project registration or removal;
- hot reload of `remote.toml`;
- hot reload of auth, network trust, Tunnel, Bridge listener, storage, or global policy;
- arbitrary runtime config reload;
- changing the public MCP tool surface;
- broad file-watcher infrastructure.

The public MCP surface must remain the existing 22 tools and MUST NOT gain:

- `project_add`
- `project_remove`
- `project_reload`
- `project_configure`
- any equivalent remote project-administration tool.

## 2. Security Model

The authorization boundary is:

```text
Local Windows operator
  -> codemcp-remote.exe project add/remove
  -> atomic projects.toml update
  -> running Bridge detects validated change
  -> project authorization snapshot changes

ChatGPT / MCP
  -> may use only projects present in the current validated snapshot
  -> cannot create, remove, reload, redirect, or re-authorize a project
```

This separation is a long-term invariant, not just an implementation detail.

### 2.1 Local CLI authority

Only local CLI commands may mutate project registration:

```powershell
.\codemcp-remote.exe project add <project-id> <absolute-project-root>
.\codemcp-remote.exe project remove <project-id> --expected-root <absolute-project-root>
```

CLI writes must remain validated and atomic.

### 2.2 MCP non-authority

Repository content, prompts, MCP calls, project files, tool output, or remote callers MUST NOT be able to:

- write the runtime `projects.toml`;
- add/remove projects;
- trigger a privileged reload endpoint;
- redirect an existing project ID to another root;
- widen branches, commands, paths, or project scope outside the local configuration contract.

## 3. Current Root Cause

Today the Bridge loads project authorization once at process startup:

```text
load_settings(...)
  -> BridgeService(settings)
     -> ProjectRegistry(settings)
     -> PolicyEngine(settings, registry)
     -> CodemcpAdapter(settings, registry)
     -> RegisteredCommandRunner(settings)
```

`project add/remove` updates `projects.toml`, but the live `BridgeService` continues using the original in-memory `settings.projects`.

Therefore a Bridge restart is currently required.

## 4. Target Architecture

Introduce one central, validated project-registry snapshot owner.

Preferred implementation: extend `ProjectRegistry` or introduce a tightly scoped `ProjectRegistryManager`. Avoid duplicating project reload logic across tools.

The component owns:

- current validated `ProjectSpec` mapping;
- current projects configuration fingerprint;
- registry generation number;
- last successful reload metadata;
- last reload failure metadata;
- synchronization for concurrent reload checks.

It MUST NOT own or reload:

- authentication;
- network trust;
- Tunnel configuration;
- listener configuration;
- database/storage configuration;
- global Bridge policy;
- model-egress policy.

## 5. Configuration Fingerprint

Do not introduce `FileSystemWatcher` for v0.1.

Use a cheap polling fingerprint before project authorization operations.

Recommended fast path:

```text
projects.toml stat
  -> mtime_ns
  -> size
```

If unchanged:

```text
reuse current validated snapshot
```

If changed:

```text
read whole file
-> parse TOML
-> validate
-> build candidate project snapshot
-> compare safety invariants
-> atomic swap
```

An optional SHA-256 of the complete file may be used after a stat change to avoid unnecessary rebuilds or to strengthen duplicate-change detection.

The Bridge must never expose or consume a half-written configuration. Local CLI writes should continue using temporary-file + atomic replace semantics.

## 6. Reload Trigger

No explicit remote `reload` tool.

The Bridge should call something conceptually equivalent to:

```python
registry.refresh_if_changed()
```

before operations that resolve or rely on project authorization.

At minimum, refresh must occur before:

- `project_open`;
- `project_status`;
- any tool that resolves `project_id`;
- session/project authorization checks where a removed project must be revoked.

The implementation should centralize this path so individual MCP tools do not each implement reload logic.

## 7. Add Semantics

Initial state:

```toml
[projects.project_a]
...
```

Local operator runs:

```powershell
.\codemcp-remote.exe project add alex-runtime "D:\Documents\CodexProject\alex-runtime"
```

Expected behavior:

1. CLI validates and atomically updates `projects.toml`.
2. CLI returns success without restarting services.
3. Running Bridge sees the changed fingerprint on the next project-authorized request.
4. Candidate configuration is fully validated.
5. Registry snapshot is atomically replaced.
6. `project_open("alex-runtime")` succeeds immediately.
7. Tunnel and ChatGPT Connector remain connected.

Desired CLI response fields:

```json
{
  "status": "ok",
  "project_id": "alex-runtime",
  "root": "D:\\Documents\\CodexProject\\alex-runtime",
  "reload": "automatic",
  "restart_required": false
}
```

The CLI must not call a privileged Bridge reload API to achieve this.

## 8. Remove and Revocation Semantics

Local operator runs:

```powershell
.\codemcp-remote.exe project remove alex-runtime --expected-root "D:\Documents\CodexProject\alex-runtime"
```

Expected behavior after the next refresh:

- new `project_open("alex-runtime")` -> `PROJECT_NOT_ALLOWED`;
- new operations for that project -> rejected;
- existing sessions for that removed project MUST NOT preserve authorization.

### 8.1 Existing-session revocation

Removing a project is an authorization revoke.

Every operation must ultimately revalidate that the session's `project_id` still exists in the current validated registry snapshot.

A previously valid session must not allow continued access after local removal.

The implementation may keep historical session/audit records in SQLite, but those records must not grant project authorization.

## 9. Project Root Change Protection

A project ID is an authorization identity. It must not silently point to a different filesystem root during hot reload.

Example unsafe direct edit:

```toml
[projects.foo]
root = "D:/Project/A"
```

changed to:

```toml
[projects.foo]
root = "D:/Project/B"
```

Required behavior:

- reject the candidate hot reload;
- keep the last valid project snapshot active;
- report a non-secret reload error;
- do not transfer existing sessions or authorization to `D:/Project/B`.

Recommended error identity:

```text
PROJECT_ROOT_CHANGE_REQUIRES_REMOVE_ADD
```

The supported transition is explicitly:

```powershell
project remove foo --expected-root D:\Project\A
project add foo D:\Project\B
```

This gives the local operator an auditable authorization boundary.

## 10. Policy and Command Changes

The following project-local fields may be eligible for hot reload after full validation:

- `allowed_branches`;
- `require_clean_workspace`;
- `codemcp_config`;
- registered commands;
- project profile-derived command metadata.

Rules:

1. A new operation uses the newest successfully validated project snapshot.
2. An already dispatched operation keeps the `ProjectSpec`/`CommandSpec` snapshot resolved for that operation.
3. Reload must not mutate an operation's authorization or executable command while it is running.
4. A configuration change cannot widen an already-running operation.
5. Invalid command/policy changes fail closed and leave the prior snapshot active.

## 11. Invalid Configuration Behavior

A bad edit to `projects.toml` must not destroy the currently working Bridge.

Examples:

- TOML syntax error;
- invalid project ID;
- invalid/missing root;
- non-directory root;
- disallowed reparse/symlink condition;
- invalid command schema;
- unsafe command configuration;
- malformed branch policy;
- incompatible project configuration.

Required behavior:

```text
new candidate configuration = rejected
last known-good registry snapshot = remains active
reload status = failed
```

Do not partially apply a candidate configuration.

When the file is corrected, a later request should automatically retry and install the valid snapshot.

## 12. Concurrency and Atomicity

Reload must be safe under concurrent requests.

Required properties:

- one logical candidate snapshot per observed file generation;
- no partially replaced project mapping;
- no mixed old/new registry state inside one operation;
- no duplicate expensive rebuild storm under concurrent `project_open`;
- operations that already captured a project spec may finish under that immutable per-operation snapshot, except authorization revocation checks that are explicitly required before side effects;
- mutation safety and per-project locks remain unchanged.

Use an internal lock around candidate reload/atomic swap if required.

Do not hold the registry reload lock while performing long-running codemcp, Git, test, or format operations.

## 13. Integration With Bridge Components

Review all components currently constructed from startup `BridgeSettings`:

- `ProjectRegistry`;
- `PolicyEngine`;
- `CodemcpAdapter`;
- `RegisteredCommandRunner`.

Do not merely refresh `ProjectRegistry` if another component keeps a stale copy of `settings.projects`.

The implementation must ensure project-specific resolution uses the current `ProjectSpec` snapshot consistently.

Global immutable settings may remain from process startup.

Prefer passing current `ProjectSpec` into downstream policy/adapter/runner functions rather than rebuilding the entire Bridge service.

## 14. CLI Behavior

`project add/remove` remain local administrative commands.

Enhance successful output with:

```text
reload = automatic
restart_required = false
```

Do not make project registration depend on the Bridge being online.

If Bridge is stopped:

```text
project add/remove
-> projects.toml changes correctly
-> next Bridge start naturally loads the new registry
```

If Bridge is running:

```text
project add/remove
-> next authorized project request automatically reloads
```

No CLI-to-Bridge privileged control channel is required.

## 15. Observability

### 15.1 Local status / doctor

Local-only operator diagnostics may expose:

- `projects_config` path;
- `projects_registered` count;
- registry generation;
- last reload status;
- last successful reload time;
- last reload error code/message, sanitized.

Do not expose project configuration contents or secret-adjacent data unnecessarily.

### 15.2 Public health

If `/healthz` includes registry data, keep it minimal and non-sensitive, for example:

```json
{
  "projects_registered": 3,
  "project_registry_reload": {
    "status": "ok",
    "generation": 4
  }
}
```

Do not expose:

- registered project roots;
- command argv;
- complete project IDs unless already intentionally public;
- configuration file contents.

Public health observability is optional; local `doctor/status` is preferred for detail.

## 16. MCP Contract Freeze

The public MCP tool set must remain exactly the intentional existing contract.

Add regression assertions that these tools do not exist:

```text
project_add
project_remove
project_reload
project_configure
```

Also verify no generic file operation can escape a registered project and write:

```text
<CODEMCP_HOME>/config/projects.toml
```

This is an explicit release/security invariant.

## 17. Implementation Phases

### Phase 1 — Registry Snapshot and Reload Core

Goal:

- central current project snapshot;
- fingerprint tracking;
- validated candidate reload;
- atomic swap;
- reload synchronization;
- no behavior change to remote tool surface.

Likely files:

- `bridge/src/codemcp_bridge/project_registry.py`
- `bridge/src/codemcp_bridge/settings.py`
- `bridge/src/codemcp_bridge/mcp_server.py`
- focused tests.

STOP after Phase 1 implementation and targeted tests if a design blocker is found. Otherwise continue.

### Phase 2 — Authorization Semantics

Implement and validate:

- add becomes visible without restart;
- remove revokes new access;
- existing session loses authorization after remove;
- root change is rejected;
- remove + add permits an explicit new root;
- project policy/command snapshot behavior;
- invalid candidate preserves last known-good snapshot.

Do not weaken session ownership, project locks, checkpoint, replay, approval, CAS, or sensitive-path behavior.

### Phase 3 — CLI and Observability

Update:

- `project add/remove` result fields;
- `status`;
- `doctor`;
- reload metadata;
- sanitized logging.

No remote administrative tool is added.

### Phase 4 — Documentation and Full Regression

Update at least:

- `README.md`;
- `docs/guides/windows-build-install-use.md`;
- `docs/guides/operations-runbook.md`;
- `docs/architecture/security-model.md`;
- relevant config/acceptance documentation.

Then run targeted tests and full regression.

## 18. Required Test Matrix

At minimum:

1. Bridge starts with only project A.
2. Local CLI-style atomic config change adds B.
3. Without restart, `project_open(B)` succeeds.
4. Remove B without restart.
5. New `project_open(B)` returns `PROJECT_NOT_ALLOWED`.
6. An existing B session cannot read/write after removal.
7. Invalid TOML leaves A available.
8. Fixing TOML allows later automatic recovery.
9. Same project ID with changed root is rejected.
10. Remove -> add with a new root is accepted.
11. Branch/command policy change is visible to the next operation.
12. A running registered command is not mutated mid-execution by reload.
13. Concurrent requests observing one file change install one coherent snapshot.
14. Atomic CLI write never exposes a partial TOML snapshot.
15. Reload failure never partially updates the registry.
16. MCP public tool count/contract remains unchanged.
17. `project_add`, `project_remove`, `project_reload`, `project_configure` are absent.
18. MCP file tools cannot reach runtime `projects.toml`.
19. Network-trust profile regression passes.
20. OAuth Resource Server profile regression passes.
21. session/replay namespace behavior remains unchanged.
22. checkpoint/restore/CAS regression passes.
23. registered-command allowlist remains unchanged.
24. model egress deny remains unchanged.
25. full pytest passes.
26. Ruff check passes.
27. Ruff format check passes.
28. compileall passes.
29. `git diff --check` passes.
30. final worktree is clean.

## 19. Acceptance Contract

The feature is complete only when the following user flow works:

```powershell
.\codemcp-remote.exe project add alex-runtime "D:\Documents\CodexProject\alex-runtime"
```

with no restart, followed immediately by ChatGPT:

```text
project_open("alex-runtime")
-> success
```

Then:

```powershell
.\codemcp-remote.exe project remove alex-runtime --expected-root "D:\Documents\CodexProject\alex-runtime"
```

with no restart, followed by ChatGPT:

```text
project_open("alex-runtime")
-> PROJECT_NOT_ALLOWED
```

and any old session for `alex-runtime` is also denied further project access.

At all times:

```text
Local CLI = authorization control plane
ChatGPT/MCP = authorized execution plane
Remote project-administration capability = 0
```

## 20. Non-Goals / Future Guardrail

Do not later expose project registration through MCP merely for convenience.

If a future multi-user administrative control plane is ever designed, it must be a separately authenticated and explicitly authorized subsystem with a new threat model. It must not be smuggled into the existing execution-plane MCP contract.

For this implementation, local CLI remains the sole authority for project registration.
