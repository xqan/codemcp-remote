# Phase 5 Validation

Date: 2026-08-22

## Implemented scope

Phase 5 adds the Windows local wrapper around OpenAI Secure MCP Tunnel:

- `scripts/start-bridge.ps1` starts the existing loopback Bridge;
- `scripts/start-tunnel.ps1` creates or runs a named HTTP MCP profile;
- `scripts/doctor.ps1` reports Bridge configuration, Bridge health, profile
  validity, tunnel-client doctor output, and tunnel `/healthz`/`/readyz`;
- `config/tunnel-profile.example.env` documents non-secret runtime settings;
- `docs/tunnel-setup.md` documents setup and operator recovery;
- `tests/e2e/test_tunnel_contract.md` defines the account-backed ChatGPT
  developer-mode acceptance contract.

The wrapper enforces the following local boundary before starting the client:

- OpenAI control plane only (`api.openai.com` or `mtls.api.openai.com`);
- `env:CONTROL_PLANE_API_KEY` instead of a plaintext profile key;
- exactly one HTTP MCP target at `http://127.0.0.1:46200/mcp`;
- no stdio target and no remote health/admin bind.

## Local validation performed

The installed `tunnel-client` reported version `0.0.11+8d55683eeef80bc5e360d95abf4692454fafc615`.
Its `help quickstart`, `init --help`, `doctor --help`, and `run --help` output
were checked against the wrapper flags and environment variable names.

The following checks passed:

```text
PowerShell parser: 4 scripts passed
tunnel-client init: generated an HTTP profile for the loopback Bridge
profile contract validation: passed
non-loopback MCP URL rejection: passed
non-loopback health/admin bind rejection: passed
example profile with placeholder tunnel_id: rejected as expected
doctor.ps1 -SkipTunnel: emitted structured diagnostics and correctly reported
  Bridge health as unavailable when Bridge was not running
```

The existing Bridge and codemcp test suites were run as the required
regression checks: the Bridge suite passed `24 passed, 1 skipped, 2 xfailed`,
and the fixed codemcp compatibility suite passed `4 passed, 2 xfailed`.

## Account-backed validation pending

The following acceptance criteria require external OpenAI Platform and
ChatGPT workspace state and were not claimed as locally verified:

- associating the tunnel with the target Platform organization and ChatGPT
  workspace;
- ChatGPT developer-mode tool discovery through Tunnel;
- remote read, edit, test, diff, checkpoint, and rollback calls;
- disconnect/restart checks across tunnel-client, Bridge, and worker.

Run [tests/e2e/test_tunnel_contract.md](../tests/e2e/test_tunnel_contract.md)
with a real `tunnel_id`, runtime API key, and workspace permission before
marking the full Phase 5 acceptance complete.
