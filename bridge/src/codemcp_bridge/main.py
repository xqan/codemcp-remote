"""CLI entry point for the local loopback Bridge server."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from .mcp_server import create_server
from .settings import SettingsError, load_settings

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_BRIDGE_CONFIG = REPOSITORY_ROOT / "config" / "bridge.example.toml"
DEFAULT_PROJECTS_CONFIG = REPOSITORY_ROOT / "config" / "projects.example.toml"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the loopback codemcp Bridge")
    parser.add_argument("command", choices=("serve", "check"), nargs="?", default="serve")
    parser.add_argument("--bridge-config", type=Path, default=DEFAULT_BRIDGE_CONFIG)
    parser.add_argument("--projects-config", type=Path, default=DEFAULT_PROJECTS_CONFIG)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        settings = load_settings(args.bridge_config, args.projects_config)
    except SettingsError as exc:
        print(f"configuration_error={exc}")
        return 1

    if args.command == "check":
        print(
            json.dumps(
                {
                    "status": "ok",
                    "phase": "4",
                    "host": settings.server.host,
                    "port": settings.server.port,
                    "path": settings.server.path,
                    "worker_mode": settings.codemcp.worker_mode,
                    "projects_registered": len(settings.projects),
                    "model_egress": "deny",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    server, service = create_server(settings)
    try:
        server.run(transport=settings.server.transport)
    finally:
        asyncio.run(service.close())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
