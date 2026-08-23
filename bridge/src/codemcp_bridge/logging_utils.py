"""Centralized, bounded and redacted runtime logging for the Bridge."""

from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import TextIO

LOG_MAX_BYTES = 5 * 1024 * 1024
LOG_BACKUP_COUNT = 3
PROJECT_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_KEY_VALUE_PATTERN = re.compile(
    r"(?i)((?:[\"']?\b(?:CONTROL_PLANE_API_KEY|OPENAI_API_KEY|API_KEY|"
    r"AUTHORIZATION|ACCESS_TOKEN|REFRESH_TOKEN|TOKEN)\b[\"']?)\s*[:=]\s*)"
    r"(\"[^\"]*\"|'[^']*'|[^\s,;]+)"
)
_BEARER_PATTERN = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
_OPENAI_KEY_PATTERN = re.compile(r"(?i)\bsk-[A-Za-z0-9_-]{8,}")


def redact_text(value: str) -> str:
    """Remove common API-key and authorization forms from diagnostic text."""

    redacted = _BEARER_PATTERN.sub("Bearer <redacted>", value)
    redacted = _KEY_VALUE_PATTERN.sub(r"\1<redacted>", redacted)
    return _OPENAI_KEY_PATTERN.sub("<redacted-api-key>", redacted)


class RedactingFormatter(logging.Formatter):
    """Format records and redact the final rendered message and traceback."""

    def format(self, record: logging.LogRecord) -> str:
        return redact_text(super().format(record))


def configure_logging(log_dir: Path) -> Path:
    """Attach the bounded Bridge file handler and return its path."""

    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = (log_dir / "bridge.log").resolve()
    root_logger = logging.getLogger()

    for handler in list(root_logger.handlers):
        existing_path = getattr(handler, "baseFilename", None)
        if existing_path and Path(existing_path).resolve() == log_path:
            root_logger.removeHandler(handler)
            handler.close()

    handler = RotatingFileHandler(
        log_path,
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
        delay=True,
    )
    handler.setFormatter(
        RedactingFormatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(handler)
    return log_path


def _rotate_worker_log(path: Path) -> None:
    if not path.is_file() or path.stat().st_size < LOG_MAX_BYTES:
        return

    for index in range(LOG_BACKUP_COUNT - 1, 0, -1):
        source = Path(f"{path}.{index}")
        destination = Path(f"{path}.{index + 1}")
        if source.is_file():
            if destination.exists():
                destination.unlink()
            source.replace(destination)
    first_backup = Path(f"{path}.1")
    if first_backup.exists():
        first_backup.unlink()
    path.replace(first_backup)


def open_worker_stderr(log_dir: Path, project_id: str) -> TextIO:
    """Open an append-only, rotated stderr file for one codemcp worker."""

    if not PROJECT_ID_PATTERN.fullmatch(project_id):
        raise ValueError("invalid project_id for worker log")
    worker_log_dir = log_dir / "workers"
    worker_log_dir.mkdir(parents=True, exist_ok=True)
    log_path = worker_log_dir / f"{project_id}.stderr.log"
    _rotate_worker_log(log_path)
    return log_path.open("a+", encoding="utf-8")
