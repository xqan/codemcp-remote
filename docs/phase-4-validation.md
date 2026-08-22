# Phase 4 Validation

## Scope

Phase 4 adds Bridge-owned Git checkpoints, bounded checkpoint diffs, baseline
metadata for mutation operations, and compare-and-swap rollback. Secure MCP
Tunnel integration remains deferred to Phase 5.

## Implemented surface

- `checkpoint_create`: clean-worktree checkpoint creation with explicit
  approval.
- `checkpoint_restore`: two-step approved restore of a registered checkpoint
  with caller-supplied expected HEAD.
- `git_diff(checkpoint_id=...)`: bounded, sensitive-path-filtered comparison
  against a registered checkpoint.
- Automatic mutation checkpoints for `file_edit`, `format_run`, `test_run`,
  and rollback safety checkpoints.
- SQLite migration 3 with checkpoint metadata and audit linkage.

## Validation commands

~~~text
uv sync --project bridge
uv run --project bridge codemcp-bridge-server check
uv run --project bridge ruff check bridge/src bridge/tests
uv run --project bridge pytest -q --basetemp=.local/pytest-phase4
~~~

The Phase 4 tests cover a Chinese/space-containing project path, clean and
dirty worktrees, before/after HEAD and tree metadata, sensitive diff
rejection, manual checkpoint approval, checkpoint diff, external HEAD races,
CAS rejection, safety checkpoint creation, and successful restore.

## Known limitations

- The current compatibility decision still requires WSL2 for codemcp
  Git-backed mutation; native Windows codemcp mutation remains unsupported.
- Diff hashes are computed over the bounded diff returned by GitGuard. The
  full diff is never persisted.
- A checkpoint ref is retained until a future retention policy is designed;
  Phase 4 does not delete user branches or clean up checkpoint refs.
- Secure MCP Tunnel is not connected.
