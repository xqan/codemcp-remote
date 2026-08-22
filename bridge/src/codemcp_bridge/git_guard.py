"""Bounded Git inspection and mutation preconditions."""

from __future__ import annotations

import asyncio
import os
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
        )
        changed_files = tuple(
            line[3:].strip() for line in porcelain.splitlines() if len(line) >= 3
        )
        return GitStatus(
            branch=branch,
            head=head,
            dirty=bool(changed_files),
            changed_files=changed_files,
        )

    async def diff(self, project_root: Path) -> tuple[str, bool]:
        changed_names = await self._run(
            project_root,
            "diff",
            "--no-ext-diff",
            "--no-renames",
            "--name-only",
            "-z",
        )
        sensitive_names = [
            name for name in changed_names.split("\0") if name and is_sensitive_relative_path(name)
        ]
        if sensitive_names:
            raise BridgeError(
                "SENSITIVE_PATH",
                "diff includes sensitive paths and is not exposed",
                {"paths": sensitive_names},
            )
        output = await self._run(project_root, "diff", "--no-ext-diff", "--unified=3")
        return _truncate_text(output, self._max_output_bytes)
