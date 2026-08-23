"""Project and path authorization for the Bridge."""

from __future__ import annotations

import fnmatch
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
SENSITIVE_GLOBS = tuple(
    SENSITIVE_NAMES
    | {"*.env", "*.env.*"}
    | {f"*{suffix}" for suffix in SENSITIVE_SUFFIXES}
)


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
        if any(fnmatch.fnmatchcase(lower, pattern) for pattern in SENSITIVE_GLOBS):
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

    def safe_search_paths(self, project: ProjectSpec, target: Path) -> list[Path]:
        """Return search roots that cannot recursively include sensitive paths.

        codemcp's Grep accepts one include pathspec but no exclude pathspec. Split
        only directories that contain an excluded descendant, keeping the normal
        one-call path for projects without sensitive files.
        """

        try:
            if not target.is_dir():
                return [target]
        except OSError:
            return []
        paths, excluded = self._safe_search_paths(project, target)
        return paths if excluded else [target]

    def _safe_search_paths(
        self, project: ProjectSpec, target: Path
    ) -> tuple[list[Path], bool]:
        try:
            entries = sorted(target.iterdir(), key=lambda item: item.name.lower())
        except OSError:
            return [], True

        safe_children: list[Path] = []
        excluded = False
        for entry in entries:
            relative = entry.relative_to(project.root).as_posix()
            # Git never searches its own metadata directory, so it need not
            # force every otherwise-safe project directory into file-level calls.
            if entry.name.lower() == ".git":
                continue
            if _is_reparse_point(entry) or is_sensitive_relative_path(relative):
                excluded = True
                continue
            try:
                if entry.is_dir():
                    child_paths, child_excluded = self._safe_search_paths(project, entry)
                    safe_children.extend(child_paths)
                    excluded = excluded or child_excluded
                elif entry.is_file():
                    safe_children.append(entry)
                else:
                    excluded = True
            except OSError:
                excluded = True

        if not excluded:
            return [target], False
        return safe_children, True

    @staticmethod
    def relative_path(project: ProjectSpec, path: Path) -> str:
        return path.resolve(strict=False).relative_to(project.root.resolve(strict=False)).as_posix()
