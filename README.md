# codemcp-remote

独立的本机代码修改服务，目标架构为：

ChatGPT（唯一推理） → Secure MCP Tunnel → 本机 MCP Bridge → codemcp → 已登记项目

本项目不使用 Codex、OpenCode 或其他推理模型。Bridge 和 codemcp 只负责工具执行、安全控制、会话、审计和结果返回。

## 当前状态

- 当前阶段：Phase 6（Windows 11 运维化和开发者体验）
- 当前实现：loopback MCP Bridge、SQLite 生命周期、幂等 operation、一次性审批、审计、Bridge-owned Git checkpoint/CAS rollback、WSL2 codemcp worker，以及受限的 tunnel-client 启动/诊断包装
- 当前远程验收：真实 Tunnel 工具发现、主合同和失败恢复矩阵已通过；Phase 6 已完成一键启动/停止首个原子任务；Windows 原生 Git mutation 仍不支持
- 平台决策：codemcp mutation worker 运行在 WSL2；Windows 原生 Git-backed
  mutation 不支持，详见 [docs/codemcp-compatibility-matrix.md](docs/codemcp-compatibility-matrix.md)

## Phase 5 本地检查

需要 Python 3.12+、uv 和 Git：

~~~text
uv sync --project bridge
uv run --project bridge codemcp-bridge doctor --strict --json
uv run --project bridge codemcp-bridge-server check
uv run --project bridge pytest -q --basetemp=.local/pytest-phase5
uv run --project bridge ruff check bridge/src bridge/tests
~~~

Phase 1 已固定并安装 `codemcp==0.3.0`；WSL2 路径已通过 Git-backed 集成验证，
实际协议、工具和 Git 行为记录在兼容性矩阵中。Phase 2 的基础验证记录在
[docs/phase-2-validation.md](docs/phase-2-validation.md)，Phase 3 的生命周期验证记录在
[docs/phase-3-validation.md](docs/phase-3-validation.md)，Phase 4 的 Git 安全验证记录在
[docs/phase-4-validation.md](docs/phase-4-validation.md)。Git 边界和 rollback
约束见 [docs/git-policy.md](docs/git-policy.md)。Tunnel 配置和诊断见
[docs/tunnel-setup.md](docs/tunnel-setup.md)，远程验收合同见
[tests/e2e/test_tunnel_contract.md](tests/e2e/test_tunnel_contract.md)。Phase 5
本地验证记录见 [docs/phase-5-validation.md](docs/phase-5-validation.md)。

本地启动 Bridge 和 Tunnel：

~~~text
Copy-Item config/tunnel-profile.example.env config/tunnel-profile.local.env
pwsh -File .\scripts\start-all.ps1 -Initialize
pwsh -File .\scripts\doctor.ps1
~~~

项目注册信息写入本地的 `config/projects.toml`；该文件已被 Git 忽略。
`config/projects.example.toml` 仅作为模板保留，不要把真实项目路径写回 example：

~~~powershell
Copy-Item config/projects.example.toml config/projects.toml
# 编辑 config/projects.toml 后再启动 Bridge
~~~

后续启动可直接运行 `pwsh -File .\scripts\start-all.ps1`；停止使用
`pwsh -File .\scripts\stop-all.ps1`。`start-all.ps1` 会先等待 Bridge
健康，再等待 Tunnel `readyz`；只有确认进程属于本仓库和 Tunnel profile
时才会复用已健康的本机服务。

## 关键约束

- ChatGPT 是唯一推理引擎。
- Bridge 不包含模型 provider、模型 key 或模型调用代码。
- Bridge 只允许已登记的 project_id、项目路径和命令 ID。
- 不暴露任意路径读写和任意 shell。
- Secure MCP Tunnel 只承担远程传输，不替代 Bridge 的授权、审批和审计。
- tunnel-client 只允许使用 OpenAI control plane、loopback Bridge MCP URL 和环境变量密钥引用。
- 本机不开放公网入站端口；Tunnel 通过出站 HTTPS 连接 OpenAI control plane。
- 默认禁止 dirty workspace 直接写入。
- checkpoint 使用 `refs/codemcp-remote/checkpoints/<id>`，只允许 Bridge 登记的 ref。
- rollback 必须显式审批，并提交当前 branch/HEAD 作为 compare-and-swap 预期值；发生外部修改时 fail closed。

详细执行计划见 [docs/implementation-plan.md](docs/implementation-plan.md)。
