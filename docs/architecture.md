# Architecture Baseline

## Scope

This repository is the independent ChatGPT-only coding service described in
docs/implementation-plan.md.

The only reasoning engine is ChatGPT. The local components are execution and
control components:

~~~text
ChatGPT
  -> Secure MCP Tunnel
  -> tunnel-client
  -> MCP Bridge at 127.0.0.1:46200/mcp
  -> codemcp Adapter / Worker
  -> registered project
~~~

## Phase 0 decisions

- Runtime baseline: Python 3.12+.
- Bridge package: Python async MCP SDK, bounded to the MCP major version 1.
- Local endpoint baseline: loopback HTTP, 127.0.0.1:46200, path /mcp.
- Local persistence baseline: SQLite under .local/bridge.sqlite3 during development.
- Local logs baseline: .local/logs during development.
- Project access: explicit project_id registry; no arbitrary local paths.
- Command access: explicit command IDs with structured argv; no arbitrary shell.
- Model egress: denied for Bridge and codemcp.
- Platform decision after Phase 1: run codemcp mutation workers in WSL2 Ubuntu;
  native Windows Git-backed mutation is unsupported.
- codemcp baseline: release 0.3.0 at commit 683e6ec29b15b91ec12430afabf5a45ed57d2489.
- Phase 1 adapter decision: use upstream codemcp 0.3.0 unchanged initially; do
  not maintain a fork unless native Windows support becomes a requirement.

## Deliberately deferred to later phases

- Whether codemcp automatic Git commits are retained or controlled by a
  Bridge-specific commit mode.
- The exact downstream MCP transport used by the Adapter.

## Security boundary

The Tunnel is only the remote transport. It does not grant access to arbitrary
projects or commands. All project, path, command, approval, audit, and
idempotency checks belong to the Bridge.

## Phase 3 lifecycle persistence

The Bridge stores lifecycle metadata in `.local/bridge.sqlite3`:

~~~text
Bridge
  -> sessions: created / active / closing / closed / blocked
  -> operations: validated / awaiting_approval / running / terminal state
  -> approvals: hashed, short-lived, one-time tokens
  -> audit_events: append-only state transition records
~~~

The database stores paths, hashes, bounded result summaries, and error
metadata. It does not store full source files or plaintext approval tokens.
