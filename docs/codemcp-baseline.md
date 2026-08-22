# codemcp Phase 0 Baseline

## Pinned source

- Repository: https://github.com/ezyang/codemcp
- Release: 0.3.0
- Commit: 683e6ec29b15b91ec12430afabf5a45ed57d2489
- License reported by the repository: Apache-2.0

The release tag and commit must be rechecked locally in Phase 1 before the
adapter is implemented. The Bridge must not depend on the moving main branch.

## Intended use in this project

codemcp is used only as a downstream MCP execution component for file
operations, search, formatting, tests, and Git-related behavior. It is not
allowed to call a model and it is not directly exposed through Secure MCP
Tunnel.

## Phase 1 verification checklist

- MCP initialize and tools/list schema
- InitProject, LS, ReadFile, Grep, EditFile, WriteFile, Format
- codemcp.toml command behavior
- stdout, stderr, exit code, timeout, and process termination
- Git commit and amend behavior
- Windows native and WSL2 path behavior
- crash, restart, duplicate worker, and port collision behavior
