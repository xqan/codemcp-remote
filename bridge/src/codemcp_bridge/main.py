"""CLI entry point for the local loopback Bridge server."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

from . import __version__
from .logging_utils import configure_logging
from .mcp_server import create_server
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
    parser = argparse.ArgumentParser(description="Run the loopback codemcp Bridge")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "command",
        choices=("serve", "check", "_worker"),
        nargs="?",
        default="serve",
    )
    parser.add_argument("--bridge-config", type=Path, default=DEFAULT_BRIDGE_CONFIG)
    parser.add_argument("--projects-config", type=Path, default=DEFAULT_PROJECTS_CONFIG)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.command == "_worker":
        sys.argv = [sys.argv[0]]
        native_worker_main()
        return 0

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
                    "phase": "5",
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

    configure_logging(settings.storage.log_dir)
    logging.getLogger(__name__).info("Bridge logging initialized")
    server, service = create_server(settings)
    try:
        server.run(transport=settings.server.transport)
    finally:
        asyncio.run(service.close())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
