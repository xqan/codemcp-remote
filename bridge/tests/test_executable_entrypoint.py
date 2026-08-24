from __future__ import annotations

import sys
from pathlib import Path

import codemcp_bridge.main as main_module


def test_runtime_root_uses_executable_directory_when_frozen(tmp_path: Path) -> None:
    executable = tmp_path / "dist" / "codemcp-remote.exe"

    assert main_module.runtime_root(frozen=True, executable=executable) == executable.parent.resolve()


def test_internal_worker_dispatch_skips_bridge_configuration(
    monkeypatch,
) -> None:
    calls: list[str] = []

    monkeypatch.setattr(sys, "argv", ["codemcp-remote.exe", "_worker"])
    monkeypatch.setattr(main_module, "native_worker_main", lambda: calls.append("worker"))

    assert main_module.main() == 0
    assert calls == ["worker"]
    assert sys.argv == ["codemcp-remote.exe"]
