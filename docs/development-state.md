# Development State

Last updated: 2026-08-30

## Current branch and source state

- Branch: `codex/macos-cli-packaging`
- Source commit containing the BridgeError fix: `2ccfc5a5654b2c3077bedde0d498f4abebb27eff`
- macOS Release Candidate workflow is configured to run on pushes to `codex/macos-cli-packaging`.
- macOS candidate matrix includes `macos-arm64` and `macos-intel64`.

## macOS Intel64 live acceptance

Test host: Intel Mac (`x86_64`).
Registered project: `sample_project`.
Project root observed through codemacos: `/Users/qyf/projects/example-project`.

Verified PASS:

- Remote MCP connection to the Mac host.
- `project_open` succeeds on an allowed branch.
- Branch policy enforcement works: `main` was rejected with `BRANCH_NOT_ALLOWED`.
- Current accepted project branch: `develop`.
- `git_status` succeeds and reports a clean worktree.
- `file_list` succeeds.
- `file_read` succeeds.
- `file_create` succeeds.
- Mutations automatically create Git commits and Bridge-owned checkpoints.
- `git_diff(checkpoint)` returns the expected bounded diff.
- `file_delete` succeeds and commits the cleanup.
- Worktree returned to clean after the create/delete acceptance cycle.
- `checkpoint_create` correctly enters `awaiting_approval` and does not create a checkpoint before approval.
- Approval audit trail contains `operation.created -> validated -> approval.created -> awaiting_approval`.

Observed acceptance commits in `sample_project`:

- Baseline: `84aa5b9ca05d701d4dbc5fd935fc09ffef339356`
- Create acceptance file: `441cf87f45e3a761954ff81ff9a820e5d978915e`
- Cleanup acceptance file: `ceca4c30486cf30a33b39e8ac7e932bd55c8b817`

## Fixed macOS blocker

A packaged-runtime failure surfaced as:

`super(type, obj): obj must be an instance or subtype of type`

Root cause was `BridgeError` using zero-argument `super()` inside a `@dataclass(slots=True)` exception class.

Fix:

```python
Exception.__init__(self, self.message)
```

After the fix, the previous broad test failure collapsed from 42 failures to:

- 385 passed
- 2 failed
- 8 skipped

The remaining two failures are unrelated integration failures in the real codemcp read/edit path and are not the original BridgeError constructor failure.

## Current blocker

The ChatGPT platform currently blocks calls to high-risk execution tools before they reach codemacos, including attempts to consume or cancel the pending approval operation.

Pending operation:

- Operation id: `5c3df312bb1f45d0a30f098b15e7c4c0`
- Kind: `checkpoint_create`
- State: `awaiting_approval`

Because the platform blocks `approval_confirm` / `operation_cancel`, the following acceptance items remain incomplete:

- approval token consumption
- one-time approval semantics
- checkpoint restore
- restore compare-and-swap conflict protection
- registered command execution
- `test_run`
- `format_run`

## Next steps

1. Resolve or characterize the platform-level blocking of high-risk MCP execution calls.
2. Complete approval-confirm and checkpoint-restore acceptance on macOS Intel64.
3. Configure a development command profile for `sample_project` and verify registered command, test, and format flows.
4. Re-run native macOS Intel64 release acceptance after any related code changes.
