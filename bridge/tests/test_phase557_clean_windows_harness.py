from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest


def _script() -> str:
    return (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "validate-clean-windows-release.ps1"
    ).read_text(encoding="utf-8")


def test_phase557_clean_windows_harness_is_cloudflare_first() -> None:
    script = _script()

    assert '[string]$Transport = "cloudflare"' in script
    assert '"--transport", "cloudflare"' in script
    assert '"--public-url", $PublicUrl' in script
    assert '"--origin-url", $OriginUrl' in script
    assert '"--metrics-addr", $MetricsAddr' in script
    assert '"--store-transport-secret"' in script
    assert '"--auth-mode", "oauth-resource-server"' in script
    assert '"--authorization-server-issuer", $AuthorizationServerIssuer' in script
    assert '"--canonical-resource-uri", $CanonicalResourceUri' in script
    assert '"--validation-resource-id", $ValidationResourceId' in script
    assert '"--store-auth-secret"' in script


def test_phase557_secrets_are_environment_only_and_rechecked_from_dpapi() -> None:
    script = _script()

    assert "$env:TUNNEL_TOKEN" in script
    assert "$env:CODEMCP_RS_VERIFICATION_SECRET" in script
    assert "never pass the secret on the command line" in script
    assert "-TunnelToken" not in script
    assert "-VerificationSecret" not in script
    assert "$env:TUNNEL_TOKEN = $null" in script
    assert "$env:CODEMCP_RS_VERIFICATION_SECRET = $null" in script
    assert '$Doctor.checks.tunnel_token.source -ne "windows-dpapi"' in script
    assert '$Doctor.checks.auth.secret_source -ne "windows-dpapi"' in script


def test_phase557_local_contract_requires_cloudflared_loopback_and_external_auth() -> None:
    script = _script()

    assert 'Join-Path $release.install_dir "cloudflared.exe"' in script
    assert '"http://127.0.0.1:46200/mcp"' in script
    assert '"mcp-rs-verification-v1"' in script
    assert "Assert-NoEmbeddedAuthServerState" in script
    assert '"*mcp-auth-server*"' in script
    assert "OAuth canonical resource does not match the Cloudflare public MCP URL" in script
    assert 'phase = "5.5.7"' in script


def test_phase557_disposable_project_has_profile_marker_but_no_codemcp_config() -> None:
    script = _script()

    assert '"README.md"' in script
    assert '"pyproject.toml"' in script
    assert '"PHASE5_ACCEPTANCE.txt"' in script
    assert 'name = "codemcp-remote-phase5-acceptance"' in script
    assert 'add README.md pyproject.toml PHASE5_ACCEPTANCE.txt' in script
    assert 'Join-Path $Root "codemcp.toml"' not in script


def test_phase557_retains_explicit_openai_transport_compatibility() -> None:
    script = _script()

    assert '[ValidateSet("cloudflare", "openai-tunnel")]' in script
    assert '$Transport -eq "cloudflare"' in script
    assert '"--transport", "openai-tunnel"' in script
    assert '"--tunnel-id", $TunnelId' in script
    assert '"--store-api-key"' in script


@pytest.mark.skipif(os.name != "nt", reason="PowerShell parser check runs on native Windows")
def test_phase557_clean_windows_harness_parses_as_powershell() -> None:
    powershell = shutil.which("pwsh.exe") or shutil.which("pwsh")
    if powershell is None:
        pytest.skip("PowerShell 7 is unavailable")

    script_path = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "validate-clean-windows-release.ps1"
    )
    escaped_script_path = str(script_path).replace("'", "''")
    parser_command = (
        f"$path='{escaped_script_path}'; "
        "$tokens=$null; $errors=$null; "
        "[System.Management.Automation.Language.Parser]::ParseFile("
        "$path,[ref]$tokens,[ref]$errors) | Out-Null; "
        "if ($errors.Count -gt 0) { "
        "$errors | ForEach-Object { Write-Error $_.Message }; exit 1 }"
    )
    completed = subprocess.run(
        [
            powershell,
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            parser_command,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )

    assert completed.returncode == 0, completed.stderr or completed.stdout
