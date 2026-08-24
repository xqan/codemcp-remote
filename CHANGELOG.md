# Changelog

All notable public changes to codemcp-remote will be documented here.

The project is currently pre-release. Version `v0.1.0` must not be published until the release gates in `docs/acceptance-test-plan.md` and `docs/open-source-readiness-plan.md` pass.

## [Unreleased]

### Added

- AGPL-3.0-only project licensing.
- Security policy, security model, and threat model.
- Open-source readiness baseline and release acceptance plan.
- Windows lifecycle validation runner.
- WSL2 worker bootstrap script.
- Public-facing README onboarding flow.
- GitHub governance, CI, issue templates, pull-request template, and Dependabot configuration.

### Changed

- Package metadata now identifies the project license as AGPL-3.0-only.
- README status is explicitly pre-release and separates CI checks from real Windows 11 + WSL2 + Tunnel release gates.

### Known limitations

- Git-backed mutation is supported through WSL2, not native Windows codemcp.
- Secure MCP Tunnel availability depends on the user's OpenAI/ChatGPT workspace capabilities.
- The Bridge is single-operator local policy infrastructure, not a multi-user authorization service.
- Arbitrary shell, automatic push/merge/deploy, and model calls inside the Bridge are intentionally unavailable.

## Release policy

Each stable release should include:

- a dated changelog entry;
- known limitations;
- the validated commit;
- release artifacts and `SHA256SUMS.txt`;
- confirmation that P0 security and acceptance blockers are closed.
