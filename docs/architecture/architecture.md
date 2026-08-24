# Architecture Baseline

## Scope

This repository is the independent ChatGPT-only coding service described in
the [implementation plan](../implementation-plan.md).

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
- Platform decision after the native Windows compatibility follow-up: run codemcp
  workers locally on Windows by default. A Bridge-owned compatibility entry point
  prevents Git-backed child processes from inheriting MCP stdin and prevents
  duplicate Windows newline translation. WSL2 Ubuntu remains an explicit fallback.
- codemcp baseline: release 0.3.0 at commit 683e6ec29b15b91ec12430afabf5a45ed57d2489.
- The dependency remains upstream codemcp 0.3.0 unchanged; Windows compatibility
  is isolated in the Bridge wrapper rather than maintained as an upstream fork.

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

## Phase 4 Git protection

Each mutation runs under the existing project lock. After the clean-worktree
and worktree-root checks, the Bridge records a Git tree manifest (object IDs,
not source contents) and creates a lightweight ref under
`refs/codemcp-remote/checkpoints/`. The post-mutation HEAD, changed paths and
bounded diff hash are persisted with the operation. Manual checkpoints and
rollback safety checkpoints use the same namespace and SQLite table.

`checkpoint_restore` is a two-step approved mutation. It verifies the recorded
ref, current branch, caller-supplied expected HEAD and clean worktree before
issuing the fixed `git reset --hard <Bridge-owned-ref>`. Any external change
causes a fail-closed `CHECKPOINT_CONFLICT`; an uncertain Git result becomes
`UNKNOWN_SIDE_EFFECT` and requires reconciliation.

## Session WIP commit lifecycle

Each file mutation still creates and finalizes its own checkpoint. While the
project mutation lock is held, the Bridge independently evaluates whether the
current HEAD is eligible for a session WIP amend. Amend is allowed only when
the SQLite checkpoint evidence, exact commit footer, current branch/HEAD, clean
worktree, and Git ref inspection all agree. The GitGuard repeats the branch,
HEAD, and locally observable shared-ref checks immediately before an amend.
Otherwise the mutation creates a new WIP commit with the current session
footer.

An amend changes the branch tip but does not rewrite or move the checkpoint ref
that was created before the mutation. This is why a sequence of operations can
have one branch-visible WIP commit and still retain one recoverable checkpoint
per operation. A no-op mutation finalizes with unchanged HEAD and cannot
establish ownership. Git side effect, expected after-HEAD/branch verification,
and checkpoint finalization stay inside the same project lock. For mutation
checkpoints, the audit diff is computed between the fixed checkpoint ref and
the returned expected after-commit, followed by a terminal HEAD/branch CAS.
A mismatch is persisted as `UNKNOWN_SIDE_EFFECT` without after-state ownership
evidence.
After restart, the original session is blocked; a successor can reconcile an
unknown operation, but its next mutation starts a new WIP ownership chain.

The shared-ref guarantee is limited to local branch, tag, and remote-tracking
refs observable by GitGuard. It cannot prove the absence of a remote publication
that has not propagated to a local ref, so an active session WIP must not be
manually pushed before the session is complete.

## Phase 5 Secure MCP Tunnel

The repository wrapper starts `tunnel-client` with a generated HTTP profile:

~~~text
OpenAI Secure MCP Tunnel
  -> tunnel-client (outbound HTTPS, loopback admin UI)
  -> Bridge: http://127.0.0.1:46200/mcp
  -> codemcp Adapter / Worker
~~~

The wrapper rejects profiles that use a non-OpenAI control plane, store a
plaintext API key, point at a non-loopback MCP target, or configure a stdio
command. Tunnel transport does not add project authorization; the Bridge
continues to own session, operation, approval, idempotency, and audit checks.
