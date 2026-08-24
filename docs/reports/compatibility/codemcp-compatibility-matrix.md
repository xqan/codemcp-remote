# codemcp Phase 1 兼容性矩阵

## 结论

固定的 `codemcp==0.3.0` 可以作为 stdio MCP worker 启动，并通过
`initialize`、`tools/list` 和不触发 Git 的 `ReadFile`。在当前 Windows 11
原生环境中，所有需要调用 Git 的子工具都会在 MCP stdio worker 内超时，因而
不能直接作为本项目的写入后端使用。

WSL2 Ubuntu（版本 2）可以在同一个 Windows 项目的 `/mnt/d` 挂载路径上完成
Git-backed 读取、编辑、写入、命令执行和 Git 状态验证；长超时复核为 `2 passed`。
因此本阶段的决策是：codemcp mutation worker 运行在 WSL2，原生 Windows
codemcp 不作为 mutation 后端；Phase 2 先直接使用上游 `0.3.0`，暂不维护 fork。
如果后续必须支持原生 Windows，再单独评估针对 stdin、超时和进程树的最小 fork。

Bridge 后续必须负责 Windows 项目路径到 WSL 路径的显式映射，并在 worker 外部
执行超时、进程树清理和 unknown side-effect 保护。WSL 挂载路径上的 Git probe
需要 30 秒预算；这不是把超时责任交给 codemcp，上游命令执行仍没有可靠的内部
默认超时。

## 版本和验证环境

- 上游仓库：[ezyang/codemcp](https://github.com/ezyang/codemcp)
- Release/tag：`0.3.0`
- Release commit：`683e6ec29b15b91ec12430afabf5a45ed57d2489`
- Python：`3.14.7`（由 uv 管理；项目要求 `>=3.12`）
- Windows：Windows 11，build `26200`
- Git：`2.51.0.windows.1`
- WSL2：Ubuntu，Python `3.14.4`，Git `2.53.0`
- MCP SDK：`1.29.0`
- codemcp：`0.3.0`
- 安装来源：PyPI；版本和 wheel/sdist SHA-256 已写入 `bridge/uv.lock`

GitHub 的 release 页面将 `0.3.0` tag 映射到上述 `683e6ec` commit；本机
`git ls-remote` 因 Windows Schannel 凭据错误未能完成远程复核。

## MCP 合约

探针使用 MCP SDK 的 `stdio_client` 和 `ClientSession`，为每个 worker 设置
独立的临时用户目录，避免写入操作员 profile。实际结果如下：

| 检查项 | Windows 原生 | WSL2 Ubuntu | 实际观察 |
|---|---|---|---|
| worker 启动 | PASS | PASS | `python -m codemcp` 正常启动 |
| `initialize` | PASS | PASS | protocol `2025-11-25`，server name `codemcp` |
| `tools/list` | PASS | PASS | 只有一个 MCP tool：`codemcp` |
| 输入/输出 schema | PASS | PASS | `subtool` required，输出为 `result: string` |
| `ReadFile` | PASS | PASS | 中文、空格和长嵌套路径下可读 |
| Git-backed subtools | BLOCKED | PASS | WSL2 使用 30 秒 probe timeout；原生 Windows 2 秒内阻塞 |
| worker 关闭/重启 | PASS | PASS | context 关闭后可以重新 initialize |
| 两个 stdio worker 并行启动 | PASS | PASS | 两个独立 worker 均可发现工具 |
| 端口冲突 | N/A | N/A | stdio transport 不监听端口 |

实际暴露的是一个 `codemcp` 工具，`subtool` 值为：

`InitProject`、`ReadFile`、`WriteFile`、`EditFile`、`LS`、`Grep`、`RunCommand`。

`Format` 不是实际的独立 subtool；调用它会返回 `Unknown subtool: Format`。
格式化只能通过登记在 `codemcp.toml` 的 `RunCommand` 命令表达。

## 工具和 Git 行为

| 能力 | 结果 | 说明 |
|---|---|---|
| 能力 | Windows 原生 | WSL2 Ubuntu |
|---|---|---|
| `InitProject` | blocked | PASS；读取 `project_prompt`，生成 `codemcp-id` 并创建空 Git commit |
| `LS` / `Grep` | blocked | PASS；完成 Git 检查和搜索 |
| `EditFile` / `WriteFile` | blocked | PASS；修改后 HEAD 改变但 commit 数不增加，工作区保持 clean |
| `RunCommand` | blocked | PASS；登记命令成功、失败、stdout/stderr 和退出码均已验证 |
| timeout | 不满足要求 | 上游 `run_code_command` 不传 `wait_time`；Adapter 必须在 worker 外部强制超时 |
| crash recovery | 未完成 | 已验证正常退出、重启和重复启动；未完成强制崩溃后的恢复测试 |

### Windows blocker

`codemcp 0.3.0` 的 `codemcp/shell.py` 使用
`asyncio.create_subprocess_exec(..., stdout=PIPE, stderr=PIPE)`，没有设置
`stdin=DEVNULL` 或独立 stdin。MCP stdio server 同时消费自己的 stdin；在
worker 内调用 Git-backed subtool 时，Git 子进程继承该 stdio 输入，实测在
2 秒 probe timeout 内没有返回 MCP tool result。这里“继承 stdio 输入导致
阻塞”是由源码和运行日志共同支持的根因判断；直接在非 MCP 进程中调用同一
版本的 `InitProject` 可以完成 Git commit，说明不是 Git 本身完全不可用。

这意味着 Bridge 不能只把上游 stdio worker 包起来就宣称支持原生 Windows
写入。当前实现应把 codemcp worker 放在 WSL2，并把 Windows 原生路径、WSL
路径、worker 生命周期和超时作为 Adapter 的显式边界；不在 Bridge 中复制
codemcp 的 Git 或文件逻辑。

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

当前 Windows 结果为：`5 passed, 2 xfailed`。两个严格 xfail 正是上表中
Git-backed subtool 的已知 blocker，不是被跳过的测试；WSL2 结果为 `7 passed`。
