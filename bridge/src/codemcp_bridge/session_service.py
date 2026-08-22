"""Persistent session lifecycle and ownership checks."""

from __future__ import annotations

import uuid

from .db import Database, SessionRecord
from .errors import BridgeError

LOCAL_OWNER_ID = "local-policy"


class SessionService:
    def __init__(self, database: Database, *, owner_id: str = LOCAL_OWNER_ID):
        self._database = database
        self.owner_id = owner_id

    def create(self, project_id: str) -> SessionRecord:
        return self._database.create_session(uuid.uuid4().hex, project_id, self.owner_id)

    def require_active(self, project_id: str, session_id: str | None) -> SessionRecord:
        if not session_id:
            raise BridgeError("SESSION_REQUIRED", "session_id is required for this operation")
        session = self._database.get_session(session_id)
        if session is None or session.project_id != project_id:
            raise BridgeError(
                "SESSION_NOT_FOUND",
                "session_id is not active for this project",
                {"project_id": project_id},
            )
        if session.owner_id != self.owner_id or session.status != "active":
            raise BridgeError(
                "SESSION_NOT_FOUND",
                "session_id is not active",
                {"project_id": project_id, "status": session.status},
            )
        return session

    def close_all(self, reason: str) -> None:
        self._database.close_active_sessions(reason)

    def recover_after_restart(self) -> dict[str, list[str]]:
        return self._database.recover_after_restart()
