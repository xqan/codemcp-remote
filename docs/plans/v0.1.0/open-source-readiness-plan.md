# codemcp-remote 开源整改计划（v0.1.0 Open Source Readiness）

> 更新基线：2026-08-28  
> 目标版本：`v0.1.0`  
> 当前分支：`codex/open-source-readiness`  
> 整改起始 HEAD：`7d39cf97594aa9425067d158722f8ddbba302486`；最终 release-candidate HEAD 只在 Final Release Gate sign-off 时冻结并记录  
> 状态：**PRE-RELEASE / STABLE RELEASE BLOCKED**

## 1. 目的

本计划用于把 codemcp-remote 从“已可稳定用于个人受控环境”的工程，收口为“可公开审查、可安全安装、可重复验收、可持续维护”的首个稳定开源版本。

本计划只处理 `v0.1.0` 开源发布所需的安全、可靠性、文档、治理、供应链和发布门禁，不再把已经完成的能力重复列为待开发功能。

任何 stable `v0.1.0` tag 都必须以真实 Release Gate 证据为依据；“代码已经实现”“本机可用”“历史某次测试通过”均不能替代最终 release-candidate 验收。

---

## 2. 当前真实产品基线

以下内容以当前仓库实现、README、验收记录和测试为准，取代 2026-08-24 初版计划中的旧假设。

### 2.1 已安装 Windows 产品

当前 `v0.1.0` 目标运行形态：

- Windows 11 x64-compatible；
- 交付 `codemcp-remote.exe` / `codemcp-remote-setup.exe`；
- **安装后的产品运行不要求 Python、uv、PowerShell 7 或 WSL2**；
- **Git for Windows 是明确的运行时前置条件**；
- 默认 mutation worker 为 **Native Windows local worker**；
- WSL2 Ubuntu 仅保留为 source-mode compatibility fallback；
- `codemcp==0.3.0` 固定版本，通过 Bridge-owned Windows compatibility wrapper 使用，不维护上游 fork。

源码开发仍要求 Python 3.12+、uv 和 PowerShell 7；这与已安装产品的运行时前置条件必须在文档中明确区分。

### 2.2 推荐远程路径

`v0.1.0` 推荐的个人部署 Profile A：

```text
ChatGPT Connector (Authentication = No authentication)
  -> OpenAI / ChatGPT Connector egress
  -> Cloudflare Edge / WAF IP allowlist
  -> Cloudflare Tunnel
  -> 127.0.0.1:46200
  -> codemcp-remote Bridge
  -> native Windows codemcp worker
  -> registered local Git project
```

关键边界：

- Cloudflare WAF/IP allowlist 是 **network trust boundary**，不是用户认证；
- Profile A 的 identity level 是 `network-only`，不能声称识别具体 ChatGPT 用户、Workspace、账号或会话；
- Bridge 始终只监听 loopback；
- Cloudflare ingress 必须由外部 WAF/网络策略限制，不能依赖 Python 读取 forwarded headers 做授权；
- OpenAI Secure MCP Tunnel 仍作为 optional compatibility transport；
- Profile B `oauth-resource-server` 保留为 optional advanced/enterprise profile，不作为 `v0.1.0` 推荐个人部署路径。

### 2.3 当前 MCP / 安全能力

当前公开 MCP contract 为 22 tools：

1. `project_open`
2. `project_status`
3. `file_read`
4. `code_search`
5. `file_list`
6. `file_edit`
7. `file_create`
8. `file_write`
9. `file_move`
10. `file_delete`
11. `directory_create`
12. `registered_command_run`
13. `format_run`
14. `test_run`
15. `git_status`
16. `git_diff`
17. `checkpoint_create`
18. `checkpoint_restore`
19. `operation_status`
20. `approval_confirm`
21. `operation_cancel`
22. `operation_reconcile`

必须继续保持：

- 不暴露任意 shell；
- 不允许 caller-controlled executable path / arbitrary argv；
- 不允许任意本机绝对路径绕过 project registry；
- 敏感路径默认拒绝；
- mutation 具备 canonical request hash、幂等、项目级串行化；
- 高风险操作保留短时一次性 approval；
- Bridge-owned Git checkpoint；
- branch/HEAD compare-and-swap rollback；
- 不确定副作用进入 `unknown` / reconcile，不透明重放；
- Bridge/codemcp 不调用模型，ChatGPT 是唯一推理引擎。

### 2.4 项目授权控制面

当前项目注册已经从“改配置后重启”升级为：

```text
local CLI project add/remove
  -> validated atomic projects.toml replacement
  -> running Bridge observes validated registry change
  -> no Bridge / Tunnel / Connector restart required
```

规则：

- 本机 CLI 是唯一项目授权管理控制面；
- MCP 不提供 project add/remove/reload/reconfigure；
- `project add/remove` 需要保持 root ownership、last-known-good、revocation 和 fail-closed 语义；
- 直接编辑 `projects.toml` 仅用于可信离线维护/恢复，不作为普通用户流程。

### 2.5 已完成的关键验证

已经有真实证据的能力包括：

- GNU AGPL v3 / `AGPL-3.0-only` 已落库；
- `SECURITY.md`、security model、threat model 已存在；
- README 已重构为 public-user 入口；
- GitHub governance/CI 配置已落库；
- Windows EXE、Installer、release-candidate ZIP 和 SHA-256 流程已经实现；
- Native Windows worker 已成为默认路径；
- project registry hot reload 已实现并有自动测试；
- Cloudflare No-Auth network-trust Phase A–H 已完成；
- Phase H 真实链路已经证明：
  - ChatGPT Connector 可访问完整 22-tool surface；
  - mutation；
  - identical replay；
  - explicit approval；
  - checkpoint / CAS restore；
  - exact clean-baseline recovery；
  - ordinary public source 被 Cloudflare Block；
  - ChatGPT Connector source 被 Allow。
- Phase H 最新记录的完整 registered test gate 为 `316 passed, 6 skipped`，format gate 为 `72 files already formatted`。

上述记录是已有能力证据，不代表最终 `v0.1.0` Release Gate 已完成。

---

## 3. 当前状态总览

| Stage / Track | 当前状态 | 是否阻塞 stable `v0.1.0` | 说明 |
|---|---|---:|---|
| Stage 0 — Readiness baseline | **COMPLETE** | 否 | 初始开源整改基线已建立；最终 release freeze 仍在末尾执行 |
| Stage 1 — License / Security / Threat Model | **COMPLETE（Third-Party Notices 决策待 Stage 6）** | 部分 | 核心法律/安全文档已完成 |
| Stage 2 — Phase 6 Windows Operations | **IN PROGRESS** | **是** | 真实主机可靠性、故障、日志、路径矩阵仍缺最终证据 |
| Stage 3 — Phase 7 Final Acceptance | **IN PROGRESS / BLOCKED BY PREREQUISITES** | **是** | 本地回归有 PASS，但最终功能/安全/可靠性/真实项目 Gate 未闭环 |
| Stage 4 — README / Onboarding | **REPOSITORY IMPLEMENTATION COMPLETE** | 是 | 最终 clean-machine 文档执行验证和全仓文档一致性待完成 |
| Stage 5 — GitHub Governance / CI | **REPOSITORY IMPLEMENTATION COMPLETE** | 是 | GitHub hosted 首次运行、Dependabot、ruleset/branch protection 待验证 |
| Stage 6 — Secrets / Privacy / Supply Chain | **PENDING** | **是** | Git history、artifact、dependency/license audit 未形成最终 PASS |
| Stage 7 — Release Packaging | **IMPLEMENTATION SUBSTANTIALLY COMPLETE** | **是** | Installer/ZIP/SHA 已有；strict clean-machine/final-RC packaging 仍未闭环 |
| Network Trust Phase A–H | **COMPLETE** | 否 | 推荐 Profile A 的 live path 已完成，不能替代 Phase 6/7 |
| Optional OAuth Profile B | **IMPLEMENTED / OPTIONAL** | 否* | *仅在 `v0.1.0` 不把其 live OAuth 端到端能力作为默认发布承诺时不阻塞 |

---

# 4. 整改阶段

## Stage 0 — 发布边界与当前基线

**优先级：P0**  
**状态：COMPLETE（最终 release freeze 不在本阶段提前执行）**

### 已完成

- 已确定首个 stable 版本为 `v0.1.0`；
- 已冻结“ChatGPT-only reasoning / Bridge as policy gateway / codemcp as execution backend”的核心边界；
- 已固定 `codemcp==0.3.0`；
- 已明确 installed runtime 与 source-development runtime 的区别；
- 已明确 Native Windows worker 为默认路径；
- 已明确 Cloudflare Profile A 为推荐个人远程路径；
- 当前更新分支、HEAD 和 clean worktree 已记录。

### 发布前仍需重新捕获

最终 RC 必须重新记录：

- exact branch / commit；
- worktree clean；
- tool contract；
- dependency lock；
- installer/package identity；
-最终测试结果。

---

## Stage 1 — License、Security 与 Threat Model

**优先级：P0**  
**状态：CORE COMPLETE**

### 已完成

- [x] 根目录 `LICENSE`；
- [x] GNU AGPL v3，SPDX `AGPL-3.0-only`；
- [x] `bridge/pyproject.toml` license 一致；
- [x] `SECURITY.md`；
- [x] `docs/architecture/security-model.md`；
- [x] `docs/architecture/threat-model.md`；
- [x] 关键威胁已映射到自动测试或 Phase 6/7 验收项。

### Stage 6 联动项

- [ ] 复核全部第三方 dependency license；
- [ ] 明确是否生成 `THIRD_PARTY_NOTICES.md`；
- [ ] 如果生成，区分本项目 AGPL 与第三方依赖各自许可证。

---

## Stage 2 — Phase 6 Windows 运维与可靠性收口

**优先级：P0**  
**状态：IN PROGRESS — RELEASE BLOCKER**

权威记录：

`docs/acceptance/phase-6-validation.md`

### 目标

证明推荐 release path 在真实 Windows 11 环境中具备可重复启动、诊断、停止、异常恢复和安全日志行为。

### Mandatory Profile A 验收

必须针对：

```text
Windows packaged runtime
+ Native Windows worker
+ Git for Windows
+ Cloudflare Tunnel
+ No-Auth network trust Profile A
```

完成并记录：

- [ ] 20/20 `start -> doctor -> stop` 生命周期；
- [ ] Bridge 异常退出恢复；
- [ ] `cloudflared` / managed Tunnel 异常退出恢复；
- [ ] native codemcp worker 异常退出；
- [ ] Bridge 端口被非本项目进程占用时 fail closed；
- [ ] Tunnel/health 端口冲突时不误杀无关进程；
- [ ] stale process metadata / stale state 安全恢复；
- [ ] Git unavailable 时给出 actionable diagnostic；
- [ ] Cloudflare tunnel credential 缺失/无效时不泄漏 secret；
- [ ] mutation 边界断线时不透明重放；
- [ ] command timeout / owned process-tree cleanup；
- [ ] synthetic secret/log canary scan；
- [ ] 空格路径；
- [ ] 中文路径/文件名；
- [ ] CRLF；
- [ ] LF；
- [ ] supported long Windows path；
- [ ] upgrade / rollback procedure 对当前 pinned baseline 复核。

### Compatibility 路径

WSL2 fallback 与 OpenAI Secure MCP Tunnel 已不是 installed release 的 mandatory default path。

处理原则：

- 若 `v0.1.0` 继续公开声明为“支持的 compatibility path”，保留相应测试/文档；
- 不再把“WSL 不可用”当作 Native Windows 默认安装路径的 P0 前置条件；
- 不得让 compatibility path 的旧假设覆盖当前默认产品架构。

### Exit

只有 Phase 6 validation 的 mandatory release checklist 全部有真实证据，Stage 2 才能 PASS。

---

## Stage 3 — Phase 7 最终 Release Acceptance

**优先级：P0**  
**状态：IN PROGRESS — RELEASE BLOCKER**

权威记录：

`docs/acceptance/acceptance-test-plan.md`

### 3.1 Automated release-candidate gate

最终 RC 必须重新执行并记录：

- [ ] complete registered test workflow；
- [ ] Ruff lint；
- [ ] Ruff format check；
- [ ] package/build checks；
- [ ] `git diff --check` 等价检查；
- [ ] worktree 在只读检查后保持 clean；
- [ ] 22-tool MCP contract 与预期完全一致。

历史的 `312 passed` / `316 passed` 属于已有证据，不代替 final RC re-run。

### 3.2 Functional acceptance

完整验证当前 22-tool surface，包括此前旧计划遗漏的：

- `directory_create`；
- `operation_reconcile`；
- `approval_confirm`；
- `file_create` / `file_write` 的当前 hash/baseline 语义。

### 3.3 Security negative matrix

至少重新覆盖：

- unknown project；
- arbitrary absolute path；
- traversal；
- symlink / junction / reparse escape；
- sensitive path read/search/diff；
- binary / oversized file；
- unregistered command；
- runtime argv / executable injection；
- dirty workspace；
- forged canonical request hash；
- idempotency conflict；
- wrong/expired/reused approval；
- cross-session / cross-project operation；
- checkpoint tamper；
- branch/HEAD CAS race；
- prompt injection cannot widen Bridge authorization；
- non-loopback configuration rejection；
- secret/log canary；
- Host/Origin boundary；
- ordinary public source cannot reach Bridge；
- model/provider egress remains absent。

### 3.4 Reliability / recovery matrix

必须验证：

- duplicate mutation replay；
- changed-hash conflict；
- Bridge restart before/after backend boundary；
- pending approval across restart；
- Tunnel disconnect；
- worker crash；
- timeout/process-tree cleanup；
- external Git race；
- reconcile verified-not-applied；
- reconcile verified-applied；
- 20-cycle lifecycle result。

### 3.5 Real-project acceptance

最终 Gate 仍要求至少 10 个完整远程修改任务，而不是 10 个孤立 tool call：

- 至少一个真实 Java 项目；
- 至少一个具有前端 build/test workflow 的项目；
- 覆盖 checkpoint / restore / reconcile；
- 每个任务记录 branch/HEAD、session、operation、commands、diff、approval、unknown state 和最终 test；
- 公共验收记录不得复制 proprietary source 内容。

### 3.6 ChatGPT-only reasoning boundary

必须确认：

- Bridge 无 model provider；
- 无 hidden agent loop；
- codemcp 是 execution backend，不是第二推理 agent；
- repo prompt/content 不能自行获得高权限；
- 观察到的网络流量能区分合法 Tunnel 控制流量与禁止的 model/provider egress。

---

## Stage 4 — README、Onboarding 与文档一致性

**优先级：P1**  
**状态：REPOSITORY IMPLEMENTATION COMPLETE / FINAL VERIFICATION PENDING**

### 已完成

主 README 已经反映：

- packaged Windows runtime；
- Native Windows worker；
- Git for Windows prerequisite；
- Cloudflare Profile A；
- optional OAuth Profile B；
- project add/remove hot reload；
-无任意 shell；
-无 auto push/merge/deploy；
- public-user Quick Start。

### 文档对齐状态（2026-08-28）

当前规范文档已完成仓库侧对齐：

- [x] `docs/implementation-plan.md` 已从绿色场景/旧 Phase 计划改为当前 `v0.1.0` 实施基线；
- [x] `docs/architecture/architecture.md` 已改为 Cloudflare Profile A + Native Windows 默认拓扑；
- [x] `docs/guides/operations-runbook.md` 已以 packaged managed CLI 为主运维路径；
- [x] `docs/guides/codemcp-baseline.md` 已明确 Native Windows 默认、WSL2 compatibility fallback；
- [x] `docs/acceptance/phase-6-validation.md` 已改为 packaged Windows / Cloudflare / local worker mandatory matrix；
- [x] `docs/acceptance/acceptance-test-plan.md` 已同步 22-tool contract、当前治理文件与最终 RC Gate；
- [x] 主 README 的 source-development 与 operator 流程已不再把 Secure MCP scripts 当默认路径；
- [x] Cloudflare runbook 已同步 Phase H COMPLETE 与 optional `1033` deviation；
- [x] security/threat model 中相关 worker/transport/release-matrix 表述已同步当前边界。

`docs/releases/` 与 `docs/reports/` 中的旧 WSL2 / Secure MCP-first 描述保留为 historical evidence，不应被重写成当前事实；`docs/README.md` 已明确区分 current normative docs 与 historical records。

### 最终验收

- [ ] 从 final artifact / clean Windows 环境只按 README 完成安装；
- [ ] 注册项目；
- [ ] `doctor`；
- [ ] start；
- [ ] read-only call；
- [ ] controlled mutation；
- [ ] stop；
- [ ] 用户能理解 Profile A 是 network trust 而非 user authentication；
- [ ] known limitations 与代码一致；
- [x] 当前规范文档不存在 WSL2-required / native-Windows-unsupported 等错误现行声明；历史记录仅作为 historical evidence 保留。

---

## Stage 5 — GitHub 开源治理与 CI

**优先级：P1**  
**状态：REPOSITORY IMPLEMENTATION COMPLETE / HOSTED ACTIVATION PENDING**

验证记录：

`docs/reports/testing/stage-5-validation.md`

### 已落库

- [x] `CONTRIBUTING.md`
- [x] `CODE_OF_CONDUCT.md`
- [x] `CHANGELOG.md`
- [x] `.github/workflows/ci.yml`
- [x] bug report issue form
- [x] feature request issue form
- [x] PR template
- [x] Dependabot configuration

### GitHub hosted 验收

仓库进入正式 GitHub 开源发布流程后必须验证：

- [ ] first hosted CI run 在 Ubuntu / Windows 成功；
- [ ] PR 自动获得 required CI checks；
- [ ] Dependabot 正确识别 uv 和 GitHub Actions；
- [ ] release branch/main branch ruleset 要求必要 checks；
- [ ] Issue forms / PR template 渲染正确；
- [ ] hosted CI 使用最小权限，不持久化不必要 credentials。

本地存在 workflow 文件不能等价于 hosted CI PASS。

---

## Stage 6 — Secrets、隐私与供应链审查

**优先级：P0**  
**状态：LOCAL AUTOMATED SECURITY GATES PASS / MANUAL LICENSE REVIEW + HOSTED CI + CLEAN-MACHINE PRODUCTION INSTALLER PENDING — RELEASE BLOCKER**

验证记录：

`docs/reports/testing/stage-6-validation.md`

### 仓库侧已实现

- [x] current non-historical tracked tree privacy regression；
- [x] 固定 `security-audit`：locked dependency audit、tracked-tree scan、all-ref Git-history scan；
- [x] 固定 `artifact-audit`：强制标准 `v0.1.0` RC ZIP，并拒绝 runtime/secret material 与 operator-specific data；
- [x] Gitleaks `8.30.0` Windows/Linux 资产固定版本与 SHA-256；
- [x] hosted CI security job 已落库，使用 full-history checkout 与 `--log-opts=--all`；
- [x] built-in command catalog 与根 `codemcp.toml` 已同步；
- [x] `codemcp==0.3.0` provenance / license metadata discrepancy 已复核并记录；
- [x] dependency license inventory 已进入本地 security workflow 与 hosted CI，并有实际执行回归；
- [x] Windows PyInstaller 构建工具完整 wheel 闭包已固定版本 + PyPI SHA-256，禁止 transitive drift；
- [x] PyInstaller upstream `COPYING.txt` / bootloader exception 与 `BUILD_PROVENANCE.json` 已进入 release contract；
- [x] third-party notice 策略已确定：生成 `THIRD_PARTY_NOTICES.txt` + `BUILD_PROVENANCE.json` + component license files；
- [x] 一键 `build-windows-release.ps1` 已实现 installer smoke → staging payload audit → RC 构建 → final RC audit，并分别保存审计证据；
- [x] 仓库侧回归：`77 files already formatted`；`342 passed, 7 skipped, 0 failed`。

### 本地自动化证据

- [x] 扫描当前 tracked working tree：PASS；
- [x] 扫描整个 Git history：PASS，无 Gitleaks findings；
- [x] 扫描 `.github/`、scripts、configs、docs、tests、fixtures：PASS；
- [x] 扫描 final release artifact：PASS；
- [x] final artifact 未检测到：
  - 本地 `projects.toml`；
  - Tunnel profile；
  - `.local/` runtime state；
  - logs；
  - SQLite；
  - DPAPI/runtime secret material；
  - operator-specific deployment/path data。
- [x] dependency vulnerability audit：47 packages，0 known vulnerabilities，0 adverse statuses；
- [x] dependency license evidence inventory：47/47 accounted for，`missing_license_evidence=[]`；
- [x] exact installer SHA-256：`902e15205aee3d585fafa0248c89419171f5a14d6bb249655820318d4fd8e7c6`；
- [x] exact RC ZIP SHA-256：`0ce11c91e5735808ffa1260755ba4030adbed220f5d2f9fe5ca9818b3a39fed1`。

### 仍需真实执行

- [ ] 对 exact RC 的 dependency/license compatibility 做人工 signoff；
- [ ] hosted CI security job PASS；
- [ ] production AppId installer clean-machine validation PASS；

### Secret 发现规则

如果发现历史凭据：

1. 先 revoke / rotate；
2. 再清理 Git history；
3. 重新扫描；
4. 重新生成 release candidate；
5. 删除当前文件不等于历史清理完成。

### Exit

必须形成可审计的：

- working tree scan PASS；
- Git history scan PASS；
- artifact scan PASS；
- dependency audit PASS 或明确 accepted risk；
- license review PASS。

---

## Stage 7 — Release Packaging 与 Clean Machine

**优先级：P1**  
**状态：IMPLEMENTATION SUBSTANTIALLY COMPLETE / STRICT PASS PENDING**

### 已实现

当前已经具备：

- packaged `codemcp-remote.exe`；
- Inno Setup installer；
- `codemcp-remote-setup.exe`；
- release-candidate Windows ZIP；
- SHA-256 manifest / checksum 流程；
- clean Windows validation harness；
- Windows PowerShell 5.1-compatible validation path；
- bundled `cloudflared`；
- optional bundled `tunnel-client`；
- DPAPI transport-secret handling；
- Native Windows worker；
- installer identity / upgrade ownership checks。

### 为什么仍不能标记 PASS

现有记录明确说明 strict Packaging Phase 5 尚未正式关闭：

- live mutation 使用了 `codemcp-remote` 仓库中的临时 acceptance file，而不是固定 disposable `phase5-clean` repo；
- Cleanup/uninstall 为保持当前工作 Connector 而被延后；
- 因此这次 Phase H live success 不能直接升级为 strict clean-machine packaging PASS。

### Final RC 必须执行

- [ ] 从最终 commit 重新构建 installer；
- [ ] 从最终 commit 重新构建 ZIP；
- [ ] 生成并核对 SHA-256；
- [ ] 在 clean Windows 11 环境安装；
- [ ] 隔离 PATH 后确认 Python/uv/pwsh 不可见；
- [ ] `worker_mode=local`；
- [ ] Git prerequisite 正确；
- [ ] Profile A tunnel token 使用 DPAPI；
- [ ] 注册 disposable `phase5-clean`；
- [ ] start Bridge + Tunnel；
- [ ] 真实 ChatGPT Connector 对 disposable repo 完成 read/mutation/replay/restore；
- [ ] final Git state 精确恢复 baseline；
- [ ] Cleanup/uninstall PASS；
- [ ] artifact 再做 secret scan；
- [ ] release notes / known limitations / exact commit identity 一致。

### 当前 Authenticode

现有 candidate 记录为 `NotSigned`。

在 `v0.1.0` 前必须明确二选一：

- 对 installer/code signing 做正式签名；或
- 将未签名作为明确 known limitation，并评估 Windows SmartScreen/用户信任影响。

不能既保持 `NotSigned` 又在文档中暗示已签名发布。

---

# 5. 当前阻塞项

## P0 — 未关闭不得发布 stable

1. **Phase 6 mandatory Windows real-host matrix PASS**；
2. **Phase 7 final release-candidate acceptance PASS**；
3. **Git history / working tree / artifact secret scans PASS**；
4. **dependency vulnerability + license audit PASS/accepted**；
5. **strict clean-machine packaging / disposable repo / cleanup PASS**；
6. **关键安全 finding 全部关闭或明确阻止 release**；
7. **当前规范文档不能继续包含与真实产品相冲突的运行时声明**。

## P1 — `v0.1.0` 前必须收口

1. GitHub hosted CI 首次 PASS；
2. required checks / branch ruleset；
3. Dependabot hosted activation；
4. clean-machine README onboarding；
5. final CHANGELOG；
6. final known limitations；
7. final release artifact；
8. final SHA-256；
9. release notes；
10. tag 与已验收 commit 一致。

## P2 — `v0.1.x / v0.2` 可继续

- CodeQL / dependency review 深化；
-自动 release workflow；
- code signing 自动化；
-更多平台；
-更多 transport adapter；
-多用户身份 / RBAC；
- OAuth Profile B 更完整 live interoperability matrix；
- codemcp fork /替代执行后端（仅在实际兼容性问题需要时）。

Native Windows mutation **不再是 P2**，因为它已经是当前默认实现。

---

# 6. 从当前状态开始的推荐执行顺序

不再沿用“Stage 0 -> 1 -> 2 -> 3 -> 6 -> 4 -> 5 -> 7”的旧线性顺序，因为 Stage 4/5/7 的大量实现已经提前完成。

从当前分支开始建议：

1. **当前计划与规范文档对齐：COMPLETE**；
2. **Phase 6 Windows mandatory real-host matrix**；
3. 修复 Phase 6 暴露的 blocker；
4. **Phase 7 final RC automated + functional + security + reliability gate**；
5. **10 个 real-project remote tasks**；
6. **Stage 6 secrets / dependency / license / supply-chain audit**；
7. **strict clean-machine packaging acceptance**；
8. **GitHub hosted CI / Dependabot / ruleset activation**；
9. 从最终 release commit **重新构建** installer + ZIP；
10. 重新生成 SHA-256、artifact scan、CHANGELOG、release notes；
11. Final Release Gate sign-off；
12. tag `v0.1.0` 并发布 GitHub Release。

原则：

> 所有最终证据必须绑定同一个 release-candidate commit。  
> 任何修复只要改变 release artifact 或安全语义，就必须重新执行受影响的 Gate。

---

# 7. Final Release Gate

Stable `v0.1.0` 只有在下表全部满足后才可批准：

| Gate | 要求 |
|---|---|
| Release identity | exact branch / commit / lock / artifact identity 已记录 |
| Automated suite | final RC tests / lint / format / build PASS |
| MCP contract | 22-tool surface 与安全 contract VERIFIED |
| Functional | 核心 MCP 正常路径全部 PASS |
| Security | negative matrix / threat-model P0 paths PASS |
| Reliability | crash / restart / timeout / disconnect / unknown / reconcile / rollback PASS |
| Phase 6 | mandatory Windows real-host operations PASS |
| Real projects | 10/10 remote tasks 有完整 operation/audit/Git lineage |
| ChatGPT-only boundary | 无 hidden model/provider/agent loop |
| Network trust | Profile A live boundary保持 PASS |
| Secrets | working tree + Git history + artifact scan PASS |
| Supply chain | dependency vulnerability/license review PASS |
| Docs | README / architecture / guides / limitations 与实现一致 |
| GitHub CI | hosted required checks PASS |
| Packaging | final clean-machine installer/ZIP PASS |
| Cleanup | uninstall/cleanup contract PASS |
| Integrity | SHA-256 对 final artifacts VERIFIED |
| Signing | signed，或 NotSigned 被明确接受并记录为 limitation |
| Git | worktree clean，tag 指向唯一已验收 commit |

任何 P0 blocker、无法解释的 skip、secret exposure、unsafe mutation ambiguity、文档与实际行为冲突，都必须保持：

```text
release_decision = BLOCKED
```

---

# 8. Definition of Done

本 Open Source Readiness 计划只有在以下条件同时成立时才结束：

1. 默认产品架构明确为 Windows packaged runtime + Native Windows worker；
2. 推荐个人公网路径明确为 Cloudflare Profile A network trust；
3. optional Secure MCP / OAuth / WSL2 compatibility path 不再污染默认产品说明；
4.法律、安全、贡献、治理文件完整；
5. Phase 6 PASS；
6. Phase 7 PASS；
7. 10 个真实远程任务 PASS；
8. secrets / Git history / artifact scan PASS；
9. dependency vulnerability/license review PASS；
10. README 在 clean Windows 上独立可执行；
11. GitHub hosted CI/ruleset 已激活并 PASS；
12. final installer/ZIP 可从同一个已验收 commit 重复构建；
13. final artifact clean-machine acceptance PASS；
14. SHA-256 与 release artifact 一致；
15. known limitations 包含真实剩余边界，包括 network-only identity 与 signing 状态；
16. release tag 精确指向已验收 commit；
17. `v0.1.0` GitHub Release 发布后，第三方无需开发机隐含状态即可安装、诊断和开始受控使用。

完成以上条件后，codemcp-remote 才从 **pre-release / controlled private operation** 进入 **stable public open-source release**。
