# Codemcp Remote 文档中心

这里按“当前规范、执行指南、验收、计划、版本记录、验证报告、历史归档”分类，避免把历史证据误当成现行操作说明。

## 从这里开始

- [项目总览](../README.md)

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

## 当前运行与退役边界



## 维护约定

1. `docs/` 根目录只保留本索引和当前活动 `implementation-plan.md`；计划冻结后移入 `plans/`。
2. 当前文档放在分类目录根部，已取代或仅具历史价值的内容进入相应 `archive/`。
3. 迁移、测试和兼容性结果分别进入 `reports/migration/`、`reports/testing/`、`reports/compatibility/`。
4. `domain-schema.sql`、`mcp-contract.json` 等机器可读契约继续保留在仓库根目录，不与说明文档混放。
5. 移动文档时同步更新 README、测试和文档内引用，并执行完整回归。
