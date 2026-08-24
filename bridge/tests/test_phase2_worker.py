from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import anyio
import pytest

import codemcp_bridge.worker_manager as worker_manager_module
from codemcp_bridge.errors import BridgeError
from codemcp_bridge.settings import (
    BridgeSettings,
    CodemcpSettings,
    PolicySettings,
    ProjectSpec,
    ServerSettings,
    StorageSettings,
)
from codemcp_bridge.worker_manager import WorkerManager, _CodemcpWorker


def _settings(
    project: Path,
    data_dir: Path,
    *,
    worker_mode: str = "local",
) -> BridgeSettings:
    spec = ProjectSpec(
        project_id="demo",
        root=project,
        allowed_branches=("main",),
        require_clean_workspace=True,
        codemcp_config=project / "codemcp.toml",
        commands={},
    )
    return BridgeSettings(
        repository_root=project.parent,
        bridge_config_path=project.parent / "bridge.toml",
        projects_config_path=project.parent / "projects.toml",
        server=ServerSettings("127.0.0.1", 46200, "/mcp", "streamable-http"),
        storage=StorageSettings(data_dir, data_dir / "bridge.sqlite3", data_dir / "logs"),
        policy=PolicySettings(False, False, False, True, 1024, 4096, "per-project"),
        codemcp=CodemcpSettings(worker_mode, "Ubuntu", None, 10, 10, 5),
        projects={"demo": spec},
    )


def test_wsl_worker_git_environment_aligns_autocrlf_with_windows(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    settings = _settings(project, tmp_path / "data", worker_mode="wsl2")
    worker = _CodemcpWorker(settings, settings.projects["demo"])

    parameters = worker._parameters(os_name="nt")

    assert parameters.command == "wsl.exe"
    assert parameters.env is not None
    assert parameters.env["GIT_CONFIG_COUNT"] == "2"
    assert parameters.env["GIT_CONFIG_KEY_0"] == "core.excludesfile"
    assert parameters.env["GIT_CONFIG_KEY_1"] == "core.autocrlf"
    assert parameters.env["GIT_CONFIG_VALUE_1"] == "true"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [(False, "BACKEND_UNAVAILABLE"), (True, "UNKNOWN_SIDE_EFFECT")],
)
async def test_worker_timeout_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: bool,
    expected_code: str,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    settings = _settings(project, tmp_path / "data")

    async def timeout(
        self: _CodemcpWorker,
        subtool: str,
        arguments: dict[str, object],
        timeout_seconds: float,
    ) -> object:
        del self, subtool, arguments, timeout_seconds
        raise TimeoutError("test timeout")

    monkeypatch.setattr(_CodemcpWorker, "call", timeout)
    manager = WorkerManager(settings)

    with pytest.raises(BridgeError) as raised:
        await manager.call(
            settings.projects["demo"],
            "EditFile" if mutation else "ReadFile",
            {},
            mutation=mutation,
        )
    assert raised.value.code == expected_code
    assert manager.is_active("demo") is False
    await manager.close()


@pytest.mark.asyncio
async def test_worker_crash_maps_to_backend_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    settings = _settings(project, tmp_path / "data")

    async def crash(
        self: _CodemcpWorker,
        subtool: str,
        arguments: dict[str, object],
        timeout_seconds: float,
    ) -> object:
        del self, subtool, arguments, timeout_seconds
        raise RuntimeError("test worker crash")

    monkeypatch.setattr(_CodemcpWorker, "call", crash)
    manager = WorkerManager(settings)

    with pytest.raises(BridgeError) as raised:
        await manager.call(settings.projects["demo"], "ReadFile", {})
    assert raised.value.code == "BACKEND_UNAVAILABLE"
    assert raised.value.retryable is True
    assert manager.is_active("demo") is False
    await manager.close()
