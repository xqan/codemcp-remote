# Changelog

All notable public changes to codemcp-remote will be documented here.

The project is currently pre-release. Version `v0.1.0` must not be published until the release gates in `docs/acceptance/acceptance-test-plan.md` and `docs/plans/v0.1.0/open-source-readiness-plan.md` pass.

## [Unreleased]

### Added

- AGPL-3.0-only project licensing.
- Security policy, security model, and threat model.
- Open-source readiness baseline and release acceptance plan.
- Windows lifecycle validation runner.
- WSL2 worker bootstrap script.
- Public-facing README onboarding flow.
- GitHub governance, CI, issue templates, pull-request template, and Dependabot configuration.
- End-to-end Windows build/install/use guide.
- One-click `codemcp-start.cmd` and `codemcp-stop.cmd` lifecycle launchers in the packaged Windows payload.

### Changed

- Package metadata now identifies the project license as AGPL-3.0-only.
- README status is explicitly pre-release and separates completed private network-trust acceptance from the broader stable release gates.
- A packaged `codemcp-remote.exe` launched without a command now starts the managed lifecycle.
- The packaged EXE directory is the default runtime home unless `--home` or `CODEMCP_HOME` overrides it.

### Known limitations

- Native Windows local mutation is the default packaged worker and requires Git for Windows; WSL2 remains an optional source-mode compatibility fallback.
- ChatGPT Connector availability depends on the capabilities enabled for the user's OpenAI/ChatGPT account or workspace.
- The Bridge is single-operator local policy infrastructure, not a multi-user authorization service.
- Arbitrary shell, automatic push/merge/deploy, and model calls inside the Bridge are intentionally unavailable.

## Release policy

Each stable release should include:

- a dated changelog entry;
- known limitations;
- the validated commit;
- release artifacts and `SHA256SUMS.txt`;
- confirmation that P0 security and acceptance blockers are closed.
