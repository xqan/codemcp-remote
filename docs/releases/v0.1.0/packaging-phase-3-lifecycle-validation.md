# Packaging Phase 3 — Native EXE Lifecycle Validation

Date: 2026-08-24

## Objective

Replace the PowerShell-managed Bridge/Tunnel lifecycle with native `codemcp-remote.exe` lifecycle commands while preserving loopback-only networking, tunnel profile constraints, secret handling, health checks, logging protections, and safe process ownership.

## Implemented

- `codemcp-remote.exe` exposes `init`, `project add`, `start`, `status`, `stop`, and `doctor`.
- Bridge and Tunnel lifecycle orchestration is implemented in Python and runs from the packaged EXE without requiring PowerShell for normal operation.
- Writable runtime state lives outside the distribution under `%LOCALAPPDATA%\codemcp-remote` by default.
- `CONTROL_PLANE_API_KEY` is never written to TOML or env config; Windows DPAPI storage is supported.
- Tunnel profile validation requires an allowed OpenAI control-plane URL, `env:CONTROL_PLANE_API_KEY`, exactly one configured loopback Bridge MCP URL, and no stdio commands.
- Tunnel logs are redacted and rotated at 5 MiB with three backups.
- Lifecycle ownership uses recorded child PIDs plus Windows process-creation markers so a reused PID is never treated as owned.
- `project add` validates a temporary TOML configuration before atomically replacing `projects.toml`.
- `scripts/validate-windows-exe-lifecycle.ps1` performs rollback-safe migration from the legacy script-managed lifecycle to the EXE-managed lifecycle.

## Windows build validation

Command:

```powershell
pwsh -File .\scripts\build-windows-exe.ps1
```

Observed result on 2026-08-24:

- Phase 3 scoped Ruff format gate: PASS.
- Phase 3 lifecycle tests: PASS.
- PyInstaller 6.22.2 build: PASS.
- `codemcp-remote.exe 0.1.0`: PASS.
- Frozen Bridge `check`: PASS.
- Frozen worker mutation smoke: PASS.
- Frozen lifecycle `status` smoke: PASS (`status: stopped` in isolated lifecycle smoke root).
- Final build status: `ok`.
- Final smoke status: `passed`.
- EXE SHA-256: `2dbacbef5ef408925707926acc948653a5221f0eaee46b0dea7e8b4e71957284`.
- Checksum file: `.local\dist\codemcp-remote\SHA256SUMS.txt`.

## Remaining acceptance

Packaging Phase 3 is not closed until the live Windows lifecycle migration passes:

```powershell
pwsh -File .\scripts\validate-windows-exe-lifecycle.ps1
```

Expected result:

- frozen `doctor` passes before the legacy lifecycle is stopped;
- the legacy PowerShell-managed Bridge/Tunnel are stopped;
- `codemcp-remote.exe start` starts both services;
- `codemcp-remote.exe status` reports native lifecycle ownership and healthy Bridge/Tunnel endpoints;
- the validation script returns `phase: "3"`, `status: "ok"`, and `lifecycle: "native-exe"`;
- the native EXE-managed services remain running for connector verification.

If native startup fails after the legacy lifecycle has been stopped, the validation script attempts to restore the legacy lifecycle automatically.

Do not enter Packaging Phase 4 until this live migration and connector verification pass.
