"""Loopback MCP server and the Phase 3 policy-controlled tool surface."""

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

from .approval_service import ApprovalService
from .audit_store import AuditStore
from .codemcp_adapter import CodemcpAdapter
from .db import Database, OperationRecord, SessionRecord
from .errors import BridgeError, error_payload, success_payload
from .git_guard import GitGuard
from .operation_service import OperationService
from .operation_service import request_hash as calculate_request_hash
from .policy_engine import PolicyEngine
from .project_registry import ProjectRegistry
from .session_service import SessionService
from .settings import BridgeSettings, CommandSpec, ProjectSpec

logger = logging.getLogger(__name__)


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
        self.database = Database(settings.storage.sqlite_file)
        self.sessions = SessionService(self.database)
        self.operations = OperationService(self.database)
        self.approvals = ApprovalService(
            self.database, ttl_seconds=settings.policy.approval_ttl_seconds
        )
        self.audit = AuditStore(self.database)
        self._started = False
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
        operation_kind: str,
        operation_input: dict[str, Any] | None = None,
        mutation: bool = False,
        client_request_id: str | None = None,
        supplied_request_hash: str | None = None,
        approval_required: bool = False,
        approval_action: str | None = None,
        approval_check: Callable[[], Awaitable[bool]] | None = None,
    ) -> dict[str, Any]:
        await self.start()
        request_id = self._request_id(ctx)
        client_id = client_request_id or ("" if mutation else request_id)
        input_data = operation_input or {}
        request_hash_value = (
            supplied_request_hash or ("" if mutation else calculate_request_hash(input_data))
        )
        operation_id = uuid.uuid4().hex
        try:
            started = self.operations.start(
                operation_id=operation_id,
                project_id=project_id or "__bridge__",
                session_id=session_id,
                kind=operation_kind,
                mutation=mutation,
                client_request_id=client_id,
                supplied_request_hash=request_hash_value,
                input_data=input_data,
            )
        except BridgeError as exc:
            return error_payload(
                request_id=request_id,
                session_id=session_id,
                project_id=project_id,
                operation_id=operation_id,
                error=exc,
            )
        if started.replay_payload is not None:
            return started.replay_payload
        operation_id = started.record.operation_id
        try:
            needs_approval = approval_required
            if approval_check is not None:
                needs_approval = await approval_check()
        except BridgeError as exc:
            payload = error_payload(
                request_id=request_id,
                session_id=session_id,
                project_id=project_id,
                operation_id=operation_id,
                error=exc,
            )
            self.operations.finish(operation_id, state="failed", payload=payload)
            return payload
        if needs_approval:
            action = approval_action or operation_kind
            grant = self.approvals.issue(started.record, action=action)
            approval_error = BridgeError(
                "APPROVAL_REQUIRED",
                "explicit approval is required before this operation can run",
                {
                    "operation_id": operation_id,
                    "approval_id": grant.approval_id,
                    "approval_token": grant.token,
                    "expires_at": grant.expires_at,
                    "action": action,
                },
                status="awaiting_approval",
            )
            payload = error_payload(
                request_id=request_id,
                session_id=session_id,
                project_id=project_id,
                operation_id=operation_id,
                error=approval_error,
            )
            self.operations.await_approval(operation_id, error_data=payload["error"])
            return payload
        try:
            self.operations.dispatch(operation_id)
            outcome = await operation()
            response_session_id = session_id
            returned_session_id = outcome.data.get("session_id")
            if response_session_id is None and isinstance(returned_session_id, str):
                response_session_id = returned_session_id
            payload = success_payload(
                request_id=request_id,
                session_id=response_session_id,
                project_id=project_id,
                operation_id=operation_id,
                data=outcome.data,
                changed_files=outcome.changed_files,
                truncated=outcome.truncated,
                status=outcome.status,
            )
            terminal_state = "failed" if outcome.status == "failed" else "succeeded"
            self.operations.finish(operation_id, state=terminal_state, payload=payload)
            return payload
        except BridgeError as exc:
            payload = error_payload(
                request_id=request_id,
                session_id=session_id,
                project_id=project_id,
                operation_id=operation_id,
                error=exc,
            )
            terminal_state = "unknown" if exc.status == "unknown" else "failed"
            self.operations.finish(operation_id, state=terminal_state, payload=payload)
            return payload
        except Exception:
            logger.exception("unexpected Bridge operation failure")
            error = BridgeError(
                "BACKEND_UNAVAILABLE",
                "Bridge backend operation failed",
                {"project_id": project_id},
                retryable=True,
                status="failed",
            )
            payload = error_payload(
                request_id=request_id,
                session_id=session_id,
                project_id=project_id,
                operation_id=operation_id,
                error=error,
            )
            self.operations.finish(operation_id, state="failed", payload=payload)
            return payload

    async def _require_session(self, project_id: str, session_id: str | None) -> SessionRecord:
        return self.sessions.require_active(project_id, session_id)

    async def start(self) -> None:
        if self._started:
            return
        self.database.initialize()
        self.database.recover_after_restart()
        self._started = True

    async def project_open(self, ctx: Context | None, project_id: str) -> dict[str, Any]:
        async def operation() -> _Outcome:
            project = self.registry.get(project_id)
            status = await self.policy.inspect_project(project)
            session = self.sessions.create(project_id)
            return _Outcome(
                data={
                    "session_id": session.session_id,
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
            session_id=None,
            operation=operation,
            operation_kind="project_open",
            operation_input={"project_id": project_id},
            client_request_id=uuid.uuid4().hex,
            supplied_request_hash=calculate_request_hash({"project_id": project_id}),
        )

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
            operation_kind="project_status",
            operation_input={"project_id": project_id, "session_id": session_id},
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
            operation_kind="file_read",
            operation_input={
                "path": path,
                "offset": offset,
                "limit": limit,
            },
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
            operation_kind="code_search",
            operation_input={"pattern": pattern, "path": path, "include": include},
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
            operation_kind="file_list",
            operation_input={"path": path},
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
        client_request_id: str | None,
        request_hash: str | None,
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
            operation_kind="file_edit",
            operation_input={
                "path": path,
                "description": description,
                "old_string_digest": calculate_request_hash(old_string),
                "new_string_digest": calculate_request_hash(new_string),
            },
            mutation=True,
            client_request_id=client_request_id,
            supplied_request_hash=request_hash,
        )

    async def _run_registered_command(
        self,
        ctx: Context | None,
        project_id: str,
        session_id: str,
        command_id: str,
        expected_kind: str,
        client_request_id: str | None,
        request_hash: str | None,
    ) -> dict[str, Any]:
        prepared: dict[str, Any] = {}

        async def approval_check() -> bool:
            await self._require_session(project_id, session_id)
            project = self.registry.get(project_id)
            command = self.policy.command(
                project, command_id, expected_kind, require_approval=False
            )
            prepared["project"] = project
            prepared["command"] = command
            return command.approval == "required"

        async def operation() -> _Outcome:
            await self._require_session(project_id, session_id)
            project = prepared.get("project") or self.registry.get(project_id)
            command = prepared.get("command")
            if not isinstance(command, CommandSpec):
                command = self.policy.command(
                    project, command_id, expected_kind, require_approval=False
                )
            return await self._run_command_body(project, command, session_id)

        return await self._execute(
            ctx,
            project_id=project_id,
            session_id=session_id,
            operation=operation,
            operation_kind=f"{expected_kind}_run",
            operation_input={
                "command_id": command_id,
                "expected_kind": expected_kind,
            },
            mutation=True,
            client_request_id=client_request_id,
            supplied_request_hash=request_hash,
            approval_action=f"{expected_kind}:{command_id}",
            approval_check=approval_check,
        )

    async def _run_command_body(
        self, project: ProjectSpec, command: CommandSpec, session_id: str
    ) -> _Outcome:
        async with self._mutation_lock(project.project_id):
            await self.policy.require_mutation_preconditions(project)
            result = await self.adapter.call(
                project,
                "RunCommand",
                {"path": project.root, "command": command.command_id, "chat_id": session_id},
                timeout_seconds=command.timeout_seconds,
                mutation=True,
            )
        if _is_codemcp_error(result):
            raise BridgeError(
                "BACKEND_UNAVAILABLE",
                "codemcp rejected RunCommand",
                status="failed",
            )
        return _Outcome(
            {"command_id": command.command_id, "text": result.text},
            [],
            result.truncated,
            "succeeded",
        )

    async def format_run(
        self,
        ctx: Context | None,
        project_id: str,
        session_id: str,
        command_id: str,
        client_request_id: str | None,
        request_hash: str | None,
    ) -> dict[str, Any]:
        return await self._run_registered_command(
            ctx,
            project_id,
            session_id,
            command_id,
            "format",
            client_request_id,
            request_hash,
        )

    async def test_run(
        self,
        ctx: Context | None,
        project_id: str,
        session_id: str,
        command_id: str,
        client_request_id: str | None,
        request_hash: str | None,
    ) -> dict[str, Any]:
        return await self._run_registered_command(
            ctx,
            project_id,
            session_id,
            command_id,
            "test",
            client_request_id,
            request_hash,
        )

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
            operation_kind="git_status",
            operation_input={"project_id": project_id, "session_id": session_id},
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
            operation_kind="git_diff",
            operation_input={"project_id": project_id, "session_id": session_id},
        )

    async def operation_status(
        self,
        ctx: Context | None,
        operation_id: str,
        session_id: str,
    ) -> dict[str, Any]:
        await self.start()
        request_id = self._request_id(ctx)
        try:
            record = self.operations.operation(operation_id)
            self.sessions.require_active(record.project_id, session_id)
            if record.owner_id != self.sessions.owner_id:
                raise BridgeError(
                    "OPERATION_NOT_FOUND", "operation_id is not owned by this profile"
                )
            return success_payload(
                request_id=request_id,
                session_id=session_id,
                project_id=record.project_id,
                operation_id=record.operation_id,
                data={
                    "state": record.state,
                    "kind": record.kind,
                    "mutation": record.mutation,
                    "client_request_id": record.client_request_id,
                    "created_at": record.created_at,
                    "updated_at": record.updated_at,
                    "started_at": record.started_at,
                    "finished_at": record.finished_at,
                    "result": record.result_data,
                    "error": record.error_data,
                    "audit_events": self.audit.for_operation(record.operation_id),
                },
            )
        except BridgeError as exc:
            return error_payload(
                request_id=request_id,
                session_id=session_id,
                project_id=None,
                operation_id=operation_id,
                error=exc,
            )

    async def approval_confirm(
        self,
        ctx: Context | None,
        operation_id: str,
        session_id: str,
        approval_token: str,
        client_request_id: str | None,
        request_hash: str | None,
    ) -> dict[str, Any]:
        await self.start()
        try:
            original = self.operations.operation(operation_id)
        except BridgeError as exc:
            return error_payload(
                request_id=self._request_id(ctx),
                session_id=session_id,
                project_id=None,
                operation_id=operation_id,
                error=exc,
            )

        async def operation() -> _Outcome:
            self.sessions.require_active(original.project_id, session_id)
            if original.session_id != session_id:
                raise BridgeError(
                    "SESSION_NOT_FOUND",
                    "approval belongs to a different session",
                    {"operation_id": operation_id},
                )
            if original.state != "awaiting_approval":
                raise BridgeError(
                    "OPERATION_NOT_CANCELABLE",
                    "operation is not awaiting approval",
                    {"operation_id": operation_id, "state": original.state},
                )
            approved = self.approvals.consume(operation_id, approval_token)
            running = self.operations.dispatch(
                approved.operation_id, from_state="awaiting_approval"
            )
            try:
                outcome = await self._run_command_for_operation(running)
            except BridgeError as exc:
                final = error_payload(
                    request_id=self._request_id(ctx),
                    session_id=session_id,
                    project_id=running.project_id,
                    operation_id=running.operation_id,
                    error=exc,
                )
                final_state = "unknown" if exc.status == "unknown" else "failed"
                self.operations.finish(running.operation_id, state=final_state, payload=final)
                return _Outcome(
                    {"approved_operation": final},
                    [],
                    status="failed",
                )
            except Exception:
                logger.exception("unexpected approved mutation failure")
                final = error_payload(
                    request_id=self._request_id(ctx),
                    session_id=session_id,
                    project_id=running.project_id,
                    operation_id=running.operation_id,
                    error=BridgeError(
                        "UNKNOWN_SIDE_EFFECT",
                        "approved mutation outcome is unknown and requires reconciliation",
                        {"operation_id": running.operation_id},
                        status="unknown",
                    ),
                )
                self.operations.finish(running.operation_id, state="unknown", payload=final)
                return _Outcome(
                    {"approved_operation": final},
                    [],
                    status="failed",
                )
            final = success_payload(
                request_id=self._request_id(ctx),
                session_id=session_id,
                project_id=running.project_id,
                operation_id=running.operation_id,
                data=outcome.data,
                changed_files=outcome.changed_files,
                truncated=outcome.truncated,
                status=outcome.status,
            )
            self.operations.finish(running.operation_id, state="succeeded", payload=final)
            return _Outcome(
                {"approved_operation": final},
                outcome.changed_files,
                outcome.truncated,
                outcome.status,
            )

        return await self._execute(
            ctx,
            project_id=original.project_id,
            session_id=session_id,
            operation=operation,
            operation_kind="approval_confirm",
            operation_input={
                "operation_id": operation_id,
                "approval_token_digest": calculate_request_hash(approval_token),
            },
            client_request_id=client_request_id,
            supplied_request_hash=request_hash,
        )

    async def _run_command_for_operation(self, operation: OperationRecord) -> _Outcome:
        input_data = operation.input_data
        command_id = input_data.get("command_id")
        expected_kind = input_data.get("expected_kind")
        if not isinstance(command_id, str) or not isinstance(expected_kind, str):
            raise BridgeError("INVALID_REQUEST", "stored command operation is malformed")
        project = self.registry.get(operation.project_id)
        command = self.policy.command(
            project, command_id, expected_kind, require_approval=False
        )
        if operation.session_id is None:
            raise BridgeError("SESSION_REQUIRED", "approved operation has no session")
        return await self._run_command_body(project, command, operation.session_id)

    async def operation_cancel(
        self,
        ctx: Context | None,
        operation_id: str,
        session_id: str,
        client_request_id: str | None,
        request_hash: str | None,
    ) -> dict[str, Any]:
        await self.start()
        try:
            original = self.operations.operation(operation_id)
        except BridgeError as exc:
            return error_payload(
                request_id=self._request_id(ctx),
                session_id=session_id,
                project_id=None,
                operation_id=operation_id,
                error=exc,
            )

        async def operation() -> _Outcome:
            self.sessions.require_active(original.project_id, session_id)
            if original.session_id != session_id:
                raise BridgeError("SESSION_NOT_FOUND", "operation belongs to a different session")
            if original.state != "awaiting_approval":
                raise BridgeError(
                    "OPERATION_NOT_CANCELABLE",
                    "only an operation awaiting approval can be cancelled",
                    {"operation_id": operation_id, "state": original.state},
                )
            self.approvals.cancel(operation_id, reason="client_cancelled")
            final = success_payload(
                request_id=self._request_id(ctx),
                session_id=session_id,
                project_id=original.project_id,
                operation_id=operation_id,
                data={"state": "cancelled"},
                status="cancelled",
            )
            self.operations.finish(operation_id, state="cancelled", payload=final)
            return _Outcome({"cancelled_operation": final}, [], status="cancelled")

        return await self._execute(
            ctx,
            project_id=original.project_id,
            session_id=session_id,
            operation=operation,
            operation_kind="operation_cancel",
            operation_input={"operation_id": operation_id},
            client_request_id=client_request_id,
            supplied_request_hash=request_hash,
        )

    async def operation_reconcile(
        self,
        ctx: Context | None,
        operation_id: str,
        session_id: str,
        decision: str,
        evidence: str,
        client_request_id: str | None,
        request_hash: str | None,
    ) -> dict[str, Any]:
        await self.start()
        try:
            original = self.operations.operation(operation_id)
        except BridgeError as exc:
            return error_payload(
                request_id=self._request_id(ctx),
                session_id=session_id,
                project_id=None,
                operation_id=operation_id,
                error=exc,
            )

        async def operation() -> _Outcome:
            self.sessions.require_active(original.project_id, session_id)
            if decision != "failed":
                raise BridgeError(
                    "RECONCILE_REQUIRED",
                    "only an explicit failed reconciliation can clear unknown state",
                )
            if not evidence or len(evidence) > 1000:
                raise BridgeError("INVALID_REQUEST", "evidence must be 1-1000 characters")
            if original.state != "unknown":
                raise BridgeError(
                    "RECONCILE_REQUIRED",
                    "only unknown operations require reconciliation",
                    {"state": original.state},
                )
            final = error_payload(
                request_id=self._request_id(ctx),
                session_id=session_id,
                project_id=original.project_id,
                operation_id=operation_id,
                error=BridgeError(
                    "BRIDGE_RESTARTED",
                    "operation was reconciled as not executed",
                    {"evidence": evidence, "reconciled": True},
                    status="failed",
                ),
            )
            self.operations.finish(operation_id, state="failed", payload=final)
            return _Outcome({"reconciled_operation": final}, [], status="failed")

        return await self._execute(
            ctx,
            project_id=original.project_id,
            session_id=session_id,
            operation=operation,
            operation_kind="operation_reconcile",
            operation_input={"operation_id": operation_id, "decision": decision},
            client_request_id=client_request_id,
            supplied_request_hash=request_hash,
        )

    async def health(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "phase": "3",
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
        if not self._started:
            return
        try:
            await self.close_backend()
        finally:
            self.sessions.close_all("bridge_shutdown")
            self.database.close()
            self._started = False

    async def close_backend(self) -> None:
        await self.adapter.close()


def create_server(
    settings: BridgeSettings,
    adapter: AdapterLike | None = None,
) -> tuple[FastMCP, BridgeService]:
    service = BridgeService(settings, adapter)

    @asynccontextmanager
    async def lifespan(_: FastMCP):
        await service.start()
        try:
            yield
        finally:
            await service.close_backend()

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

    @server.tool(description="Open a registered project and create a persistent session.")
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
        client_request_id: str,
        request_hash: str,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        return await service.file_edit(
            ctx,
            project_id,
            session_id,
            path,
            old_string,
            new_string,
            description,
            client_request_id,
            request_hash,
        )

    @server.tool(description="Run one registered formatting command.")
    async def format_run(
        project_id: str,
        session_id: str,
        command_id: str,
        client_request_id: str,
        request_hash: str,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        return await service.format_run(
            ctx,
            project_id,
            session_id,
            command_id,
            client_request_id,
            request_hash,
        )

    @server.tool(description="Run one registered test command.")
    async def test_run(
        project_id: str,
        session_id: str,
        command_id: str,
        client_request_id: str,
        request_hash: str,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        return await service.test_run(
            ctx,
            project_id,
            session_id,
            command_id,
            client_request_id,
            request_hash,
        )

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

    @server.tool(description="Return the persistent state and audit trail of one operation.")
    async def operation_status(
        operation_id: str, session_id: str, ctx: Context | None = None
    ) -> dict[str, Any]:
        return await service.operation_status(ctx, operation_id, session_id)

    @server.tool(description="Consume a one-time approval token and run its operation.")
    async def approval_confirm(
        operation_id: str,
        session_id: str,
        approval_token: str,
        client_request_id: str,
        request_hash: str,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        return await service.approval_confirm(
            ctx,
            operation_id,
            session_id,
            approval_token,
            client_request_id,
            request_hash,
        )

    @server.tool(description="Cancel an operation that is still awaiting approval.")
    async def operation_cancel(
        operation_id: str,
        session_id: str,
        client_request_id: str,
        request_hash: str,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        return await service.operation_cancel(
            ctx,
            operation_id,
            session_id,
            client_request_id,
            request_hash,
        )

    @server.tool(description="Reconcile an unknown mutation as explicitly not executed.")
    async def operation_reconcile(
        operation_id: str,
        session_id: str,
        decision: str,
        evidence: str,
        client_request_id: str,
        request_hash: str,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        return await service.operation_reconcile(
            ctx,
            operation_id,
            session_id,
            decision,
            evidence,
            client_request_id,
            request_hash,
        )

    return server, service


def create_app(
    settings: BridgeSettings,
    adapter: AdapterLike | None = None,
) -> tuple[Any, BridgeService]:
    """Create the ASGI app and service for local contract tests."""

    server, service = create_server(settings, adapter)
    return server.streamable_http_app(), service
