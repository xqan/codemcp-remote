# Codemcp Remote 文档中心

这里按“当前规范、执行指南、验收、计划、版本记录、验证报告、历史归档”分类，避免把历史证据误当成现行操作说明。

## 从这里开始

- [项目总览](../README.md)
- [当前实施计划](implementation-plan.md)
- [当前架构](architecture/architecture.md)
- [运维手册](guides/operations-runbook.md)
- [Secure MCP Tunnel 配置](guides/tunnel-setup.md)
- [Phase 6 当前验收](acceptance/phase-6-validation.md)
- [v0.1.0 最终验收门禁](acceptance/acceptance-test-plan.md)

## 文档分类

| 目录 | 内容 | 使用原则 |
| --- | --- | --- |
| `implementation-plan.md` | 当前活动实施计划 | 仅表示已规划的下一阶段，不表示已经实现；冻结后归档到 `plans/` |
| `architecture/` | 当前架构；旧版本放在 `architecture/archive/` | 产品边界和设计决策以当前版本为准 |
| `guides/` | 配置、集成、运行和项目结构说明 | 可执行操作优先从这里进入 |
| `acceptance/` | 当前验收与 Freeze Gate；旧版本放在 `acceptance/archive/` | 执行前确认目标版本 |
| `plans/` | 各版本实施计划及其归档副本 | 版本化计划不是当前任务的自动授权 |
| `releases/` | 按版本归类的阶段说明和完成记录 | 用于理解能力演进 |
| `reports/` | migration、testing、compatibility 验证证据 | 报告描述当时结果，不是现行 runbook |
| `archive/` | 已退役 Cloudflare 材料、历史 handoff 和阶段 notes | 仅作审计与历史参考 |

## 当前文档

### 架构与安全

- [架构基线](architecture/architecture.md)
- [Git checkpoint 与回滚策略](architecture/git-policy.md)
- [安全模型](architecture/security-model.md)
- [威胁模型](architecture/threat-model.md)

### 执行指南

- [codemcp 固定版本基线](guides/codemcp-baseline.md)
- [运维手册](guides/operations-runbook.md)
- [Secure MCP Tunnel 配置](guides/tunnel-setup.md)

### 当前验收与计划

- [Phase 6 Windows 运维验收](acceptance/phase-6-validation.md)
- [Phase 7 / v0.1.0 最终验收](acceptance/acceptance-test-plan.md)
- [v0.1.0 开源整改计划](plans/v0.1.0/open-source-readiness-plan.md)

### 版本记录与验证证据

- [v0.1.0 阶段记录](releases/v0.1.0/)
- [迁移与基线报告](reports/migration/)
- [测试报告](reports/testing/)
- [兼容性报告](reports/compatibility/)

## 当前运行与退役边界

- 当前支持边界是 Windows 11 主机、WSL2 Ubuntu mutation worker、Python 3.12+、
  `codemcp==0.3.0` 和 OpenAI Secure MCP Tunnel。
- 当前可执行说明以 `guides/`、`architecture/` 和 `acceptance/` 中的文档为准。
- `releases/` 中的 Phase 0–5 文件是已完成阶段记录；`reports/` 中的内容是当时的
  验证证据，不能替代当前 runbook 或尚未完成的 release gate。
- 稳定版 `v0.1.0` 仍受 Phase 6、Phase 7、secrets/supply-chain 和 clean-machine
  验收阻断；历史记录中的 PASS 不代表稳定版已经获准发布。
- 当前没有需要放入 `archive/` 的退役文档；后续被替代的文档按维护约定归档。

## 维护约定

1. `docs/` 根目录只保留本索引和当前活动 `implementation-plan.md`；计划冻结后移入 `plans/`。
2. 当前文档放在分类目录根部，已取代或仅具历史价值的内容进入相应 `archive/`。
3. 迁移、测试和兼容性结果分别进入 `reports/migration/`、`reports/testing/`、`reports/compatibility/`。
4. `domain-schema.sql`、`mcp-contract.json` 等机器可读契约继续保留在仓库根目录，不与说明文档混放。
5. 移动文档时同步更新 README、测试和文档内引用，并执行完整回归。
