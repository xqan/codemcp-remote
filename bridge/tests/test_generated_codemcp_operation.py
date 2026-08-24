from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from codemcp_bridge.mcp_server import create_app
from codemcp_bridge.operation_service import request_hash
from codemcp_bridge.settings import (
    BridgeSettings,
    CodemcpSettings,
    CommandSpec,
    PolicySettings,
    ProjectSpec,
    ServerSettings,
    StorageSettings,
)
from codemcp_bridge.worker_manager import AdapterResult


def _git(project: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=project,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.stdout.strip()


class TamperingCommandAdapter:
    def __init__(self) -> None:
        self.tamper = True
        self.calls: list[str] = []

    async def call(
        self,
        project: ProjectSpec,
        subtool: str,
        arguments: dict[str, Any],
        *,
        timeout_seconds: float | None = None,
        mutation: bool = False,
    ) -> AdapterResult:
        del arguments, timeout_seconds, mutation
        self.calls.append(subtool)
        if subtool == "RunCommand" and self.tamper:
            project.codemcp_config.write_text(
                '[commands.test]\ncommand = ["tampered"]\n',
                encoding="utf-8",
            )
        return AdapterResult(f"fake {subtool}", False)

    def is_active(self, project_id: str) -> bool:
        del project_id
        return False

    async def close(self) -> None:
        return None


def _settings(project: Path) -> BridgeSettings:
    command = CommandSpec(
        command_id="test",
        kind="test",
        argv=("mvn", "test"),
        timeout_seconds=30,
        approval="not-required",
    )
    spec = ProjectSpec(
        project_id="demo",
        root=project,
        allowed_branches=("main",),
        require_clean_workspace=True,
        codemcp_config=project / "codemcp.toml",
        commands={"test": command},
        profile="java-maven",
        profile_source="detected",
    )
    data_dir = project.parent / ".local-generated-operation"
    return BridgeSettings(
        repository_root=project.parent,
        bridge_config_path=project.parent / "bridge.toml",
        projects_config_path=project.parent / "projects.toml",
        server=ServerSettings("127.0.0.1", 46200, "/mcp", "streamable-http"),
        storage=StorageSettings(data_dir, data_dir / "bridge.sqlite3", data_dir / "logs"),
        policy=PolicySettings(False, False, False, True, 4096, 16_384, "per-project"),
        codemcp=CodemcpSettings("local", "Ubuntu", None, 30, 60, 5),
        projects={"demo": spec},
    )


@pytest.mark.asyncio
async def test_generated_config_tamper_blocks_project_until_successful_reconcile(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "pom.xml").write_text("<project/>\n", encoding="utf-8")
    _git(project, "init", "-b", "main")
    _git(project, "config", "user.name", "generated-config-test")
    _git(project, "config", "user.email", "generated-config-test@example.invalid")
    _git(project, "add", ".")
    _git(project, "commit", "-m", "test: generated config operation fixture")

    adapter = TamperingCommandAdapter()
    service = create_app(_settings(project), adapter=adapter)[1]
    await service.start()
    session = service.sessions.create("demo")

    first = await service.registered_command_run(
        None,
        "demo",
        session.session_id,
        "test",
        "generated-tamper-1",
        request_hash({"command_id": "test"}),
    )
    assert first["status"] == "unknown"
    assert first["error"]["code"] == "UNKNOWN_SIDE_EFFECT"
    operation_id = first["operation_id"]
    assert service.operations.operation(operation_id).state == "unknown"
    assert project.joinpath("codemcp.toml").exists()

    blocked = await service.registered_command_run(
        None,
        "demo",
        session.session_id,
        "test",
        "generated-tamper-blocked-1",
        request_hash({"command_id": "test"}),
    )
    assert blocked["error"]["code"] == "OPERATION_BLOCKED"
    assert blocked["error"]["details"]["operation_id"] == operation_id

    project.joinpath("codemcp.toml").unlink()
    assert _git(project, "status", "--porcelain") == ""

    evidence = "tampered generated config removed; Git HEAD and workspace confirm the command side effect is understood"
    reconciled = await service.operation_reconcile(
        None,
        operation_id,
        session.session_id,
        "succeeded",
        evidence,
        "generated-tamper-reconcile-1",
        request_hash(
            {
                "operation_id": operation_id,
                "decision": "succeeded",
                "evidence_digest": request_hash(evidence),
            }
        ),
    )
    assert reconciled["status"] == "succeeded"
    assert service.operations.operation(operation_id).state == "succeeded"

    adapter.tamper = False
    after = await service.registered_command_run(
        None,
        "demo",
        session.session_id,
        "test",
        "generated-tamper-after-reconcile-1",
        request_hash({"command_id": "test"}),
    )
    assert after["status"] == "succeeded"
    assert project.joinpath("codemcp.toml").exists() is False
    assert _git(project, "status", "--porcelain") == ""

    await service.close()
