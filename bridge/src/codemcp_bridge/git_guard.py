"""Bounded Git inspection and mutation preconditions."""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
import signal
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .errors import BridgeError
from .project_registry import is_sensitive_relative_path


@dataclass(frozen=True, slots=True)
class GitStatus:
    branch: str
    head: str
    dirty: bool
    changed_files: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class GitSnapshot:
    branch: str
    head: str
    dirty: bool
    changed_files: tuple[str, ...]
    file_hashes: dict[str, str]

    def as_data(self) -> dict[str, object]:
        return {
            "branch": self.branch,
            "head": self.head,
            "dirty": self.dirty,
            "changed_files": list(self.changed_files),
            "file_hashes": dict(self.file_hashes),
        }


_CHECKPOINT_REF_PATTERN = re.compile(
    r"^refs/codemcp-remote/checkpoints/[0-9a-f]{32}$"
)
_HEAD_PATTERN = re.compile(r"^[0-9a-fA-F]{40,64}$")


def _truncate_text(value: str, max_bytes: int) -> tuple[str, bool]:
    encoded = value.encode("utf-8", errors="replace")
    if len(encoded) <= max_bytes:
        return value, False
    return encoded[:max_bytes].decode("utf-8", errors="ignore"), True


async def _terminate_process(process: asyncio.subprocess.Process) -> None:
    if process.returncode is not None:
        return
    if os.name == "nt":
        try:
            killer = await asyncio.create_subprocess_exec(
                "taskkill",
                "/PID",
                str(process.pid),
                "/T",
                "/F",
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            await asyncio.wait_for(killer.communicate(), timeout=5)
        except (TimeoutError, OSError):
            process.kill()
    else:
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        except (OSError, ProcessLookupError):
            process.kill()
    try:
        await asyncio.wait_for(process.wait(), timeout=5)
    except (TimeoutError, ProcessLookupError):
        try:
            process.kill()
        except ProcessLookupError:
            return
        await process.wait()


class GitGuard:
    """Run fixed Git inspection commands with stdin closed and bounded output."""

    def __init__(self, *, timeout_seconds: float = 30, max_output_bytes: int = 262_144):
        self._timeout_seconds = timeout_seconds
        self._max_output_bytes = max_output_bytes

    async def _run(self, project_root: Path, *arguments: str) -> str:
        process_kwargs: dict[str, object] = {}
        if os.name != "nt":
            process_kwargs["start_new_session"] = True
        try:
            process = await asyncio.create_subprocess_exec(
                "git",
                *arguments,
                cwd=project_root,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                **process_kwargs,
            )
        except OSError as exc:
            raise BridgeError(
                "BACKEND_UNAVAILABLE",
                "Git is not available for the registered project",
                {"project_id": None},
                retryable=True,
                status="failed",
            ) from exc
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=self._timeout_seconds
            )
        except TimeoutError as exc:
            await _terminate_process(process)
            raise BridgeError(
                "BACKEND_UNAVAILABLE",
                "Git command timed out",
                {"command": ["git", *arguments]},
                retryable=True,
                status="failed",
            ) from exc
        output = stdout.decode("utf-8", errors="replace")
        error_output = stderr.decode("utf-8", errors="replace")
        if process.returncode != 0:
            detail, _ = _truncate_text(error_output, 2_000)
            raise BridgeError(
                "BACKEND_UNAVAILABLE",
                "Git command failed",
                {
                    "command": ["git", *arguments],
                    "returncode": process.returncode,
                    "stderr": detail,
                },
                status="failed",
            )
        return output

    async def status(self, project_root: Path) -> GitStatus:
        branch = (await self._run(project_root, "rev-parse", "--abbrev-ref", "HEAD")).strip()
        head = (await self._run(project_root, "rev-parse", "HEAD")).strip()
        porcelain = await self._run(
            project_root,
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
            "-z",
        )
        entries = porcelain.split("\0")
        changed: list[str] = []
        index = 0
        while index < len(entries):
            entry = entries[index]
            if len(entry) < 3:
                index += 1
                continue
            status_code = entry[:2]
            changed.append(entry[3:])
            if "R" in status_code or "C" in status_code:
                index += 1
                if index < len(entries) and entries[index]:
                    changed.append(entries[index])
            index += 1
        changed_files = tuple(changed)
        return GitStatus(
            branch=branch,
            head=head,
            dirty=bool(changed_files),
            changed_files=changed_files,
        )

    async def require_worktree_root(self, project_root: Path) -> None:
        actual = Path(
            (await self._run(project_root, "rev-parse", "--show-toplevel")).strip()
        ).resolve(strict=False)
        expected = project_root.resolve(strict=False)
        if os.path.normcase(str(actual)) != os.path.normcase(str(expected)):
            raise BridgeError(
                "PROJECT_NOT_ALLOWED",
                "registered project root must be the Git worktree root",
                {"expected_root": str(expected), "actual_root": str(actual)},
            )

    async def snapshot(self, project_root: Path) -> GitSnapshot:
        status = await self.status(project_root)
        tree = await self._run(project_root, "ls-tree", "-r", "-z", "--full-tree", "HEAD")
        file_hashes: dict[str, str] = {}
        for entry in tree.split("\0"):
            if "\t" not in entry:
                continue
            header, path = entry.split("\t", 1)
            fields = header.split()
            if len(fields) == 3 and fields[1] == "blob":
                file_hashes[path] = fields[2]
        return GitSnapshot(
            branch=status.branch,
            head=status.head,
            dirty=status.dirty,
            changed_files=status.changed_files,
            file_hashes=file_hashes,
        )

    @staticmethod
    def diff_hash(diff: str) -> str:
        return hashlib.sha256(diff.encode("utf-8", errors="replace")).hexdigest()

    @staticmethod
    def _require_checkpoint_ref(ref_name: str) -> None:
        if not _CHECKPOINT_REF_PATTERN.fullmatch(ref_name):
            raise BridgeError("CHECKPOINT_INVALID", "checkpoint ref is not Bridge-owned")

    @staticmethod
    def _require_head(head: str) -> None:
        if not _HEAD_PATTERN.fullmatch(head):
            raise BridgeError("CHECKPOINT_INVALID", "checkpoint head is not a Git commit")

    @staticmethod
    def _reject_sensitive_names(names: tuple[str, ...] | list[str]) -> None:
        sensitive_names = [name for name in names if is_sensitive_relative_path(name)]
        if sensitive_names:
            raise BridgeError(
                "SENSITIVE_PATH",
                "diff includes sensitive paths and is not exposed",
                {"paths": sensitive_names},
            )

    async def create_checkpoint_ref(self, project_root: Path, ref_name: str, head: str) -> None:
        self._require_checkpoint_ref(ref_name)
        self._require_head(head)
        await self._run(project_root, "update-ref", "--no-deref", ref_name, head)

    async def delete_checkpoint_ref(self, project_root: Path, ref_name: str) -> None:
        self._require_checkpoint_ref(ref_name)
        await self._run(project_root, "update-ref", "--no-deref", "-d", ref_name)

    async def resolve_checkpoint_ref(self, project_root: Path, ref_name: str) -> str:
        self._require_checkpoint_ref(ref_name)
        resolved = (
            await self._run(
                project_root,
                "rev-parse",
                "--verify",
                f"{ref_name}^{{commit}}",
            )
        ).strip()
        self._require_head(resolved)
        return resolved

    async def reset_to_checkpoint(self, project_root: Path, ref_name: str) -> None:
        self._require_checkpoint_ref(ref_name)
        await self._run(project_root, "reset", "--hard", ref_name)

    async def diff(self, project_root: Path) -> tuple[str, bool]:
        status = await self.status(project_root)
        self._reject_sensitive_names(status.changed_files)
        changed_names = await self._run(
            project_root,
            "diff",
            "--no-ext-diff",
            "--no-renames",
            "--name-only",
            "-z",
            "HEAD",
            "--",
        )
        self._reject_sensitive_names([name for name in changed_names.split("\0") if name])
        output = await self._run(
            project_root,
            "diff",
            "--no-ext-diff",
            "--no-renames",
            "--unified=3",
            "HEAD",
            "--",
        )
        return _truncate_text(output, self._max_output_bytes)

    async def diff_names_from(self, project_root: Path, ref_name: str) -> tuple[str, ...]:
        self._require_checkpoint_ref(ref_name)
        status = await self.status(project_root)
        self._reject_sensitive_names(status.changed_files)
        changed_names = await self._run(
            project_root,
            "diff",
            "--no-ext-diff",
            "--no-renames",
            "--name-only",
            "-z",
            ref_name,
            "--",
        )
        names = tuple(name for name in changed_names.split("\0") if name)
        self._reject_sensitive_names(names)
        return names

    async def diff_from(self, project_root: Path, ref_name: str) -> tuple[str, bool]:
        self._require_checkpoint_ref(ref_name)
        await self.diff_names_from(project_root, ref_name)
        output = await self._run(
            project_root,
            "diff",
            "--no-ext-diff",
            "--no-renames",
            "--unified=3",
            ref_name,
            "--",
        )
        return _truncate_text(output, self._max_output_bytes)
