# Security Model

## Purpose

codemcp-remote exposes controlled local development capabilities to ChatGPT through an MCP Bridge. Because those capabilities include source reads, source mutations, registered development commands, and limited Git recovery, the Bridge is the security enforcement point.

The design goal is not to make arbitrary remote shell access safe. The design goal is to avoid exposing arbitrary shell or arbitrary filesystem access at all.

## Architecture and trust boundaries

```text
ChatGPT
  |
  | Secure MCP Tunnel
  v
tunnel-client
  |
  | loopback HTTP MCP
  v
codemcp-remote Bridge
  |
  | validated project/tool invocation
  v
codemcp worker (WSL2)
  |
  v
registered local Git project
```

### ChatGPT

ChatGPT is the only reasoning engine in the current architecture. It decides which MCP tool to call and what edit intent to submit.

ChatGPT is **not** trusted to bypass Bridge policy. A mistaken instruction, prompt injection from repository content, or compromised conversation must still be constrained by project registration, relative-path validation, command registration, mutation preconditions, approvals, and Git compare-and-swap checks.

### Secure MCP Tunnel and tunnel-client

The Tunnel is a transport boundary. The supported profile forwards to the Bridge's loopback MCP endpoint and uses outbound connectivity to the OpenAI control plane.

The Tunnel does not grant project authorization and does not replace the Bridge's approval, session, operation, or audit checks. The Bridge must remain safe if a caller sends policy-violating MCP input through an otherwise valid Tunnel.

### Bridge

The Bridge is the primary security boundary. It is responsible for:

- resolving only registered `project_id` values;
- accepting only project-relative authorized paths;
- rejecting sensitive paths;
- rejecting symlink, junction, and reparse-point traversal;
- exposing fixed tools instead of arbitrary shell;
- executing only registered commands with bounded timeouts;
- enforcing mutation preconditions and per-project mutation serialization;
- binding operations to session/project state;
- validating canonical request hashes for mutation idempotency;
- issuing and consuming short-lived one-time approvals;
- recording operation/audit state;
- creating Bridge-owned Git checkpoints;
- performing compare-and-swap rollback;
- preserving `unknown` when a side effect cannot be established safely;
- bounding and sanitizing tool output.

The default example configuration binds to `127.0.0.1:46200`, denies arbitrary paths, arbitrary commands, and model calls, requires a clean workspace, and sets `model_egress = "deny"`.

### codemcp worker

`codemcp==0.3.0` is a pinned third-party execution backend. Mutation workers currently run under WSL2 Ubuntu.

The worker is not a second reasoning agent. The Bridge must not assume that a backend error proves no local side effect occurred. Where completion cannot be determined, the operation must become `unknown` and require reconciliation.

The upstream dependency remains separately licensed under Apache-2.0.

### Registered project and repository content

A project root is authorized by local operator configuration. Files inside the repository are data, not policy authority.

Repository text can contain malicious instructions or prompt injection. Such content must not:

- register another project;
- widen allowed paths;
- add arbitrary runtime arguments;
- approve an operation;
- disable audit;
- change the meaning of an approval token;
- authorize destructive Git actions.

Project configuration that controls executable commands is security-sensitive and must be treated as operator-controlled configuration, not as permission derived from repository prose.

### Local operating-system account

The local OS user is a root trust assumption for the current version. An attacker who can arbitrarily modify the Bridge executable, its Python environment, local configuration, SQLite database, trusted scripts, Git executable, WSL environment, or runtime process memory is outside the protection boundary.

codemcp-remote is not a sandbox against a compromised local administrator/user account.

## Filesystem authorization

### Registered roots only

The public tool surface accepts a `project_id`, not an arbitrary host path. Unknown IDs are rejected.

Paths are normalized as project-relative paths. Resolution must remain below the registered project root.

### Link escape prevention

Existing path components are checked for symbolic links and Windows reparse points. A path that traverses such a component is rejected rather than followed.

This protects the intended repository-root boundary but is not a substitute for OS-level sandboxing.

### Sensitive-path denial

The current deny rules include names such as `.git`, credentials/password/secret/token names, common private-key/certificate suffixes, and `*.env` / `*.env.*`.

Search traversal also excludes sensitive paths before invoking the backend, and results are filtered again before return.

The deny list is defense in depth, not a guarantee that every secret can be recognized by filename. Users must not store high-value secrets in source repositories merely because this filter exists.

## Command execution

The Bridge does not accept arbitrary executable paths, shell strings, or caller-supplied argv for registered commands.

Commands are resolved by ID from operator-controlled configuration. Known lower-risk development command kinds can run without an extra approval; unknown or higher-risk kinds default to explicit approval. Commands have bounded timeouts.

The Bridge does not expose push, merge, rebase, deploy, branch deletion, force reset, or arbitrary Git arguments as generic MCP capabilities.

A registered command itself can still be dangerous if the operator configured it dangerously. Command registration is therefore part of the trusted local policy surface.

## Mutation safety

### Clean baseline

The default policy requires:

- an allowed branch;
- a clean Git worktree;
- a recorded branch/HEAD baseline;
- serialized mutation for a project.

### Idempotency

Mutation calls require a caller request ID and SHA-256 request hash. The Bridge independently computes a canonical hash of security-relevant operation input and rejects mismatches.

A previously used request ID cannot safely be repurposed for a different mutation.

### Approval

High-risk operations use a random, short-lived approval token. Only its hash is persisted. Approval is operation-bound, expires, and is one-time consumable.

An approval is not a general capability token for another session, project, or action.

### Checkpoints and rollback

Before mutation, the Bridge records Git state and creates a Bridge-owned checkpoint ref.

Rollback is compare-and-swap:

1. identify a registered checkpoint belonging to the current project/session;
2. verify its ref;
3. require the expected current HEAD;
4. recheck branch/HEAD and clean worktree;
5. require explicit approval;
6. create a rollback safety checkpoint;
7. execute the fixed restore path.

If external Git state changes, rollback fails closed instead of overwriting the newer state.

### Unknown side effects

Network loss, process crashes, backend rejection, timeout, or cleanup failure can leave uncertainty about whether a mutation occurred.

When the Bridge cannot prove the outcome, `unknown` is a valid terminal/recovery state. The project must be reconciled before unsafe replay. Availability is secondary to avoiding duplicate or destructive mutation.

## Audit and secret handling

Operations, approvals, checkpoints, and audit events are persisted in SQLite. The database is intended to store metadata, hashes, bounded summaries, and errors rather than complete source-file snapshots.

Plaintext approval tokens must not be persisted. Runtime Tunnel credentials must not be committed to the repository or printed in diagnostics.

Logs and tool results are still potential disclosure paths; release validation must include explicit secret/log scanning.

## Network model

The Bridge is expected to listen only on loopback. The supported remote path is Secure MCP Tunnel. The example policy denies model egress from the Bridge.

This is an application policy, not a host firewall. A compromised dependency or local process can violate assumptions unless separately constrained by the OS/network environment.

## Current non-guarantees

The initial `v0.1.0` target does not guarantee:

- protection against a compromised local OS user or administrator;
- multi-user identity, tenancy isolation, or RBAC;
- native Windows Git-backed mutation;
- recognition of every possible secret filename/content;
- containment of an arbitrary malicious registered command;
- security against a malicious replacement of the pinned dependencies or local toolchain;
- automatic recovery from every `unknown` mutation;
- availability when Tunnel, WSL2, Git, or codemcp is unhealthy;
- safety of unsupported transport adapters.

Any future capability that expands filesystem scope, executable scope, identity scope, Git behavior, or remote transport must update this document, the threat model, and regression tests before release.
