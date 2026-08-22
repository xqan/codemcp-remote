# Goal

## 任务目标

构建一套完全独立于 Codex、OpenCode 和其他推理模型的本机代码修改服务。

ChatGPT 作为唯一的推理与决策引擎；本机 MCP Bridge 负责权限、会话、审计和协议转换；codemcp 负责文件操作、代码搜索、格式化、测试命令和 Git 相关执行；Secure MCP Tunnel 负责远程连接。

## 完成定义

1. 只有 ChatGPT 负责需求理解、规划、判断下一步和生成修改意图。
2. Bridge 和 codemcp 不调用任何 LLM、Embedding 服务或其他推理 API。
3. ChatGPT 通过 Secure MCP Tunnel 调用 Bridge。
4. Bridge 只允许访问预先登记的项目和命令。
5. 每次写操作可追踪、可验证、可回滚。

## 非目标

- 不引入 OpenCode Server。
- 不在 Bridge 中实现 Agent 循环、任务规划器、自动重试推理或模型路由。
- 不让 Bridge 连接任何模型服务。
- 不提供任意路径读写和无约束 shell。

# Current Architecture

## 当前事实与依据

当前工作区没有已有源码仓库，因此本计划是新项目的绿色场景设计。

已确认：

- Secure MCP Tunnel 支持本机运行 tunnel-client，通过出站 HTTPS 将 MCP 请求转发到本地 stdio 或 HTTP MCP 服务。
- codemcp 提供文件读取、写入、定点编辑、目录列表、搜索、项目初始化、格式化等 MCP 工具，并支持通过 codemcp.toml 配置项目提示和命令。
- codemcp 主要面向 Claude Desktop；必须固定版本并先做兼容性验证，不能把上游当前行为视为稳定 API。

## 目标拓扑

~~~mermaid
flowchart LR
    C["ChatGPT：唯一推理"] --> T["Secure MCP Tunnel"]
    T --> TC["tunnel-client"]
    TC --> B["MCP Bridge"]
    B --> A["codemcp Adapter / Worker"]
    A --> P["已登记的本机项目"]
~~~

## 请求处理链

1. ChatGPT 根据用户请求决定读取、搜索、编辑、测试、查看 diff 或申请高风险操作。
2. Secure MCP Tunnel 将 MCP 请求转发到本机 tunnel-client。
3. tunnel-client 将请求转发到 Bridge 的 loopback HTTP MCP endpoint。
4. Bridge 校验 project_id、session_id、路径、操作权限和幂等键。
5. Bridge 通过 codemcp Adapter 调用对应的 codemcp 工具。
6. Bridge 对结果进行截断、脱敏、结构化和审计，然后返回 ChatGPT。
7. ChatGPT 决定下一次工具调用；Bridge 不主动替 ChatGPT 规划下一步。

# Architecture Decision

## AD-1：ChatGPT 是唯一推理引擎

Bridge 的依赖和配置中不得出现模型 provider、模型名称、API key、prompt router、agent loop 或自动任务分解器。

codemcp 的 project_prompt 只用于静态项目约束，例如编码规范、测试命令和禁止修改的目录，不用于驱动第二个 Agent。

每一个需要继续修改的步骤，都必须由 ChatGPT 再次发起 MCP tool call。Bridge 不能接收一个自然语言任务后自行循环执行多个推理步骤。

## AD-2：Bridge 是安全网关，不是第二个 Agent

Bridge 对外是 MCP Server，对内是 codemcp MCP Client 或受控进程管理器。

Bridge 负责：

- 项目注册与路径映射
- session 和 operation 生命周期
- codemcp worker 启停、健康检查和崩溃恢复
- 工具参数验证
- 文件范围、命令范围和权限判断
- Git 基线、checkpoint、diff 和回滚保护
- 审批、审计、幂等和超时
- 结果大小限制、敏感信息脱敏和错误归一化

Bridge 不负责：

- 解释用户需求
- 生成代码方案
- 自动选择下一步
- 调用任何外部模型

## AD-3：Bridge 是唯一对外暴露的 MCP Server

codemcp 不直接连接 Secure MCP Tunnel，也不直接暴露给 ChatGPT。这样可以避免 ChatGPT 绕过项目权限、审计和审批逻辑。

第一版优先采用：

~~~text
ChatGPT
  -> OpenAI Secure MCP Tunnel
  -> tunnel-client
  -> Bridge: 127.0.0.1:<bridge_port>/mcp
  -> codemcp Adapter
  -> 一个 project/session 对应的 codemcp worker
~~~

codemcp Adapter 的实现方式在 Phase 1 根据固定版本的实际接口选择：

1. 优先使用 codemcp 的本地 stdio 或 HTTP/SSE MCP 接口。
2. 如果必须调用 codemcp CLI，则由 Adapter 启动子进程并使用结构化协议。
3. 如果上游的自动提交、Windows Git 或工具描述与安全模型冲突，维护最小 fork，而不是在 Bridge 中复制大量 codemcp 逻辑。

## AD-4：对 ChatGPT 暴露受控工具

Bridge 不把原始 shell 直接暴露给 ChatGPT。第一版建议工具：

| 工具 | 用途 | 是否写操作 | 默认策略 |
|---|---|---:|---|
| project_open | 打开已登记项目并创建 session | 否 | 仅允许 project_id |
| project_status | 返回项目、分支、dirty 状态和 worker 状态 | 否 | 自动允许 |
| file_read | 读取项目内文本文件 | 否 | 路径校验、大小限制 |
| code_search | 在项目范围内搜索代码 | 否 | 忽略 .git、构建目录和敏感文件 |
| file_list | 列出允许范围内的目录 | 否 | 禁止越过项目根目录 |
| file_edit | 调用 codemcp EditFile 或 WriteFile | 是 | 需要 session 和基线 |
| format_run | 执行登记的格式化命令 | 可能 | 仅允许命令 ID |
| test_run | 执行登记的测试命令 | 可能 | 仅允许命令 ID |
| git_status | 返回分支、HEAD 和文件变更摘要 | 否 | 自动允许 |
| git_diff | 返回受限 diff | 否 | 截断并脱敏 |
| checkpoint_create | 建立 Git checkpoint | 是 | 显式确认 |
| checkpoint_restore | 恢复指定 checkpoint | 是 | 二次确认 |
| operation_status | 查询长时间运行操作 | 否 | 自动允许 |
| operation_cancel | 取消当前操作 | 是 | 只允许操作所有者 |
| approval_confirm | 确认明确列出的高风险操作 | 是 | 一次性、短时有效 |

工具结果统一返回 request_id、session_id、project_id、operation_id、status、changed_files、输出摘要、truncated、next_cursor 和 error_code。

## AD-5：项目和命令采用显式注册

Bridge 配置文件只登记项目别名和绝对路径，不接受 ChatGPT 传入任意本机路径。命令只允许结构化 argv，第一版禁止 ChatGPT 追加任意参数。

~~~toml
[projects.pet_manage]
root = "D:/workspace/pet-manage"
allowed_branches = ["main", "develop", "feature/*"]
require_clean_workspace = true
codemcp_config = "codemcp.toml"

[projects.pet_manage.commands.test]
kind = "test"
argv = ["mvn", "-q", "test"]
timeout_seconds = 900

[projects.pet_manage.commands.build]
kind = "build"
argv = ["mvn", "-q", "-DskipTests", "package"]
timeout_seconds = 900
approval = "required"
~~~

实际配置格式在 Phase 0 固化。

## AD-6：操作具有明确状态和幂等语义

操作状态：

~~~text
received -> validated -> awaiting_approval -> dispatched -> running
                                      -> succeeded | failed | cancelled | unknown
~~~

关键规则：

- 每次写操作必须有 client_request_id 和 request_hash。
- 相同请求重试返回原结果，不重新执行。
- 写操作在断线后不能直接重试，必须先通过 HEAD、文件 hash、Git 状态和 operation 记录进行 reconcile。
- 无法判断 codemcp 是否已经完成写入时，状态必须为 unknown，并阻止同一项目继续写入。
- 同一个项目默认只允许一个 mutation operation 运行。

## AD-7：Git 是保护层，不是隐式发布机制

第一版默认：

- dirty workspace 禁止直接写入，除非用户明确确认并记录基线。
- 写操作前记录 HEAD、工作区文件 hash 和 dirty 文件清单。
- 写操作后记录 codemcp 产生的 commit、文件 hash 和 diff 摘要。
- 不自动 push、merge、rebase、deploy 或删除分支。
- rollback 使用 compare-and-swap，发现外部新修改时 fail closed。

codemcp 上游可能对每次编辑创建或 amend Git commit。Phase 1 必须先确认实际行为，再决定是否增加 commit_mode 或维护最小 fork。

## AD-8：本地持久化使用 SQLite

建议对象：

- projects
- sessions
- operations
- approvals
- checkpoints
- audit_events
- worker_processes
- locks

默认不保存完整源文件内容；保存路径、大小、SHA-256、diff 摘要、结果摘要和必要错误信息。

## 推荐目录结构

~~~text
codemcp-remote/
├─ bridge/
│  ├─ pyproject.toml
│  ├─ src/codemcp_bridge/
│  │  ├─ main.py
│  │  ├─ settings.py
│  │  ├─ mcp_server.py
│  │  ├─ project_registry.py
│  │  ├─ policy_engine.py
│  │  ├─ session_service.py
│  │  ├─ operation_service.py
│  │  ├─ codemcp_adapter.py
│  │  ├─ worker_manager.py
│  │  ├─ git_guard.py
│  │  ├─ audit_store.py
│  │  ├─ approval_service.py
│  │  ├─ output_sanitizer.py
│  │  └─ errors.py
│  └─ tests/
├─ config/
│  ├─ bridge.example.toml
│  └─ projects.example.toml
├─ scripts/
│  ├─ start-bridge.ps1
│  ├─ start-tunnel.ps1
│  ├─ doctor.ps1
│  └─ stop-all.ps1
├─ docs/
│  └─ implementation-plan.md
└─ README.md
~~~

# Constraints

## 模型与执行边界

- ChatGPT 是唯一推理引擎。
- Bridge、codemcp、tunnel-client 都不得配置或调用模型。
- 不允许隐藏的后台 Agent、任务队列自动执行或自然语言转 shell。
- 每次工具调用都必须能映射到一个可审计 operation。

## 安全边界

- Bridge 只监听 127.0.0.1，不绑定 0.0.0.0。
- Secure MCP Tunnel 只作为传输通道，不能替代 Bridge 的项目授权。
- 项目必须通过 project_id 登记；拒绝绝对路径和路径穿越。
- 检查 Windows junction、symlink、reparse point，不能通过链接逃逸项目根目录。
- 默认拒绝 .env、私钥、证书、token、密码文件和密钥目录。
- 不暴露任意 shell；命令必须来自项目命令目录。
- 高风险动作必须显式审批。
- 运行命令必须有超时、进程树清理、输出上限和退出状态。
- 日志不得记录 runtime API key、完整 secret 文件或未脱敏 token。

## 兼容性

- 首要运行环境为 Windows 11。
- 同时验证 Windows 原生 Python/Git 和 WSL2 运行 codemcp。
- 固定 codemcp commit 或 release，不依赖 main 分支。
- 不能假设 codemcp 的 Claude Desktop 配置、SSE 行为、自动提交行为或 Windows Git 行为稳定。
- Bridge 核心逻辑必须能在不启动 MCP transport、不连接 Tunnel 的情况下测试。

## 可靠性

- 每个 project/session 使用独立 worker 或独立 adapter context。
- 同一项目的写操作串行化。
- Bridge 重启后能从 SQLite 恢复未完成 operation 状态。
- Tunnel 断开不应触发本地 mutation 重放。
- 任何无法确认副作用的失败必须 fail closed。

# Impact Scope

## 代码模块

- Bridge MCP transport
- codemcp adapter 和 worker 生命周期
- 项目注册与路径沙箱
- 文件、搜索、编辑工具映射
- 受控命令执行
- Git checkpoint、diff、rollback
- session、operation、approval、audit 持久化
- Windows 启停脚本和诊断命令

## 配置

- 项目注册文件
- 命令白名单
- codemcp.toml
- Bridge 本地端口和数据库路径
- tunnel-client profile、tunnel_id 和运行时认证配置

## 测试

- Bridge 核心单元测试
- MCP JSON-RPC 合约测试
- Bridge-codemcp 集成测试
- Git 和 checkpoint 测试
- Windows 路径、中文路径、空格路径和进程树测试
- Secure MCP Tunnel 端到端验收
- 断线、超时、重复请求、codemcp 崩溃和 unknown 状态测试

# Phases

## Phase 0：确定版本、边界和最小仓库骨架

### Goal

建立新项目骨架，固定技术选型、codemcp 版本、Windows/WSL 运行策略和配置格式。

### Files / Modules

- pyproject.toml
- README.md
- config/bridge.example.toml
- config/projects.example.toml
- docs/architecture.md
- docs/operations-runbook.md
- tests/fixtures/sample-git-project/

### Changes

1. 选择 Python 3.12+ 作为 Bridge 语言，使用异步 MCP SDK。
2. 固定 codemcp release 或 commit，并记录来源、许可证和升级方式。
3. 固定 Bridge 的本地 HTTP MCP endpoint、SQLite 路径和日志路径。
4. 定义 project registry、command catalog 和安全默认值。
5. 明确 native Windows 与 WSL2 的第一阶段支持矩阵。
6. 明确所有不允许的模型依赖和网络出口。

### Dependencies

- Python、uv、Git
- MCP SDK
- 已固定版本的 codemcp
- Windows 11 或 WSL2 测试环境

### Risks

- codemcp 上游行为与 README 不完全一致。
- Windows 原生 Git、路径编码或子进程行为导致后续需要 WSL2。
- 过早复制 codemcp 内部实现，造成维护负担。

### Validation

- 空项目可以安装 Bridge 依赖。
- codemcp 版本、Python 版本和 Git 版本可以被 doctor 输出。
- 示例配置能通过 schema/config validation。

### Acceptance Criteria

- 形成可提交的空仓库骨架。
- README 明确 ChatGPT-only 约束。
- 版本、平台和回退策略已写入文档。

## Phase 1：codemcp 本地兼容性验证

### Goal

确认 codemcp 可以在目标环境中作为纯 MCP 执行后端使用，并记录真实工具、协议和 Git 行为。

### Files / Modules

- bridge/src/codemcp_bridge/codemcp_probe.py
- tests/integration/test_codemcp_compatibility.py
- docs/codemcp-compatibility-matrix.md
- tests/fixtures/sample-git-project/

### Changes

1. 启动固定版本 codemcp server。
2. 验证 initialize、tools/list 和各工具的实际 schema。
3. 验证 InitProject、LS、ReadFile、Grep、EditFile、WriteFile、Format。
4. 验证 codemcp.toml 的 project_prompt 和 commands 行为。
5. 验证格式化、测试命令、退出码、stdout/stderr 和超时。
6. 记录每次编辑是否创建 commit、是否 amend、失败时是否留下半成品。
7. 分别在 Windows 原生和 WSL2 执行包含空格、中文和长路径的 Git 项目。
8. 验证 worker 崩溃、退出、重复启动和端口占用时的行为。

### Dependencies

- Phase 0 版本和测试项目。

### Risks

- 上游工具定义可能带有 Claude-specific 假设。
- 原始命令配置可能在 shell context 中拼接参数，存在注入风险。
- Windows Git 行为可能不满足可靠性要求。

### Validation

- 使用 MCP Inspector 或等价 MCP client 完成本地工具合约测试。
- 每个写操作前后记录 HEAD、文件 hash 和 diff。
- 运行失败和 worker 崩溃场景，不允许无记录地重试。

### Acceptance Criteria

- 明确列出可复用的 codemcp 工具和需要由 Bridge 屏蔽的工具。
- 明确选择 Windows 原生、WSL2 或双模式。
- 明确选择直接使用上游还是维护最小 fork。
- 未发现任何模型调用路径。

### Phase 1 decision record (2026-08-22)

- 平台选择：codemcp mutation worker 运行在 WSL2 Ubuntu；原生 Windows
  worker 的 Git-backed subtool 在 stdio 场景阻塞，不纳入当前支持矩阵。
- 上游选择：Phase 2 先直接使用固定的上游 `codemcp==0.3.0`，不维护 fork。
  如果未来必须支持原生 Windows，再单独评估最小 stdin/timeout/process-tree fork。
- 路径与超时：Adapter 必须把已登记的 Windows 项目根显式映射到 WSL 路径，
  在 worker 外部执行超时和进程树清理；WSL 挂载路径的兼容性测试使用 30 秒
  probe budget。上游 `RunCommand` 的可选 timeout 不足以替代 Bridge 的超时控制。
- Git 语义：已确认 `InitProject` 创建初始 codemcp commit，`EditFile` 和
  `WriteFile` 会改变 HEAD 但不增加 commit 数；Bridge 的 checkpoint、审计和
  rollback 语义由 Bridge 自己实现，不把上游 commit 当作审批替代品。
- ChatGPT-only：安装包源码和依赖未发现模型 provider；Bridge 仍必须保持
  `model_egress = "deny"`。

## Phase 2：Bridge 核心与 codemcp Adapter

### Goal

实现本地、非 Tunnel 环境下可工作的安全 Bridge，并把 codemcp 封装为受控后端。

### Files / Modules

- bridge/src/codemcp_bridge/main.py
- bridge/src/codemcp_bridge/settings.py
- bridge/src/codemcp_bridge/project_registry.py
- bridge/src/codemcp_bridge/policy_engine.py
- bridge/src/codemcp_bridge/codemcp_adapter.py
- bridge/src/codemcp_bridge/worker_manager.py
- bridge/src/codemcp_bridge/errors.py
- bridge/tests/unit/
- bridge/tests/integration/

### Changes

1. 实现 loopback-only MCP Server。
2. 实现 project_id 到绝对路径的安全映射。
3. 实现 codemcp worker 按项目或 session 隔离。
4. 实现工具参数 schema 验证、项目根目录检查和文件类型限制。
5. 实现统一错误码：PROJECT_NOT_ALLOWED、PATH_ESCAPE、COMMAND_NOT_ALLOWED、APPROVAL_REQUIRED、WORKSPACE_DIRTY、CONFLICT、BACKEND_UNAVAILABLE、UNKNOWN_SIDE_EFFECT。
6. 实现 stdout/stderr、文件内容和 diff 的大小限制。
7. 实现 request_id、session_id、operation_id 和 structured error。
8. 通过本地 MCP client 验证 file_read、code_search、file_edit、format_run、test_run。

### Dependencies

- Phase 1 的 codemcp Adapter 结论。
- MCP SDK 和配置 schema。

### Risks

- MCP transport 和 codemcp downstream transport 的并发语义不一致。
- worker 重启时可能丢失当前 tool call 状态。
- 大文件和大 diff 可能耗尽 ChatGPT 上下文。

### Validation

- 不连接 Tunnel，使用本地 MCP client 完成完整读、改、格式化、测试、diff 流程。
- 使用恶意路径、符号链接、二进制文件和超大文件验证拒绝逻辑。
- 模拟 codemcp 不可用、崩溃和响应超时。

### Acceptance Criteria

- Bridge 可以独立启动和健康检查。
- 本地 MCP client 可以发现并调用受控工具。
- Bridge 没有模型配置、模型依赖和外部推理网络调用。
- 未登记的项目、路径和命令全部被拒绝。

## Phase 3：Session、Operation、审批和审计

### Goal

让远程代码修改具备可恢复、可追踪和可审计的生命周期。

### Files / Modules

- bridge/src/codemcp_bridge/session_service.py
- bridge/src/codemcp_bridge/operation_service.py
- bridge/src/codemcp_bridge/approval_service.py
- bridge/src/codemcp_bridge/audit_store.py
- bridge/src/codemcp_bridge/db/
- bridge/tests/test_phase3_persistence.py
- bridge/tests/test_phase2_server.py

### Changes

1. 建立 SQLite schema 和 migration 机制。
2. 实现 session 状态：created、active、closing、closed、blocked。
3. 实现 operation 状态机及状态变更审计。
4. 实现 mutation 的幂等键和 request hash。
5. 实现项目级写锁和读取并发限制。
6. 实现显式 approval token，设置短 TTL、一次性消费和 operation 绑定。
7. 实现 Bridge 重启后的恢复扫描。
8. 对断线后的 mutation 标记 unknown，并要求 reconcile。
9. 单用户 v1 以本机 policy profile 为授权边界；不把 chatgpt-mcp-session 当作完整用户身份。

### Dependencies

- Phase 2 Bridge 基础能力。

### Risks

- 进程在文件已经改变但数据库尚未提交时崩溃。
- 重试请求可能造成重复编辑或重复命令。
- 审批确认可能错误绑定到另一个项目或 operation。

### Validation

- 在每个状态转移点注入进程终止。
- 重复发送相同和不同 request_hash。
- 让 Tunnel、Bridge、codemcp worker 分别断开后恢复。
- 验证 approval token 过期、复用、跨 session 和跨 project 均失败。

### Acceptance Criteria

- Bridge 重启后能区分已完成、未执行、失败和 unknown 的 operation。
- mutation 不会因网络重试自动重复执行。
- 每个高风险操作都能关联唯一审批记录和审计记录。

## Phase 4：Git checkpoint、diff 和回滚

### Goal

在不改变用户原有 Git 工作流的前提下，为远程修改提供可靠的检查点和恢复能力。

### Files / Modules

- bridge/src/codemcp_bridge/git_guard.py
- bridge/src/codemcp_bridge/checkpoint_service.py
- bridge/tests/test_phase4_git.py
- docs/git-policy.md

### Changes

1. 实现 project_status 和 git_status。
2. 实现 dirty workspace 检查和用户确认流程。
3. 写操作前记录 HEAD、分支、文件 hash 和 baseline。
4. 写操作后记录 codemcp commit、变更文件和 diff hash。
5. 实现受限 git_diff，禁止返回未经脱敏的密钥文件。
6. 实现 compare-and-swap rollback。
7. 禁止通过 MCP 执行 push、force reset、rebase、删除分支和部署。
8. 根据 Phase 1 结果决定是否提交 codemcp 最小 fork，以控制自动提交行为。

### Dependencies

- Phase 3 operation/audit。
- Phase 1 codemcp Git 行为结论。

### Risks

- 用户在 ChatGPT 操作期间从 IDE 或命令行修改同一文件。
- codemcp 自动 commit 与 Bridge checkpoint 语义重复。
- Windows 换行符和大小写导致 hash/diff 不一致。

### Validation

- clean workspace、dirty workspace、外部修改、分支切换、HEAD 改变和 rollback 竞争测试。
- 使用中文路径、CRLF/LF 和大小写不同文件名测试。
- 验证 rollback 在冲突时 fail closed。

### Acceptance Criteria

- 用户可以看到每次修改前后的准确基线和 diff。
- 回滚不会静默覆盖并发修改。
- 无明确批准时不会执行破坏性 Git 操作。

## Phase 5：Secure MCP Tunnel 集成

### Goal

让 ChatGPT 通过 Secure MCP Tunnel 访问本机 Bridge，并验证远程工具调用闭环。

### Files / Modules

- scripts/start-bridge.ps1
- scripts/start-tunnel.ps1
- scripts/doctor.ps1
- config/tunnel-profile.example.env
- docs/tunnel-setup.md
- tests/e2e/test_tunnel_contract.md

### Changes

1. Bridge 只监听 loopback HTTP MCP endpoint。
2. tunnel-client 使用 HTTP MCP server URL 指向 Bridge，不直接指向 codemcp。
3. 使用 Windows secret 存储或环境变量注入 runtime API key，不写入 Git。
4. 提供 tunnel-client init、doctor、run、healthz、readyz 的诊断脚本。
5. 在 ChatGPT developer mode 创建开发 app，连接类型选择 Tunnel。
6. 验证 tunnel_id 与 ChatGPT workspace、Platform organization 的关联。
7. 检查 Tunnel 出站 HTTPS、Bridge 本地连通性和 MCP tool discovery。
8. 关联 ChatGPT request_id 与 Bridge operation_id。

### Dependencies

- Phase 2、3、4 本地流程全部通过。
- OpenAI Platform tunnel 权限和 ChatGPT developer mode 权限。

### Risks

- tunnel-client 停止时 ChatGPT 工具发现和调用都会失败。
- Tunnel 选择和 workspace 关联错误会表现为“看不到服务”。
- Tunnel 只解决连接，不会自动解决 Bridge 的项目权限。

### Validation

- 执行 tunnel-client doctor。
- 从 ChatGPT 发现 Bridge 工具。
- 完成一次只读、一次编辑、一次测试、一次 diff。
- 分别停止 tunnel-client、Bridge 和 codemcp worker，验证诊断和恢复行为。

### Acceptance Criteria

- ChatGPT 可以通过 Tunnel 发现并调用 Bridge。
- 本机不需要开放公网入站端口。
- 远程调用链能关联到完整审计记录。
- Tunnel 断开时不会触发本地 mutation 重放。

## Phase 6：Windows 11 运维化和开发者体验

### Goal

把服务变成可重复启动、停止、诊断和升级的本机工具。

### Files / Modules

- scripts/start-bridge.ps1
- scripts/start-tunnel.ps1
- scripts/stop-all.ps1
- scripts/doctor.ps1
- docs/operations-runbook.md
- docs/security-model.md
- README.md

### Changes

1. 提供一键启动 Bridge、codemcp worker 和 tunnel-client 的 PowerShell 流程。
2. 提供一键停止并清理子进程树的流程。
3. 提供版本、路径、配置、worker、数据库、Tunnel 和 Git 状态检查。
4. 统一日志目录、日志轮转、敏感字段脱敏和 operation 查询。
5. 处理 UTF-8、中文路径、空格路径、长路径和 CRLF。
6. 明确 native Windows 与 WSL2 的安装、迁移和故障排查步骤。
7. 固定依赖版本并提供升级前兼容性检查。

### Dependencies

- Phase 5 端到端流程。

### Risks

- PowerShell 权限、PATH 和 Git 配置差异。
- 进程树清理不完整导致端口或锁残留。
- 直接升级 codemcp 破坏 Adapter 兼容性。

### Validation

- 新机器或干净 Windows 用户目录执行安装和启动。
- 连续启动、停止、重启 20 次。
- 模拟 tunnel-client、Bridge 和 worker 任一进程异常退出。
- 检查日志不泄露密钥和敏感源文件内容。

### Acceptance Criteria

- 用户可以按 README 在 Windows 11 上完成安装和启动。
- doctor 可以定位常见问题。
- 升级 codemcp 前后都有明确的版本检查和回退方式。

## Phase 7：最终验收与交接

### Goal

完成安全、功能、可靠性和文档验收，形成可交给 developer 持续实现的基线。

### Files / Modules

- docs/acceptance-test-plan.md
- docs/threat-model.md
- docs/operations-runbook.md
- docs/implementation-plan.md
- tests/e2e/

### Changes

1. 编写从 ChatGPT 发起的完整验收脚本。
2. 验证 ChatGPT-only：Bridge、codemcp 和 tunnel-client 没有任何模型调用。
3. 验证读取、搜索、编辑、格式化、测试、diff、checkpoint、rollback。
4. 验证路径逃逸、命令注入、敏感文件读取、越权 project_id 和错误审批均被拒绝。
5. 验证重复请求、超时、断线、崩溃和 unknown 状态。
6. 记录已知限制、codemcp 固定版本和升级流程。

### Dependencies

- Phase 0 至 Phase 6。

### Risks

- Tunnel 端到端验收受 ChatGPT workspace 权限影响。
- 上游 codemcp 版本变化导致复测结果变化。
- 长任务和超大项目的上下文/响应上限未在小样例中暴露。

### Validation

- 通过全部单元、合约、集成和 Windows e2e 测试。
- 使用至少一个真实 Java 项目和一个包含前端构建命令的项目。
- 完成连续 10 次远程修改任务，逐次核对 operation、Git 和审计记录。

### Acceptance Criteria

- 具备可重复部署和回滚能力。
- 关键安全测试全部通过。
- developer 可以只依据 README 和 implementation-plan.md 开始实现和验收。

# Final Validation

## 功能验收

1. ChatGPT 通过 Tunnel 打开已登记项目。
2. ChatGPT 读取并搜索项目代码。
3. ChatGPT 通过多个 MCP 调用完成定点编辑。
4. Bridge 执行格式化或用户明确要求的测试。
5. ChatGPT 查看结构化结果和 Git diff。
6. 用户确认后创建 checkpoint 或执行回滚。

## ChatGPT-only 验收

- Bridge 源码中无模型 SDK、模型 endpoint 和模型 key。
- 运行时网络访问仅允许 tunnel-client 到 OpenAI Tunnel control plane；Bridge 不访问模型服务。
- codemcp worker 的进程树、环境变量和日志中无模型凭据。
- 一次用户请求能在审计中还原为 ChatGPT tool calls，而不是隐藏的 Agent 步骤。

## 安全与可靠性验收

- 任意路径、路径穿越、symlink/junction 逃逸均拒绝。
- 任意 shell、命令拼接、未经登记的参数均拒绝。
- 敏感文件默认不可读。
- 高风险操作没有审批记录时拒绝。
- 断线后 mutation 不自动重放。
- rollback 遇到外部变更时 fail closed。
- Bridge、codemcp、tunnel-client 单独重启后可以诊断并恢复。
- 同一 idempotency key 重试不会重复改文件或执行命令。
- 超时任务能够终止进程树，无法确认副作用时进入 unknown。

# Open Risks

1. codemcp 上游面向 Claude Desktop，且上游已经提示其逐渐 obsolete；长期维护前需要评估是否保留 fork。
2. codemcp 的 Git 自动提交策略可能与“审批后提交”不一致，需要 Phase 1 实测后决定是否补充 commit_mode。
3. codemcp 的部分命令执行语义可能依赖 shell；即使命令来自白名单，也需要 Bridge 禁止任意参数拼接。
4. Windows 原生 Git 和 WSL2 的路径、权限、换行符和进程管理差异，可能导致最终只支持其中一种模式。
5. Secure MCP Tunnel 是连接能力，不是业务级用户身份系统；未来多用户必须增加独立 OAuth/身份和项目授权层。
6. ChatGPT 负责全部推理意味着长任务需要较多 MCP 往返；Bridge 应返回小而结构化的结果。
7. 仓库内文档可能包含 prompt injection；文件内容始终视为不可信数据，不能改变 Bridge 权限和审批要求。

# Developer 起始顺序

Phase 0、Phase 1、Phase 2、Phase 3 和 Phase 4 已完成。Phase 5 的本地
tunnel-client 包装、profile 校验和诊断入口已实现；仍需使用真实 OpenAI
tunnel_id、runtime API key 和 ChatGPT workspace 权限完成 account-backed
验收。未完成该验收前，不进入 Phase 6，也不要扩大当前阶段范围。

Phase 1 已确定：

1. codemcp mutation worker 使用 WSL2，原生 Windows mutation 不支持。
2. 初始 Adapter 直接依赖上游 `codemcp==0.3.0`，暂不维护 fork。
3. 上游 Git commit 只作为后端事实记录；Bridge 的审批、checkpoint 和 rollback
   由 Phase 3/4 的本地 Bridge 实现。

Phase 4 的本地安全和可靠性测试已通过；Phase 5 的远程合同验收完成后，
才可以进入 Phase 6 运维化。
