# codemcp-remote

A policy-controlled local MCP bridge for using **ChatGPT as the only reasoning engine** while safely operating on registered local code repositories.

```text
ChatGPT
  -> OpenAI Secure MCP Tunnel
  -> loopback codemcp-remote Bridge
  -> pinned codemcp worker in WSL2
  -> registered local Git project
```

> **Pre-release:** the core remote-coding path is implemented and has passed earlier phase validation, but the first stable `v0.1.0` is still blocked on the final Windows operations, security, clean-machine, secrets, and release gates in [`docs/acceptance/acceptance-test-plan.md`](docs/acceptance/acceptance-test-plan.md).

Browse the [documentation center](docs/README.md) for current architecture,
operator guides, release gates, plans, and historical validation records.

## Why codemcp-remote

Remote code modification is a high-privilege operation. codemcp-remote deliberately exposes a smaller surface than arbitrary remote shell access:

- local projects must be explicitly registered;
- tool paths stay inside the registered project root;
- sensitive paths are denied by default;
- commands are selected by registered command ID, not arbitrary shell text or caller-supplied argv;
- mutations are idempotent and serialized per project;
- high-risk operations use short-lived, one-time approvals;
- mutations create Bridge-owned Git checkpoints;
- rollback uses compare-and-swap checks and fails closed on external Git changes;
- uncertain mutation outcomes remain `unknown` until explicitly reconciled;
- Bridge listens on loopback only.

The Bridge does not contain an agent loop or model provider. Repository content is treated as untrusted data and cannot authorize a privileged action.

## Current support

| Component | `v0.1.0` target |
|---|---|
| Host OS | Windows 11 |
| PowerShell | PowerShell 7 (`pwsh`) |
| Bridge | Python 3.12+ |
| Mutation worker | WSL2 Ubuntu |
| codemcp | pinned `0.3.0` |
| Remote transport | OpenAI Secure MCP Tunnel |
| Identity model | single-user local policy profile |
| Native Windows Git-backed mutation | **not supported** |
| Arbitrary shell / arbitrary path | **not exposed** |
| Automatic push / merge / rebase / deploy | **not supported** |

Secure MCP Tunnel and ChatGPT developer-mode availability depend on the capabilities enabled for your account/workspace. Tunnel connectivity is transport only; it does not replace Bridge authorization or approvals.

See [`docs/reports/compatibility/codemcp-compatibility-matrix.md`](docs/reports/compatibility/codemcp-compatibility-matrix.md) for the tested backend behavior.

## Requirements

On Windows:

- Windows 11 with WSL2 enabled;
- an Ubuntu WSL2 distribution;
- Python 3.12+ on Windows;
- Python 3.12+ and `python3-venv` inside the WSL distribution;
- Git;
- PowerShell 7 (`pwsh`);
- [`uv`](https://docs.astral.sh/uv/);
- `tunnel-client` for the remote ChatGPT path;
- an OpenAI Tunnel and the required account/workspace permissions for Tunnel use.

Do not store the Tunnel runtime API key in this repository, a local env file, the generated Tunnel profile, shell history, or logs.

## Quick start

### 1. Install the Bridge dependencies

From the repository root:

```powershell
uv sync --project bridge
```

### 2. Bootstrap the locked WSL2 worker environment

The default worker Python is `.local/bridge-venv-wsl/bin/python` inside the repository as seen from WSL.

```powershell
pwsh -File .\scripts\bootstrap-wsl.ps1
```

The bootstrap exports the locked non-development dependency set from `bridge/uv.lock` into a Git-ignored `.local/worker-requirements.txt`, creates the WSL venv, installs those dependencies, and verifies `codemcp==0.3.0`.

For a distribution other than the default Ubuntu name:

```powershell
pwsh -File .\scripts\bootstrap-wsl.ps1 -WslDistribution Ubuntu-24.04
```

### 3. Register your first project

Create the Git-ignored local registry:

```powershell
Copy-Item config/projects.example.toml config/projects.toml
```

Edit `config/projects.toml`. A conservative explicit example is:

```toml
[projects.my_project]
root = "D:/workspace/my-project"
allowed_branches = ["main", "develop", "feature/*"]
require_clean_workspace = true
codemcp_config = "codemcp.toml"

[projects.my_project.commands.test]
kind = "test"
argv = ["mvn", "-q", "test"]
timeout_seconds = 900
approval = "not-required"
```

Only register repositories you intend ChatGPT to access. Treat registered command configuration as trusted local policy.

### 4. Prepare the Tunnel profile input

```powershell
Copy-Item config/tunnel-profile.example.env config/tunnel-profile.local.env
```

Put the Tunnel ID and other non-secret profile settings in the local file as documented in [`docs/guides/tunnel-setup.md`](docs/guides/tunnel-setup.md).

Inject `CONTROL_PLANE_API_KEY` into the process from a secret manager or another non-persistent mechanism. The wrapper rejects storing that key in `config/tunnel-profile.local.env`.

### 5. Start and diagnose

First local Tunnel profile initialization:

```powershell
pwsh -File .\scripts\start-all.ps1 -Initialize
pwsh -File .\scripts\doctor.ps1
```

Normal later startup:

```powershell
pwsh -File .\scripts\start-all.ps1
pwsh -File .\scripts\doctor.ps1
```

Stop project-owned Bridge, Tunnel, and worker process trees:

```powershell
pwsh -File .\scripts\stop-all.ps1
```

Preview what the stop script would target:

```powershell
pwsh -File .\scripts\stop-all.ps1 -WhatIf
```

## Connect from ChatGPT

Follow [`docs/guides/tunnel-setup.md`](docs/guides/tunnel-setup.md):

1. keep the local Bridge and `tunnel-client` healthy;
2. create/use a ChatGPT developer-mode app with the supported Tunnel connection;
3. select the Tunnel associated with the intended workspace;
4. confirm that the Bridge tools are discovered;
5. run the remote contract in [`tests/e2e/test_tunnel_contract.md`](tests/e2e/test_tunnel_contract.md).

A safe first request is read-only: open one registered project, inspect its status, then read a non-sensitive source file.

Before the first mutation, make sure the target branch and worktree are exactly the state you expect. The default policy rejects a dirty worktree.

## Mutation, approval, and recovery

Mutation calls require a caller request ID and a canonical SHA-256 request hash. Repeating an already completed mutation with the same identity replays the persisted result instead of executing it twice.

Commands or Git operations that require approval return a short-lived one-time approval flow. Plaintext approval tokens are not persisted in SQLite.

For file mutations, the first successful mutation in an eligible Bridge session
creates a branch-visible WIP commit with a
`Codemcp-Remote-Session: <session_id>` footer. Later mutations amend that WIP
only when the Bridge can prove the same session, branch, clean HEAD, finalized
successful checkpoint, exact footer, and absence of locally observable shared
refs. The Bridge rechecks branch, HEAD, and shared refs immediately before an
amend and records an unknown result if finalization observes a different HEAD.
Missing or uncertain ownership evidence during mode selection safely creates a
new commit; a race discovered after a file side effect starts remains `unknown`
for explicit reconciliation. No-op content changes do not create or transfer
WIP ownership.

Before mutation, the Bridge records a Git baseline and creates a Bridge-owned checkpoint. Checkpoint restore:

- is scoped to the registered project/session;
- verifies the registered checkpoint ref;
- requires the expected current HEAD;
- requires a clean worktree;
- requires explicit approval;
- creates a rollback safety checkpoint;
- refuses to overwrite externally changed Git state.

If the Bridge cannot prove whether a side effect occurred, the operation remains `unknown`; do not blindly retry it. Inspect `operation_status` and use the explicit reconciliation flow.

The branch WIP commit and the Bridge checkpoint ref serve different purposes:
the commit is the visible Git baseline for the active session, while each
mutation checkpoint retains the exact pre-mutation commit for audit, diff, and
restore. Checkpoint refs are Bridge-owned recovery metadata and are not a
publication mechanism. Commits or checkpoints created before session WIP
footers were introduced are never automatically adopted for amend.

Local branch, tag, and remote-tracking refs are the shared refs the Bridge can
inspect. The Bridge cannot prove that a commit was never pushed to a remote
state not represented locally, so operators must not publish an active session's
WIP before its mutations are complete.

See [`docs/architecture/git-policy.md`](docs/architecture/git-policy.md) and [`docs/architecture/security-model.md`](docs/architecture/security-model.md).

## Doctor and operations

The main operator commands are:

```powershell
pwsh -File .\scripts\doctor.ps1
pwsh -File .\scripts\doctor.ps1 -SkipTunnel
pwsh -File .\scripts\start-all.ps1
pwsh -File .\scripts\stop-all.ps1
```

The detailed operator guide is [`docs/guides/operations-runbook.md`](docs/guides/operations-runbook.md).

For release validation, the repository also contains a 20-cycle lifecycle runner:

```powershell
pwsh -File .\scripts\validate-lifecycle.ps1 -Iterations 20
```

This is only one release gate. It does not replace the crash, secret-canary, path/encoding, Tunnel-disconnect, and security tests in [`docs/acceptance/phase-6-validation.md`](docs/acceptance/phase-6-validation.md).

## Security model

Read these before exposing a local repository through the Bridge:

- [`SECURITY.md`](SECURITY.md) — vulnerability reporting;
- [`docs/architecture/security-model.md`](docs/architecture/security-model.md) — trust boundaries and guarantees;
- [`docs/architecture/threat-model.md`](docs/architecture/threat-model.md) — threats, mitigations, and residual risks;
- [`docs/architecture/git-policy.md`](docs/architecture/git-policy.md) — checkpoint/diff/rollback constraints.

Important boundaries:

- the local OS account and trusted local configuration are root trust assumptions;
- a dangerously configured registered command is still dangerous;
- filename filtering cannot identify every secret stored under an ordinary filename;
- a compromised dependency/toolchain is not fully contained by the Bridge;
- this first release is not a multi-user identity/RBAC system.

Security issues should follow [`SECURITY.md`](SECURITY.md), not a public exploit report.

## Development

Local checks:

```powershell
uv sync --project bridge
uv run --project bridge codemcp-bridge doctor --strict --json
uv run --project bridge codemcp-bridge-server check
uv run --project bridge ruff check bridge/src bridge/tests tests/integration
uv run --project bridge pytest -q bridge/tests tests/integration
```

The final stable release additionally requires the gates in:

- [`docs/plans/v0.1.0/open-source-readiness-plan.md`](docs/plans/v0.1.0/open-source-readiness-plan.md)
- [`docs/acceptance/phase-6-validation.md`](docs/acceptance/phase-6-validation.md)
- [`docs/acceptance/acceptance-test-plan.md`](docs/acceptance/acceptance-test-plan.md)

## Contributing

Contributions must preserve the project's fail-closed security model. In particular, changes that widen filesystem, command, identity, transport, model-egress, or destructive Git scope require an explicit threat-model update and negative tests.

See [`CONTRIBUTING.md`](CONTRIBUTING.md), [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md), and [`CHANGELOG.md`](CHANGELOG.md).

## License

codemcp-remote is licensed under the **GNU Affero General Public License v3.0 only** (`AGPL-3.0-only`). See [`LICENSE`](LICENSE).

`codemcp==0.3.0` is a separate third-party dependency and retains its upstream Apache-2.0 license. Other dependency licenses are reviewed as part of the release supply-chain gate.
