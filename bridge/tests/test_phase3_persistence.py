from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from codemcp_bridge.approval_service import ApprovalService
from codemcp_bridge.db import Database
from codemcp_bridge.errors import BridgeError
from codemcp_bridge.operation_service import OperationService, request_hash
from codemcp_bridge.session_service import SessionService


def _database(tmp_path: Path) -> Database:
    database = Database(tmp_path / "bridge.sqlite3")
    database.initialize()
    return database


def _start(
    operations: OperationService,
    *,
    operation_id: str,
    project_id: str = "demo",
    session_id: str | None = "session-1",
    client_request_id: str | None = None,
    mutation: bool = True,
) -> object:
    input_data = {"operation_id": operation_id, "project_id": project_id}
    client_id = client_request_id or f"request-{operation_id}"
    return operations.start(
        operation_id=operation_id,
        project_id=project_id,
        session_id=session_id,
        kind="file_edit" if mutation else "file_read",
        mutation=mutation,
        client_request_id=client_id,
        supplied_request_hash=request_hash(input_data),
        input_data=input_data,
    ).record


def test_schema_migrations_are_idempotent(tmp_path: Path) -> None:
    database = _database(tmp_path)
    with sqlite3.connect(database.path) as connection:
        assert connection.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall() == [(1,), (2,), (3,)]
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='audit_events'"
        ).fetchone() == ("audit_events",)
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='checkpoints'"
        ).fetchone() == ("checkpoints",)

    database.close()
    database.initialize()
    with sqlite3.connect(database.path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM schema_migrations").fetchone() == (3,)
    database.close()


def test_idempotency_replays_without_repeating_and_detects_hash_conflict(
    tmp_path: Path,
) -> None:
    database = _database(tmp_path)
    operations = OperationService(database)
    first = _start(operations, operation_id="op-1", client_request_id="edit-1")
    operations.dispatch(first.operation_id)
    payload = {
        "operation_id": first.operation_id,
        "status": "succeeded",
        "data": {"changed": True},
        "error": None,
    }
    operations.finish(first.operation_id, state="succeeded", payload=payload)

    replay = operations.start(
        operation_id="op-retry",
        project_id="demo",
        session_id="session-1",
        kind="file_edit",
        mutation=True,
        client_request_id="edit-1",
        supplied_request_hash=request_hash({"operation_id": "op-1", "project_id": "demo"}),
        input_data={"operation_id": "op-retry", "project_id": "demo"},
    )
    assert replay.is_replay
    assert replay.replay_payload == payload
    assert replay.record.operation_id == first.operation_id

    with pytest.raises(BridgeError) as conflict:
        operations.start(
            operation_id="op-conflict",
            project_id="demo",
            session_id="session-1",
            kind="file_edit",
            mutation=True,
            client_request_id="edit-1",
            supplied_request_hash="0" * 64,
            input_data={"different": True},
        )
    assert conflict.value.code == "IDEMPOTENCY_CONFLICT"
    database.close()


def test_project_mutation_lock_covers_validated_and_unknown_states(tmp_path: Path) -> None:
    database = _database(tmp_path)
    operations = OperationService(database)
    first = _start(operations, operation_id="op-1")

    with pytest.raises(BridgeError) as blocked:
        _start(operations, operation_id="op-2")
    assert blocked.value.code == "OPERATION_BLOCKED"

    operations.finish(
        first.operation_id,
        state="failed",
        payload={"operation_id": first.operation_id, "status": "failed", "error": None},
    )
    second = _start(operations, operation_id="op-2")
    operations.dispatch(second.operation_id)
    operations.finish(
        second.operation_id,
        state="unknown",
        payload={
            "operation_id": second.operation_id,
            "status": "unknown",
            "error": {"code": "UNKNOWN_SIDE_EFFECT"},
        },
    )
    with pytest.raises(BridgeError) as unknown_block:
        _start(operations, operation_id="op-3")
    assert unknown_block.value.code == "OPERATION_BLOCKED"
    operations.finish(
        second.operation_id,
        state="failed",
        payload={
            "operation_id": second.operation_id,
            "status": "failed",
            "error": {"code": "BRIDGE_RESTARTED"},
        },
    )
    assert _start(operations, operation_id="op-3").state == "validated"
    database.close()


def test_restart_blocks_sessions_and_classifies_in_flight_operations(tmp_path: Path) -> None:
    database = _database(tmp_path)
    sessions = SessionService(database)
    session = sessions.create("demo")
    operations = OperationService(database)
    pre_dispatch = _start(operations, operation_id="op-pre", session_id=session.session_id)
    in_flight = _start(operations, operation_id="op-flight", project_id="other")
    operations.dispatch(in_flight.operation_id)
    database.close()

    recovered_database = Database(database.path)
    recovered_database.initialize()
    recovered = recovered_database.recover_after_restart()
    assert recovered["sessions_blocked"] == [session.session_id]
    assert recovered["operations_failed"] == [pre_dispatch.operation_id]
    assert recovered["operations_unknown"] == [in_flight.operation_id]
    assert recovered_database.get_session(session.session_id).status == "blocked"
    assert recovered_database.get_operation(pre_dispatch.operation_id).error_data["code"] == (
        "BRIDGE_RESTARTED"
    )
    assert recovered_database.get_operation(in_flight.operation_id).state == "unknown"
    recovered_database.close()


def test_restart_cancels_pending_approval_and_does_not_leave_lock(tmp_path: Path) -> None:
    database = _database(tmp_path)
    operations = OperationService(database)
    approval_service = ApprovalService(database)
    operation = _start(operations, operation_id="op-approval")
    grant = approval_service.issue(operation, action="format:format")
    operations.await_approval(
        operation.operation_id,
        error_data={
            "code": "APPROVAL_REQUIRED",
            "details": {"approval_token": grant.token},
        },
    )
    database.close()

    recovered_database = Database(database.path)
    recovered_database.initialize()
    recovered = recovered_database.recover_after_restart()
    assert recovered["operations_cancelled"] == [operation.operation_id]
    recovered_operation = recovered_database.get_operation(operation.operation_id)
    assert recovered_operation.state == "cancelled"
    assert recovered_operation.error_data["code"] == "BRIDGE_RESTARTED"
    with sqlite3.connect(recovered_database.path) as connection:
        approval_id, status = connection.execute(
            "SELECT approval_id, status FROM approvals WHERE operation_id=?",
            (operation.operation_id,),
        ).fetchone()
        assert status == "cancelled"
    assert approval_id in recovered["approvals_cancelled"]
    assert "approval_token" not in recovered_operation.error_data.get("details", {})
    event_types = {
        event["event_type"]
        for event in recovered_database.list_audit_events(operation_id=operation.operation_id)
    }
    assert "approval.recovered_cancelled" in event_types
    recovered_database.close()


def test_approval_is_one_time_and_token_is_not_persisted(tmp_path: Path) -> None:
    database = _database(tmp_path)
    operations = OperationService(database)
    approval_service = ApprovalService(database)
    operation = _start(operations, operation_id="op-approval")
    grant = approval_service.issue(operation, action="format:format")
    operations.await_approval(
        operation.operation_id,
        error_data={
            "code": "APPROVAL_REQUIRED",
            "details": {"approval_token": grant.token},
        },
    )
    stored = database.get_operation(operation.operation_id)
    assert "approval_token" not in stored.error_data.get("details", {})

    with pytest.raises(BridgeError) as invalid:
        approval_service.consume(operation.operation_id, "wrong-token")
    assert invalid.value.code == "APPROVAL_INVALID"
    approval_service.consume(operation.operation_id, grant.token)
    with pytest.raises(BridgeError) as reused:
        approval_service.consume(operation.operation_id, grant.token)
    assert reused.value.code == "APPROVAL_ALREADY_USED"
    database.close()
