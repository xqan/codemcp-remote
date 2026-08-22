from __future__ import annotations

from pathlib import Path

import pytest

from codemcp_bridge.settings import SettingsError, load_settings


def test_settings_reject_unsafe_phase2_flags(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "bridge.toml").write_text(
        "[server]\n"
        'host = "127.0.0.1"\n'
        "port = 46200\n"
        'path = "/mcp"\n'
        'transport = "streamable-http"\n'
        "\n"
        "[storage]\n"
        'data_dir = ".local"\n'
        'sqlite_file = ".local/bridge.sqlite3"\n'
        'log_dir = ".local/logs"\n'
        "\n"
        "[policy]\n"
        "allow_arbitrary_paths = true\n"
        "allow_arbitrary_commands = false\n"
        "allow_model_calls = false\n"
        "require_clean_workspace = true\n",
        encoding="utf-8",
    )
    (config_dir / "projects.toml").write_text(
        '[projects.demo]\nroot = "../project"\n', encoding="utf-8"
    )

    with pytest.raises(SettingsError, match="must remain false"):
        load_settings(config_dir / "bridge.toml", config_dir / "projects.toml")
