# Packaging Phase 5 — Clean Windows Release Validation

Date: 2026-08-25

## Objective

Validate the packaged `codemcp-remote-setup.exe` on a clean Windows 11 x64 host or VM, independent of the source tree and development runtime.

Packaging Phase 5 must prove that the installed product can:

1. install from the Phase 4 installer;
2. run without Python, `uv`, PowerShell 7, or WSL2 on the product runtime `PATH`;
3. initialize its own writable runtime/configuration under `%LOCALAPPDATA%\codemcp-remote`;
4. store `CONTROL_PLANE_API_KEY` with Windows DPAPI and continue after the plaintext process environment value is removed;
5. use the bundled OpenAI `tunnel-client`;
6. use the native local codemcp worker;
7. register and operate on a disposable local Git repository;
8. start an owned, healthy Bridge and Tunnel;
9. complete the remote ChatGPT connector contract against that clean-machine repository;
10. stop and uninstall without deleting preserved runtime/user data.

Phase 5 does not change the application architecture or installer payload unless clean-machine validation exposes a release blocker.

## Runtime prerequisite boundary

The installed v0.1.0 target does **not** require:

- Python;
- `uv`;
- PowerShell 7 (`pwsh`);
- WSL2;
- the codemcp-remote source repository;
- a separately installed `tunnel-client`.

The installed v0.1.0 target **does require Git for Windows**.

This is an intentional release prerequisite, not a development-only convenience. Git is part of the safety model used for clean-worktree checks, mutation baselines, Bridge-owned checkpoints, session WIP commits, compare-and-swap rollback, and reconciliation. The current installer does not redistribute Git.

The Phase 5 harness rewrites the product runtime `PATH` so that only the installed product directory, the resolved Git directory, and Windows system directories remain visible. It fails if `python.exe`, `py.exe`, `uv.exe`, or `pwsh.exe` are still resolvable after that isolation. `wsl.exe` may remain visible because it is a Windows system component, but the acceptance contract requires `doctor.checks.configuration.worker_mode == "local"` and never configures the WSL2 worker.

## Release artifact under test

Phase 4 produced:

```text
codemcp-remote-setup.exe
SHA-256:
659651d9c0c1f333c39bf1ae4cee107c99bf147487f855aca4600309ec39c37c
```

The exact installer hash must be supplied to the clean-machine harness. A mismatch fails before installation.

On 2026-08-25, `scripts/prepare-windows-release-candidate.ps1` completed successfully and produced the exact clean-machine release candidate:

```text
codemcp-remote-v0.1.0-windows-x64.zip
SHA-256:
6974548d300356dff8219fcb7c84b0ce0ae618cfaa9f64e65424603587ad4168

embedded installer SHA-256:
659651d9c0c1f333c39bf1ae4cee107c99bf147487f855aca4600309ec39c37c

Authenticode:
NotSigned
```

The release-candidate gate also parsed the clean-machine harness with Windows PowerShell 5.1 before creating the archive. This gate is PASS. Phase 5 remains open until a separate clean Windows 11 host/VM completes `Prepare`, `Start`, the remote connector contract, and `Cleanup`.

## Secret handling

Never pass `CONTROL_PLANE_API_KEY` as a script parameter or command-line argument.

On the clean machine, place it only in the current PowerShell process environment before `Prepare`:

```powershell
$env:CONTROL_PLANE_API_KEY = "<set locally; do not paste into chat>"
```

`Prepare` calls:

```text
codemcp-remote.exe init --tunnel-id <id> --store-api-key
```

The product stores the secret with Windows DPAPI. The harness then removes the plaintext process environment variable and requires `doctor` to report:

```text
checks.api_key.status = ok
checks.api_key.source = windows-dpapi
```

## Acceptance harness

The standalone harness is:

```text
scripts\validate-clean-windows-release.ps1
```

It is intentionally Windows PowerShell 5.1-compatible so the clean host does not need PowerShell 7.

The harness has three actions.

### 1. Prepare

`Prepare`:

- requires a clean host with no existing codemcp-remote installation;
- verifies the installer SHA-256;
- requires Git for Windows;
- silently installs to the default per-user location;
- verifies required installed files;
- rejects bundled Python/uv/pwsh/WSL executables;
- isolates the runtime `PATH`;
- checks `codemcp-remote.exe 0.1.0`;
- initializes the Tunnel profile;
- stores the API key with DPAPI;
- removes the plaintext API key from the process;
- verifies `doctor`;
- creates a disposable Git repository;
- registers that project;
- records non-secret Phase 5 state under `%LOCALAPPDATA%\codemcp-remote\phase5-validation.json`;
- deliberately leaves Bridge/Tunnel stopped.

Expected terminal state:

```json
{
  "status": "ready-for-start",
  "phase": "5",
  "action": "prepare",
  "worker_mode": "local",
  "api_key_source": "windows-dpapi"
}
```

### 2. Start

`Start` re-applies the isolated runtime `PATH`, verifies `doctor`, then starts Bridge and Tunnel.

Expected terminal state:

```json
{
  "status": "ready-for-remote-verification",
  "phase": "5",
  "action": "start",
  "bridge_health": "ok",
  "tunnel_health": "ok"
}
```

This split is intentional. If the same Tunnel ID is currently used by the development machine, stop the development lifecycle after `Prepare` and before `Start`. Prefer a dedicated Phase 5 Tunnel/connector when available.

### 3. Cleanup

After remote verification:

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\validate-clean-windows-release.ps1 -Action Cleanup
```

Cleanup stops the installed lifecycle and runs the Inno Setup uninstaller. It intentionally preserves `%LOCALAPPDATA%\codemcp-remote` and the disposable project because the product uninstall contract preserves user/runtime data.

### 4. Reset for acceptance retries only

`Reset` is not part of normal product uninstall behavior. It exists only so the same clean Windows VM can safely retry Phase 5 after a failed acceptance attempt.

Run it only after `Cleanup`:

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\validate-clean-windows-release.ps1 -Action Reset
```

`Reset` fails if codemcp-remote is still installed. It can remove only these fixed acceptance roots:

```text
%LOCALAPPDATA%\codemcp-remote
%LOCALAPPDATA%\codemcp-remote-phase5
```

It refuses other paths and refuses reparse-point roots. A custom `-ProjectRoot` outside the default acceptance tree is never deleted automatically.

The first clean-machine attempt on 2026-08-25 exposed a harness-only isolation defect: the PATH gate kept both `System32` and `%SystemRoot%`, which reintroduced the Windows Python Launcher at `C:\Windows\py.exe`. The product installer had already succeeded, but `Prepare` correctly stopped before initialization. The harness now keeps only the installed product directory, the resolved Git directory, and `System32`; `%SystemRoot%` is no longer added.

## Disposable repository

Default project identity:

```text
project_id: phase5-clean
project root:
%LOCALAPPDATA%\codemcp-remote-phase5\project
```

The harness creates and commits:

```text
README.md
codemcp.toml
PHASE5_ACCEPTANCE.txt
```

The baseline commit hash is returned by `Prepare` and persisted in the Phase 5 validation state.

## Remote connector contract

Phase 5 is not closed by local installation checks alone.

After `Start`, ChatGPT must connect through the intended Secure MCP Tunnel and perform the following against `phase5-clean`:

1. `project_open` succeeds.
2. `project_status` reports the disposable project and `development_ready=true`.
3. `file_read` reads `PHASE5_ACCEPTANCE.txt`.
4. `git_status` reports the baseline branch/HEAD and a clean worktree.
5. One deterministic text mutation is performed on the disposable repository.
6. The resulting Git/checkpoint state is inspected.
7. Idempotent replay is checked for the same mutation identity.
8. The repository is restored to its original baseline using the normal approval/checkpoint restore path.
9. Final `git_status` proves the original baseline HEAD and a clean worktree.

No real user repository is used for this test.

## Tunnel cutover options

### Preferred: dedicated acceptance Tunnel

Use a separate OpenAI Tunnel ID and connector for the clean-machine host. This avoids ambiguity and leaves the development connector running.

### Fallback: reuse the current Tunnel

1. Run `Prepare` on the clean machine.
2. Stop the current development-machine `codemcp-remote.exe` lifecycle.
3. Run `Start` on the clean machine.
4. Wait for the existing connector to reconnect.
5. Run the remote contract.
6. Run `Cleanup` on the clean machine.
7. Restore the development lifecycle if needed.

Do not run two active clients for the same acceptance path when the result would be ambiguous.

## Completion criteria

Packaging Phase 5 is PASS only when all of the following are recorded:

- exact installer SHA-256 verified;
- clean-machine install succeeded;
- no Python/uv/pwsh dependency is visible on the isolated product runtime `PATH`;
- worker mode is `local`;
- Git prerequisite is resolved and reported by `doctor`;
- DPAPI secret storage works after the plaintext environment value is removed;
- bundled `tunnel-client` is found;
- project registration succeeds;
- Bridge and Tunnel are owned and healthy;
- remote ChatGPT connector contract succeeds against the disposable project;
- final Git state returns to the recorded baseline and is clean;
- cleanup/uninstall succeeds;
- no Phase 6 work is started automatically.

Until the remote connector contract and cleanup are complete, Phase 5 remains open.
