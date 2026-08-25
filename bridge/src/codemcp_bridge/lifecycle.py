"""Native Windows lifecycle, configuration, and tunnel orchestration."""

from __future__ import annotations

import ctypes
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .settings import PROJECT_ID_PATTERN, SettingsError, load_settings
from .transports import (
    LifecycleError,
    OPENAI_TUNNEL_PROVIDER,
    OpenAITunnelSettings,
    RemoteTransportProvider,
    TransportContext,
)
from .transports.openai_tunnel import (
    DEFAULT_BRIDGE_URL,
    DEFAULT_HEALTH_LISTEN_ADDR,
    DEFAULT_PROFILE,
    DEFAULT_TUNNEL_HEALTH_URL,
)

APP_NAME = "codemcp-remote"
TunnelSettings = OpenAITunnelSettings
_REMOTE_TRANSPORT = OPENAI_TUNNEL_PROVIDER
_SECRET_NAME = _REMOTE_TRANSPORT.secret_env_name
_LOG_MAX_BYTES = 5 * 1024 * 1024
_LOG_BACKUP_COUNT = 3


@dataclass(frozen=True, slots=True)
class RuntimePaths:
    runtime_root: Path
    app_root: Path
    config_dir: Path
    data_dir: Path
    log_dir: Path
    run_dir: Path
    tunnel_dir: Path
    secret_dir: Path
    bridge_config: Path
    projects_config: Path
    tunnel_env: Path
    state_file: Path
    secret_file: Path


def app_data_root(*, environ: dict[str, str] | None = None, home: Path | None = None) -> Path:
    env = os.environ if environ is None else environ
    local_appdata = env.get("LOCALAPPDATA")
    if local_appdata:
        return Path(local_appdata).expanduser().resolve(strict=False) / APP_NAME
    base = Path.home() if home is None else home
    return base.resolve(strict=False) / f".{APP_NAME}"


def runtime_paths(runtime_root: Path, *, app_root: Path | None = None) -> RuntimePaths:
    runtime = runtime_root.resolve(strict=False)
    root = app_data_root() if app_root is None else app_root.resolve(strict=False)
    config_dir = root / "config"
    data_dir = root / "data"
    log_dir = root / "logs"
    run_dir = root / "run"
    tunnel_dir = root / "tunnel"
    secret_dir = root / "secrets"
    return RuntimePaths(
        runtime_root=runtime,
        app_root=root,
        config_dir=config_dir,
        data_dir=data_dir,
        log_dir=log_dir,
        run_dir=run_dir,
        tunnel_dir=tunnel_dir,
        secret_dir=secret_dir,
        bridge_config=config_dir / "bridge.toml",
        projects_config=config_dir / "projects.toml",
        tunnel_env=config_dir / "tunnel.env",
        state_file=run_dir / "state.json",
        secret_file=secret_dir / "control-plane-api-key.dpapi",
    )


def _transport_context(paths: RuntimePaths) -> TransportContext:
    return TransportContext(
        runtime_root=paths.runtime_root,
        app_root=paths.app_root,
        config_dir=paths.config_dir,
        log_dir=paths.log_dir,
        tunnel_dir=paths.tunnel_dir,
        secret_file=paths.secret_file,
        tunnel_env=paths.tunnel_env,
    )


def ensure_runtime_dirs(paths: RuntimePaths) -> None:
    for path in (
        paths.config_dir,
        paths.data_dir,
        paths.log_dir,
        paths.run_dir,
        paths.tunnel_dir,
        paths.secret_dir,
    ):
        path.mkdir(parents=True, exist_ok=True)


def _toml_quote(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _rewrite_bridge_storage(template: str, paths: RuntimePaths) -> str:
    replacements = {
        r'(?m)^data_dir\s*=\s*["\'][^"\']*["\']\s*$': (
            f"data_dir = {_toml_quote(str(paths.data_dir))}"
        ),
        r'(?m)^sqlite_file\s*=\s*["\'][^"\']*["\']\s*$': (
            f"sqlite_file = {_toml_quote(str(paths.data_dir / 'bridge.sqlite3'))}"
        ),
        r'(?m)^log_dir\s*=\s*["\'][^"\']*["\']\s*$': f"log_dir = {_toml_quote(str(paths.log_dir))}",
    }
    updated = template
    for pattern, replacement in replacements.items():
        updated = re.sub(pattern, lambda _match, value=replacement: value, updated)
    return updated


def initialize_runtime(
    paths: RuntimePaths,
    *,
    tunnel_id: str,
    profile_name: str = DEFAULT_PROFILE,
    bridge_url: str = DEFAULT_BRIDGE_URL,
    tunnel_health_url: str = DEFAULT_TUNNEL_HEALTH_URL,
    health_listen_addr: str = DEFAULT_HEALTH_LISTEN_ADDR,
    force: bool = False,
) -> dict[str, Any]:
    ensure_runtime_dirs(paths)

    template = paths.runtime_root / "config" / "bridge.example.toml"
    if not template.is_file():
        raise LifecycleError(f"bridge template not found: {template}")

    created: list[str] = []
    if force or not paths.bridge_config.exists():
        bridge_text = _rewrite_bridge_storage(template.read_text(encoding="utf-8"), paths)
        paths.bridge_config.write_text(bridge_text, encoding="utf-8")
        created.append(str(paths.bridge_config))

    if force or not paths.projects_config.exists():
        paths.projects_config.write_text("# Managed by codemcp-remote\n", encoding="utf-8")
        created.append(str(paths.projects_config))

    created.extend(
        _REMOTE_TRANSPORT.initialize_config(
            _transport_context(paths),
            tunnel_id=tunnel_id,
            profile_name=profile_name,
            bridge_url=bridge_url,
            tunnel_health_url=tunnel_health_url,
            health_listen_addr=health_listen_addr,
            force=force,
        )
    )

    return {"status": "ok", "app_root": str(paths.app_root), "created": created}


def add_project(paths: RuntimePaths, *, project_id: str, root: Path) -> dict[str, Any]:
    if not PROJECT_ID_PATTERN.fullmatch(project_id):
        raise LifecycleError("project id must contain only letters, digits, '.', '_' or '-'")
    project_root = root.expanduser().resolve(strict=False)
    if not project_root.is_dir():
        raise LifecycleError(f"project root is not a directory: {project_root}")
    if not paths.projects_config.is_file():
        raise LifecycleError("projects.toml is missing; run 'codemcp-remote init' first")

    import tomllib

    raw = paths.projects_config.read_text(encoding="utf-8")
    try:
        parsed = tomllib.loads(raw)
    except tomllib.TOMLDecodeError as exc:
        raise LifecycleError(f"projects.toml is invalid: {exc}") from exc
    projects = parsed.get("projects", {})
    if isinstance(projects, dict) and project_id in projects:
        raise LifecycleError(f"project already exists: {project_id}")

    entry = (
        f"\n[projects.{project_id}]\n"
        f"root = {_toml_quote(str(project_root))}\n"
        'codemcp_config = "codemcp.toml"\n'
    )
    candidate = raw + entry
    temporary = paths.projects_config.with_suffix(".toml.tmp")
    temporary.write_text(candidate, encoding="utf-8", newline="\n")
    try:
        load_settings(paths.bridge_config, temporary)
    except SettingsError as exc:
        temporary.unlink(missing_ok=True)
        raise LifecycleError(f"project configuration is invalid: {exc}") from exc
    os.replace(temporary, paths.projects_config)
    return {"status": "ok", "project_id": project_id, "root": str(project_root)}


def load_tunnel_settings(paths: RuntimePaths, *, env_file: Path | None = None) -> TunnelSettings:
    return _REMOTE_TRANSPORT.load_settings(
        _transport_context(paths),
        env_file=env_file,
    )


def find_tunnel_client(paths: RuntimePaths) -> Path:
    return _REMOTE_TRANSPORT.find_client(_transport_context(paths))


def validate_tunnel_profile(settings: TunnelSettings) -> Path:
    profile = _REMOTE_TRANSPORT.validate_config(settings)
    if not isinstance(profile, Path):
        raise LifecycleError("OpenAI tunnel provider did not return a profile path")
    return profile


def redact_log_text(value: str) -> str:
    return _REMOTE_TRANSPORT.redact(value)


def _rotate_log(path: Path) -> None:
    if not path.is_file() or path.stat().st_size < _LOG_MAX_BYTES:
        return
    for index in range(_LOG_BACKUP_COUNT - 1, 0, -1):
        source = path.with_name(f"{path.name}.{index}")
        destination = path.with_name(f"{path.name}.{index + 1}")
        if source.exists():
            os.replace(source, destination)
    os.replace(path, path.with_name(f"{path.name}.1"))


def _self_command() -> list[str]:
    if bool(getattr(sys, "frozen", False)):
        return [sys.executable]
    return [sys.executable, "-m", "codemcp_bridge.main"]


def _http_check(url: str, *, timeout: float = 2.0) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return {"status": "ok", "status_code": int(response.status), "url": url}
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        return {"status": "unreachable", "status_code": None, "url": url, "error": str(exc)}


def _wait_endpoint(
    url: str,
    process: subprocess.Popen[Any],
    timeout_seconds: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        code = process.poll()
        if code is not None:
            return {
                "status": "failed",
                "url": url,
                "error": "process exited before endpoint became healthy",
                "exit_code": code,
                "last_check": last,
            }
        last = _http_check(url)
        if last["status"] == "ok":
            return last
        time.sleep(0.25)
    return {"status": "timeout", "url": url, "last_check": last}


def _bridge_health_url(bridge_url: str) -> str:
    from urllib.parse import urlsplit

    parsed = urlsplit(bridge_url)
    return f"{parsed.scheme}://{parsed.netloc}/healthz"


def _provider_secret_path(
    paths: RuntimePaths,
    provider: RemoteTransportProvider | None = None,
) -> Path:
    effective = _REMOTE_TRANSPORT if provider is None else provider
    filename = effective.secret_file_name
    if not filename or Path(filename).name != filename or filename in {".", ".."}:
        raise LifecycleError("transport provider secret file name is invalid")
    return paths.secret_dir / filename


def _secret_from_runtime(
    paths: RuntimePaths,
    provider: RemoteTransportProvider | None = None,
) -> str | None:
    effective = _REMOTE_TRANSPORT if provider is None else provider
    value = os.environ.get(effective.secret_env_name)
    if value:
        return value
    secret_path = _provider_secret_path(paths, effective)
    if secret_path.is_file() and os.name == "nt":
        return _dpapi_unprotect(secret_path.read_bytes()).decode("utf-8")
    return None


def store_transport_secret_from_environment(
    paths: RuntimePaths,
    *,
    provider: RemoteTransportProvider | None = None,
) -> bool:
    effective = _REMOTE_TRANSPORT if provider is None else provider
    value = os.environ.get(effective.secret_env_name)
    if not value:
        raise LifecycleError(
            f"{effective.secret_env_name} is not set in the current process"
        )
    if os.name != "nt":
        raise LifecycleError("secure transport secret storage is currently supported only on Windows")
    ensure_runtime_dirs(paths)
    secret_path = _provider_secret_path(paths, effective)
    encrypted = _dpapi_protect(value.encode("utf-8"))
    secret_path.write_bytes(encrypted)
    return True


def store_api_key_from_environment(paths: RuntimePaths) -> bool:
    return store_transport_secret_from_environment(
        paths,
        provider=OPENAI_TUNNEL_PROVIDER,
    )


def initialize_tunnel_profile(
    paths: RuntimePaths,
    settings: TunnelSettings,
    *,
    force: bool = False,
) -> Path:
    secret = _secret_from_runtime(paths)
    if not secret:
        raise LifecycleError(
            f"{_SECRET_NAME} is not available; set it for init or store it with --store-api-key"
        )
    profile = _REMOTE_TRANSPORT.initialize(
        _transport_context(paths),
        settings,
        secret=secret,
        force=force,
    )
    if not isinstance(profile, Path):
        raise LifecycleError("OpenAI tunnel provider did not return a profile path")
    return profile


def run_tunnel_proxy(paths: RuntimePaths, settings: TunnelSettings) -> int:
    secret = _secret_from_runtime(paths)
    if not secret:
        raise LifecycleError(f"{_SECRET_NAME} is unavailable")
    return _REMOTE_TRANSPORT.run(
        _transport_context(paths),
        settings,
        secret=secret,
        rotate_log=_rotate_log,
    )


def _popen_background(
    args: list[str],
    *,
    cwd: Path,
    log_path: Path,
    env: dict[str, str],
) -> subprocess.Popen[Any]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_handle = log_path.open("a", encoding="utf-8")
    kwargs: dict[str, Any] = {
        "cwd": cwd,
        "env": env,
        "stdin": subprocess.DEVNULL,
        "stdout": log_handle,
        "stderr": subprocess.STDOUT,
        "text": True,
    }
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(
            subprocess, "CREATE_NO_WINDOW", 0
        )
    try:
        process = subprocess.Popen(args, **kwargs)
    finally:
        log_handle.close()
    return process


def start_services(
    paths: RuntimePaths,
    *,
    bridge_config: Path | None = None,
    projects_config: Path | None = None,
    env_file: Path | None = None,
    startup_timeout_seconds: float = 45,
) -> dict[str, Any]:
    ensure_runtime_dirs(paths)
    bridge_path = (
        paths.bridge_config if bridge_config is None else bridge_config.resolve(strict=False)
    )
    projects_path = (
        paths.projects_config if projects_config is None else projects_config.resolve(strict=False)
    )
    try:
        load_settings(bridge_path, projects_path)
    except SettingsError as exc:
        raise LifecycleError(f"Bridge configuration is invalid: {exc}") from exc
    tunnel = load_tunnel_settings(paths, env_file=env_file)
    validate_tunnel_profile(tunnel)
    secret = _secret_from_runtime(paths)
    if not secret:
        raise LifecycleError(
            f"{_SECRET_NAME} is unavailable; set it in the environment or store it securely"
        )
    if paths.state_file.exists():
        existing = status_services(paths)
        if existing["status"] == "running":
            return existing
        paths.state_file.unlink(missing_ok=True)

    bridge_health = _bridge_health_url(_REMOTE_TRANSPORT.bridge_url(tunnel))
    tunnel_ready = _REMOTE_TRANSPORT.ready_url(tunnel)
    if _http_check(bridge_health)["status"] == "ok":
        raise LifecycleError("Bridge health endpoint is already occupied; refusing unsafe takeover")
    if _http_check(tunnel_ready)["status"] == "ok":
        raise LifecycleError("Tunnel health endpoint is already occupied; refusing unsafe takeover")

    environment = os.environ.copy()
    bridge_process: subprocess.Popen[Any] | None = None
    tunnel_process: subprocess.Popen[Any] | None = None
    try:
        bridge_process = _popen_background(
            [
                *_self_command(),
                "serve",
                "--bridge-config",
                str(bridge_path),
                "--projects-config",
                str(projects_path),
            ],
            cwd=paths.app_root,
            log_path=paths.log_dir / "bridge-supervisor.log",
            env=environment,
        )
        bridge_wait = _wait_endpoint(bridge_health, bridge_process, startup_timeout_seconds)
        if bridge_wait["status"] != "ok":
            raise LifecycleError(
                f"Bridge startup failed: {json.dumps(bridge_wait, ensure_ascii=False)}"
            )

        tunnel_process = _popen_background(
            [
                *_self_command(),
                "_tunnel",
                "--env-file",
                str(tunnel.env_file),
                "--app-root",
                str(paths.app_root),
            ],
            cwd=paths.app_root,
            log_path=paths.log_dir / "tunnel-supervisor.log",
            env=environment,
        )
        tunnel_wait = _wait_endpoint(tunnel_ready, tunnel_process, startup_timeout_seconds)
        if tunnel_wait["status"] != "ok":
            raise LifecycleError(
                f"Tunnel startup failed: {json.dumps(tunnel_wait, ensure_ascii=False)}"
            )

        state = {
            "version": 1,
            "bridge_pid": bridge_process.pid,
            "tunnel_pid": tunnel_process.pid,
            "bridge_process_marker": _process_marker(bridge_process.pid),
            "tunnel_process_marker": _process_marker(tunnel_process.pid),
            "bridge_config": str(bridge_path),
            "projects_config": str(projects_path),
            "env_file": str(tunnel.env_file),
            "bridge_health_url": bridge_health,
            "tunnel_ready_url": tunnel_ready,
        }
        _write_json_atomic(paths.state_file, state)
        return {
            "status": "ok",
            "services": {
                "bridge": {"status": "started", "pid": bridge_process.pid, "health": bridge_wait},
                "tunnel": {"status": "started", "pid": tunnel_process.pid, "health": tunnel_wait},
            },
        }
    except Exception:
        for process in (tunnel_process, bridge_process):
            if process is not None and process.poll() is None:
                _terminate_tree(process.pid)
        raise


def status_services(paths: RuntimePaths) -> dict[str, Any]:
    if not paths.state_file.is_file():
        return {"status": "stopped", "state_file": str(paths.state_file)}
    try:
        state = json.loads(paths.state_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"status": "unknown", "error": f"cannot read lifecycle state: {exc}"}

    bridge_owned = _matches_process_marker(
        int(state.get("bridge_pid", 0)), state.get("bridge_process_marker")
    )
    tunnel_owned = _matches_process_marker(
        int(state.get("tunnel_pid", 0)), state.get("tunnel_process_marker")
    )
    bridge_health = _http_check(str(state.get("bridge_health_url", DEFAULT_BRIDGE_URL)))
    tunnel_health = _http_check(
        str(state.get("tunnel_ready_url", f"{DEFAULT_TUNNEL_HEALTH_URL}/readyz"))
    )
    running = (
        bridge_owned
        and tunnel_owned
        and bridge_health["status"] == "ok"
        and tunnel_health["status"] == "ok"
    )
    return {
        "status": "running" if running else "degraded",
        "bridge": {
            "pid": state.get("bridge_pid"),
            "owned": bridge_owned,
            "health": bridge_health,
        },
        "tunnel": {
            "pid": state.get("tunnel_pid"),
            "owned": tunnel_owned,
            "health": tunnel_health,
        },
        "state_file": str(paths.state_file),
    }


def stop_services(paths: RuntimePaths) -> dict[str, Any]:
    if not paths.state_file.is_file():
        return {"status": "ok", "actions": [], "note": "already stopped"}
    try:
        state = json.loads(paths.state_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LifecycleError(f"cannot read lifecycle state: {exc}") from exc

    actions: list[dict[str, Any]] = []
    for category in ("tunnel", "bridge"):
        pid = int(state.get(f"{category}_pid", 0))
        marker = state.get(f"{category}_process_marker")
        if pid <= 0 or not _matches_process_marker(pid, marker):
            actions.append({"service": category, "pid": pid or None, "status": "not_owned"})
            continue
        _terminate_tree(pid)
        actions.append({"service": category, "pid": pid, "status": "stopped"})
    paths.state_file.unlink(missing_ok=True)
    return {"status": "ok", "actions": actions}


def doctor_report(
    paths: RuntimePaths,
    *,
    bridge_config: Path | None = None,
    projects_config: Path | None = None,
    env_file: Path | None = None,
) -> dict[str, Any]:
    bridge_path = (
        paths.bridge_config if bridge_config is None else bridge_config.resolve(strict=False)
    )
    projects_path = (
        paths.projects_config if projects_config is None else projects_config.resolve(strict=False)
    )
    checks: dict[str, Any] = {}
    try:
        settings = load_settings(bridge_path, projects_path)
        checks["configuration"] = {
            "status": "ok",
            "projects": len(settings.projects),
            "worker_mode": settings.codemcp.worker_mode,
        }
    except SettingsError as exc:
        checks["configuration"] = {"status": "failed", "error": str(exc)}
    secret = _secret_from_runtime(paths)
    secret_path = _provider_secret_path(paths)
    secret_source = (
        "environment"
        if os.environ.get(_REMOTE_TRANSPORT.secret_env_name)
        else ("windows-dpapi" if secret_path.is_file() else "none")
    )
    checks.update(
        _REMOTE_TRANSPORT.doctor(
            _transport_context(paths),
            env_file=env_file,
            secret_available=bool(secret),
            secret_source=secret_source,
        )
    )
    checks["git"] = {
        "status": "ok" if shutil.which("git") else "failed",
        "path": shutil.which("git"),
    }
    checks["services"] = status_services(paths)
    failed = [
        name
        for name, value in checks.items()
        if isinstance(value, dict) and value.get("status") in {"failed", "missing", "unknown"}
    ]
    return {"status": "ok" if not failed else "attention", "checks": checks}


def _write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def _terminate_tree(pid: int) -> None:
    if os.name == "nt":
        completed = subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )
        if completed.returncode not in {0, 128}:
            raise LifecycleError(f"failed to stop PID {pid}: {completed.stderr.strip()}")
        return
    try:
        os.kill(pid, 15)
    except ProcessLookupError:
        return


def _process_marker(pid: int) -> str | None:
    if os.name != "nt":
        return str(pid) if _pid_exists(pid) else None
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None
    try:
        creation = wintypes.FILETIME()
        exit_time = wintypes.FILETIME()
        kernel = wintypes.FILETIME()
        user = wintypes.FILETIME()
        if not ctypes.windll.kernel32.GetProcessTimes(
            handle,
            ctypes.byref(creation),
            ctypes.byref(exit_time),
            ctypes.byref(kernel),
            ctypes.byref(user),
        ):
            return None
        value = (creation.dwHighDateTime << 32) | creation.dwLowDateTime
        return str(value)
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


def _matches_process_marker(pid: int, marker: Any) -> bool:
    if pid <= 0 or marker is None:
        return False
    current = _process_marker(pid)
    return current is not None and str(current) == str(marker)


def _pid_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


class _DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _blob_from_bytes(value: bytes) -> tuple[_DATA_BLOB, Any]:
    buffer = ctypes.create_string_buffer(value)
    blob = _DATA_BLOB(len(value), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
    return blob, buffer


def _dpapi_protect(value: bytes) -> bytes:
    if os.name != "nt":
        raise LifecycleError("DPAPI is available only on Windows")
    source, source_buffer = _blob_from_bytes(value)
    destination = _DATA_BLOB()
    CRYPTPROTECT_UI_FORBIDDEN = 0x1
    ok = ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(source),
        None,
        None,
        None,
        None,
        CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(destination),
    )
    _ = source_buffer
    if not ok:
        raise LifecycleError("Windows DPAPI failed to protect the API key")
    try:
        return ctypes.string_at(destination.pbData, destination.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(destination.pbData)


def _dpapi_unprotect(value: bytes) -> bytes:
    if os.name != "nt":
        raise LifecycleError("DPAPI is available only on Windows")
    source, source_buffer = _blob_from_bytes(value)
    destination = _DATA_BLOB()
    CRYPTPROTECT_UI_FORBIDDEN = 0x1
    ok = ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(source),
        None,
        None,
        None,
        None,
        CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(destination),
    )
    _ = source_buffer
    if not ok:
        raise LifecycleError("Windows DPAPI failed to decrypt the API key")
    try:
        return ctypes.string_at(destination.pbData, destination.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(destination.pbData)
