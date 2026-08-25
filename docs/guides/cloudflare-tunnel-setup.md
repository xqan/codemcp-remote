# Cloudflare Tunnel Setup for Phase 5.5.7

Status: **LIVE ACCEPTANCE GUIDE**

This guide covers the final `codemcp-remote` transport topology. Cloudflare provides HTTPS transport only. OAuth authorization is enforced by `codemcp-remote` through an independent compatible `mcp-auth-server`.

## Final topology

```text
ChatGPT
  |
  | OAuth access token
  v
https://<mcp-host>/mcp
  |
  | Cloudflare Tunnel
  v
http://127.0.0.1:46200/mcp
  |
  v
codemcp-remote OAuth Resource Server
  |
  | mcp-rs-verification-v1
  v
https://<auth-host>/mcp/resource-server/validate
```

Cloudflare Access identity headers are not an authorization input for the Bridge. The acceptance path must work without `Cf-Access-*` identity headers.

## Cloudflare setup

1. Create a remotely managed Cloudflare Tunnel in the user-owned Cloudflare account.
2. Add a public hostname for the dedicated MCP acceptance hostname.
3. Route the public MCP hostname to the local Bridge service on `http://127.0.0.1:46200`.
4. The externally configured MCP endpoint is `https://<mcp-host>/mcp`; do not rewrite or strip `/mcp`.
5. Do not put Cloudflare Access in front of this acceptance hostname as an authentication dependency. The independent OAuth server is the authorization authority.
6. Copy the remotely managed tunnel token once. Do not save it in repository files, TOML files, plaintext `.env` files, logs, screenshots, or acceptance records.

The bundled `cloudflared.exe` is pinned by the release and runs with fixed arguments. The clean-machine harness stores the token through Windows DPAPI and clears `TUNNEL_TOKEN` before the final doctor/start proof.

## Clean Windows acceptance

Use the accepted installer:

```text
.local\installer-dist\codemcp-remote-setup.exe
SHA-256: 7716e7bf7c5ceff536744f6342f1e7f6615eed770c7114c955a2bc70c33e6a93
```

In a fresh PowerShell process, provide secrets only through the process environment:

```powershell
$env:TUNNEL_TOKEN = '<cloudflare-remotely-managed-tunnel-token>'
$env:CODEMCP_RS_VERIFICATION_SECRET = '<resource-server-verification-secret>'

pwsh -NoLogo -NoProfile -File .\scripts\validate-clean-windows-release.ps1 `
  -Action Prepare `
  -InstallerPath .\.local\installer-dist\codemcp-remote-setup.exe `
  -ExpectedInstallerSha256 7716e7bf7c5ceff536744f6342f1e7f6615eed770c7114c955a2bc70c33e6a93 `
  -Transport cloudflare `
  -PublicUrl 'https://<mcp-host>/mcp' `
  -AuthorizationServerIssuer 'https://<auth-host>' `
  -CanonicalResourceUri 'https://<mcp-host>/mcp' `
  -ValidationResourceId '<resource-id>'
```

`Prepare` installs the release, verifies the installer hash, proves the isolated runtime does not depend on Python/uv/pwsh, initializes the Cloudflare transport and OAuth Resource Server configuration, stores both runtime secrets with DPAPI, creates the disposable `phase5-clean` project, and records the baseline Git HEAD without storing either secret.

Then start from DPAPI-backed state:

```powershell
pwsh -NoLogo -NoProfile -File .\scripts\validate-clean-windows-release.ps1 -Action Start
```

The `Start` action clears all supported transport/auth secret environment variables before doctor/start. It must report the Cloudflare provider, loopback origin, bundled `cloudflared`, DPAPI secret sources, healthy Bridge/tunnel processes, and the disposable project baseline.

Do not run `Cleanup` until the ChatGPT remote mutation/replay/restore and negative-auth evidence has been captured.
