# Phase 5.5.7 — mcp-auth-server + ChatGPT Live Interoperability Acceptance

Status: **IN PROGRESS — RFC 9728 repository fix READY; installed live binary STALE and ChatGPT proof pending**

Date: 2026-08-26

Repositories:

```text
codemcp-remote
  branch: codex/20260824
  repository-side acceptance code baseline before this record:
  f85010169fdd79a1ed0b298082a2015ff97d8e4c

mcp-auth-server
  version: 0.1.0
  current clean repository HEAD:
  b2372b61cf702874c6cae438ba504efe8bc0b4e6
  @cloudflare/workers-oauth-provider: 0.10.3
  live staging issuer:
  https://auth-staging.quickclip.cc

codemcp-remote public MCP resource:
  https://codemcp.quickclip.cc/mcp
```

The live staging issuer and Cloudflare MCP route are now assigned. The current `mcp-auth-server` repository is clean at the HEAD above, and its Phase 8 acceptance already records `https://auth-staging.quickclip.cc` as the live public issuer. The exact deployed Worker version/build corresponding to this acceptance still must be captured before final PASS; repository HEAD alone is not treated as proof of the deployed Worker version.

## Final architecture under acceptance

```text
ChatGPT
  |
  | OAuth Authorization Code + PKCE
  v
independent mcp-auth-server
  |
  | opaque access token
  v
https://<mcp-host>/mcp
  |
  | Cloudflare Tunnel only
  v
127.0.0.1:46200/mcp
  |
  | authenticated mcp-rs-verification-v1 online validation
  v
independent mcp-auth-server
```

Cloudflare Access identity assertions are not part of the authorization contract. The Bridge must accept or reject requests solely through its external OAuth Resource Server contract plus existing Bridge policy.

## Repository-side evidence

The Phase 5.5.7 clean Windows harness is now Cloudflare-first and preserves the OpenAI Tunnel only as an explicit compatibility option.

It proves or enforces before live ChatGPT testing:

- exact installer SHA verification;
- native local worker;
- isolated runtime without Python/uv/pwsh;
- Git available;
- bundled `cloudflared.exe`;
- loopback-only origin;
- Cloudflare tunnel token enters through process environment and is reloaded from Windows DPAPI;
- Resource Server verification secret enters through process environment and is reloaded from Windows DPAPI;
- canonical OAuth resource equals the public Cloudflare MCP URL;
- `mcp-rs-verification-v1`;
- no embedded `mcp-auth-server` runtime/private signing/user/client/refresh-token state;
- disposable `phase5-clean` repository with `README.md`, `PHASE5_ACCEPTANCE.txt`, and `pyproject.toml`, but no `codemcp.toml`;
- native PowerShell parser validity of the acceptance harness.

Current full regression after the harness upgrade:

```text
217 passed
6 skipped
0 failed
```

Accepted installer from Phase 5.5.6:

```text
codemcp-remote-setup.exe
SHA-256:
7716e7bf7c5ceff536744f6342f1e7f6615eed770c7114c955a2bc70c33e6a93
```

## 2026-08-26 LIVE discovery blocker and repository fix

Clean Windows `Prepare` and `Start` passed with the accepted installer above, and the live
Authorization Server metadata returned the expected issuer, authorization endpoint, token endpoint,
Authorization Code/refresh-token grants, PKCE S256, and client metadata document support. The next
public discovery checks found two Resource Server surface blockers:

```text
GET https://codemcp.quickclip.cc/.well-known/oauth-protected-resource/mcp
-> 404 Not Found

GET https://codemcp.quickclip.cc/mcp
-> 401 Unauthorized
-> WWW-Authenticate: Bearer
```

The `401` fail-closed decision was correct, but the RFC 9728 Protected Resource Metadata endpoint was
absent and the Bearer challenge did not provide its `resource_metadata` URL. ChatGPT OAuth discovery
was therefore paused before OAuth E2E.

The repository fix is now **READY**:

- the configured canonical resource path derives the RFC 9728 metadata location, including nested
  resource paths;
- the unauthenticated metadata route returns the exact configured resource, configured Authorization
  Server issuer, and `header` bearer method;
- missing/inactive bearer responses retain `401` plus `Cache-Control: no-store` and advertise the
  same derived metadata URL;
- `/healthz` remains outside the OAuth gate;
- Resource Server id, verification secret, bearer token, Cloudflare identity headers, and loopback
  origin are not authorization inputs or public metadata;
- `mcp-rs-verification-v1` online validation behavior is unchanged.

Repository validation is `219 passed / 6 skipped / 0 failed`. This is not LIVE proof. Installer
SHA-256 `7716e7bf7c5ceff536744f6342f1e7f6615eed770c7114c955a2bc70c33e6a93` predates the fix and is
**STALE / needs rebuild** for this acceptance. ChatGPT OAuth discovery remains blocked until a new
installer is built, hashed, installed through clean `Prepare`/`Start`, and both public curl checks are
repeated successfully.

## Client-policy correction from the historical spike

The older Cloudflare Access spike is not the final auth contract.

The current `mcp-auth-server` client trust profile used for final acceptance is:

```text
public client only
token_endpoint_auth_method = none
authorization_code
PKCE S256
CIMD enabled
static public clients supported
public DCR endpoint disabled
refresh-token rotation enabled
exact resource binding
```

Therefore final Phase 5.5.7 acceptance does not require successful public DCR. It must instead verify that ChatGPT interoperates with the actually frozen client strategy through CIMD or a pre-registered public client. If ChatGPT requires DCR and cannot operate without it, that is a live interoperability blocker and must not be hidden by weakening policy.

Meaningful custom OAuth scope-to-tool enforcement remains **NOT PROVEN** and is not part of the authorization claim.

## PASS / PENDING matrix

| Requirement | Result | Evidence / remaining work |
|---|---|---|
| Installer hash / packaging | PASS | Accepted SHA-256 recorded |
| Native local worker / isolated PATH | PASS | Clean harness + prior native packaging acceptance |
| Cloudflared bundled / fixed transport | PASS | Packaging and regression gates |
| Loopback-only Bridge origin | PASS | Provider + harness contract |
| Tunnel-token DPAPI boundary | PASS | Harness + provider regression |
| Resource Server secret DPAPI boundary | PASS | Harness + auth regression |
| No embedded auth-server private state | PASS | Harness fail-closed scan |
| `mcp-rs-verification-v1` consumer behavior | PASS | Resource Server regression suite |
| Wrong-resource / inactive / outage unit behavior | PASS | Resource Server security regression |
| Current full regression | PASS | 219 passed / 6 skipped / 0 failed after RFC 9728 repository fix |
| Real public Cloudflare hostname/tunnel | ASSIGNED / LIVE PROOF PENDING | `https://codemcp.quickclip.cc/mcp` |
| Real deployed auth issuer | LIVE ISSUER ASSIGNED | `https://auth-staging.quickclip.cc`; positive OAuth still pending |
| codemcp Resource Registry entry | PASS | resource_id `0a8721b3-8944-47a5-b1ce-7351963fcb71`; resource `https://codemcp.quickclip.cc/mcp` |
| Clean Windows Prepare | LIVE PASS | installer SHA `7716e7bf7c5ceff536744f6342f1e7f6615eed770c7114c955a2bc70c33e6a93`; project `phase5-clean`; baseline `87fca7ed129cd2493e6b872331873a4664077128`; worker `local`; tunnel/auth secrets recovered from `windows-dpapi`; isolated PATH excludes Python/uv/pwsh |
| Exact deployed auth-server commit/build | PARTIAL | Clean repo HEAD `b2372b61cf702874c6cae438ba504efe8bc0b4e6`; deployed Worker version still must be captured |
| ChatGPT OAuth discovery | BLOCKED — REPOSITORY FIX READY / LIVE BINARY STALE | RFC 9728 metadata/challenge fix requires a new installer and repeated public curl proof |
| CIMD/static-client interoperability | PENDING LIVE | Use current ChatGPT UI values |
| Authorization Code + PKCE | PENDING LIVE | Requires real identity/session |
| Refresh/session renewal | PENDING LIVE | Must preserve exact resource binding |
| Tool discovery | PENDING LIVE | ChatGPT connector |
| `project_open phase5-clean` | PENDING LIVE | ChatGPT connector |
| `development_ready == true` | PENDING LIVE | Disposable project |
| `file_read PHASE5_ACCEPTANCE.txt` | PENDING LIVE | Expected `phase5-clean-machine` |
| Remote mutation + checkpoint | PENDING LIVE | Disposable project only |
| Identical replay | PENDING LIVE | Must return original operation/checkpoint |
| Approval + checkpoint restore | PENDING LIVE | Canonical restore request hash |
| Final baseline HEAD + clean | PENDING LIVE | Must exactly match recorded baseline |
| Negative live credential without Git change | PENDING LIVE | Wrong-resource/invalid/revoked vector |
| Cloudflare identity headers unnecessary | PENDING LIVE | Authenticated MCP path must work without them |
| Cleanup/uninstall | PENDING LIVE | Run only after evidence capture |

## Live stop gate

Phase 5.5.7 must remain **IN PROGRESS** until all PENDING LIVE items above are evidenced.

Do not:

- substitute the `.invalid` staging issuer;
- enable development identity on a public domain;
- re-enable DCR just to make ChatGPT connect;
- put tunnel/auth credentials in source, docs, command-line arguments, or chat;
- use Cloudflare Access identity headers as the Bridge authorization truth;
- mark Phase 5.5 or `v0.1.0` packaging frozen before the complete remote mutation/replay/restore, negative-auth, refresh, and cleanup evidence exists.

After a real Cloudflare tunnel and real `mcp-auth-server` deployment are prepared, run the clean-machine `Prepare` and `Start` actions described in the two Phase 5.5.7 setup guides, then continue this record with the live ChatGPT evidence.
