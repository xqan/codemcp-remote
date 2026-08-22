# codemcp-remote-bridge

本包是 codemcp-remote 的本机 Bridge。Phase 2 已实现 loopback-only MCP
Server、项目注册、路径/命令策略、结构化错误和固定版 codemcp Adapter；SQLite
持久化、checkpoint/rollback 和 Tunnel 集成按 docs/implementation-plan.md 的
后续 Phase 实现。

Phase 1 已确定 codemcp mutation worker 运行在 WSL2；原生 Windows 的
Git-backed mutation 不支持。Adapter 必须显式处理 Windows/WSL 路径映射、
worker 超时和进程树清理，详见 `docs/codemcp-compatibility-matrix.md`。

本包不包含任何模型调用。

本地检查和启动：

~~~text
uv run --project bridge codemcp-bridge-server check
uv run --project bridge codemcp-bridge-server serve
~~~
