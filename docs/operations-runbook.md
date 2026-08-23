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

## Phase 6 local lifecycle control

Use the one-click launcher after the Tunnel profile has been initialized:

~~~text
pwsh -File .\scripts\start-all.ps1
pwsh -File .\scripts\doctor.ps1
~~~

On the first run, initialize the local Tunnel profile explicitly:

~~~text
pwsh -File .\scripts\start-all.ps1 -Initialize
~~~

`start-all.ps1` starts Bridge first, waits for its loopback health endpoint,
then starts tunnel-client and waits for Tunnel `readyz`. If either endpoint is
already healthy and its process command line belongs to this repository/profile,
the existing service is reused. An unknown process occupying a health endpoint
is rejected. The codemcp WSL2 worker is started on demand by the Bridge when a
registered project operation requires it.

For isolated troubleshooting, the underlying foreground scripts remain
available:

~~~text
pwsh -File .\scripts\start-bridge.ps1
pwsh -File .\scripts\start-tunnel.ps1
~~~

Preview the process trees that Phase 6 will stop:

~~~text
pwsh -File .\scripts\stop-all.ps1 -WhatIf
~~~

Stop only the project-owned Bridge, Tunnel profile and codemcp worker trees:

~~~text
pwsh -File .\scripts\stop-all.ps1
~~~

`stop-all.ps1` matches the repository Bridge command line, the configured
Tunnel profile directory and the WSL2 codemcp worker. It does not terminate an
unrelated process that merely occupies port 46200 or 46201; such a listener is
reported for manual investigation. Run it with permission to query
`Win32_Process` when a service was started elevated.

## Phase 5 local Bridge and Tunnel

The local Bridge can be started for loopback-only validation with:

~~~text
pwsh -File .\scripts\start-bridge.ps1
curl http://127.0.0.1:46200/healthz
~~~

On Windows, the default codemcp worker runs in WSL2 Ubuntu. The WSL virtual
environment is expected at `.local/bridge-venv-wsl`; configure
`codemcp.wsl_python` when the environment is elsewhere. This is a local
development server. The Phase 5 tunnel wrapper is configured separately and
never points directly at codemcp.

Do not expose codemcp directly to ChatGPT. The startup order is Bridge,
codemcp worker on demand, tunnel-client, then ChatGPT tool discovery. The
Bridge is the only MCP server exposed to the Tunnel. See
[docs/tunnel-setup.md](tunnel-setup.md) for the complete setup.

SQLite state is stored at `.local/bridge.sqlite3` and is ignored by Git. A
normal shutdown closes active sessions. After an unclean restart, active
sessions become `blocked`; operations that were not dispatched become
`failed`, while mutations that may have crossed the backend boundary become
`unknown` and require explicit `operation_reconcile` before the project can be
mutated again.

Mutation tools require a caller-provided `client_request_id` and SHA-256
`request_hash`. Repeating the same key and hash replays the persisted result;
changing the hash is rejected. Commands configured with `approval =
"required"` return a short-lived one-time token. The plaintext token is never
stored in SQLite; use `approval_confirm` or `operation_cancel` while the
operation is awaiting approval.

Use `operation_status` to inspect the state and audit events of an operation.
Do not manually edit the SQLite file while the Bridge is running.

Before a mutation, the Bridge records a clean Git baseline and creates a
Bridge-owned checkpoint ref. The mutation result contains the before/after
branch and HEAD, changed files, and a bounded diff hash. The ref and metadata
are persisted in `.local/bridge.sqlite3` and linked to the operation audit
trail.

`checkpoint_create` requires explicit approval and a clean worktree. To
restore, first call `git_status`, then pass its current `head` as
`expected_head` to `checkpoint_restore`; the restore requires a second explicit
approval. A branch change, HEAD change, dirty worktree, missing checkpoint ref,
or ref mismatch rejects the operation without running `git reset --hard`.
The reset is issued only for a database-registered checkpoint and only when
the registered project is the Git worktree root. Use `git_diff` with
`checkpoint_id` to inspect a bounded, sensitive-path-filtered comparison.

Secure MCP Tunnel local setup is implemented in Phase 5. Account-backed
ChatGPT workspace association and remote tool-call acceptance remain an
operator test documented in `tests/e2e/test_tunnel_contract.md`.

## Local state

Development state is kept under .local and is ignored by Git. Runtime secrets
must not be stored in the repository or example configuration files.
