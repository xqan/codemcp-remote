"""Loopback MCP server and the Phase 2 policy-controlled tool surface."""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Protocol

from mcp.server.fastmcp import Context, FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from .codemcp_adapter import CodemcpAdapter
from .errors import BridgeError, error_payload, success_payload
from .git_guard import GitGuard
from .policy_engine import PolicyEngine
from .project_registry import ProjectRegistry
from .settings import BridgeSettings, CommandSpec, ProjectSpec

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _Session:
    session_id: str
    project_id: str


@dataclass(frozen=True, slots=True)
class _Outcome:
    data: dict[str, Any]
    changed_files: list[str]
    truncated: bool = False
    status: str = "succeeded"


class AdapterLike(Protocol):
    async def call(
        self,
        project: ProjectSpec,
        subtool: str,
        arguments: dict[str, Any],
        *,
        timeout_seconds: float | None = None,
        mutation: bool = False,
    ) -> Any: ...

    def is_active(self, project_id: str) -> bool: ...

    async def close(self) -> None: ...


Operation = Callable[[], Awaitable[_Outcome]]


def _is_codemcp_error(result: Any) -> bool:
    return bool(result.is_error) or result.text.lstrip().lower().startswith("error")


class BridgeService:
    def __init__(self, settings: BridgeSettings, adapter: AdapterLike | None = None):
        self.settings = settings
        self.registry = ProjectRegistry(settings)
        self.git = GitGuard(max_output_bytes=settings.policy.max_result_bytes)
        self.policy = PolicyEngine(settings, self.registry, self.git)
        self.adapter = adapter or CodemcpAdapter(settings, self.registry)
        self._sessions: dict[str, _Session] = {}
        self._sessions_lock = asyncio.Lock()
        self._mutation_locks: dict[str, asyncio.Lock] = {}

    def _mutation_lock(self, project_id: str) -> asyncio.Lock:
        lock = self._mutation_locks.get(project_id)
        if lock is None:
            lock = asyncio.Lock()
            self._mutation_locks[project_id] = lock
        return lock

    @staticmethod
    def _request_id(ctx: Context | None) -> str:
        if ctx is not None:
            try:
                return ctx.request_id
            except (LookupError, ValueError):
                pass
        return uuid.uuid4().hex

    async def _execute(
        self,
        ctx: Context | None,
        *,
        project_id: str | None,
        session_id: str | None,
        operation: Operation,
    ) -> dict[str, Any]:
        request_id = self._request_id(ctx)
        operation_id = uuid.uuid4().hex
        try:
            outcome = await operation()
            return success_payload(
                request_id=request_id,
                session_id=session_id,
                project_id=project_id,
                operation_id=operation_id,
                data=outcome.data,
                changed_files=outcome.changed_files,
                truncated=outcome.truncated,
                status=outcome.status,
            )
        except BridgeError as exc:
            return error_payload(
                request_id=request_id,
                session_id=session_id,
                project_id=project_id,
                operation_id=operation_id,
                error=exc,
            )
        except Exception:
            logger.exception("unexpected Bridge operation failure")
            error = BridgeError(
                "BACKEND_UNAVAILABLE",
                "Bridge backend operation failed",
                {"project_id": project_id},
                retryable=True,
                status="failed",
            )
            return error_payload(
                request_id=request_id,
                session_id=session_id,
                project_id=project_id,
                operation_id=operation_id,
                error=error,
            )

    async def _require_session(self, project_id: str, session_id: str | None) -> _Session:
        if not session_id:
            raise BridgeError("SESSION_REQUIRED", "session_id is required for this operation")
        async with self._sessions_lock:
            session = self._sessions.get(session_id)
        if session is None or session.project_id != project_id:
            raise BridgeError(
                "SESSION_NOT_FOUND",
                "session_id is not active for this project",
                {"project_id": project_id},
            )
        return session

    async def project_open(self, ctx: Context | None, project_id: str) -> dict[str, Any]:
        async def operation() -> _Outcome:
            project = self.registry.get(project_id)
            status = await self.policy.inspect_project(project)
            session_id = uuid.uuid4().hex
            async with self._sessions_lock:
                self._sessions[session_id] = _Session(session_id, project_id)
            return _Outcome(
                data={
                    "session_id": session_id,
                    "root": str(project.root),
                    "branch": status.branch,
                    "head": status.head,
                    "dirty": status.dirty,
                    "worker_active": self.adapter.is_active(project_id),
                },
                changed_files=list(status.changed_files),
            )

        return await self._execute(ctx, project_id=project_id, session_id=None, operation=operation)

    async def project_status(
        self,
        ctx: Context | None,
        project_id: str,
        session_id: str | None,
    ) -> dict[str, Any]:
        async def operation() -> _Outcome:
            project = self.registry.get(project_id)
            if session_id:
                await self._require_session(project_id, session_id)
            status = await self.policy.inspect_project(project)
            return _Outcome(
                data={
                    "root": str(project.root),
                    "branch": status.branch,
                    "head": status.head,
                    "dirty": status.dirty,
                    "worker_active": self.adapter.is_active(project_id),
                },
                changed_files=list(status.changed_files),
            )

        return await self._execute(
            ctx,
            project_id=project_id,
            session_id=session_id,
            operation=operation,
        )

    async def file_read(
        self,
        ctx: Context | None,
        project_id: str,
        session_id: str,
        path: str,
        offset: int | None,
        limit: int | None,
    ) -> dict[str, Any]:
        async def operation() -> _Outcome:
            await self._require_session(project_id, session_id)
            if offset is not None and offset < 0:
                raise BridgeError("INVALID_REQUEST", "offset must not be negative")
            if limit is not None and not 0 <= limit <= 10_000:
                raise BridgeError("INVALID_REQUEST", "limit must be between 0 and 10000")
            project, target, _ = self.registry.resolve_path(project_id, path)
            self.policy.require_regular_file(target)
            self.policy.validate_file_size(target)
            self.policy.require_text_file(target)
            result = await self.adapter.call(
                project,
                "ReadFile",
                {"path": target, "offset": offset, "limit": limit, "chat_id": session_id},
            )
            if _is_codemcp_error(result):
                raise BridgeError(
                    "BACKEND_UNAVAILABLE",
                    "codemcp rejected ReadFile",
                    {"subtool": "ReadFile"},
                    status="failed",
                )
            return _Outcome(
                {"path": self.registry.relative_path(project, target), "text": result.text},
                [],
                result.truncated,
            )

        return await self._execute(
            ctx,
            project_id=project_id,
            session_id=session_id,
            operation=operation,
        )

    async def code_search(
        self,
        ctx: Context | None,
        project_id: str,
        session_id: str,
        pattern: str,
        path: str | None,
        include: str | None,
    ) -> dict[str, Any]:
        async def operation() -> _Outcome:
            await self._require_session(project_id, session_id)
            self.policy.validate_pattern(pattern)
            project, target, _ = self.registry.resolve_path(project_id, path, allow_root=True)
            result = await self.adapter.call(
                project,
                "Grep",
                {"pattern": pattern, "path": target, "include": include, "chat_id": session_id},
            )
            if _is_codemcp_error(result):
                raise BridgeError("BACKEND_UNAVAILABLE", "codemcp rejected Grep", status="failed")
            return _Outcome(
                {"path": self.registry.relative_path(project, target), "text": result.text},
                [],
                result.truncated,
            )

        return await self._execute(
            ctx,
            project_id=project_id,
            session_id=session_id,
            operation=operation,
        )

    async def file_list(
        self,
        ctx: Context | None,
        project_id: str,
        session_id: str,
        path: str | None,
    ) -> dict[str, Any]:
        async def operation() -> _Outcome:
            await self._require_session(project_id, session_id)
            project, target, _ = self.registry.resolve_path(project_id, path, allow_root=True)
            if not target.is_dir():
                raise BridgeError("FILE_NOT_FOUND", "a directory is required")
            result = await self.adapter.call(
                project,
                "LS",
                {"path": target, "chat_id": session_id},
            )
            if _is_codemcp_error(result):
                raise BridgeError("BACKEND_UNAVAILABLE", "codemcp rejected LS", status="failed")
            return _Outcome(
                {"path": self.registry.relative_path(project, target), "text": result.text},
                [],
                result.truncated,
            )

        return await self._execute(
            ctx,
            project_id=project_id,
            session_id=session_id,
            operation=operation,
        )

    async def file_edit(
        self,
        ctx: Context | None,
        project_id: str,
        session_id: str,
        path: str,
        old_string: str,
        new_string: str,
        description: str,
    ) -> dict[str, Any]:
        async def operation() -> _Outcome:
            await self._require_session(project_id, session_id)
            if not description or len(description) > 500:
                raise BridgeError("INVALID_REQUEST", "description must be 1-500 characters")
            if len(old_string.encode("utf-8")) > self.settings.policy.max_file_bytes:
                raise BridgeError("FILE_TOO_LARGE", "old_string exceeds the configured size limit")
            if len(new_string.encode("utf-8")) > self.settings.policy.max_file_bytes:
                raise BridgeError("FILE_TOO_LARGE", "new_string exceeds the configured size limit")
            project, target, relative = self.registry.resolve_path(project_id, path)
            self.policy.require_regular_file(target)
            self.policy.validate_file_size(target)
            async with self._mutation_lock(project_id):
                await self.policy.require_mutation_preconditions(project)
                result = await self.adapter.call(
                    project,
                    "EditFile",
                    {
                        "path": target,
                        "old_string": old_string,
                        "new_string": new_string,
                        "description": description,
                        "chat_id": session_id,
                    },
                    mutation=True,
                )
            if _is_codemcp_error(result):
                raise BridgeError("CONFLICT", "codemcp rejected EditFile", status="failed")
            if result.text.startswith("String to replace not found"):
                raise BridgeError("CONFLICT", "old_string was not found in the file")
            return _Outcome({"text": result.text}, [relative], result.truncated)

        return await self._execute(
            ctx,
            project_id=project_id,
            session_id=session_id,
            operation=operation,
        )

    async def _run_registered_command(
        self,
        ctx: Context | None,
        project_id: str,
        session_id: str,
        command_id: str,
        expected_kind: str,
    ) -> dict[str, Any]:
        async def operation() -> _Outcome:
            await self._require_session(project_id, session_id)
            project = self.registry.get(project_id)
            command: CommandSpec = self.policy.command(project, command_id, expected_kind)
            async with self._mutation_lock(project_id):
                await self.policy.require_mutation_preconditions(project)
                result = await self.adapter.call(
                    project,
                    "RunCommand",
                    {"path": project.root, "command": command_id, "chat_id": session_id},
                    timeout_seconds=command.timeout_seconds,
                    mutation=True,
                )
            if _is_codemcp_error(result):
                raise BridgeError(
                    "BACKEND_UNAVAILABLE",
                    "codemcp rejected RunCommand",
                    status="failed",
                )
            status = "failed" if _is_codemcp_error(result) else "succeeded"
            return _Outcome(
                {"command_id": command_id, "text": result.text},
                [],
                result.truncated,
                status,
            )

        return await self._execute(
            ctx,
            project_id=project_id,
            session_id=session_id,
            operation=operation,
        )

    async def format_run(
        self,
        ctx: Context | None,
        project_id: str,
        session_id: str,
        command_id: str,
    ) -> dict[str, Any]:
        return await self._run_registered_command(
            ctx, project_id, session_id, command_id, "format"
        )

    async def test_run(
        self,
        ctx: Context | None,
        project_id: str,
        session_id: str,
        command_id: str,
    ) -> dict[str, Any]:
        return await self._run_registered_command(ctx, project_id, session_id, command_id, "test")

    async def git_status(
        self,
        ctx: Context | None,
        project_id: str,
        session_id: str,
    ) -> dict[str, Any]:
        async def operation() -> _Outcome:
            await self._require_session(project_id, session_id)
            project = self.registry.get(project_id)
            status = await self.policy.inspect_project(project)
            return _Outcome(
                {
                    "branch": status.branch,
                    "head": status.head,
                    "dirty": status.dirty,
                    "changed_files": list(status.changed_files),
                },
                list(status.changed_files),
            )

        return await self._execute(
            ctx,
            project_id=project_id,
            session_id=session_id,
            operation=operation,
        )

    async def git_diff(
        self,
        ctx: Context | None,
        project_id: str,
        session_id: str,
    ) -> dict[str, Any]:
        async def operation() -> _Outcome:
            await self._require_session(project_id, session_id)
            project = self.registry.get(project_id)
            await self.policy.inspect_project(project)
            diff, truncated = await self.git.diff(project.root)
            return _Outcome({"text": diff}, [], truncated)

        return await self._execute(
            ctx,
            project_id=project_id,
            session_id=session_id,
            operation=operation,
        )

    async def health(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "phase": "2",
            "transport": self.settings.server.transport,
            "endpoint": (
                f"{self.settings.server.host}:{self.settings.server.port}"
                f"{self.settings.server.path}"
            ),
            "worker_mode": self.settings.codemcp.worker_mode,
            "projects_registered": len(self.settings.projects),
            "model_egress": "deny",
        }

    async def close(self) -> None:
        await self.adapter.close()


def create_server(
    settings: BridgeSettings,
    adapter: AdapterLike | None = None,
) -> tuple[FastMCP, BridgeService]:
    service = BridgeService(settings, adapter)

    @asynccontextmanager
    async def lifespan(_: FastMCP):
        try:
            yield
        finally:
            await service.close()

    server = FastMCP(
        "codemcp-remote-bridge",
        instructions="ChatGPT-only local policy bridge; codemcp is an execution backend.",
        host=settings.server.host,
        port=settings.server.port,
        streamable_http_path=settings.server.path,
        stateless_http=True,
        json_response=True,
        lifespan=lifespan,
    )

    @server.custom_route("/healthz", methods=["GET"], include_in_schema=False)
    async def healthz(_: Request) -> JSONResponse:
        return JSONResponse(await service.health())

    @server.tool(description="Open a registered project and create an ephemeral session.")
    async def project_open(project_id: str, ctx: Context) -> dict[str, Any]:
        return await service.project_open(ctx, project_id)

    @server.tool(description="Return registered project and worker status.")
    async def project_status(
        project_id: str, session_id: str | None = None, ctx: Context | None = None
    ) -> dict[str, Any]:
        return await service.project_status(ctx, project_id, session_id)

    @server.tool(description="Read one UTF-8 project file through codemcp.")
    async def file_read(
        project_id: str,
        session_id: str,
        path: str,
        offset: int | None = None,
        limit: int | None = None,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        return await service.file_read(ctx, project_id, session_id, path, offset, limit)

    @server.tool(description="Search project code through codemcp Grep.")
    async def code_search(
        project_id: str,
        session_id: str,
        pattern: str,
        path: str | None = None,
        include: str | None = None,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        return await service.code_search(ctx, project_id, session_id, pattern, path, include)

    @server.tool(description="List a registered project directory through codemcp.")
    async def file_list(
        project_id: str,
        session_id: str,
        path: str | None = None,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        return await service.file_list(ctx, project_id, session_id, path)

    @server.tool(description="Apply one exact replacement through codemcp EditFile.")
    async def file_edit(
        project_id: str,
        session_id: str,
        path: str,
        old_string: str,
        new_string: str,
        description: str,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        return await service.file_edit(
            ctx, project_id, session_id, path, old_string, new_string, description
        )

    @server.tool(description="Run one registered formatting command.")
    async def format_run(
        project_id: str,
        session_id: str,
        command_id: str,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        return await service.format_run(ctx, project_id, session_id, command_id)

    @server.tool(description="Run one registered test command.")
    async def test_run(
        project_id: str,
        session_id: str,
        command_id: str,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        return await service.test_run(ctx, project_id, session_id, command_id)

    @server.tool(description="Return bounded Git status for a registered project.")
    async def git_status(
        project_id: str, session_id: str, ctx: Context | None = None
    ) -> dict[str, Any]:
        return await service.git_status(ctx, project_id, session_id)

    @server.tool(description="Return a bounded Git diff for a registered project.")
    async def git_diff(
        project_id: str, session_id: str, ctx: Context | None = None
    ) -> dict[str, Any]:
        return await service.git_diff(ctx, project_id, session_id)

    return server, service


def create_app(
    settings: BridgeSettings,
    adapter: AdapterLike | None = None,
) -> tuple[Any, BridgeService]:
    """Create the ASGI app and service for local contract tests."""

    server, service = create_server(settings, adapter)
    return server.streamable_http_app(), service
