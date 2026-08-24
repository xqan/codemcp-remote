# Phase 4 Validation

## Scope

Phase 4 adds Bridge-owned Git checkpoints, bounded checkpoint diffs, baseline
metadata for mutation operations, compare-and-swap rollback, and the follow-up
session WIP commit safety behavior. Secure MCP Tunnel integration remains
deferred to Phase 5.

## Implemented surface

- `checkpoint_create`: clean-worktree checkpoint creation with explicit
  approval.
- `checkpoint_restore`: two-step approved restore of a registered checkpoint
  with caller-supplied expected HEAD.
- `git_diff(checkpoint_id=...)`: bounded, sensitive-path-filtered comparison
  against a registered checkpoint.
- Automatic mutation checkpoints for `file_edit`, `format_run`, `test_run`,
  and rollback safety checkpoints.
- Session WIP commits use an exact `Codemcp-Remote-Session` footer and amend
  only after SQLite, checkpoint, branch, HEAD, clean-worktree, and locally
  observable shared-ref evidence agrees; GitGuard repeats the checks before the
  amend and finalization uses an expected after-HEAD/branch CAS.
- Mutation checkpoint audit diffs compare the fixed checkpoint ref with the
  returned after-commit, followed by a terminal HEAD/branch CAS before SQLite
  finalization.
- SQLite migration 3 with checkpoint metadata and audit linkage.

## Validation commands

~~~text
uv sync --project bridge
uv run --project bridge codemcp-bridge-server check
uv run --project bridge ruff check bridge/src bridge/tests
uv run --project bridge pytest -q --basetemp=.local/pytest-phase4
~~~

The Phase 4 and follow-up tests cover a Chinese/space-containing project path,
clean and dirty worktrees, before/after HEAD and tree metadata, sensitive diff
rejection, manual checkpoint approval, checkpoint diff, external HEAD races,
CAS rejection, safety checkpoint creation, successful restore, session WIP
amend, restart/reconcile, successor-session isolation, idempotent replay, and
unknown/cancelled mutation handling.

## Known limitations

- The current compatibility decision still requires WSL2 for codemcp
  Git-backed mutation; native Windows codemcp mutation remains unsupported.
- Diff hashes are computed over the bounded diff returned by GitGuard. The
  full diff is never persisted.
- A checkpoint ref is retained until a future retention policy is designed;
  Phase 4 and the session WIP follow-up do not delete user branches or clean up
  checkpoint refs.
- Secure MCP Tunnel is not connected.

## Session WIP rollout constraints

The rollout is backward-compatible with existing SQLite data and MCP request
parameters. Historical commits or checkpoints without the new footer are
treated as lacking ownership evidence and cause a safe CREATE fallback. A code
rollback requires no database downgrade and does not delete either old or new
checkpoint refs. Operators should not publish an active session's WIP before
the session's mutations are complete; a local remote-tracking ref may otherwise
force the next mutation to create a new commit.

The shared-ref check is limited to local branch, tag, and remote-tracking refs.
It cannot prove that an unseen remote ref does not already contain the WIP.
