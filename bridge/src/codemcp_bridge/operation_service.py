"""Operation state machine, idempotency and restart-safe result handling."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

from .db import ActiveOperationConflict, Database, OperationRecord
from .errors import BridgeError, error_payload

REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
REQUEST_HASH_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")


def request_hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _persistable_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Keep retry metadata while never persisting a plaintext approval token."""

    persisted = json.loads(json.dumps(payload, ensure_ascii=False))
    error = persisted.get("error")
    if isinstance(error, dict):
        details = error.get("details")
        if isinstance(details, dict):
            details.pop("approval_token", None)
    return persisted


@dataclass(frozen=True, slots=True)
class OperationStart:
    record: OperationRecord
    replay_payload: dict[str, Any] | None

    @property
    def is_replay(self) -> bool:
        return self.replay_payload is not None


class OperationService:
    def __init__(self, database: Database):
        self._database = database

    def start(
        self,
        *,
        operation_id: str,
        project_id: str,
        session_id: str | None,
        kind: str,
        mutation: bool,
        client_request_id: str,
        supplied_request_hash: str,
        input_data: dict[str, Any],
    ) -> OperationStart:
        if mutation and not client_request_id:
            raise BridgeError(
                "INVALID_REQUEST", "client_request_id is required for mutation operations"
            )
        if not REQUEST_ID_PATTERN.fullmatch(client_request_id):
            raise BridgeError("INVALID_REQUEST", "client_request_id has an invalid format")
        if not REQUEST_HASH_PATTERN.fullmatch(supplied_request_hash):
            raise BridgeError("INVALID_REQUEST", "request_hash must be a SHA-256 hex digest")
        canonical_request_hash = request_hash(input_data)
        if supplied_request_hash.lower() != canonical_request_hash:
            raise BridgeError(
                "INVALID_REQUEST",
                "request_hash does not match the canonical operation input",
                {"field": "request_hash"},
            )
        try:
            record, existing = self._database.create_operation(
                operation_id=operation_id,
                project_id=project_id,
                session_id=session_id,
                owner_id="local-policy",
                client_request_id=client_request_id,
                request_hash=canonical_request_hash,
                kind=kind,
                mutation=mutation,
                input_data=input_data,
            )
        except ActiveOperationConflict as exc:
            raise BridgeError(
                "OPERATION_BLOCKED",
                "another mutation operation blocks this project",
                {
                    "operation_id": exc.operation.operation_id,
                    "state": exc.operation.state,
                },
            ) from exc
        if existing:
            if record.request_hash != canonical_request_hash:
                raise BridgeError(
                    "IDEMPOTENCY_CONFLICT",
                    "client_request_id was already used with a different request_hash",
                    {"operation_id": record.operation_id},
                )
            if record.result_data is not None:
                return OperationStart(record, record.result_data)
            if record.state == "unknown":
                return OperationStart(record, self._unknown_payload(record))
            if record.state in {"failed", "cancelled"} and record.error_data is not None:
                return OperationStart(record, self._error_from_record(record))
            raise BridgeError(
                "OPERATION_IN_PROGRESS",
                "the operation for this client_request_id is still active",
                {"operation_id": record.operation_id, "state": record.state},
                retryable=True,
                status="running",
            )
        record = self._database.transition_operation(
            record.operation_id, "validated", expected_state="received"
        )
        return OperationStart(record, None)

    def dispatch(self, operation_id: str, *, from_state: str = "validated") -> OperationRecord:
        record = self._database.transition_operation(
            operation_id, "dispatched", expected_state=from_state
        )
        return self._database.transition_operation(
            operation_id, "running", expected_state=record.state
        )

    def await_approval(
        self, operation_id: str, *, error_data: dict[str, Any]
    ) -> OperationRecord:
        safe_error = _persistable_payload({"error": error_data}).get("error", {})
        return self._database.transition_operation(
            operation_id,
            "awaiting_approval",
            expected_state="validated",
            error_data=safe_error,
        )

    def finish(
        self,
        operation_id: str,
        *,
        state: str,
        payload: dict[str, Any],
    ) -> OperationRecord:
        error = payload.get("error")
        safe_error = (
            _persistable_payload({"error": error}).get("error")
            if isinstance(error, dict)
            else None
        )
        return self._database.transition_operation(
            operation_id,
            state,
            result_data=_persistable_payload(payload),
            error_data=safe_error,
        )

    def replay_or_none(self, start: OperationStart) -> dict[str, Any] | None:
        return start.replay_payload

    def operation(self, operation_id: str) -> OperationRecord:
        record = self._database.get_operation(operation_id)
        if record is None:
            raise BridgeError("OPERATION_NOT_FOUND", "operation_id is not known")
        return record

    def operation_payload(self, record: OperationRecord) -> dict[str, Any]:
        if record.result_data is not None:
            return record.result_data
        if record.error_data is not None:
            return self._error_from_record(record)
        return {
            "operation_id": record.operation_id,
            "project_id": record.project_id,
            "session_id": record.session_id,
            "status": record.state,
            "data": {},
            "error": None,
        }

    def _unknown_payload(self, record: OperationRecord) -> dict[str, Any]:
        return error_payload(
            request_id=record.client_request_id,
            session_id=record.session_id,
            project_id=record.project_id,
            operation_id=record.operation_id,
            error=BridgeError(
                "UNKNOWN_SIDE_EFFECT",
                "mutation outcome is unknown and requires reconciliation",
                {"operation_id": record.operation_id},
                status="unknown",
            ),
        )

    @staticmethod
    def _error_from_record(record: OperationRecord) -> dict[str, Any]:
        error_data = record.error_data or {
            "code": "BACKEND_UNAVAILABLE",
            "message": "operation failed",
            "details": {},
            "retryable": False,
        }
        return {
            "request_id": record.client_request_id,
            "session_id": record.session_id,
            "project_id": record.project_id,
            "operation_id": record.operation_id,
            "status": record.state,
            "changed_files": [],
            "truncated": False,
            "data": {},
            "error": error_data,
        }
