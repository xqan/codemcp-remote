from __future__ import annotations

import json
import os
import tomllib
from pathlib import Path
from types import SimpleNamespace

import pytest

import codemcp_bridge.lifecycle as lifecycle
from codemcp_bridge.lifecycle import (
    LifecycleError,
    TunnelSettings,
    add_project,
    initialize_runtime,
    load_tunnel_settings,
    redact_log_text,
    runtime_paths,
    start_services,
    stop_services,
    validate_tunnel_profile,
)


def _bridge_template() -> str:
    return """\
[server]
host = "127.0.0.1"
port = 46200
path = "/mcp"
transport = "streamable-http"

[storage]
data_dir = ".local"
sqlite_file = ".local/bridge.sqlite3"
log_dir = ".local/logs"

[policy]
allow_arbitrary_paths = false
allow_arbitrary_commands = false
allow_model_calls = false
require_clean_workspace = true
max_file_bytes = 1048576
max_result_bytes = 262144
mutation_lock = "per-project"

[codemcp]
worker_mode = "local"
wsl_distribution = "Ubuntu"
wsl_python = ""
startup_timeout_seconds = 30
worker_timeout_seconds = 60
shutdown_timeout_seconds = 5
"""


def _runtime(tmp_path: Path) -> tuple[Path, lifecycle.RuntimePaths]:
    runtime = tmp_path / "runtime"
    (runtime / "config").mkdir(parents=True)
    (runtime / "config" / "bridge.example.toml").write_text(_bridge_template(), encoding="utf-8")
    paths = runtime_paths(runtime, app_root=tmp_path / "app")
    return runtime, paths


def test_initialize_runtime_moves_writable_state_out_of_distribution(tmp_path: Path) -> None:
    _, paths = _runtime(tmp_path)

    result = initialize_runtime(paths, tunnel_id="tunnel_12345678")

    assert result["status"] == "ok"
    bridge = tomllib.loads(paths.bridge_config.read_text(encoding="utf-8"))
    assert bridge["storage"]["data_dir"] == str(paths.data_dir)
    assert bridge["storage"]["log_dir"] == str(paths.log_dir)
    env = paths.tunnel_env.read_text(encoding="utf-8")
    assert "CONTROL_PLANE_TUNNEL_ID=tunnel_12345678" in env
    assert "CONTROL_PLANE_API_KEY" not in env
    assert paths.projects_config.read_text(encoding="utf-8") == "# Managed by codemcp-remote\n"


def test_tunnel_env_rejects_plaintext_secret_and_resolves_relative_profile_dir(
    tmp_path: Path,
) -> None:
    _, paths = _runtime(tmp_path)
    env_file = tmp_path / "legacy" / "config" / "tunnel.env"
    env_file.parent.mkdir(parents=True)
    env_file.write_text(
        "\n".join(
            [
                "CONTROL_PLANE_TUNNEL_ID=tunnel_12345678",
                "TUNNEL_CLIENT_PROFILE_DIR=.local/tunnel-client",
                "",
            ]
        ),
        encoding="utf-8",
    )

    settings = load_tunnel_settings(paths, env_file=env_file)

    assert settings.profile_dir == (env_file.parent.parent / ".local/tunnel-client").resolve()

    env_file.write_text(
        "CONTROL_PLANE_TUNNEL_ID=tunnel_12345678\nCONTROL_PLANE_API_KEY=secret\n",
        encoding="utf-8",
    )
    with pytest.raises(LifecycleError, match="must never be stored"):
        load_tunnel_settings(paths, env_file=env_file)


def test_add_project_validates_then_atomically_replaces_config(tmp_path: Path) -> None:
    _, paths = _runtime(tmp_path)
    initialize_runtime(paths, tunnel_id="tunnel_12345678")
    project = tmp_path / "demo project"
    project.mkdir()
    (project / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")

    result = add_project(paths, project_id="demo", root=project)

    assert result["project_id"] == "demo"
    text = paths.projects_config.read_text(encoding="utf-8")
    assert "[projects.demo]" in text
    assert str(project.resolve()).replace("\\", "\\\\") in text
    assert not paths.projects_config.with_suffix(".toml.tmp").exists()

    with pytest.raises(LifecycleError, match="already exists"):
        add_project(paths, project_id="demo", root=project)


def test_validate_tunnel_profile_enforces_openai_http_contract(tmp_path: Path) -> None:
    profile_dir = tmp_path / "profiles"
    profile_dir.mkdir()
    settings = TunnelSettings(
        tunnel_id="tunnel_12345678",
        profile_name="codemcp-bridge",
        profile_dir=profile_dir,
        bridge_url="http://127.0.0.1:46200/mcp",
        tunnel_health_url="http://127.0.0.1:46201",
        health_listen_addr="127.0.0.1:46201",
        env_file=tmp_path / "tunnel.env",
    )
    profile = profile_dir / "codemcp-bridge.yaml"
    profile.write_text(
        """\
tunnel_id: tunnel_12345678
control_plane:
  base_url: https://api.openai.com
  api_key: env:CONTROL_PLANE_API_KEY
server_urls:
  - url: http://127.0.0.1:46200/mcp
""",
        encoding="utf-8",
    )

    assert validate_tunnel_profile(settings) == profile

    profile.write_text(
        profile.read_text(encoding="utf-8").replace(
            "env:CONTROL_PLANE_API_KEY", "sk-plaintext-not-allowed"
        ),
        encoding="utf-8",
    )
    with pytest.raises(LifecycleError, match="env:CONTROL_PLANE_API_KEY"):
        validate_tunnel_profile(settings)


def test_redact_log_text_removes_common_secret_forms() -> None:
    text = "Authorization=secret Bearer abc.def CONTROL_PLANE_API_KEY=topsecret sk-1234567890abcdef"
    redacted = redact_log_text(text)

    assert "topsecret" not in redacted
    assert "abc.def" not in redacted
    assert "sk-1234567890abcdef" not in redacted


def test_start_services_records_only_owned_child_processes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, paths = _runtime(tmp_path)
    initialize_runtime(paths, tunnel_id="tunnel_12345678")
    settings = load_tunnel_settings(paths)
    settings.profile_dir.mkdir(parents=True, exist_ok=True)
    (settings.profile_dir / "codemcp-bridge.yaml").write_text(
        """\
tunnel_id: tunnel_12345678
control_plane:
  base_url: https://api.openai.com
  api_key: env:CONTROL_PLANE_API_KEY
server_urls:
  - url: http://127.0.0.1:46200/mcp
""",
        encoding="utf-8",
    )

    processes: list[SimpleNamespace] = []

    def fake_popen(args, *, cwd, log_path, env):
        process = SimpleNamespace(
            pid=100 + len(processes),
            args=args,
            poll=lambda: None,
        )
        processes.append(process)
        return process

    monkeypatch.setattr(lifecycle, "_popen_background", fake_popen)
    monkeypatch.setattr(
        lifecycle,
        "_wait_endpoint",
        lambda url, process, timeout: {"status": "ok", "status_code": 200, "url": url},
    )
    monkeypatch.setattr(
        lifecycle,
        "_http_check",
        lambda url, timeout=2.0: {"status": "unreachable", "url": url},
    )
    monkeypatch.setattr(lifecycle, "_secret_from_runtime", lambda runtime: "secret")
    monkeypatch.setattr(lifecycle, "_process_marker", lambda pid: f"marker-{pid}")

    result = start_services(paths)

    assert result["status"] == "ok"
    state = json.loads(paths.state_file.read_text(encoding="utf-8"))
    assert state["bridge_process_marker"] == "marker-100"
    assert state["tunnel_process_marker"] == "marker-101"
    assert processes[1].args[-2:] == ["--app-root", str(paths.app_root)]


def test_stop_services_never_kills_a_reused_pid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, paths = _runtime(tmp_path)
    paths.run_dir.mkdir(parents=True)
    paths.state_file.write_text(
        json.dumps(
            {
                "bridge_pid": 123,
                "tunnel_pid": 456,
                "bridge_process_marker": "old-a",
                "tunnel_process_marker": "old-b",
            }
        ),
        encoding="utf-8",
    )
    killed: list[int] = []
    monkeypatch.setattr(lifecycle, "_matches_process_marker", lambda pid, marker: False)
    monkeypatch.setattr(lifecycle, "_terminate_tree", killed.append)

    result = stop_services(paths)

    assert killed == []
    assert [item["status"] for item in result["actions"]] == ["not_owned", "not_owned"]
    assert not paths.state_file.exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows DPAPI acceptance runs on Windows")
def test_windows_dpapi_round_trip() -> None:
    payload = b"phase3-dpapi-secret"

    protected = lifecycle._dpapi_protect(payload)

    assert protected != payload
    assert lifecycle._dpapi_unprotect(protected) == payload


def test_rotate_log_keeps_bounded_backups(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    log = tmp_path / "tunnel-client.log"
    log.write_text("current", encoding="utf-8")
    log.with_name(f"{log.name}.1").write_text("one", encoding="utf-8")
    log.with_name(f"{log.name}.2").write_text("two", encoding="utf-8")
    monkeypatch.setattr(lifecycle, "_LOG_MAX_BYTES", 1)

    lifecycle._rotate_log(log)

    assert not log.exists()
    assert log.with_name(f"{log.name}.1").read_text(encoding="utf-8") == "current"
    assert log.with_name(f"{log.name}.2").read_text(encoding="utf-8") == "one"
    assert log.with_name(f"{log.name}.3").read_text(encoding="utf-8") == "two"
