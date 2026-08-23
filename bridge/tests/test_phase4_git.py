from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from codemcp_bridge.checkpoint_service import CheckpointService
from codemcp_bridge.db import Database
from codemcp_bridge.errors import BridgeError
from codemcp_bridge.git_guard import GitGuard
from codemcp_bridge.mcp_server import BridgeService
from codemcp_bridge.operation_service import request_hash
from codemcp_bridge.settings import (
    BridgeSettings,
    CodemcpSettings,
    PolicySettings,
    ProjectSpec,
    ServerSettings,
    StorageSettings,
)


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


def _project_spec(project: Path) -> ProjectSpec:
    return ProjectSpec(
        project_id="demo",
        root=project,
        allowed_branches=("main",),
        require_clean_workspace=True,
        codemcp_config=project / "codemcp.toml",
        commands={},
    )


def _settings(project: Path, data_dir: Path) -> BridgeSettings:
    spec = _project_spec(project)
    return BridgeSettings(
        repository_root=project.parent,
        bridge_config_path=project.parent / "bridge.toml",
        projects_config_path=project.parent / "projects.toml",
        server=ServerSettings("127.0.0.1", 46200, "/mcp", "streamable-http"),
        storage=StorageSettings(data_dir, data_dir / "bridge.sqlite3", data_dir / "logs"),
        policy=PolicySettings(False, False, False, True, 1024, 4096, "per-project"),
        codemcp=CodemcpSettings("local", "Ubuntu", None, 10, 10, 5),
        projects={"demo": spec},
    )


class NullAdapter:
    async def call(
        self,
        project: ProjectSpec,
        subtool: str,
        arguments: dict[str, Any],
        *,
        timeout_seconds: float | None = None,
        mutation: bool = False,
    ) -> Any:
        del project, subtool, arguments, timeout_seconds, mutation
        raise AssertionError("the checkpoint tests must not call codemcp")

    def is_active(self, project_id: str) -> bool:
        del project_id
        return False

    async def close(self) -> None:
        return None


@pytest.fixture
def git_project(tmp_path: Path) -> Path:
    project = tmp_path / "phase4 project 中文"
    project.mkdir()
    (project / "src").mkdir()
    (project / "src" / "hello.txt").write_text("hello\n", encoding="utf-8")
    (project / "codemcp.toml").write_text("[commands]\n", encoding="utf-8")
    _git(project, "init", "-b", "main")
    _git(project, "config", "user.name", "Phase 4 test")
    _git(project, "config", "user.email", "phase4@example.invalid")
    _git(project, "add", ".")
    _git(project, "commit", "-m", "test: phase 4 baseline")
    return project


@pytest.mark.asyncio
async def test_checkpoint_records_git_baseline_and_diff(git_project: Path, tmp_path: Path) -> None:
    database = Database(tmp_path / "data" / "bridge.sqlite3")
    database.initialize()
    service = CheckpointService(database, GitGuard())
    spec = _project_spec(git_project)

    checkpoint = await service.create(
        spec,
        session_id="session-1",
        operation_id=None,
        kind="manual",
    )
    before_head = checkpoint.head
    (git_project / "src" / "hello.txt").write_text("changed\n", encoding="utf-8")
    _git(git_project, "add", ".")
    _git(git_project, "commit", "--amend", "--no-edit")

    finalized = await service.finalize(spec, checkpoint)
    assert finalized.before_data["head"] == before_head
    assert finalized.after_data["head"] != before_head
    assert finalized.after_data["changed_files"] == ["src/hello.txt"]
    assert len(finalized.diff_hash) == 64
    assert "changed" in (await GitGuard().diff_from(git_project, checkpoint.ref_name))[0]
    assert database.get_checkpoint(checkpoint.checkpoint_id).diff_hash == finalized.diff_hash

    with pytest.raises(BridgeError) as nested_root:
        await GitGuard().require_worktree_root(git_project / "src")
    assert nested_root.value.code == "PROJECT_NOT_ALLOWED"

    (git_project / "src" / "hello.txt").write_text("dirty\n", encoding="utf-8")
    with pytest.raises(BridgeError) as raised:
        await service.create(
            spec,
            session_id="session-1",
            operation_id=None,
            kind="manual",
        )
    assert raised.value.code == "WORKSPACE_DIRTY"
    _git(git_project, "reset", "--hard", "HEAD")
    database.close()


@pytest.mark.asyncio
async def test_checkpoint_mcp_approval_diff_and_cas_restore(
    git_project: Path, tmp_path: Path
) -> None:
    bridge = BridgeService(_settings(git_project, tmp_path / "data"), adapter=NullAdapter())
    await bridge.start()
    session = bridge.sessions.create("demo")

    created_request = {"project_id": "demo", "session_id": session.session_id}
    pending = await bridge.checkpoint_create(
        None,
        "demo",
        session.session_id,
        "checkpoint-create-1",
        request_hash(created_request),
    )
    assert pending["status"] == "awaiting_approval"
    checkpoint_id = pending["error"]["details"]["operation_id"]
    token = pending["error"]["details"]["approval_token"]
    created = await bridge.approval_confirm(
        None,
        checkpoint_id,
        session.session_id,
        token,
        "checkpoint-approval-1",
        request_hash(
            {
                "operation_id": checkpoint_id,
                "approval_token_digest": request_hash(token),
            }
        ),
    )
    assert created["status"] == "succeeded"
    checkpoint = created["data"]["approved_operation"]["data"]["checkpoint"]
    checkpoint_id = checkpoint["checkpoint_id"]
    baseline_head = checkpoint["before"]["head"]

    _git(git_project, "checkout", "-b", "phase4-race-branch")
    branch_conflict = await bridge.checkpoint_restore(
        None,
        "demo",
        session.session_id,
        checkpoint_id,
        baseline_head,
        "restore-branch-conflict-1",
        request_hash(
            {
                "project_id": "demo",
                "session_id": session.session_id,
                "checkpoint_id": checkpoint_id,
                "expected_head": baseline_head,
            }
        ),
    )
    assert branch_conflict["error"]["code"] == "CHECKPOINT_CONFLICT"
    _git(git_project, "checkout", "main")

    (git_project / "src" / "hello.txt").write_text("external change\n", encoding="utf-8")
    _git(git_project, "add", ".")
    _git(git_project, "commit", "--amend", "--no-edit")
    changed_head = _git(git_project, "rev-parse", "HEAD")

    diff = await bridge.git_diff(None, "demo", session.session_id, checkpoint_id)
    assert diff["status"] == "succeeded"
    assert diff["data"]["text"]
    assert diff["changed_files"] == ["src/hello.txt"]

    restore_request = {
        "project_id": "demo",
        "session_id": session.session_id,
        "checkpoint_id": checkpoint_id,
        "expected_head": changed_head,
    }
    restore_pending = await bridge.checkpoint_restore(
        None,
        "demo",
        session.session_id,
        checkpoint_id,
        changed_head,
        "restore-cas-1",
        request_hash(restore_request),
    )
    restore_operation_id = restore_pending["error"]["details"]["operation_id"]
    restore_token = restore_pending["error"]["details"]["approval_token"]

    (git_project / "src" / "hello.txt").write_text("race\n", encoding="utf-8")
    _git(git_project, "add", ".")
    _git(git_project, "commit", "--amend", "--no-edit")
    raced_head = _git(git_project, "rev-parse", "HEAD")
    conflicted = await bridge.approval_confirm(
        None,
        restore_operation_id,
        session.session_id,
        restore_token,
        "restore-cas-confirm-1",
        request_hash(
            {
                "operation_id": restore_operation_id,
                "approval_token_digest": request_hash(restore_token),
            }
        ),
    )
    assert conflicted["data"]["approved_operation"]["error"]["code"] == ("CHECKPOINT_CONFLICT")
    assert _git(git_project, "rev-parse", "HEAD") == raced_head

    restore_request_2 = {
        "project_id": "demo",
        "session_id": session.session_id,
        "checkpoint_id": checkpoint_id,
        "expected_head": raced_head,
    }
    restore_pending_2 = await bridge.checkpoint_restore(
        None,
        "demo",
        session.session_id,
        checkpoint_id,
        raced_head,
        "restore-cas-2",
        request_hash(restore_request_2),
    )
    restored = await bridge.approval_confirm(
        None,
        restore_pending_2["error"]["details"]["operation_id"],
        session.session_id,
        restore_pending_2["error"]["details"]["approval_token"],
        "restore-cas-confirm-2",
        request_hash(
            {
                "operation_id": restore_pending_2["error"]["details"]["operation_id"],
                "approval_token_digest": request_hash(
                    restore_pending_2["error"]["details"]["approval_token"]
                ),
            }
        ),
    )
    assert restored["status"] == "succeeded"
    assert _git(git_project, "rev-parse", "HEAD") == baseline_head
    assert (git_project / "src" / "hello.txt").read_text(encoding="utf-8") == "hello\n"
    await bridge.close()
