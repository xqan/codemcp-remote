# codemcp-remote-bridge

本包是 codemcp-remote 的本机 Bridge。Phase 1 增加固定版 codemcp 的 MCP
兼容性探针和诊断；MCP Server、codemcp Adapter、权限策略和 Tunnel 集成按
docs/implementation-plan.md 的 Phase 顺序实现。

Phase 1 已确定 codemcp mutation worker 运行在 WSL2；原生 Windows 的
Git-backed mutation 不支持。Adapter 必须显式处理 Windows/WSL 路径映射、
worker 超时和进程树清理，详见 `docs/codemcp-compatibility-matrix.md`。

本包不包含任何模型调用。
