# Operations Runbook

## Phase 0 local validation

From the repository root:

~~~text
uv sync --project bridge
uv run --project bridge codemcp-bridge doctor --json
uv run --project bridge pytest -q
~~~

The Phase 0 doctor should report:

- Python 3.12 or newer
- Git is installed
- the Bridge and project example configurations are valid
- the codemcp baseline is release 0.3.0 at the pinned commit
- model egress is denied
- codemcp is not required until Phase 1

## Current start policy

There is no production Bridge server or Tunnel startup script yet. Those are
implemented only after the local Adapter and policy tests pass.

Do not expose codemcp directly to ChatGPT. The intended future startup order
is Bridge, codemcp worker, tunnel-client, then ChatGPT tool discovery.

## Local state

Development state is kept under .local and is ignored by Git. Runtime secrets
must not be stored in the repository or example configuration files.
