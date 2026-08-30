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

## macOS Intel64 approval and restore acceptance

The annotated `macos-intel64` candidate was deployed and re-tested through the live `codemacos` connector. The previously observed host-level blocking is resolved for the approval/restore control path.

Verified PASS:

- `project_open` succeeded on `sample_project` / `develop`, clean at baseline HEAD `ceca4c30486cf30a33b39e8ac7e932bd55c8b817`.
- `checkpoint_create` operation `a1133255c6ec42728046a0e1acbd4555` entered `awaiting_approval` and created no checkpoint before confirmation.
- `approval_confirm` reached the Bridge and succeeded, creating manual checkpoint `3b02ac21903e4f82a2697bfd211beeed`.
- Replaying the same approval against the already-succeeded operation was rejected with `OPERATION_NOT_CANCELABLE`; the approval cannot execute the operation twice.
- A controlled mutation created `checkpoint-restore-acceptance.txt` and advanced HEAD to `f64bc1853464162ee74d96f9174f0ff13de4deef`.
- `checkpoint_restore` operation `68e59888488c4062ab9ca4516e52d5a9` correctly entered `awaiting_approval`.
- Confirming that restore succeeded and returned HEAD to `ceca4c30486cf30a33b39e8ac7e932bd55c8b817`.
- Restore automatically created rollback-safety checkpoint `31b6ca40996e49c4a9e4e471782b16fa`.
- Reusing stale `expected_head=f64bc1853464162ee74d96f9174f0ff13de4deef` after restore was rejected before approval with `CHECKPOINT_CONFLICT`; actual HEAD remained `ceca4c30486cf30a33b39e8ac7e932bd55c8b817`.
- The restore acceptance file is absent after rollback and the project is back at its pre-test Git state.

Conclusion: MCP `ToolAnnotations` deployment restored ChatGPT-host compatibility for `checkpoint_create`, `approval_confirm`, and `checkpoint_restore` without weakening Bridge-side approval, checkpoint, CAS, audit, or fail-closed behavior.

## Current blocker

The approval/restore blocker is closed. The project-side development command contract is now present:

- `sample_project` HEAD after adding `codemcp.toml`: `60b4180d99680615fcf0ea4cc68146911df20a0f`.
- Fixed commands `test`, `format`, and `verify` all use the deterministic read-only argv `["/usr/bin/grep", "-qx", "test", "test.md"]`.
- The command contract is intentionally minimal and accepts no model-supplied argv or runtime parameters.

The remaining blocker is Bridge authorization configuration: the runtime `projects.toml` entry for `sample_project` still has no `commands` tables. That file is outside the registered project root, so the Bridge correctly refuses to mutate it through project file tools. The runtime configuration must explicitly register the same fixed argv before command execution can become `development_ready`.

A final full repository regression after correcting `bridge/tests/test_mcp_tool_annotations.py` also remains outstanding. The last completed full run before that test correction preserved the known baseline of 385 passed, 2 failed, 8 skipped.

## Next steps

1. Add matching `test`, `format`, and `verify` command entries under `projects.sample_project.commands` in the macOS runtime `projects.toml`.
2. Let project-registry hot reload pick up the saved configuration; no Bridge restart should be required when the project root is unchanged.
3. Verify `project_status` reports `test`, `format`, and `verify` as matched commands with `development_ready=true`.
4. Run live Intel64 `registered_command_run(verify)`, `test_run(test)`, and `format_run(format)` acceptance.
5. Re-run the full `codemcp-remote` regression including `test_mcp_tool_annotations.py`; distinguish any remaining known integration failures from new regressions.
6. Re-run native macOS Intel64 release acceptance and update this document with the final gate result.
