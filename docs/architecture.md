# Phase 0 Architecture Baseline

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
- Platform decision: validate native Windows first and keep WSL2 as the fallback candidate.
- codemcp baseline: release 0.3.0 at commit 683e6ec29b15b91ec12430afabf5a45ed57d2489.

## Deliberately deferred to Phase 1

- Whether codemcp is run natively on Windows or inside WSL2.
- Whether upstream codemcp can be used unchanged.
- Whether a minimal codemcp fork is required.
- Whether codemcp automatic Git commits are retained or controlled by a
  Bridge-specific commit mode.
- The exact downstream MCP transport used by the Adapter.

## Security boundary

The Tunnel is only the remote transport. It does not grant access to arbitrary
projects or commands. All project, path, command, approval, audit, and
idempotency checks belong to the Bridge.
