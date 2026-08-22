# codemcp Phase 1 兼容性矩阵

## 结论

固定的 `codemcp==0.3.0` 可以作为 stdio MCP worker 启动，并通过
`initialize`、`tools/list` 和不触发 Git 的 `ReadFile`。在当前 Windows 11
原生环境中，所有需要调用 Git 的子工具都会在 MCP stdio worker 内超时，因而
不能直接作为本项目的写入后端使用。

本阶段的平台决策是：暂不支持 Windows 原生 mutation；下一轮优先验证 WSL2，
若 WSL2 不能满足 Windows 路径与进程要求，则维护一个最小 codemcp fork。当前
机器的 WSL2 命令存在，但 `wsl --status` 和 `wsl --list --verbose` 均返回
`E_ACCESSDENIED`，所以 WSL2 结论仍未完成。

## 版本和验证环境

- 上游仓库：[ezyang/codemcp](https://github.com/ezyang/codemcp)
- Release/tag：`0.3.0`
- Release commit：`683e6ec29b15b91ec12430afabf5a45ed57d2489`
- Python：`3.14.7`（由 uv 管理；项目要求 `>=3.12`）
- Windows：Windows 11，build `26200`
- Git：`2.51.0.windows.1`
- MCP SDK：`1.29.0`
- codemcp：`0.3.0`
- 安装来源：PyPI；版本和 wheel/sdist SHA-256 已写入 `bridge/uv.lock`

GitHub 的 release 页面将 `0.3.0` tag 映射到上述 `683e6ec` commit；本机
`git ls-remote` 因 Windows Schannel 凭据错误未能完成远程复核。

## MCP 合约

探针使用 MCP SDK 的 `stdio_client` 和 `ClientSession`，为每个 worker 设置
独立的临时用户目录，避免写入操作员 profile。实际结果如下：

| 检查项 | Windows 原生结果 | 实际观察 |
|---|---|---|
| worker 启动 | PASS | `python -m codemcp` 正常启动 |
| `initialize` | PASS | protocol `2025-11-25`，server name `codemcp` |
| `tools/list` | PASS | 只有一个 MCP tool：`codemcp` |
| 输入 schema | PASS | 只有 `subtool` required；路径、内容、命令和 chat id 均为可选字段 |
| 输出 schema | PASS | `result: string` |
| `ReadFile` | PASS | 中文、空格和长嵌套路径下可读 |
| worker 关闭/重启 | PASS | context 关闭后可以重新 initialize |
| 两个 stdio worker 并行启动 | PASS | 两个独立 worker 均可发现工具 |
| 端口冲突 | N/A | stdio transport 不监听端口 |

实际暴露的是一个 `codemcp` 工具，`subtool` 值为：

`InitProject`、`ReadFile`、`WriteFile`、`EditFile`、`LS`、`Grep`、`RunCommand`。

`Format` 不是实际的独立 subtool；调用它会返回 `Unknown subtool: Format`。
格式化只能通过登记在 `codemcp.toml` 的 `RunCommand` 命令表达。

## 工具和 Git 行为

| 能力 | 结果 | 说明 |
|---|---|---|
| `InitProject` | MCP Windows blocked；直接 Python 调用 PASS | 直接调用会读取 `project_prompt`，生成 `codemcp-id`，并创建空 Git commit |
| `LS` | blocked | 首先调用 `is_git_repository()`，MCP worker 内无响应 |
| `Grep` | blocked | 使用 Git 检查和 `git grep` |
| `EditFile` | 未完成 | 写入前的 Git 检查无法返回 |
| `WriteFile` | 未完成 | 写入前的 Git 检查无法返回 |
| `RunCommand` | 未完成 | 在 Git 项目中先做 Git snapshot；配置命令未进入执行阶段 |
| stdout/stderr/退出码 | 源码已确认，MCP e2e 未完成 | `run_code_command` 会格式化成功/失败输出，但 Windows Git blocker 阻止端到端验证 |
| timeout | 不满足要求 | `shell.run_command` 有可选 `wait_time`，但 `run_code_command` 调用时不传 timeout，默认无限等待 |
| crash recovery | 未完成 | 已验证正常退出、重启和重复启动；未完成强制崩溃后的恢复测试 |

### Windows blocker

`codemcp 0.3.0` 的 `codemcp/shell.py` 使用
`asyncio.create_subprocess_exec(..., stdout=PIPE, stderr=PIPE)`，没有设置
`stdin=DEVNULL` 或独立 stdin。MCP stdio server 同时消费自己的 stdin；在
worker 内调用 Git-backed subtool 时，Git 子进程继承该 stdio 输入，实测在
2 秒 probe timeout 内没有返回 MCP tool result。这里“继承 stdio 输入导致
阻塞”是由源码和运行日志共同支持的根因判断；直接在非 MCP 进程中调用同一
版本的 `InitProject` 可以完成 Git commit，说明不是 Git 本身完全不可用。

这也意味着 Bridge 不能只把上游 stdio worker 包起来就宣称支持 Windows
写入。后续必须在 WSL2 实测通过，或在保持上游逻辑最小化的前提下 fork 修复
stdin、超时、进程树清理和错误返回。

### 命令安全边界

上游 `RunCommand` 从 `codemcp.toml` 读取命令列表，并会把调用方传入的
`arguments` 追加到该列表。Bridge 不能把这个参数面直接暴露给 ChatGPT，必须
只接受已登记的 command id 和完整的结构化 argv。

## ChatGPT-only 检查

- 已扫描安装包源码，未发现 `openai`、`anthropic`、`litellm`、`ollama` 等模型 provider 或模型 key 入口。
- `uv tree` 中 codemcp 依赖为 anyio、MCP、ruff、toml/tomli，没有模型 SDK。
- 这是静态源码和依赖检查，不等同于网络层 egress 证明；Bridge 后续仍需保持 `model_egress = "deny"`。

## 验证命令

~~~text
uv sync --project bridge
uv run --project bridge codemcp-bridge doctor --strict --json
uv run --project bridge pytest -q --basetemp=.local/pytest-phase1 tests/integration/test_codemcp_compatibility.py
uv run --project bridge ruff check bridge/src bridge/tests tests/integration
~~~

当前 Windows 结果为：`4 passed, 2 xfailed`。两个严格 xfail 正是上表中
Git-backed subtool 的已知 blocker，不是被跳过的测试。
