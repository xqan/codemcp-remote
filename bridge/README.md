# codemcp-remote-bridge

本包是 codemcp-remote 的本机 Bridge。Phase 1 增加固定版 codemcp 的 MCP
兼容性探针和诊断；MCP Server、codemcp Adapter、权限策略和 Tunnel 集成按
docs/implementation-plan.md 的 Phase 顺序实现。

原生 Windows 的 Git-backed codemcp subtool 兼容性目前未通过，详见
`docs/codemcp-compatibility-matrix.md`。

本包不包含任何模型调用。
