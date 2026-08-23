from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from codemcp_bridge.errors import BridgeError, error_payload
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


class SearchAdapter(FakeAdapter):
    def __init__(self) -> None:
        super().__init__()
        self.search_paths: list[Path] = []

    async def call(
        self,
        project: ProjectSpec,
        subtool: str,
        arguments: dict[str, Any],
        *,
        timeout_seconds: float | None = None,
        mutation: bool = False,
    ) -> AdapterResult:
        if subtool == "Grep":
            self.search_paths.append(Path(arguments["path"]))
            return AdapterResult(
                "\n".join(
                    [
                        "Found 3 files",
                        str(project.root / "src" / "hello.txt"),
                        str(project.root / "secrets" / "private.key"),
                        str(project.root / "local.env"),
                    ]
                ),
                False,
            )
        return await super().call(
            project,
            subtool,
            arguments,
            timeout_seconds=timeout_seconds,
            mutation=mutation,
        )


class MultiFileEditAdapter(FakeAdapter):
    async def call(
        self,
        project: ProjectSpec,
        subtool: str,
        arguments: dict[str, Any],
        *,
        timeout_seconds: float | None = None,
        mutation: bool = False,
    ) -> AdapterResult:
        if subtool == "EditFile":
            target = Path(arguments["path"])
            target.write_text(
                target.read_text(encoding="utf-8").replace(
                    arguments["old_string"], arguments["new_string"], 1
                ),
                encoding="utf-8",
            )
            (project.root / "src" / "notes.txt").write_text(
                "unexpected side effect\n", encoding="utf-8"
            )
            return AdapterResult("fake EditFile", False)
        return await super().call(
            project,
            subtool,
            arguments,
            timeout_seconds=timeout_seconds,
            mutation=mutation,
        )


def _payload(result: Any) -> dict[str, Any]:
    if result.structuredContent:
        return result.structuredContent
    text_blocks = [block.text for block in result.content if hasattr(block, "text")]
    return json.loads("\n".join(text_blocks))


def _file_edit_input(
    path: str, old_string: str, new_string: str, description: str
) -> dict[str, str]:
    return {
        "path": path,
        "description": description,
        "old_string_digest": request_hash(old_string),
        "new_string_digest": request_hash(new_string),
    }


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
async def test_local_mcp_contract_and_policy_rejections(
    git_project: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.ERROR)
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
                        "checkpoint_create",
                        "checkpoint_restore",
                        "operation_status",
                        "approval_confirm",
                        "operation_cancel",
                        "operation_reconcile",
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
                                "client_request_id": "format-1",
                                "request_hash": request_hash(
                                    {"command_id": "format", "expected_kind": "format"}
                                ),
                            },
                        )
                    )
                    assert approval["error"]["code"] == "APPROVAL_REQUIRED"

                    cancelled = _payload(
                        await client.call_tool(
                            "operation_cancel",
                            {
                                "operation_id": approval["operation_id"],
                                "session_id": session_id,
                                "client_request_id": "cancel-format-1",
                                "request_hash": request_hash(
                                    {"operation_id": approval["operation_id"]}
                                ),
                            },
                        )
                    )
                    assert cancelled["status"] == "cancelled"

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
                                "client_request_id": "edit-1",
                                "request_hash": request_hash(
                                    _file_edit_input(
                                        "src/hello.txt", "dirty", "changed", "test edit"
                                    )
                                ),
                            },
                        )
                    )
                    assert dirty["error"]["code"] == "WORKSPACE_DIRTY"

    await service.close()
    assert not any(
        record.getMessage() == "Stateless session crashed" for record in caplog.records
    )


@pytest.mark.asyncio
async def test_code_search_excludes_sensitive_paths_before_and_after_grep(
    git_project: Path,
) -> None:
    (git_project / "local.env").write_text("TOKEN=do-not-return\n", encoding="utf-8")
    (git_project / "secrets").mkdir()
    (git_project / "secrets" / "private.key").write_text(
        "private material\n", encoding="utf-8"
    )
    adapter = SearchAdapter()
    service = create_app(_settings(git_project), adapter=adapter)[1]
    await service.start()
    session = service.sessions.create("demo")

    result = await service.code_search(
        None,
        "demo",
        session.session_id,
        "private",
        None,
        None,
    )

    assert result["status"] == "succeeded"
    assert "hello.txt" in result["data"]["text"]
    assert "private.key" not in result["data"]["text"]
    assert "local.env" not in result["data"]["text"]
    assert all(path.name not in {"local.env", "secrets"} for path in adapter.search_paths)
    await service.close()


@pytest.mark.asyncio
async def test_file_edit_reports_all_checkpoint_changed_files(git_project: Path) -> None:
    notes = git_project / "src" / "notes.txt"
    notes.write_text("baseline notes\n", encoding="utf-8")
    _git(git_project, "add", "src/notes.txt")
    _git(git_project, "commit", "-m", "test: add side effect target")

    adapter = MultiFileEditAdapter()
    service = create_app(_settings(git_project), adapter=adapter)[1]
    await service.start()
    session = service.sessions.create("demo")
    operation_input = {
        "path": "src/hello.txt",
        "description": "report side effects",
        "old_string_digest": request_hash("hello"),
        "new_string_digest": request_hash("changed"),
    }

    result = await service.file_edit(
        None,
        "demo",
        session.session_id,
        "src/hello.txt",
        "hello",
        "changed",
        "report side effects",
        "edit-with-side-effect-1",
        request_hash(operation_input),
    )

    assert result["status"] == "succeeded"
    assert set(result["changed_files"]) == {"src/hello.txt", "src/notes.txt"}
    assert set(result["data"]["checkpoint"]["after"]["changed_files"]) == set(
        result["changed_files"]
    )
    await service.close()


@pytest.mark.asyncio
async def test_static_zero_request_id_does_not_conflict_for_read_operations(
    git_project: Path,
) -> None:
    adapter = FakeAdapter()
    app, service = create_app(_settings(git_project), adapter=adapter)
    context = SimpleNamespace(request_id="0")

    async with app.router.lifespan_context(app):
        opened = await service.project_open(context, "demo")
        session_id = opened["data"]["session_id"]
        responses = [
            await service.project_status(context, "demo", session_id),
            await service.file_read(context, "demo", session_id, "src/hello.txt", None, None),
            await service.code_search(context, "demo", session_id, "hello", None, None),
            await service.file_list(context, "demo", session_id, "src"),
        ]

    assert all(response["status"] == "succeeded" for response in responses)
    assert all(response["request_id"] == "0" for response in responses)
    assert len({response["operation_id"] for response in responses}) == len(responses)

    await service.close()


@pytest.mark.asyncio
async def test_phase3_idempotency_approval_and_operation_status(git_project: Path) -> None:
    adapter = FakeAdapter()
    app, service = create_app(_settings(git_project), adapter=adapter)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://127.0.0.1:46200",
        ) as http:
            async with streamable_http_client(
                "http://127.0.0.1:46200/mcp", http_client=http
            ) as (read_stream, write_stream, _):
                async with ClientSession(read_stream, write_stream) as client:
                    await client.initialize()
                    opened = _payload(
                        await client.call_tool("project_open", {"project_id": "demo"})
                    )
                    session_id = opened["data"]["session_id"]

                    edit_arguments = {
                        "project_id": "demo",
                        "session_id": session_id,
                        "path": "src/hello.txt",
                        "old_string": "hello",
                        "new_string": "changed",
                        "description": "idempotent edit",
                        "client_request_id": "edit-replay-1",
                        "request_hash": request_hash(
                            _file_edit_input(
                                "src/hello.txt", "hello", "changed", "idempotent edit"
                            )
                        ),
                    }
                    first_edit = _payload(
                        await client.call_tool("file_edit", edit_arguments)
                    )
                    second_edit = _payload(
                        await client.call_tool("file_edit", edit_arguments)
                    )
                    assert first_edit == second_edit
                    assert [name for name, _ in adapter.calls].count("EditFile") == 1

                    approval = _payload(
                        await client.call_tool(
                            "format_run",
                            {
                                "project_id": "demo",
                                "session_id": session_id,
                                "command_id": "format",
                                "client_request_id": "format-approval-1",
                                "request_hash": request_hash(
                                    {"command_id": "format", "expected_kind": "format"}
                                ),
                            },
                        )
                    )
                    assert approval["status"] == "awaiting_approval"
                    operation_id = approval["operation_id"]
                    token = approval["error"]["details"]["approval_token"]

                    pending_status = _payload(
                        await client.call_tool(
                            "operation_status",
                            {"operation_id": operation_id, "session_id": session_id},
                        )
                    )
                    assert pending_status["data"]["state"] == "awaiting_approval"
                    assert "approval_token" not in str(pending_status["data"])

                    confirmed = _payload(
                        await client.call_tool(
                            "approval_confirm",
                            {
                                "operation_id": operation_id,
                                "session_id": session_id,
                                "approval_token": token,
                                "client_request_id": "approval-confirm-1",
                                "request_hash": request_hash(
                                    {
                                        "operation_id": operation_id,
                                        "approval_token_digest": request_hash(token),
                                    }
                                ),
                            },
                        )
                    )
                    assert confirmed["status"] == "succeeded"
                    assert confirmed["data"]["approved_operation"]["status"] == "succeeded"
                    assert [name for name, _ in adapter.calls].count("RunCommand") == 1

                    final_status = _payload(
                        await client.call_tool(
                            "operation_status",
                            {"operation_id": operation_id, "session_id": session_id},
                        )
                    )
                    assert final_status["data"]["state"] == "succeeded"
                    event_types = {
                        event["event_type"] for event in final_status["data"]["audit_events"]
                    }
                    assert "approval.created" in event_types
                    assert "approval.consumed" in event_types

    await service.close()


@pytest.mark.asyncio
async def test_phase3_reconcile_unknown_mutation_releases_project_lock(
    git_project: Path,
) -> None:
    adapter = FakeAdapter()
    app, service = create_app(_settings(git_project), adapter=adapter)
    await service.start()
    session = service.sessions.create("demo")
    input_data = {"path": "src/hello.txt", "new_string_digest": "digest"}
    started = service.operations.start(
        operation_id="unknown-operation",
        project_id="demo",
        session_id=session.session_id,
        kind="file_edit",
        mutation=True,
        client_request_id="unknown-edit-1",
        supplied_request_hash=request_hash(input_data),
        input_data=input_data,
    )
    service.operations.dispatch(started.record.operation_id)
    unknown = error_payload(
        request_id="unknown-request",
        session_id=session.session_id,
        project_id="demo",
        operation_id=started.record.operation_id,
        error=BridgeError(
            "UNKNOWN_SIDE_EFFECT",
            "mutation outcome is unknown and requires reconciliation",
            status="unknown",
        ),
    )
    service.operations.finish(started.record.operation_id, state="unknown", payload=unknown)

    other_session = service.sessions.create("demo")
    foreign_status = await service.operation_status(
        None, started.record.operation_id, other_session.session_id
    )
    assert foreign_status["error"]["code"] == "OPERATION_NOT_FOUND"
    foreign_reconcile = await service.operation_reconcile(
        None,
        started.record.operation_id,
        other_session.session_id,
        "failed",
        "foreign session must not reconcile",
        "foreign-reconcile-1",
        request_hash(
            {
                "operation_id": started.record.operation_id,
                "decision": "failed",
                "evidence_digest": request_hash("foreign session must not reconcile"),
            }
        ),
    )
    assert foreign_reconcile["error"]["code"] == "OPERATION_NOT_FOUND"
    assert service.operations.operation(started.record.operation_id).state == "unknown"

    evidence = "backend confirmed that no mutation was applied"
    reconciled = await service.operation_reconcile(
        None,
        started.record.operation_id,
        session.session_id,
        "failed",
        evidence,
        "reconcile-unknown-1",
        request_hash(
            {
                "operation_id": started.record.operation_id,
                "decision": "failed",
                "evidence_digest": request_hash(evidence),
            }
        ),
    )
    assert reconciled["status"] == "failed"
    assert reconciled["data"]["reconciled_operation"]["error"]["details"]["reconciled"]
    assert service.operations.operation(started.record.operation_id).state == "failed"

    edit_input = {
        "path": "src/hello.txt",
        "description": "post-reconcile edit",
        "old_string_digest": request_hash("hello"),
        "new_string_digest": request_hash("changed"),
    }
    edit = await service.file_edit(
        None,
        "demo",
        session.session_id,
        "src/hello.txt",
        "hello",
        "changed",
        "post-reconcile edit",
        "post-reconcile-edit-1",
        request_hash(edit_input),
    )
    assert edit["status"] == "succeeded"
    await service.close()
