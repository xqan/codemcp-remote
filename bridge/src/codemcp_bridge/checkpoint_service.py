"""Bridge-owned Git checkpoints and compare-and-swap restore operations."""

from __future__ import annotations

import string
import uuid
from typing import Any

from .db import CheckpointRecord, Database
from .errors import BridgeError
from .git_guard import GitGuard
from .settings import ProjectSpec


class CheckpointService:
    """Persist checkpoints while keeping all Git mutations narrowly scoped."""

    def __init__(self, database: Database, git: GitGuard):
        self._database = database
        self._git = git

    @staticmethod
    def validate_expected_head(head: str) -> None:
        if (
            not isinstance(head, str)
            or len(head) not in {40, 64}
            or any(character not in string.hexdigits for character in head)
        ):
            raise BridgeError(
                "INVALID_REQUEST",
                "expected_head must be a Git commit hash",
                {"field": "expected_head"},
            )

    @staticmethod
    def _ref_name(checkpoint_id: str) -> str:
        return f"refs/codemcp-remote/checkpoints/{checkpoint_id}"

    async def create(
        self,
        project: ProjectSpec,
        *,
        session_id: str | None,
        operation_id: str | None,
        kind: str,
    ) -> CheckpointRecord:
        if kind not in {"manual", "mutation", "rollback_safety"}:
            raise BridgeError("INVALID_REQUEST", "invalid checkpoint kind")
        await self._git.require_worktree_root(project.root)
        snapshot = await self._git.snapshot(project.root)
        if snapshot.dirty:
            raise BridgeError(
                "WORKSPACE_DIRTY",
                "checkpoint requires a clean workspace",
                {"changed_files": list(snapshot.changed_files)},
            )
        checkpoint_id = uuid.uuid4().hex
        ref_name = self._ref_name(checkpoint_id)
        await self._git.create_checkpoint_ref(project.root, ref_name, snapshot.head)
        try:
            return self._database.create_checkpoint(
                checkpoint_id=checkpoint_id,
                project_id=project.project_id,
                session_id=session_id,
                operation_id=operation_id,
                owner_id="local-policy",
                kind=kind,
                branch=snapshot.branch,
                head=snapshot.head,
                ref_name=ref_name,
                before_data=snapshot.as_data(),
            )
        except Exception:
            try:
                await self._git.delete_checkpoint_ref(project.root, ref_name)
            except BridgeError:
                pass
            raise

    async def finalize(
        self,
        project: ProjectSpec,
        checkpoint: CheckpointRecord,
    ) -> CheckpointRecord:
        after = await self._git.snapshot(project.root)
        changed_files = await self._git.diff_names_from(project.root, checkpoint.ref_name)
        diff, truncated = await self._git.diff_from(project.root, checkpoint.ref_name)
        after_data = after.as_data()
        after_data["changed_files"] = list(changed_files)
        after_data["diff_truncated"] = truncated
        return self._database.finalize_checkpoint(
            checkpoint.checkpoint_id,
            after_data=after_data,
            diff_hash=self._git.diff_hash(diff),
        )

    async def verify_ref(self, project: ProjectSpec, checkpoint: CheckpointRecord) -> None:
        try:
            resolved = await self._git.resolve_checkpoint_ref(project.root, checkpoint.ref_name)
        except BridgeError as exc:
            raise BridgeError(
                "CHECKPOINT_INVALID",
                "checkpoint ref is missing or invalid",
                {"checkpoint_id": checkpoint.checkpoint_id},
            ) from exc
        if resolved.lower() != checkpoint.head.lower():
            raise BridgeError(
                "CHECKPOINT_INVALID",
                "checkpoint ref no longer points to its recorded commit",
                {
                    "checkpoint_id": checkpoint.checkpoint_id,
                    "recorded_head": checkpoint.head,
                    "actual_head": resolved,
                },
            )

    def get_for_session(
        self,
        checkpoint_id: str,
        *,
        project_id: str,
        session_id: str,
    ) -> CheckpointRecord:
        checkpoint = self._database.get_checkpoint(checkpoint_id)
        if (
            checkpoint is None
            or checkpoint.owner_id != "local-policy"
            or checkpoint.project_id != project_id
            or checkpoint.session_id != session_id
        ):
            raise BridgeError(
                "CHECKPOINT_NOT_FOUND",
                "checkpoint_id is not available to this project session",
                {"checkpoint_id": checkpoint_id},
            )
        return checkpoint

    def for_operation(self, operation_id: str) -> list[dict[str, Any]]:
        checkpoints = self._database.list_checkpoints(operation_id=operation_id)
        return [self.summary(checkpoint) for checkpoint in checkpoints]

    def mark_restored(self, checkpoint_id: str) -> CheckpointRecord:
        return self._database.mark_checkpoint_restored(checkpoint_id)

    @staticmethod
    def summary(checkpoint: CheckpointRecord) -> dict[str, Any]:
        before = checkpoint.before_data
        after = checkpoint.after_data
        result: dict[str, Any] = {
            "checkpoint_id": checkpoint.checkpoint_id,
            "kind": checkpoint.kind,
            "status": checkpoint.status,
            "branch": checkpoint.branch,
            "ref_name": checkpoint.ref_name,
            "before": {
                "branch": before.get("branch"),
                "head": before.get("head"),
                "dirty": before.get("dirty"),
                "changed_files": before.get("changed_files", []),
                "file_hash_count": len(before.get("file_hashes", {})),
            },
            "diff_hash": checkpoint.diff_hash,
        }
        if after is not None:
            result["after"] = {
                "branch": after.get("branch"),
                "head": after.get("head"),
                "dirty": after.get("dirty"),
                "changed_files": after.get("changed_files", []),
                "file_hash_count": len(after.get("file_hashes", {})),
            }
            result["diff_truncated"] = bool(after.get("diff_truncated", False))
        return result
