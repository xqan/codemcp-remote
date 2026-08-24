# codemcp-remote 开源整改计划（v0.13 — Open Source Readiness）

> 基线日期：2026-08-24  
> 目标版本：完成整改后发布 `v0.1.0`  
> 当前定位：Windows 11 + WSL2 下，通过 OpenAI Secure MCP Tunnel 将 ChatGPT 连接到本机受控 MCP Bridge，并由 codemcp 执行受限代码操作。

## 1. 目标

本计划的目标不是继续扩展 codemcp-remote 的核心功能，而是把现有工程从“可用的内部项目”提升为“可公开审查、可安全安装、可重复验收、可持续维护的开源项目”。

完成整改后应满足：

1. 陌生用户能够仅依据公开文档完成安装、项目注册、启动、诊断和基本使用。
2. 安全边界、威胁模型、已知限制和漏洞报告方式公开且可验证。
3. Phase 7 的功能、安全、可靠性和文档验收全部通过。
4. CI 能持续验证代码质量、测试、依赖和安全基线。
5. 仓库不存在已知凭据泄露，发布流程不会包含本地配置或敏感文件。
6. 能生成可重复的 `v0.1.0` 发布产物，并附 SHA-256 校验值。
7. 开源治理文件、贡献流程和版本维护策略齐备。

## 2. 当前基线与主要缺口

截至本计划创建时，仓库已经具备：

- loopback-only MCP Bridge；
- SQLite session / operation / approval / audit 生命周期；
- 幂等 mutation、项目级写入保护和失败恢复；
- Bridge-owned Git checkpoint、diff、CAS rollback；
- WSL2 codemcp worker；
- Secure MCP Tunnel 启动、诊断和远程合同验收；
- Windows 11 一键启动/停止的初步运维能力；
- 项目注册、命令白名单和敏感路径默认拒绝策略；
- 单元、集成和阶段性验证文档。

当前主要开源缺口：

- 根目录缺少正式 `LICENSE`；
- 缺少 `SECURITY.md`；
- 缺少 `docs/security-model.md`；
- 缺少 `docs/threat-model.md`；
- 缺少 `docs/acceptance-test-plan.md`；
- README 仍偏内部阶段记录，不是面向首次使用者的产品入口；
- 缺少 `.github/` 下的 CI、Issue/PR 模板和依赖维护配置；
- 缺少公开的贡献指南、行为准则、变更日志和版本支持策略；
- 尚未完成 Phase 6 剩余的连续重启、异常退出、日志脱敏、升级/回退验证；
- 尚未完成 Phase 7 最终验收；
- 尚未完成整个 Git 历史的 secrets 扫描和发布前清理确认；
- 尚未形成标准化 release artifact + SHA-256 流程。

## 3. 整改原则

### P0：安全优先

这是一个具备本地源码读取、修改、测试和 Git 操作能力的远程执行项目。任何“使用体验”优化都不能削弱项目注册、路径限制、命令白名单、审批、审计、Git CAS 或 fail-closed 行为。

### P1：先完成已有设计承诺，再增加新功能

整改期间原则上不新增以下能力：

- 多用户身份系统；
- 任意 shell；
- 自动 push / merge / rebase / deploy；
- 新模型 provider；
- Bridge 内 Agent loop；
- 非必要的新 transport；
- 原生 Windows mutation 支持。

如果整改过程中发现现有安全或可靠性缺陷，可以修复；功能扩展进入后续版本。

### P2：陌生机器可复现

所有发布结论必须能够在干净 Windows 11 环境中复现，不能依赖开发机已有 PATH、缓存、虚拟环境、Tunnel profile 或人工残留状态。

### P3：文档必须与代码一致

README、示例配置、CLI、脚本、支持矩阵和安全文档中的命令必须实际执行验证。禁止保留已经失效的阶段性事实作为当前说明。

---

# 4. 整改阶段

## Stage 0 — 发布冻结与基线确认

**优先级：P0**

### 目标

冻结当前功能边界，建立开源整改基线，避免整改期间同时发生无关功能扩张。

### 任务

1. 确认当前支持范围：
   - Windows 11 主机；
   - WSL2 Ubuntu mutation worker；
   - Python 3.12+；
   - `codemcp==0.3.0`；
   - OpenAI Secure MCP Tunnel；
   - 单用户本机 policy profile。
2. 记录当前分支、HEAD、测试基线。
3. 运行完整现有测试套件。
4. 执行 `git diff --check`。
5. 确认工作树 clean。
6. 建立 `v0.13` 整改 checklist，所有后续提交映射到本计划。

### 验收

- 当前功能支持矩阵无歧义；
- 全部现有测试通过；
- 工作树 clean；
- 没有未记录的 blocker。

---

## Stage 1 — License、Security 与 Threat Model

**优先级：P0**

### 目标

让潜在用户在安装前能够明确知道：代码如何授权、系统信任什么、不信任什么、发生漏洞如何报告。

### 新增文件

- `LICENSE`
- `SECURITY.md`
- `docs/security-model.md`
- `docs/threat-model.md`

### 任务

#### 1. LICENSE

- 项目采用 GNU Affero General Public License v3.0，SPDX 标识为 `AGPL-3.0-only`；
- 根目录加入正式 GNU AGPL v3 license 文本；
- 核对 `bridge/pyproject.toml` 的 license 声明与根 LICENSE 一致；
- `codemcp==0.3.0` 继续作为 Apache-2.0 第三方依赖单独记录，不改变其上游许可证；
- 必要时新增 Third-Party Notices，并明确项目代码与第三方依赖的许可证边界。

#### 2. SECURITY.md

至少包含：

- 当前支持版本；
- 漏洞报告渠道；
- 不应公开提交安全漏洞的说明；
- 响应与披露原则；
- 安全问题范围；
- 非安全问题如何提交；
- 凭据泄露后的处置建议。

#### 3. security-model.md

至少明确：

- ChatGPT、Tunnel、Bridge、codemcp worker、Git repo 的信任边界；
- Bridge 为唯一对外 MCP Server；
- loopback-only 原则；
- project registry；
- 路径沙箱；
- 命令白名单；
- secret deny rules；
- approval token；
- audit；
- idempotency；
- checkpoint / CAS rollback；
- unknown side-effect；
- fail-closed 策略；
- 当前不提供的安全保证。

#### 4. threat-model.md

至少覆盖：

- path traversal；
- symlink / junction / reparse point escape；
- arbitrary shell / argument injection；
- prompt injection from repository content；
- malicious project configuration；
- secret exfiltration；
- approval replay / cross-session / cross-project；
- idempotency collision / replay；
- operation state corruption；
- Tunnel disconnect during mutation；
- worker crash during mutation；
- external Git modification race；
- log leakage；
- dependency / supply-chain risk；
- compromised local user / compromised ChatGPT workspace 的边界。

每类威胁记录：

`Threat → Preconditions → Existing Mitigation → Residual Risk → Validation`

### 当前执行状态（2026-08-24）

- [x] 开源协议确定为 GNU AGPL v3，项目 SPDX 标识为 `AGPL-3.0-only`；
- [x] 根目录加入完整、未修改的 GNU AGPL v3 `LICENSE` 正文；
- [x] `bridge/pyproject.toml` 已切换为 `AGPL-3.0-only`；
- [x] 新增 `SECURITY.md`；
- [x] 新增 `docs/security-model.md`；
- [x] 新增 `docs/threat-model.md`；
- [x] 已将 threat model 每个 P0 威胁映射到现有自动测试或明确的 Phase 6/7 验收项；映射完成不代表验收已 PASS；
- [ ] Stage 6 dependency audit 时复核全部第三方依赖许可证，并决定是否生成完整 Third-Party Notices。

### 验收

- 安全文档和代码实际行为一致；
- 所有关键安全机制都有对应测试或明确的人工验收；
- 未验证的安全假设不得写成已保证事实。

---

## Stage 2 — Phase 6 运维化收尾

**优先级：P0**

### 目标

完成 implementation plan 已经承诺但尚未完成的 Phase 6 验收。

### 任务

1. 连续执行启动 → 健康检查 → 停止 → 重启至少 20 次。
2. 分别模拟：
   - Bridge 异常退出；
   - tunnel-client 异常退出；
   - codemcp worker 异常退出；
   - 端口占用；
   - stale PID / stale lock；
   - WSL 不可用；
   - Git 不可用；
   - Tunnel 未认证。
3. 验证进程树清理，不残留 worker。
4. 验证日志：
   - 不包含 runtime API key；
   - 不包含完整敏感文件内容；
   - 不记录未经脱敏 token；
   - 错误日志仍足以诊断问题。
5. 验证 UTF-8、中文路径、空格路径、CRLF/LF。
6. 建立依赖升级前检查。
7. 建立 codemcp 升级失败后的回退步骤。

### 产物

- 更新 `docs/operations-runbook.md`；
- 新增或更新 Phase 6 validation 记录；
- 必要的回归测试。

### 验收

满足 implementation plan Phase 6 Acceptance Criteria：

- 用户可按 README 在 Windows 11 完成安装和启动；
- doctor 能定位常见问题；
- codemcp 升级前后有明确版本检查和回退方式。

---

## Stage 3 — Phase 7 最终验收

**优先级：P0**

### 新增文件

- `docs/acceptance-test-plan.md`

### 目标

把目前散落的阶段验证转化成一次可重复执行的正式 Release Gate。

### 验收矩阵

#### A. 功能

- project_open；
- project_status；
- file_list / file_read；
- code_search；
- file_create / file_edit / file_write / file_move / file_delete；
- registered commands；
- format / test；
- git_status / git_diff；
- checkpoint create / restore；
- operation status / cancel；
- approval flow。

#### B. 安全

验证以下输入全部 fail closed：

- 未登记 project_id；
- absolute arbitrary path；
- `../` traversal；
- symlink / junction escape；
- secret file；
- binary file；
- 未登记 command；
- 参数注入；
- 错误 approval；
- approval replay；
- cross-session approval；
- cross-project operation；
- forged request hash；
- Git branch / HEAD race；
- dirty workspace 未授权写入。

#### C. 可靠性

- duplicate request；
- Tunnel disconnect；
- Bridge crash；
- worker crash；
- timeout；
- cancel；
- unknown side-effect；
- restart recovery；
- CAS rollback conflict；
- simultaneous mutation rejection。

#### D. 真实项目

至少验证：

- 一个真实 Java 项目；
- 一个包含前端构建命令的项目；
- 连续 10 次真实远程修改任务；
- 每次逐项核对 operation、audit、Git diff、checkpoint。

### 验收

- Release Gate 全部通过；
- 所有失败项必须形成 blocker 或明确 documented limitation；
- P0/P1 blocker 清零后才允许进入 Release Packaging。

---

## Stage 4 — README 与首次使用体验重构

**优先级：P1**

### 目标

让从未接触项目的用户可以在 5–15 分钟内判断是否适合自己，并知道如何开始。

### README 推荐结构

1. 项目一句话定位；
2. Why codemcp-remote；
3. Architecture diagram；
4. Security properties；
5. Current limitations；
6. Requirements；
7. Quick Start；
8. Register your first project；
9. Start Bridge + Tunnel；
10. Connect from ChatGPT；
11. Run first read-only call；
12. Run first mutation；
13. Approval / checkpoint / rollback；
14. Doctor / Troubleshooting；
15. Supported platforms；
16. Security；
17. Contributing；
18. License。

### 必须明确的限制

- 当前 mutation worker 依赖 WSL2；
- native Windows Git-backed mutation 不支持；
- Secure MCP Tunnel / ChatGPT developer-mode 能力取决于用户账号和 workspace 能力；
- Bridge 不是多用户身份系统；
- Bridge 不允许任意 shell；
- 不自动 push / merge / deploy；
- codemcp 固定在已验证版本。

### 清理历史性描述

将不再代表当前状态的初创内容从主 README / 当前架构文档移出，必要时保留到 ADR 或历史记录。

### 验收

找一个没有参与开发的人，仅按 README 操作：

- 能完成依赖检查；
- 能复制安全示例配置；
- 能注册 sample project；
- 能启动服务；
- doctor 正常；
- 能理解支持范围和安全边界。

---

## Stage 5 — GitHub 开源治理与 CI

**优先级：P1**

**状态：仓库侧实施完成；GitHub hosted 首次运行/规则集激活待仓库托管后验证。**

验证记录：`docs/stage-5-validation.md`

### 新增文件 / 目录

- `CONTRIBUTING.md`
- `CODE_OF_CONDUCT.md`
- `CHANGELOG.md`
- `.github/workflows/ci.yml`
- `.github/ISSUE_TEMPLATE/`
- `.github/pull_request_template.md`
- `.github/dependabot.yml`

可选：

- `.github/workflows/codeql.yml`
- `.github/workflows/release.yml`

### CI 最低要求

每次 push / pull request：

1. 安装 Python 3.12；
2. `uv sync --project bridge`；
3. `ruff check`；
4. pytest；
5. package build；
6. `git diff --check` 等价检查；
7. 关键配置 schema / doctor check。

安全检查建议：

- CodeQL；
- dependency review；
- `pip-audit` 或等价 Python dependency audit；
- secret scanner。

### 贡献指南

至少说明：

- 开发环境；
- 测试命令；
- 代码风格；
- 安全相关修改要求；
- 新工具暴露的安全审查要求；
- PR 验收标准；
- 不接受的设计方向。

### 验收

- 新 PR 可以自动得到明确 Pass/Fail；
- 主分支不能在明显测试失败时发布；
- dependency 更新有可见检查。

---

## Stage 6 — Secrets、隐私与供应链发布审查

**优先级：P0**

### 目标

确认“当前仓库看起来没有 secret”之外，Git 历史、构建产物和示例配置也安全。

### 任务

1. 扫描整个 Git history：
   - API key；
   - token；
   - tunnel ID（按敏感级别决定是否公开）；
   - 本地真实项目路径；
   - email/password；
   - private key；
   - `.env`；
   - SQLite / log artifact。
2. 检查 git tracked files。
3. 检查 release build 内容。
4. 检查示例配置不存在真实用户值。
5. 检查测试 fixture 不包含真实代码或凭据。
6. 对依赖做许可证和漏洞检查。
7. 明确是否需要 `THIRD_PARTY_NOTICES.md`。
8. 如果发现历史 secret：
   - 先吊销 / rotate；
   - 再清理历史；
   - 重新扫描；
   - 不把“删除当前文件”当作清理完成。

### 验收

- history secret scan PASS；
- working tree secret scan PASS；
- release artifact scan PASS；
- dependency license / vulnerability 没有未接受的 blocker。

---

## Stage 7 — Release Packaging

**优先级：P1**

### 目标

建立任何人都可以验证的正式发布产物。

### 发布内容

建议至少包含：

- Source archive；
- Windows 安装/启动说明；
- Bridge Python package 或明确的源码安装方式；
- example configs；
- release notes；
- `SHA256SUMS.txt`。

### 版本策略

第一次正式公开版本：

`v0.1.0`

在 Phase 7 未完成前只允许：

- `0.1.0-alpha.*`
- 或不创建 stable release。

### Release Checklist

- [ ] working tree clean
- [ ] CI PASS
- [ ] Phase 7 PASS
- [ ] security tests PASS
- [ ] secret scan PASS
- [ ] dependency audit PASS
- [ ] README quick start 重新验证
- [ ] CHANGELOG 更新
- [ ] version 更新
- [ ] release artifact 生成
- [ ] SHA-256 生成并核对
- [ ] tag 指向正确 commit
- [ ] release notes 包含 known limitations

### 验收

从 GitHub Release 下载的源码/产物可以在一台干净 Windows 11 + WSL2 环境中根据 README 完成启动。

---

# 5. 优先级与阻断关系

## P0 — 不完成不得发布 stable

1. LICENSE；
2. SECURITY；
3. security model；
4. threat model；
5. Phase 6 剩余可靠性验收；
6. Phase 7 acceptance；
7. Git history secret scan；
8. release artifact secret scan；
9. 关键安全 blocker 修复。

## P1 — `v0.1.0` 前应完成

1. README 重构；
2. CONTRIBUTING；
3. CHANGELOG；
4. GitHub Actions CI；
5. Issue / PR 模板；
6. Dependabot；
7. release packaging；
8. SHA-256。

## P2 — 可在 `v0.1.x / v0.2` 继续

1. CodeQL 深度增强；
2. 自动 release workflow；
3. 更多平台；
4. 更多 transport adapter；
5. 多用户身份与 RBAC；
6. native Windows mutation；
7. codemcp fork / 替代执行后端。

---

# 6. 推荐执行顺序

严格按以下顺序推进：

1. Stage 0：冻结 + baseline；
2. Stage 1：License / Security / Threat Model；
3. Stage 2：完成 Phase 6；
4. Stage 3：完成 Phase 7；
5. Stage 6：Secrets / supply-chain 审查；
6. Stage 4：README / onboarding；
7. Stage 5：GitHub CI / governance；
8. Stage 7：Release Packaging；
9. 最终 Release Gate；
10. tag `v0.1.0`。

原因：先把安全模型和已有工程承诺闭环，再包装 README 和 CI，可以避免文档与实现反复返工。

---

# 7. 最终 Release Gate

只有以下条件全部成立，才能发布 stable `v0.1.0`：

| Gate | 要求 |
|---|---|
| Functional | 全部核心 MCP 工具通过验收 |
| Security | threat model 中关键攻击路径有测试或明确验证 |
| Reliability | crash / restart / timeout / disconnect / unknown / rollback 均通过 |
| Secrets | working tree、Git history、release artifact 扫描通过 |
| Docs | README + Security + Threat Model + Runbook 完整 |
| CI | 测试、lint、build 在干净环境自动通过 |
| Packaging | Release artifact 可安装、可启动 |
| Integrity | 提供 SHA-256 |
| Limitations | 已知限制公开且与实际行为一致 |
| Git | release commit clean，tag 指向已验收 commit |

任何 P0 blocker 未关闭，禁止发布 stable tag。

---

# 8. Definition of Done

本整改计划完成的定义：

1. `Phase 0–7` 全部形成可验证闭环；
2. 仓库具备标准开源法律、安全、贡献和维护文件；
3. CI 能自动阻止明显质量回归；
4. 安全攻击矩阵通过；
5. 故障恢复矩阵通过；
6. Git history 与 release artifact 不包含已知秘密；
7. 新用户可按 README 独立启动；
8. release 可重复构建并附 SHA-256；
9. `v0.1.0` 的 known limitations 清晰公开；
10. 从此后新增高权限工具必须同步更新 threat model、tests 和安全文档。

完成以上条件后，codemcp-remote 才从“可公开代码仓库”进入“可供第三方实际安装使用的开源项目”状态。
