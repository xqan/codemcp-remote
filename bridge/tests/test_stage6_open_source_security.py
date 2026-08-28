from __future__ import annotations

from pathlib import Path

from codemcp_bridge.project_profiles import get_builtin_profile

GITLEAKS_VERSION = "8.30.0"
GITLEAKS_WINDOWS_X64_SHA256 = "54fe94f644b832dd08e8c3a5915efb3bfa862386d59fb27ca0792cb687a83573"
GITLEAKS_LINUX_X64_SHA256 = "79a3ab579b53f71efd634f3aaf7e04a0fa0cf206b7ed434638d1547a2470a66e"


def _root() -> Path:
    return Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (_root() / path).read_text(encoding="utf-8")


def test_local_stage6_audit_uses_pinned_gitleaks_and_locked_uv_audit() -> None:
    prepare = _read("scripts/prepare-gitleaks.ps1")
    audit = _read("scripts/validate-open-source-security.ps1")

    assert GITLEAKS_VERSION in prepare
    assert GITLEAKS_WINDOWS_X64_SHA256 in prepare
    assert "Gitleaks archive checksum mismatch" in prepare
    assert "uv.Source audit --project" in audit
    assert "--frozen" in audit
    assert "gitleaks git" not in audit
    assert "& $gitleaks git" in audit
    assert "& $gitleaks dir" in audit
    assert "--redact=100" in audit
    assert "--log-opts=--all" in audit
    assert "git archive" in audit
    assert "projects.toml" in audit
    assert "*.dpapi" in audit
    assert "*.sqlite3*" in audit
    assert "operator-specific deployment/path data" in audit
    assert ".local\\release-candidate\\codemcp-remote-v0.1.0-windows-x64.zip" in audit


def test_codemcp_remote_profile_exposes_fixed_security_audits_only() -> None:
    profile = get_builtin_profile("codemcp-remote")
    assert profile is not None

    source_command = profile.commands["security-audit"]
    assert source_command.kind == "verify"
    assert source_command.approval == "not-required"
    assert source_command.argv == (
        "pwsh",
        "-NoLogo",
        "-NoProfile",
        "-NonInteractive",
        "-File",
        "scripts/validate-open-source-security.ps1",
    )

    artifact_command = profile.commands["artifact-audit"]
    assert artifact_command.kind == "verify"
    assert artifact_command.approval == "not-required"
    assert artifact_command.argv == (
        "pwsh",
        "-NoLogo",
        "-NoProfile",
        "-NonInteractive",
        "-File",
        "scripts/validate-open-source-security.ps1",
        "-RequireArtifact",
    )


def test_ci_has_dependency_current_tree_and_full_history_security_gates() -> None:
    workflow = _read(".github/workflows/ci.yml")

    assert "security:" in workflow
    assert "fetch-depth: 0" in workflow
    assert "uv audit --project bridge --frozen" in workflow
    assert f'GITLEAKS_VERSION: "{GITLEAKS_VERSION}"' in workflow
    assert f'GITLEAKS_SHA256: "{GITLEAKS_LINUX_X64_SHA256}"' in workflow
    assert "gitleaks dir --redact=100 --no-banner" in workflow
    assert "gitleaks git --redact=100 --no-banner" in workflow
    assert "--log-opts=--all ." in workflow
