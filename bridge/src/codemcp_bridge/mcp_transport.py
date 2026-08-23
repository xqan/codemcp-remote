"""MCP Streamable HTTP compatibility helpers."""

from __future__ import annotations

import logging

import anyio
from anyio.abc import TaskStatus
from mcp.server.streamable_http import StreamableHTTPServerTransport
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.types import Receive, Scope, Send

logger = logging.getLogger(__name__)

_GRACEFUL_CLOSE_TIMEOUT_SECONDS = 1.0


class BridgeStreamableHTTPSessionManager(StreamableHTTPSessionManager):
    """Avoid MCP 1.x cancel-scope races when closing stateless requests.

    MCP 1.x terminates a stateless transport from the HTTP request task while
    the low-level server is still unwinding its per-request responder task.
    Closing the transport's input side first lets ``Server.run()`` finish its
    receive loop and unwind in the task that owns its cancel scopes. The full
    transport termination remains a bounded fallback for a stuck server task.
    """

    async def _handle_stateless_request(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        http_transport = StreamableHTTPServerTransport(
            mcp_session_id=None,
            is_json_response_enabled=self.json_response,
            event_store=None,
            security_settings=self.security_settings,
        )
        server_finished = anyio.Event()

        async def run_stateless_server(
            *, task_status: TaskStatus[None] = anyio.TASK_STATUS_IGNORED
        ) -> None:
            try:
                async with http_transport.connect() as streams:
                    read_stream, write_stream = streams
                    task_status.started()
                    await self.app.run(
                        read_stream,
                        write_stream,
                        self.app.create_initialization_options(),
                        stateless=True,
                    )
            except Exception:  # pragma: no cover - delegated MCP failure
                logger.exception("Stateless session crashed")
            finally:
                server_finished.set()

        assert self._task_group is not None
        await self._task_group.start(run_stateless_server)

        try:
            await http_transport.handle_request(scope, receive, send)
            # The HTTP response can be delivered one scheduling checkpoint
            # before RequestResponder.__exit__ finishes in the MCP task.
            await anyio.sleep(0)

            # Signal EOF to Server.run without cancelling its responder task.
            # The transport context owns the remaining stream cleanup.
            if http_transport._read_stream_writer is not None:  # noqa: SLF001
                await http_transport._read_stream_writer.aclose()  # noqa: SLF001

            with anyio.move_on_after(_GRACEFUL_CLOSE_TIMEOUT_SECONDS) as close_scope:
                await server_finished.wait()
            if close_scope.cancel_called:
                logger.warning("Timed out waiting for stateless MCP session cleanup")
                await http_transport.terminate()
        except BaseException:
            await http_transport.terminate()
            raise
