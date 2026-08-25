from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import codemcp_bridge.lifecycle as lifecycle
import codemcp_bridge.main as main_module
import codemcp_bridge.transports.cloudflare as cloudflare
from codemcp_bridge.transports import (
    CLOUDFLARE_TUNNEL_PROVIDER,
    OPENAI_TUNNEL_PROVIDER,
    LifecycleError,
    TransportContext,
    get_transport_provider,
)


def _context(tmp_path: Path) -> TransportContext:
    runtime_root = tmp_path / "runtime"
    app_root = tmp_path / "app"
    config_dir = app_root / "config"
    log_dir = app_root / "logs"
    tunnel_dir = app_root / "tunnel"
    secret_dir = app_root / "secrets"
    for path in (runtime_root, app_root, config_dir, log_dir, tunnel_dir, secret_dir):
        path.mkdir(parents=True, exist_ok=True)
    return TransportContext(
        runtime_root=runtime_root,
        app_root=app_root,
        config_dir=config_dir,
        log_dir=log_dir,
        tunnel_dir=tunnel_dir,
        secret_file=secret_dir / "cloudflare-tunnel-token.dpapi",
        tunnel_env=config_dir / "cloudflare.env",
    )


def _settings(context: TransportContext):
    CLOUDFLARE_TUNNEL_PROVIDER.initialize_config(
        context,
        public_url="https://mcp.example.com/mcp",
        origin_url="http://127.0.0.1:46200/mcp",
        metrics_addr="127.0.0.1:46202",
    )
    return CLOUDFLARE_TUNNEL_PROVIDER.load_settings(context)


def test_transport_registry_contains_openai_and_cloudflare() -> None:
    assert get_transport_provider("openai-tunnel") is OPENAI_TUNNEL_PROVIDER
    assert get_transport_provider("cloudflare") is CLOUDFLARE_TUNNEL_PROVIDER
    with pytest.raises(LifecycleError, match="unsupported remote transport"):
        get_transport_provider("unknown")


def test_cloudflare_config_is_non_secret_and_fail_closed(tmp_path: Path) -> None:
    context = _context(tmp_path)
    settings = _settings(context)

    assert settings.public_url == "https://mcp.example.com/mcp"
    assert settings.origin_url == "http://127.0.0.1:46200/mcp"
    assert settings.metrics_addr == "127.0.0.1:46202"
    assert CLOUDFLARE_TUNNEL_PROVIDER.ready_url(settings) == "http://127.0.0.1:46202/ready"
    text = context.tunnel_env.read_text(encoding="utf-8")
    assert "TUNNEL_TOKEN" not in text

    with pytest.raises(LifecycleError, match="HTTPS /mcp"):
        CLOUDFLARE_TUNNEL_PROVIDER.initialize_config(
            context,
            public_url="http://mcp.example.com/mcp",
            force=True,
        )
    with pytest.raises(LifecycleError, match="127.0.0.1"):
        CLOUDFLARE_TUNNEL_PROVIDER.initialize_config(
            context,
            public_url="https://mcp.example.com/mcp",
            origin_url="http://192.168.1.10:46200/mcp",
            force=True,
        )
    with pytest.raises(LifecycleError, match="metrics address"):
        CLOUDFLARE_TUNNEL_PROVIDER.initialize_config(
            context,
            public_url="https://mcp.example.com/mcp",
            metrics_addr="0.0.0.0:46202",
            force=True,
        )


def test_cloudflare_config_rejects_plaintext_token(tmp_path: Path) -> None:
    context = _context(tmp_path)
    context.tunnel_env.write_text(
        "\n".join(
            [
                "CLOUDFLARE_PUBLIC_URL=https://mcp.example.com/mcp",
                "CLOUDFLARE_ORIGIN_URL=http://127.0.0.1:46200/mcp",
                "CLOUDFLARE_METRICS_ADDR=127.0.0.1:46202",
                "TUNNEL_TOKEN=must-not-be-here",
                "",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(LifecycleError, match="must never be stored"):
        CLOUDFLARE_TUNNEL_PROVIDER.load_settings(context)


def test_cloudflared_discovery_prefers_bundled_binary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context(tmp_path)
    bundled = context.runtime_root / "cloudflared.exe"
    bundled.write_bytes(b"placeholder")
    monkeypatch.setattr(cloudflare.shutil, "which", lambda _name: str(tmp_path / "other.exe"))

    assert CLOUDFLARE_TUNNEL_PROVIDER.find_client(context) == bundled.resolve()


@pytest.mark.skipif(os.name != "nt", reason="bundled Windows cloudflared pin is Windows-specific")
def test_bundled_cloudflared_sha256_mismatch_fails_closed(tmp_path: Path) -> None:
    context = _context(tmp_path)
    bundled = context.runtime_root / "cloudflared.exe"
    bundled.write_bytes(b"tampered-cloudflared")

    with pytest.raises(LifecycleError, match="SHA-256"):
        CLOUDFLARE_TUNNEL_PROVIDER.client_version(context)


def test_cloudflared_missing_and_bad_version_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context(tmp_path)
    monkeypatch.setattr(cloudflare.shutil, "which", lambda _name: None)
    with pytest.raises(LifecycleError, match="cloudflared was not found"):
        CLOUDFLARE_TUNNEL_PROVIDER.find_client(context)

    fake_client = tmp_path / "cloudflared.exe"
    monkeypatch.setattr(CLOUDFLARE_TUNNEL_PROVIDER, "find_client", lambda _context: fake_client)
    monkeypatch.setattr(
        cloudflare.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout="unexpected version output",
            stderr="",
        ),
    )
    with pytest.raises(LifecycleError, match="version output is not recognized"):
        CLOUDFLARE_TUNNEL_PROVIDER.client_version(context)


def test_cloudflared_run_uses_environment_token_and_fixed_argv(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context(tmp_path)
    settings = _settings(context)
    fake_client = tmp_path / "cloudflared.exe"
    captured: dict[str, object] = {}

    monkeypatch.setattr(CLOUDFLARE_TUNNEL_PROVIDER, "find_client", lambda _context: fake_client)
    monkeypatch.setattr(
        CLOUDFLARE_TUNNEL_PROVIDER,
        "client_version",
        lambda _context: "2026.8.0",
    )

    def fake_popen(args, **kwargs):
        captured["args"] = args
        captured["env"] = kwargs["env"]
        return SimpleNamespace(
            stdout=["TUNNEL_TOKEN=supersecret\n", "connected\n"],
            wait=lambda: 0,
        )

    monkeypatch.setattr(cloudflare.subprocess, "Popen", fake_popen)
    rotated: list[Path] = []

    result = CLOUDFLARE_TUNNEL_PROVIDER.run(
        context,
        settings,
        secret="supersecret",
        rotate_log=rotated.append,
    )

    assert result == 0
    assert captured["args"] == [
        str(fake_client),
        "tunnel",
        "--no-autoupdate",
        "--loglevel",
        "info",
        "--metrics",
        "127.0.0.1:46202",
        "run",
    ]
    assert "supersecret" not in " ".join(captured["args"])
    assert captured["env"]["TUNNEL_TOKEN"] == "supersecret"
    assert rotated == [context.log_dir / "cloudflared.log"]
    log_text = (context.log_dir / "cloudflared.log").read_text(encoding="utf-8")
    assert "supersecret" not in log_text
    assert "TUNNEL_TOKEN=<redacted>" in log_text


def test_cloudflare_doctor_reports_version_without_secret_value(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context(tmp_path)
    _settings(context)
    fake_client = tmp_path / "cloudflared.exe"
    monkeypatch.setattr(CLOUDFLARE_TUNNEL_PROVIDER, "find_client", lambda _context: fake_client)
    monkeypatch.setattr(
        CLOUDFLARE_TUNNEL_PROVIDER,
        "client_version",
        lambda _context: "2026.8.0",
    )

    checks = CLOUDFLARE_TUNNEL_PROVIDER.doctor(
        context,
        env_file=None,
        secret_available=True,
        secret_source="windows-dpapi",
    )

    assert checks["cloudflare_settings"]["status"] == "ok"
    assert checks["cloudflared"] == {
        "status": "ok",
        "path": str(fake_client),
        "version": "2026.8.0",
    }
    assert checks["tunnel_token"] == {
        "status": "ok",
        "source": "windows-dpapi",
    }


@pytest.mark.skipif(os.name != "nt", reason="Windows DPAPI acceptance runs on Windows")
def test_cloudflare_tunnel_token_uses_provider_specific_dpapi_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    paths = lifecycle.runtime_paths(runtime, app_root=tmp_path / "app")
    monkeypatch.setenv("TUNNEL_TOKEN", "phase55-cloudflare-secret")
    monkeypatch.setattr(lifecycle, "_dpapi_protect", lambda value: b"encrypted-token")
    monkeypatch.setattr(
        lifecycle,
        "_dpapi_unprotect",
        lambda value: b"phase55-cloudflare-secret",
    )

    assert lifecycle.store_transport_secret_from_environment(
        paths,
        provider=CLOUDFLARE_TUNNEL_PROVIDER,
    )
    secret_path = paths.secret_dir / "cloudflare-tunnel-token.dpapi"
    assert secret_path.read_bytes() == b"encrypted-token"
    assert not paths.secret_file.exists()

    monkeypatch.delenv("TUNNEL_TOKEN")
    assert (
        lifecycle._secret_from_runtime(
            paths,
            provider=CLOUDFLARE_TUNNEL_PROVIDER,
        )
        == "phase55-cloudflare-secret"
    )


def _lifecycle_paths(tmp_path: Path) -> lifecycle.RuntimePaths:
    runtime = tmp_path / "runtime"
    (runtime / "config").mkdir(parents=True)
    (runtime / "config" / "bridge.example.toml").write_text(
        "[storage]\n"
        'data_dir = ".local"\n'
        'sqlite_file = ".local/bridge.sqlite3"\n'
        'log_dir = ".local/logs"\n',
        encoding="utf-8",
    )
    return lifecycle.runtime_paths(runtime, app_root=tmp_path / "app")


def test_versioned_transport_config_selects_cloudflare_and_preserves_legacy_default(
    tmp_path: Path,
) -> None:
    paths = _lifecycle_paths(tmp_path)
    provider, source = lifecycle.load_transport_provider(paths)
    assert provider is OPENAI_TUNNEL_PROVIDER
    assert source == "legacy-default"

    result = lifecycle.initialize_runtime(
        paths,
        tunnel_id="",
        transport="cloudflare",
        public_url="https://mcp.example.com/mcp",
        origin_url="http://127.0.0.1:46200/mcp",
        metrics_addr="127.0.0.1:46202",
    )

    assert result["transport"] == "cloudflare"
    remote = (paths.config_dir / "remote.toml").read_text(encoding="utf-8")
    assert "version = 1" in remote
    assert 'transport = "cloudflare"' in remote
    assert "TUNNEL_TOKEN" not in paths.tunnel_env.read_text(encoding="utf-8")
    provider, source = lifecycle.load_transport_provider(paths)
    assert provider is CLOUDFLARE_TUNNEL_PROVIDER
    assert source == "config"
    status = lifecycle.status_services(paths)
    assert status["status"] == "stopped"
    assert status["transport"] == "cloudflare"
    assert status["transport_source"] == "config"

    with pytest.raises(LifecycleError, match="requires --force"):
        lifecycle.initialize_runtime(
            paths,
            tunnel_id="tunnel_12345678",
            transport="openai-tunnel",
        )


def test_cli_accepts_cloudflare_transport_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "codemcp-remote",
            "init",
            "--transport",
            "cloudflare",
            "--public-url",
            "https://mcp.example.com/mcp",
            "--origin-url",
            "http://127.0.0.1:46200/mcp",
            "--metrics-addr",
            "127.0.0.1:46202",
            "--store-transport-secret",
        ],
    )

    args = main_module._parse_args()

    assert args.transport == "cloudflare"
    assert args.public_url == "https://mcp.example.com/mcp"
    assert args.origin_url == "http://127.0.0.1:46200/mcp"
    assert args.metrics_addr == "127.0.0.1:46202"
    assert args.store_transport_secret is True
