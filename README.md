# codemcp-remote

独立的本机代码修改服务，目标架构为：

ChatGPT（唯一推理） → Secure MCP Tunnel → 本机 MCP Bridge → codemcp → 已登记项目

本项目不使用 Codex、OpenCode 或其他推理模型。Bridge 和 codemcp 只负责工具执行、安全控制、会话、审计和结果返回。

## 当前状态

- 当前阶段：Phase 1（codemcp 本地兼容性验证）
- 当前实现：项目骨架、固定版 codemcp、stdio MCP 探针和兼容性测试
- 尚未实现：Bridge MCP Server、codemcp Adapter、Secure MCP Tunnel 联调
- 当前限制：Windows 原生环境的 Git-backed codemcp subtool 会在 stdio worker 内阻塞；详见 [docs/codemcp-compatibility-matrix.md](docs/codemcp-compatibility-matrix.md)

## Phase 1 本地检查

需要 Python 3.12+、uv 和 Git：

~~~text
uv sync --project bridge
uv run --project bridge codemcp-bridge doctor --strict --json
uv run --project bridge pytest -q --basetemp=.local/pytest-phase1 tests/integration/test_codemcp_compatibility.py
~~~

Phase 1 已固定并安装 `codemcp==0.3.0`；实际协议、工具和 Git 行为记录在兼容性矩阵中。

## 关键约束

- ChatGPT 是唯一推理引擎。
- Bridge 不包含模型 provider、模型 key 或模型调用代码。
- Bridge 只允许已登记的 project_id、项目路径和命令 ID。
- 不暴露任意路径读写和任意 shell。
- Secure MCP Tunnel 只承担远程传输，不替代 Bridge 的授权、审批和审计。
- 默认禁止 dirty workspace 直接写入。

详细执行计划见 [docs/implementation-plan.md](docs/implementation-plan.md)。
