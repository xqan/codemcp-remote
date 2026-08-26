"""CLI entry point for the local loopback Bridge server."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

from . import __version__
from .lifecycle import (
    DEFAULT_BRIDGE_URL,
    DEFAULT_HEALTH_LISTEN_ADDR,
    DEFAULT_PROFILE,
    DEFAULT_TUNNEL_HEALTH_URL,
    LifecycleError,
    add_project,
    configure_resource_auth,
    doctor_report,
    initialize_runtime,
    initialize_tunnel_profile,
    load_request_authenticator,
    load_transport_provider,
    load_tunnel_settings,
    run_tunnel_proxy,
    runtime_paths,
    start_services,
    status_services,
    stop_services,
    store_api_key_from_environment,
    store_resource_auth_secret_from_environment,
    store_transport_secret_from_environment,
)
from .logging_utils import configure_logging
from .mcp_server import create_server, install_resource_server_auth
from .native_codemcp_worker import main as native_worker_main
from .settings import SettingsError, load_settings


def runtime_root(
    *,
    frozen: bool | None = None,
    executable: Path | None = None,
) -> Path:
    """Return the repository root in source mode or the executable directory when frozen."""

    effective_frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
    if effective_frozen:
        executable_path = Path(sys.executable) if executable is None else executable
        return executable_path.resolve().parent
    return Path(__file__).resolve().parents[3]


RUNTIME_ROOT = runtime_root()
DEFAULT_BRIDGE_CONFIG = RUNTIME_ROOT / "config" / "bridge.example.toml"
DEFAULT_PROJECTS_CONFIG = RUNTIME_ROOT / "config" / "projects.toml"
if not DEFAULT_PROJECTS_CONFIG.is_file():
    DEFAULT_PROJECTS_CONFIG = RUNTIME_ROOT / "config" / "projects.example.toml"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run and manage codemcp-remote")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "command",
        choices=(
            "serve",
            "check",
            "init",
            "project",
            "start",
            "status",
            "stop",
            "doctor",
            "_worker",
            "_tunnel",
        ),
        nargs="?",
        default="serve",
    )
    parser.add_argument("subcommand", nargs="?")
    parser.add_argument("project_id", nargs="?")
    parser.add_argument("project_root", nargs="?")
    parser.add_argument("--bridge-config", type=Path)
    parser.add_argument("--projects-config", type=Path)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--app-root", type=Path)
    parser.add_argument("--transport", choices=("openai-tunnel", "cloudflare"))
    parser.add_argument("--tunnel-id")
    parser.add_argument("--profile-name", default=DEFAULT_PROFILE)
    parser.add_argument("--bridge-url", default=DEFAULT_BRIDGE_URL)
    parser.add_argument("--tunnel-health-url", default=DEFAULT_TUNNEL_HEALTH_URL)
    parser.add_argument("--health-listen-addr", default=DEFAULT_HEALTH_LISTEN_ADDR)
    parser.add_argument("--public-url")
    parser.add_argument("--origin-url", default=DEFAULT_BRIDGE_URL)
    parser.add_argument("--metrics-addr", default="127.0.0.1:46202")
    parser.add_argument("--startup-timeout", type=float, default=45)
    parser.add_argument("--store-api-key", action="store_true")
    parser.add_argument("--store-transport-secret", action="store_true")
    parser.add_argument("--auth-mode", choices=("none", "oauth-resource-server"))
    parser.add_argument("--authorization-server-issuer")
    parser.add_argument("--canonical-resource-uri")
    parser.add_argument("--validation-resource-id")
    parser.add_argument("--store-auth-secret", action="store_true")
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def _json(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def main() -> int:
    args = _parse_args()
    paths = runtime_paths(RUNTIME_ROOT, app_root=args.app_root)

    if args.command == "_worker":
        sys.argv = [sys.argv[0]]
        native_worker_main()
        return 0

    if args.command == "_tunnel":
        try:
            tunnel = load_tunnel_settings(paths, env_file=args.env_file)
            return run_tunnel_proxy(paths, tunnel)
        except LifecycleError as exc:
            _json({"status": "failed", "error": str(exc)})
            return 1

    if args.command in {"init", "project", "start", "status", "stop", "doctor"}:
        try:
            if args.command == "init":
                tunnel_id = args.tunnel_id or os.environ.get("CONTROL_PLANE_TUNNEL_ID", "")
                result = initialize_runtime(
                    paths,
                    tunnel_id=tunnel_id,
                    profile_name=args.profile_name,
                    bridge_url=args.bridge_url,
                    tunnel_health_url=args.tunnel_health_url,
                    health_listen_addr=args.health_listen_addr,
                    transport=args.transport,
                    public_url=args.public_url or "",
                    origin_url=args.origin_url,
                    metrics_addr=args.metrics_addr,
                    force=args.force,
                )
                auth_fields = (
                    args.authorization_server_issuer,
                    args.canonical_resource_uri,
                    args.validation_resource_id,
                )
                if args.auth_mode is None and any(value is not None for value in auth_fields):
                    raise LifecycleError(
                        "--auth-mode is required when OAuth auth fields are supplied"
                    )
                if args.auth_mode is not None:
                    result.update(
                        configure_resource_auth(
                            paths,
                            mode=args.auth_mode,
                            issuer=args.authorization_server_issuer,
                            resource=args.canonical_resource_uri,
                            validation_resource_id=args.validation_resource_id,
                        )
                    )
                provider, _ = load_transport_provider(paths)
                if args.store_api_key:
                    if provider.provider_id != "openai-tunnel":
                        raise LifecycleError(
                            "--store-api-key is only valid for the openai-tunnel transport; "
                            "use --store-transport-secret"
                        )
                    store_api_key_from_environment(paths)
                    result["api_key"] = "stored-with-windows-dpapi"
                if args.store_transport_secret:
                    store_transport_secret_from_environment(paths, provider=provider)
                    result["transport_secret"] = "stored-with-windows-dpapi"
                if args.store_auth_secret:
                    store_resource_auth_secret_from_environment(paths)
                    result["auth_secret"] = "stored-with-windows-dpapi"
                tunnel = load_tunnel_settings(paths)
                config = initialize_tunnel_profile(paths, tunnel, force=args.force)
                result["transport_config"] = str(config)
                if provider.provider_id == "openai-tunnel":
                    result["tunnel_profile"] = str(config)
            elif args.command == "project":
                if args.subcommand != "add" or not args.project_id or not args.project_root:
                    raise LifecycleError(
                        "usage: codemcp-remote project add <project-id> <project-root>"
                    )
                result = add_project(
                    paths,
                    project_id=args.project_id,
                    root=Path(args.project_root),
                )
            elif args.command == "start":
                result = start_services(
                    paths,
                    bridge_config=args.bridge_config,
                    projects_config=args.projects_config,
                    env_file=args.env_file,
                    startup_timeout_seconds=args.startup_timeout,
                )
            elif args.command == "status":
                result = status_services(paths)
            elif args.command == "stop":
                result = stop_services(paths)
            else:
                result = doctor_report(
                    paths,
                    bridge_config=args.bridge_config,
                    projects_config=args.projects_config,
                    env_file=args.env_file,
                )
            _json(result)
            return (
                1 if result.get("status") in {"failed", "attention", "unknown", "degraded"} else 0
            )
        except LifecycleError as exc:
            _json({"status": "failed", "error": str(exc)})
            return 1

    bridge_config = args.bridge_config or DEFAULT_BRIDGE_CONFIG
    projects_config = args.projects_config or DEFAULT_PROJECTS_CONFIG
    try:
        settings = load_settings(bridge_config, projects_config)
    except SettingsError as exc:
        print(f"configuration_error={exc}")
        return 1

    if args.command == "check":
        _json(
            {
                "status": "ok",
                "phase": "5",
                "host": settings.server.host,
                "port": settings.server.port,
                "path": settings.server.path,
                "worker_mode": settings.codemcp.worker_mode,
                "projects_registered": len(settings.projects),
                "model_egress": "deny",
            }
        )
        return 0

    try:
        request_authenticator = load_request_authenticator(paths)
    except LifecycleError as exc:
        print(f"configuration_error={exc}")
        return 1

    configure_logging(settings.storage.log_dir)
    logging.getLogger(__name__).info("Bridge logging initialized")
    server, service = create_server(settings)
    if request_authenticator is not None:
        install_resource_server_auth(server, request_authenticator)
    try:
        server.run(transport=settings.server.transport)
    finally:
        asyncio.run(service.close())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
