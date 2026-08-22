from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import httpx
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from codemcp_bridge.mcp_server import create_app
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


def _git(project: Path, *arguments: str) -> None:
    subprocess.run(["git", *arguments], cwd=project, check=True, capture_output=True)


def _settings(project: Path) -> BridgeSettings:
    format_command = CommandSpec(
        command_id="format",
        kind="format",
        argv=("python", "-c", "print('format')"),
        timeout_seconds=30,
        approval="required",
    )
    spec = ProjectSpec(
        project_id="demo",
        root=project,
        allowed_branches=("main",),
        require_clean_workspace=True,
        codemcp_config=project / "codemcp.toml",
        commands={"format": format_command},
    )
    return BridgeSettings(
        repository_root=project.parent,
        bridge_config_path=project.parent / "bridge.toml",
        projects_config_path=project.parent / "projects.toml",
        server=ServerSettings("127.0.0.1", 46200, "/mcp", "streamable-http"),
        storage=StorageSettings(
            project.parent / ".local",
            project.parent / ".local/db",
            project.parent / ".local/logs",
        ),
        policy=PolicySettings(False, False, False, True, 1024, 4096, "per-project"),
        codemcp=CodemcpSettings("local", "Ubuntu", None, 10, 10, 5),
        projects={"demo": spec},
    )


class FakeAdapter:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def call(
        self,
        project: ProjectSpec,
        subtool: str,
        arguments: dict[str, Any],
        *,
        timeout_seconds: float | None = None,
        mutation: bool = False,
    ) -> AdapterResult:
        del project, timeout_seconds, mutation
        self.calls.append((subtool, arguments))
        path = arguments.get("path")
        if subtool == "ReadFile":
            return AdapterResult(f"fake read: {Path(path).name}", False)
        return AdapterResult(f"fake {subtool}", False)

    def is_active(self, project_id: str) -> bool:
        del project_id
        return False

    async def close(self) -> None:
        return None


def _payload(result: Any) -> dict[str, Any]:
    if result.structuredContent:
        return result.structuredContent
    text_blocks = [block.text for block in result.content if hasattr(block, "text")]
    return json.loads("\n".join(text_blocks))


@pytest.fixture
def git_project(tmp_path: Path) -> Path:
    project = tmp_path / "phase2 project"
    project.mkdir()
    (project / "src").mkdir()
    (project / "src" / "hello.txt").write_text("hello\n", encoding="utf-8")
    (project / "src" / "binary.bin").write_bytes(b"header\x00binary\n")
    (project / "src" / "large.txt").write_text("x" * 1025, encoding="utf-8")
    (project / "codemcp.toml").write_text(
        '[commands.format]\ncommand = ["python", "-c", "print(\'format\')"]\n',
        encoding="utf-8",
    )
    _git(project, "init", "-b", "main")
    _git(project, "config", "user.name", "Phase 2 server test")
    _git(project, "config", "user.email", "phase2-server@example.invalid")
    _git(project, "add", ".")
    _git(project, "commit", "-m", "test: initial project")
    return project


@pytest.mark.asyncio
async def test_local_mcp_contract_and_policy_rejections(git_project: Path) -> None:
    adapter = FakeAdapter()
    app, service = create_app(_settings(git_project), adapter=adapter)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://127.0.0.1:46200",
        ) as http:
            health = await http.get("/healthz")
            assert health.status_code == 200
            assert health.json()["status"] == "ok"

            async with streamable_http_client(
                "http://127.0.0.1:46200/mcp", http_client=http
            ) as (read_stream, write_stream, _):
                async with ClientSession(read_stream, write_stream) as client:
                    initialize = await client.initialize()
                    assert initialize.serverInfo.name == "codemcp-remote-bridge"
                    tools = await client.list_tools()
                    assert {tool.name for tool in tools.tools} == {
                        "project_open",
                        "project_status",
                        "file_read",
                        "code_search",
                        "file_list",
                        "file_edit",
                        "format_run",
                        "test_run",
                        "git_status",
                        "git_diff",
                    }

                    opened = _payload(
                        await client.call_tool("project_open", {"project_id": "demo"})
                    )
                    session_id = opened["data"]["session_id"]
                    assert opened["status"] == "succeeded"

                    read = _payload(
                        await client.call_tool(
                            "file_read",
                            {
                                "project_id": "demo",
                                "session_id": session_id,
                                "path": "src/hello.txt",
                            },
                        )
                    )
                    assert read["data"]["text"] == "fake read: hello.txt"
                    assert adapter.calls[-1][0] == "ReadFile"

                    binary = _payload(
                        await client.call_tool(
                            "file_read",
                            {
                                "project_id": "demo",
                                "session_id": session_id,
                                "path": "src/binary.bin",
                            },
                        )
                    )
                    assert binary["error"]["code"] == "BINARY_FILE"

                    large = _payload(
                        await client.call_tool(
                            "file_read",
                            {
                                "project_id": "demo",
                                "session_id": session_id,
                                "path": "src/large.txt",
                            },
                        )
                    )
                    assert large["error"]["code"] == "FILE_TOO_LARGE"

                    escaped = _payload(
                        await client.call_tool(
                            "file_read",
                            {
                                "project_id": "demo",
                                "session_id": session_id,
                                "path": "../outside.txt",
                            },
                        )
                    )
                    assert escaped["error"]["code"] == "PATH_ESCAPE"

                    unknown = _payload(
                        await client.call_tool("project_open", {"project_id": "unknown"})
                    )
                    assert unknown["error"]["code"] == "PROJECT_NOT_ALLOWED"

                    approval = _payload(
                        await client.call_tool(
                            "format_run",
                            {
                                "project_id": "demo",
                                "session_id": session_id,
                                "command_id": "format",
                            },
                        )
                    )
                    assert approval["error"]["code"] == "APPROVAL_REQUIRED"

                    (git_project / "src" / "hello.txt").write_text("dirty\n", encoding="utf-8")
                    dirty = _payload(
                        await client.call_tool(
                            "file_edit",
                            {
                                "project_id": "demo",
                                "session_id": session_id,
                                "path": "src/hello.txt",
                                "old_string": "dirty",
                                "new_string": "changed",
                                "description": "test edit",
                            },
                        )
                    )
                    assert dirty["error"]["code"] == "WORKSPACE_DIRTY"

    await service.close()
