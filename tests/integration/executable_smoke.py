from __future__ import annotations

import argparse
import asyncio
import os
import tempfile
from pathlib import Path

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


async def _run(executable: Path, repository_root: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="codemcp-exe-smoke-") as home:
        environment = os.environ.copy()
        environment["PYTHONIOENCODING"] = "utf-8"
        environment["HOME"] = home
        environment["USERPROFILE"] = home

        server = StdioServerParameters(
            command=str(executable),
            args=["_worker"],
            env=environment,
            cwd=str(repository_root),
        )
        async with stdio_client(server) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                initialized = await asyncio.wait_for(session.initialize(), timeout=30)
                assert initialized.serverInfo.name == "codemcp"

                tools = await asyncio.wait_for(session.list_tools(), timeout=30)
                assert [tool.name for tool in tools.tools] == ["codemcp"]

                read_result = await asyncio.wait_for(
                    session.call_tool(
                        "codemcp",
                        arguments={
                            "subtool": "ReadFile",
                            "path": str(repository_root / "README.md"),
                            "chat_id": "exe-smoke",
                        },
                    ),
                    timeout=30,
                )
                assert not read_result.isError
                assert "codemcp-remote" in "\n".join(
                    block.text for block in read_result.content if hasattr(block, "text")
                )

                ls_result = await asyncio.wait_for(
                    session.call_tool(
                        "codemcp",
                        arguments={
                            "subtool": "LS",
                            "path": str(repository_root),
                            "chat_id": "exe-smoke",
                        },
                    ),
                    timeout=30,
                )
                assert not ls_result.isError
                assert "README.md" in "\n".join(
                    block.text for block in ls_result.content if hasattr(block, "text")
                )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("executable", type=Path)
    parser.add_argument("repository_root", type=Path)
    args = parser.parse_args()

    executable = args.executable.resolve()
    repository_root = args.repository_root.resolve()
    if not executable.is_file():
        raise SystemExit(f"missing executable: {executable}")
    if not repository_root.is_dir():
        raise SystemExit(f"missing repository root: {repository_root}")

    asyncio.run(_run(executable, repository_root))
    print("frozen worker smoke: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
