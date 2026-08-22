# Operations Runbook

## Phase 0 local validation

From the repository root:

~~~text
uv sync --project bridge
uv run --project bridge codemcp-bridge doctor --json
uv run --project bridge pytest -q
~~~

The Phase 0 doctor should report:

- Python 3.12 or newer
- Git is installed
- the Bridge and project example configurations are valid
- the codemcp baseline is release 0.3.0 at the pinned commit
- model egress is denied
- codemcp is installed and pinned from Phase 1 onward

## Phase 2 local Bridge

The local Bridge can now be started for loopback-only validation:

~~~text
uv run --project bridge codemcp-bridge-server check
uv run --project bridge codemcp-bridge-server serve
curl http://127.0.0.1:46200/healthz
~~~

On Windows, the default codemcp worker runs in WSL2 Ubuntu. The WSL virtual
environment is expected at `.local/bridge-venv-wsl`; configure
`codemcp.wsl_python` when the environment is elsewhere. This is a local
development server, not the production startup flow, and it is not connected
to Secure MCP Tunnel yet.

Do not expose codemcp directly to ChatGPT. The intended future startup order
is Bridge, codemcp worker, tunnel-client, then ChatGPT tool discovery. The
Bridge is the only MCP server exposed to a future Tunnel.

Phase 2 intentionally keeps sessions in memory. A Bridge restart closes all
sessions and does not provide operation recovery, approval records, audit
records, checkpoints, or rollback. Those behaviors belong to later phases.

## Local state

Development state is kept under .local and is ignored by Git. Runtime secrets
must not be stored in the repository or example configuration files.
