from __future__ import annotations

from pathlib import Path

from codemcp_bridge.transports.cloudflare import (
    BUNDLED_WINDOWS_AMD64_SHA256,
    BUNDLED_WINDOWS_AMD64_VERSION,
)

EXPECTED_CLOUDFLARED_VERSION = "2026.7.3"
EXPECTED_CLOUDFLARED_SHA256 = (
    "8635da433b6df8194746e88ed9d2589566c20e38bfc2a80e431a348b7c765841"
)


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _script(name: str) -> str:
    return (_repository_root() / "scripts" / name).read_text(encoding="utf-8")


def test_cloudflared_packaging_pin_matches_runtime_provider() -> None:
    script = _script("prepare-cloudflared.ps1")

    assert BUNDLED_WINDOWS_AMD64_VERSION == EXPECTED_CLOUDFLARED_VERSION
    assert BUNDLED_WINDOWS_AMD64_SHA256 == EXPECTED_CLOUDFLARED_SHA256
    assert f'"{EXPECTED_CLOUDFLARED_VERSION}" = "{EXPECTED_CLOUDFLARED_SHA256}"' in script
    assert "cloudflared-windows-amd64.exe" in script
    assert "cloudflare/cloudflared/releases/download" in script
    assert 'Join-Path $DestinationDir "cloudflared.exe"' in script
    assert "THIRD_PARTY\\cloudflared" in script
    assert "Apache License 2.0" in script


def test_provider_neutral_packaging_stages_both_remote_transports() -> None:
    script = _script("prepare-remote-transport.ps1")

    assert "prepare-cloudflared.ps1" in script
    assert "prepare-tunnel-client.ps1" in script
    assert 'recommended_provider = "cloudflare"' in script
    assert "THIRD_PARTY\\cloudflared\\LICENSE" in script
    assert "THIRD_PARTY\\tunnel-client\\LICENSE" in script
    assert "THIRD_PARTY_NOTICES.txt" in script


def test_installer_build_rejects_secrets_and_smokes_upgrade_preservation() -> None:
    script = _script("build-windows-installer.ps1")

    assert "prepare-remote-transport.ps1" in script
    assert '"*.dpapi"' in script
    assert 'Join-Path $appDir "config\\remote.toml"' in script
    assert 'Join-Path $appDir "config\\tunnel.env"' in script
    assert 'Join-Path $installedLocation "cloudflared.exe"' in script
    assert "installed cloudflared checksum differs from the verified staging payload" in script
    assert "silent installer upgrade smoke failed" in script
    assert "installer upgrade removed user runtime data" in script
    assert "silent uninstall removed user runtime data" in script


def test_release_manifest_is_cloudflare_first_and_external_auth_is_not_bundled() -> None:
    script = _script("prepare-windows-release-candidate.ps1")

    assert 'recommended_transport = "cloudflare"' in script
    assert 'executable = "cloudflared.exe"' in script
    assert f'version = "{EXPECTED_CLOUDFLARED_VERSION}"' in script
    assert f'sha256 = "{EXPECTED_CLOUDFLARED_SHA256}"' in script
    assert "compatible external mcp-auth-server deployment implementing mcp-rs-verification-v1" in script
    assert "local or bundled mcp-auth-server runtime" in script


def test_inno_uninstall_does_not_target_user_runtime_data() -> None:
    script = _script("codemcp-remote.iss")

    assert "[UninstallDelete]" not in script
    assert 'Source: "{#SourceDir}\\*"; DestDir: "{app}"' in script
    assert "codemcp-remote.exe\"; Parameters: \"stop\"" in script
