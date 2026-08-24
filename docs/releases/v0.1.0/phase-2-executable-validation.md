# Phase 2 — Windows EXE Validation

## Objective

Package the Bridge and native Windows codemcp worker as a PyInstaller one-dir executable that does not require `uv run` or a Python interpreter at runtime.

## Implemented

- `codemcp-remote.exe` has a normal Bridge entrypoint and an internal `_worker` stdio entrypoint.
- Frozen runtime configuration resolves relative to the executable directory.
- Native worker self-spawn uses the frozen executable instead of `python -m`.
- The native compatibility layer still applies the Windows stdin and newline fixes required by `codemcp==0.3.0`.
- `--version` reports the packaged Bridge version.
- `scripts/build-windows-exe.ps1` pins PyInstaller `6.22.2`, builds one-dir output, copies default config and `LICENSE`, calculates the executable SHA-256, and writes `SHA256SUMS.txt`.
- The build gate runs the frozen executable's default `check`.
- The build gate starts the frozen `_worker` over MCP stdio and validates `InitProject -> ReadFile -> EditFile` against an isolated Git repository whose path contains Chinese characters and spaces. The fixture must finish with a clean Git worktree.

## Build and acceptance command

Run from the repository root on Windows:

```powershell
pwsh -File .\scripts\build-windows-exe.ps1
```

Expected acceptance signals:

- `codemcp-remote.exe 0.1.0`
- frozen `check` exits with code `0`
- `frozen worker smoke: PASS`
- final JSON contains `"status": "ok"` and `"smoke": "passed"`
- output directory: `.local\dist\codemcp-remote`
- `.local\dist\codemcp-remote\codemcp-remote.exe` exists
- `.local\dist\codemcp-remote\SHA256SUMS.txt` exists and matches the reported `sha256`

## Current validation state

The Phase 2 Python changes are no longer reported by the repository-wide Ruff format gate. That gate still reports five pre-existing files outside the Phase 2 change set.

The Windows build command itself must be executed on the local Windows host. Remote execution of the registered full test/build workflow was blocked by the platform safety layer, so Phase 2 must not be marked complete until the command above returns the acceptance signals.

Do not enter Phase 3 until this host acceptance passes.
