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

## MCP host approval compatibility work

The blocking is now characterized as a ChatGPT MCP host-level issue rather than a macOS-specific Bridge failure:

- `approval_confirm` and `operation_cancel` were blocked before reaching `codemacos`.
- The same host-level blocking was later reproduced against the Windows development connector for `test_run` and `registered_command_run`.
- OpenAI MCP approval filtering consumes standard MCP `readOnlyHint` metadata, so the Bridge must publish accurate tool risk annotations instead of relying only on prose descriptions.
- Source now imports MCP `ToolAnnotations` and publishes closed-world risk hints for the high-risk execution/control surface:
  - destructive writes: `registered_command_run`, `format_run`, `test_run`, `checkpoint_restore`, `approval_confirm`, `operation_reconcile`
  - non-destructive state writes: `checkpoint_create`, `operation_cancel`
- Bridge-side policy, approval state, checkpoint, CAS, idempotency, and audit enforcement remain authoritative; the annotations are host-facing hints only.
- Contract coverage was added in `bridge/tests/test_mcp_tool_annotations.py`.
- Current source HEAD after the annotation implementation and contract-test correction: `dcbfad5bea3d2e24a46b2f06adb7e880b7013b92`.

Validation:

- Formatting check passed after the annotation implementation: 84 files already formatted.
- First full regression after adding annotations but before the contract test preserved the previous baseline: 385 passed, 2 failed, 8 skipped.
- The first run with the new contract test produced one new test-only failure because the current MCP Python model exposes annotation fields as snake_case; the test was corrected at `dcbfad5bea3d2e24a46b2f06adb7e880b7013b92`.
- A final full regression after that correction could not be started because ChatGPT blocked both `test_run` and the equivalent fixed `registered_command_run(test)` before either request reached the Bridge.
- The pre-existing two integration failures remain the known baseline until a final rerun can be completed.

## Current blocker

The ChatGPT host currently blocks selected non-read-only/high-risk MCP calls before they reach the Bridge. The new ToolAnnotations implementation has not yet been deployed to the Intel64 Mac, so its effect on ChatGPT approval UX is not yet verified.

The earlier macOS pending operation may still exist:

- Operation id: `5c3df312bb1f45d0a30f098b15e7c4c0`
- Kind: `checkpoint_create`
- Last observed state: `awaiting_approval`

Incomplete acceptance items:

- verify ChatGPT host behavior after deploying the annotated tool surface
- approval token consumption / one-time approval semantics
- checkpoint restore
- restore compare-and-swap conflict protection
- registered command execution
- `test_run`
- `format_run`
- final full regression after the contract-test correction

## Next steps

1. Push `dcbfad5bea3d2e24a46b2f06adb7e880b7013b92` (or a descendant) to `codex/macos-cli-packaging` so the macOS RC workflow builds the annotated MCP surface.
2. Install the fresh `macos-intel64` candidate and restart the Mac Bridge.
3. Refresh/reconnect the ChatGPT MCP connector so it re-discovers the new tool metadata.
4. Re-test `checkpoint_create` / `approval_confirm` and observe whether ChatGPT now presents/permits the correct host approval flow.
5. If host approval still blocks `approval_confirm`, redesign the Bridge approval protocol so the model never receives a secret approval token; retain Bridge-side CAS/checkpoint/audit fail-closed guarantees.
6. Complete checkpoint-restore and registered command/test/format acceptance, then rerun native macOS Intel64 release acceptance.
