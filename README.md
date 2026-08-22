# codemcp-remote

独立的本机代码修改服务，目标架构为：

ChatGPT（唯一推理） → Secure MCP Tunnel → 本机 MCP Bridge → codemcp → 已登记项目

本项目不使用 Codex、OpenCode 或其他推理模型。Bridge 和 codemcp 只负责工具执行、安全控制、会话、审计和结果返回。

## 当前状态

- 当前阶段：Phase 0
- 当前实现：项目骨架、配置基线、运行环境诊断
- 尚未实现：Bridge MCP Server、codemcp Adapter、Secure MCP Tunnel 联调

## Phase 0 本地检查

需要 Python 3.12+、uv 和 Git：

~~~text
uv sync --project bridge
uv run --project bridge codemcp-bridge doctor --json
uv run --project bridge pytest -q
~~~

Phase 0 不要求 codemcp 已经安装；codemcp 的实际协议、工具和 Git 行为在 Phase 1 验证。

## 关键约束

- ChatGPT 是唯一推理引擎。
- Bridge 不包含模型 provider、模型 key 或模型调用代码。
- Bridge 只允许已登记的 project_id、项目路径和命令 ID。
- 不暴露任意路径读写和任意 shell。
- Secure MCP Tunnel 只承担远程传输，不替代 Bridge 的授权、审批和审计。
- 默认禁止 dirty workspace 直接写入。

详细执行计划见 [docs/implementation-plan.md](docs/implementation-plan.md)。
