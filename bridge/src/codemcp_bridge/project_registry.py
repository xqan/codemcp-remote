"""Project and path authorization for the Bridge."""

from __future__ import annotations

import os
import stat
from pathlib import Path, PurePosixPath

from .errors import BridgeError
from .settings import BridgeSettings, ProjectSpec, normalize_relative_path, to_wsl_path

SENSITIVE_NAMES = {
    ".git",
    ".codemcp",
    "id_rsa",
    "id_ed25519",
    "credentials",
    "password",
    "passwd",
    "secret",
    "secrets",
    "token",
}
SENSITIVE_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".crt", ".cer"}


def _is_reparse_point(path: Path) -> bool:
    try:
        info = path.lstat()
    except OSError:
        return False
    if stat.S_ISLNK(info.st_mode):
        return True
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(getattr(info, "st_file_attributes", 0) & reparse_flag)


def _iter_existing_components(root: Path, candidate: Path):
    current = root
    yield current
    try:
        relative = candidate.relative_to(root)
    except ValueError:
        return
    for part in relative.parts:
        current = current / part
        if current.exists() or current.is_symlink():
            yield current


def _is_sensitive(relative_path: str) -> bool:
    parts = PurePosixPath(relative_path).parts
    for part in parts:
        lower = part.lower()
        if lower in SENSITIVE_NAMES or lower.endswith(tuple(SENSITIVE_SUFFIXES)):
            return True
        if lower == ".env" or lower.startswith(".env."):
            return True
    return False


def is_sensitive_relative_path(relative_path: str) -> bool:
    return _is_sensitive(relative_path)


class ProjectRegistry:
    """Resolve only registered project IDs and safe project-relative paths."""

    def __init__(self, settings: BridgeSettings):
        self._settings = settings
        self._projects = settings.projects

    def get(self, project_id: str) -> ProjectSpec:
        project = self._projects.get(project_id)
        if project is None:
            raise BridgeError(
                "PROJECT_NOT_ALLOWED",
                "project_id is not registered",
                {"project_id": project_id},
            )
        return project

    def resolve_path(
        self,
        project_id: str,
        relative_path: str | None,
        *,
        allow_root: bool = False,
        reject_sensitive: bool = True,
    ) -> tuple[ProjectSpec, Path, str]:
        project = self.get(project_id)
        if relative_path is None or relative_path in {"", "."}:
            if not allow_root:
                raise BridgeError("INVALID_REQUEST", "path is required", {"field": "path"})
            normalized = "."
            candidate = project.root
        else:
            try:
                normalized = normalize_relative_path(relative_path)
            except ValueError as exc:
                raise BridgeError("PATH_ESCAPE", str(exc)) from exc
            if reject_sensitive and _is_sensitive(normalized):
                raise BridgeError(
                    "SENSITIVE_PATH",
                    "access to sensitive paths is denied",
                    {"path": normalized},
                )
            candidate = project.root.joinpath(*PurePosixPath(normalized).parts)

        root = project.root.resolve(strict=False)
        resolved = candidate.resolve(strict=False)
        if root != resolved and root not in resolved.parents:
            raise BridgeError("PATH_ESCAPE", "path escapes the registered project root")
        if any(
            _is_reparse_point(item)
            for item in _iter_existing_components(project.root, candidate)
        ):
            raise BridgeError("PATH_ESCAPE", "symlink or reparse-point paths are denied")
        return project, candidate, normalized

    def worker_path(self, path: Path) -> str:
        if os.name == "nt" and self._settings.codemcp.worker_mode == "wsl2":
            return to_wsl_path(path)
        return str(path)

    @staticmethod
    def relative_path(project: ProjectSpec, path: Path) -> str:
        return path.resolve(strict=False).relative_to(project.root.resolve(strict=False)).as_posix()
