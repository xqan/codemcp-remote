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
| file_move | 移动一个已跟踪文件 | 是 | 同项目、禁止覆盖、需要 clean checkpoint |
| file_delete | 删除一个已跟踪文件 | 是 | 禁止目录/敏感路径/未跟踪文件，需要 clean checkpoint |
| registered_command_run | 执行任意已登记命令 | 可能 | 仅允许命令 ID，不接受任意 argv |
| format_run | 执行登记的格式化命令 | 可能 | 兼容入口，仅允许命令 ID |
| test_run | 执行登记的测试命令 | 可能 | 兼容入口，仅允许命令 ID |
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
- docs/architecture/architecture.md
- docs/guides/operations-runbook.md
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
- docs/reports/compatibility/codemcp-compatibility-matrix.md
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
- docs/architecture/git-policy.md

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
- docs/guides/tunnel-setup.md
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

- scripts/start-all.ps1
- scripts/start-bridge.ps1
- scripts/start-tunnel.ps1
- scripts/stop-all.ps1
- scripts/doctor.ps1
- docs/guides/operations-runbook.md
- docs/architecture/security-model.md
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

- docs/acceptance/acceptance-test-plan.md
- docs/architecture/threat-model.md
- docs/guides/operations-runbook.md
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
tunnel-client 包装、profile 校验和诊断入口已实现，真实 OpenAI tunnel_id、
runtime API key 和 ChatGPT workspace 权限的 account-backed 验收也已完成。
当前进入 Phase 6 运维化，先实现可重复的一键启动、停止和健康检查；不要在
当前阶段扩大到无关的部署或多用户身份功能。

Phase 1 已确定：

1. codemcp mutation worker 使用 WSL2，原生 Windows mutation 不支持。
2. 初始 Adapter 直接依赖上游 `codemcp==0.3.0`，暂不维护 fork。
3. 上游 Git commit 只作为后端事实记录；Bridge 的审批、checkpoint 和 rollback
   由 Phase 3/4 的本地 Bridge 实现。

Phase 4 的本地安全和可靠性测试以及 Phase 5 的远程合同验收已通过；Phase 6
仍需继续完成连续重启、异常退出、日志脱敏和版本升级回退验证。

# Change Plan：会话级 WIP commit 合并（2026-08-24）

## Goal

在不改变“每个 mutation 都先创建独立 Bridge checkpoint”的安全设计下，减少
Bridge 连续文件修改在当前分支产生的零碎 commit。

完成定义：

1. 每个 mutation 仍保留独立的修改前 checkpoint、修改后 HEAD、changed_files、
   diff hash、operation 和 audit 关联。
2. 同一 project、branch、active session 上连续且可证明由 Bridge 拥有的文件类
   mutation，只在分支历史中保留一个 WIP commit；后续 mutation 通过安全 amend
   更新该 commit。
3. session 的第一次有效修改、新 session、外部 HEAD 变化、其他 session 插入修改、
   本地可观测的已共享 HEAD，以及任何无法证明归属的状态，一律新建 commit。
4. 不自动 rebase、squash、push、删除 checkpoint ref 或重写用户提交。
5. 对现有 MCP 请求参数、幂等键、审批、rollback 和 SQLite schema 保持兼容。

本计划只减少当前分支可见的 WIP commit 数量。checkpoint ref 的数量和
`git log --all` 可见的历史对象不在本次范围内。

## Current Architecture

当前 mutation 调用链为：

~~~text
MCP file mutation
  -> project/session/operation validation
  -> per-project mutation lock
  -> _begin_mutation()
       -> clean-worktree and allowed-branch checks
       -> refs/codemcp-remote/checkpoints/<checkpoint_id>
       -> SQLite checkpoint row
  -> Git/codemcp side effect
  -> _finish_mutation()（仍在 project mutation lock 内）
       -> after HEAD/tree/changed_files/diff hash
  -> terminal operation result and audit
~~~

已验证的代码事实：

- `file_edit`、`file_create` 和 `file_write` 最终调用
  `GitGuard.commit_file_bytes()`，每次有效修改执行新的 `git commit -m "wip: ..."`。
- `file_move` 和 `file_delete` 当前无条件执行 `git commit --amend --no-edit`；当它们
  是 session 的第一次修改时，可能重写并非 Bridge 所有的当前 HEAD。
- `directory_create` 通过上游 codemcp `WriteFile` 创建 `.gitkeep`；固定版本上游同样
  amend 当前 HEAD，因此也缺少 Bridge 所有权判定。
- `_begin_mutation()` 对所有文件 mutation 和登记命令创建 checkpoint；该行为是
  rollback、diff、unknown reconciliation 和审计的保护边界，不能移除。
- SQLite 已持久化 session、operation、checkpoint 及 before/after HEAD；成功 operation
  与 checkpoint 可用于证明某个 HEAD 是否由指定 session 的 Bridge mutation 产生。
- 同一项目 mutation 已串行化，但可以存在多个 active session。不同 session 的操作
  可能依次修改同一分支，因此不能仅凭 `wip:` commit message 决定 amend。
- Bridge 没有显式的 project/session close MCP tool；session 通常持续到 Bridge 关闭或
  重启。session 是当前可复用的最小提交分组边界，但不等同于永久分支所有权。

## Architecture Decision

### AD-WIP-1：checkpoint 粒度不变，commit 以 session 为合并边界

每次 mutation 仍先创建 checkpoint。checkpoint 指向 mutation 前的 HEAD；后续 amend
生成的新 commit 即使与旧 HEAD 是兄弟关系，Git tree diff 和固定 ref rollback 仍可使用。

session 的第一次有效文件修改创建新的 WIP commit。此后的文件类 mutation 只有在
以下条件全部成立时才可 amend：

1. 当前 session 仍为 active，且判断发生在现有 per-project mutation lock 内。
2. 当前 branch 和 HEAD 与刚创建的 mutation checkpoint 完全一致，worktree clean。
3. SQLite 中存在同一 project、session 的已成功 mutation，其 finalized checkpoint
   `after.head` 等于当前 HEAD、`after.branch` 等于当前 branch，且 before/after HEAD
   不同；仅有 no-op checkpoint 不能建立提交所有权。
4. 当前 commit 含有新版 Bridge 在首次 commit 写入并由后续 `--no-edit` 保留的精确
   footer，例如 `Codemcp-Remote-Session: <session_id>`。
5. footer 只能作为辅助证明；仓库内容不可信，必须同时满足 SQLite 证据，绝不能仅凭
   commit message 授权 amend。
6. 当前 HEAD 未被本地可观测的 remote-tracking ref、tag 或当前分支之外的 local branch
   包含或直接引用。发现共享迹象时新建 commit，不重写该 HEAD；这不证明未同步到本地
   的远端 ref 没有发布该 commit。

数据库缺失、历史 checkpoint 没有新版 footer、Git ref 检查失败、branch/HEAD 不匹配，
或任何其他不确定情况都 fail safe 到 `create`，而不是失败开放到 `amend`。这样部署后
第一次修改会自然创建新的 session WIP 边界，不会收养历史零碎 commit。

### AD-WIP-2：所有文件类 mutation 使用统一的显式 commit mode

在 Git 层引入内部枚举或等价受限类型：

~~~text
CommitMode.CREATE
CommitMode.AMEND_SESSION_WIP
~~~

- `CREATE` 使用固定 argv 创建 `wip: <description>` commit，并写入 session footer。
- `AMEND_SESSION_WIP` 使用固定 argv `git commit --amend --no-edit --only -- <paths>`。
- `GitGuard` 不自行猜测归属，只执行 BridgeService/策略层传入的显式 mode，并继续校验
  expected HEAD、clean worktree、允许路径和最终新 HEAD。
- `file_edit`、`file_create`、`file_write`、`file_move`、`file_delete` 和
  `directory_create` 使用同一 mode 判定。
- `directory_create` 改为复用 Bridge 自有的原子文件提交路径写入 `.gitkeep`，避免上游
  `WriteFile` 在首次 mutation 时无条件 amend 用户 HEAD。对外目录、marker、checkpoint
  和幂等语义不变。
- 后续 amend 保留 session 第一次 mutation 的 commit message；Bridge 不在本地生成任务
  摘要，避免引入第二个推理步骤。

### AD-WIP-3：不增加 schema、配置开关或外部依赖

- 复用现有 checkpoint `before_json`、`after_json` 和关联 operation state 查询归属，
  不创建数据库 migration。
- 不修改 MCP 输入 schema、request hash、approval 或工具名称；响应结构原则上保持不变。
- 不新增 Git 库，继续通过 `GitGuard` 的固定 argv 子进程调用系统 Git。
- 不为本次需求增加 checkpoint retention、批量编辑 API、自动 session close 或提交发布
  流程；这些可独立规划，不能混入本次改动。

## Constraints

- 每个 mutation 必须继续先创建一个 Bridge-owned checkpoint ref。
- 所有 commit-mode 判断和 Git side effect 必须位于同一 project mutation lock 内。
- dirty workspace、HEAD race、branch race、unexpected paths 和敏感路径继续 fail closed。
- 幂等 replay 只能返回已持久化结果，不得再次 commit 或 amend。
- Git 结果无法确认时继续进入 `UNKNOWN_SIDE_EFFECT`，不得为了减少 commit 放宽恢复规则。
- rollback safety checkpoint 和 compare-and-swap 验证保持不变。
- 不 amend 仅由 message、author、`wip:` 前缀或仓库文件声明为 Bridge-owned 的 commit。
- 不 amend 其他 session、其他 branch、或本地可观测的 remote/tag/共享 branch 可达的
  commit。
- 不清理现有 checkpoint refs，不自动改写既有历史。
- 不新增第三方依赖，不修改部署环境变量或项目注册格式。

## Impact Scope

### 代码

- `bridge/src/codemcp_bridge/mcp_server.py`
  - mutation baseline/context 和 commit-mode 编排；六类文件 mutation 接线。
- `bridge/src/codemcp_bridge/git_guard.py`
  - 显式 commit mode、session footer、共享 ref 检查、create/amend 固定命令。
- `bridge/src/codemcp_bridge/checkpoint_service.py`
  - 基于 checkpoint、operation 和 Git 证据的保守归属判定；或仅承载对应查询封装。
- `bridge/src/codemcp_bridge/db/store.py`
  - 增加只读查询，证明指定 HEAD 来自同 session 的成功、已 finalized mutation。

### 测试

- `bridge/tests/test_phase3_persistence.py`
  - checkpoint/operation 归属查询和 no-op/failed/unknown 排除。
- `bridge/tests/test_phase4_git.py`
  - create/amend Git argv、footer、共享 ref 屏障、checkpoint diff/restore。
- `bridge/tests/test_phase2_server.py`
  - 跨文件工具、session 边界、并发 session、幂等和目录 marker 回归。
- `tests/integration/test_codemcp_compatibility.py`
  - 固定上游行为只作为兼容基线；确认新主流程不依赖上游 amend 来建立所有权。

### 文档

- `README.md`
- `docs/architecture/architecture.md`
- `docs/architecture/git-policy.md`
- `docs/releases/v0.1.0/phase-4-validation.md`
- `docs/implementation-plan.md`

### 明确不受影响

- SQLite schema version 和现有数据库文件。
- MCP tool 名称、必填参数和 request hash 计算。
- Tunnel、worker 生命周期、项目注册、命令白名单和审批 token。
- checkpoint ref 命名、manual checkpoint、rollback safety checkpoint 和 retention 现状。

## Phases

### Phase 1：建立安全的 commit 归属判定和 Git 原语

#### Goal

在不改变现有 mutation 工具行为的前提下，先提供可独立测试、默认不允许 amend 的
commit policy 基础能力，并封住“仅凭当前 HEAD/message 进行 amend”的风险。

#### Files / Modules

- `bridge/src/codemcp_bridge/db/store.py`
- `bridge/src/codemcp_bridge/checkpoint_service.py`
- `bridge/src/codemcp_bridge/git_guard.py`
- `bridge/tests/test_phase3_persistence.py`
- `bridge/tests/test_phase4_git.py`

#### Changes

1. 增加显式 `CommitMode` 受限类型，默认值必须为 `CREATE`。
2. 增加数据库只读查询：只接受同 project/session、关联 operation 为 `succeeded`、
   checkpoint 已 finalized、before/after HEAD 不同且 after branch/HEAD 精确匹配的记录。
3. 增加 Git tip footer 精确读取和校验；footer 与数据库证据必须同时成立。
4. 增加共享/发布 ref 检查，排除 remote refs、tags 和当前分支之外的 local branches；
   checkpoint refs 不作为共享阻断条件。
5. 将任何查询异常或证据缺失统一映射为 `CREATE`，并记录不含源码内容的诊断日志。
6. 增加创建 WIP commit 时写入 session footer 的固定 argv helper；此 Phase 不切换现有
   MCP mutation 调用方。

#### Dependencies

- 现有 schema 3 的 sessions、operations、checkpoints 和 audit 关联。
- 现有 GitGuard 固定 argv、HEAD 校验和 project mutation lock。

#### Risks

- SQLite 查询如果未关联 operation state，可能把 failed/unknown checkpoint 当成所有权。
- footer 若被 Git hook 改写会导致保守地多创建 commit，但不能导致错误 amend。
- `for-each-ref --contains` 的解析必须固定 namespace，不能接受调用方提供 ref 参数。

#### Validation

~~~powershell
uv run --project bridge pytest -q bridge/tests/test_phase3_persistence.py bridge/tests/test_phase4_git.py
uv run --project bridge ruff check bridge/src bridge/tests/test_phase3_persistence.py bridge/tests/test_phase4_git.py
~~~

覆盖：无历史记录、历史记录无 footer、同 HEAD no-op、failed、unknown、其他 session、
branch 不同、remote ref、tag、其他 local branch，以及数据库/Git 检查失败。

#### Acceptance Criteria

- 只有 SQLite 成功证据、精确 footer、branch/HEAD 连续性和未共享检查全部通过时返回
  `AMEND_SESSION_WIP`。
- 所有不确定与历史数据均返回 `CREATE`。
- 未改动 MCP mutation 的现有提交行为。
- `git diff --check`、目标测试和 Ruff 通过；检查 status 后仅提交本 Phase 文件。
- 完成后停止，不自动进入 Phase 2。

### Phase 2：统一六类文件 mutation 的 session WIP 行为

#### Goal

把安全 commit mode 接入全部文件类 mutation，使同 session 连续修改只增加一个分支
WIP commit，同时修复移动、删除和目录创建首次调用会无条件 amend 当前 HEAD 的问题。

#### Files / Modules

- `bridge/src/codemcp_bridge/mcp_server.py`
- `bridge/src/codemcp_bridge/git_guard.py`
- `bridge/src/codemcp_bridge/checkpoint_service.py`
- `bridge/tests/test_phase2_server.py`
- `bridge/tests/test_phase4_git.py`

#### Changes

1. 让 `_begin_mutation()` 返回 checkpoint 与已判定 commit mode 的内部 context；判断仍在
   per-project lock 内完成。
2. `commit_file_bytes()` 根据显式 mode 选择新 commit 或安全 amend，保留现有原子写入、
   expected HEAD、unexpected paths、clean-final-state 和 unknown 处理。
3. 为 `move_tracked_file()`、`delete_tracked_file()` 增加 description 和显式 mode；首次
   mutation 使用新 commit，只有已证明的 session WIP 才 amend。
4. `directory_create` 使用 Bridge 原子文件提交路径创建空 `.gitkeep`；失败时保留现有
   目录清理与 unknown 判定，不再依赖上游 `WriteFile` 的无条件 amend。
5. 接入 `file_edit`、`file_create`、`file_write`、`file_move`、`file_delete`、
   `directory_create`；每次仍创建并 finalize 独立 checkpoint。
6. no-op 文件内容继续不创建 Git commit；它也不能建立或转移 session WIP 所有权。
7. 保持现有成功 payload、changed_files、idempotency replay 和错误码兼容。

#### Dependencies

- Phase 1 的 commit mode、数据库证据和 Git ref/footer 检查。

#### Risks

- amend 后前后 commit 不再是祖先关系；checkpoint diff 必须继续按 tree 比较验证。
- 目录创建从 adapter 路径切换到 GitGuard 后，现有 fake-adapter 调用次数断言需要按新事实
  更新，但 MCP 外部契约不得变化。
- 多个 active session 交错时会主动切断合并链并新建 commit，提交数可能高于单 session，
  这是保护所有权的预期行为。

#### Validation

~~~powershell
uv run --project bridge pytest -q bridge/tests/test_phase2_server.py bridge/tests/test_phase4_git.py
uv run --project bridge ruff check bridge/src bridge/tests
~~~

至少覆盖以下 Git 序列：

1. 用户基线 `U`。
2. session A 首次编辑得到 `A1`：commit count `+1`，且 `A1^ == U`。
3. session A 创建、写入、移动、删除和目录创建依次得到 `A2...A6`：每次 HEAD 改变，
   分支 commit count 不再增加，每个 mutation checkpoint 分别指向前一个 HEAD。
4. 对任一中间 checkpoint 执行 diff 和 approved restore，结果与该次 mutation 一致。
5. session B 在当前 HEAD 修改时新建 `B1`，不得 amend session A 的 WIP。
6. 用户外部 commit、tag、remote-tracking ref 或其他 local branch 在本地共享当前 HEAD
   后，下一次 Bridge mutation 新建 commit。
7. 同一 idempotency key 重放不改变 HEAD、commit count 或 checkpoint count。

#### Acceptance Criteria

- 同 session、同 branch、无外部干预的六类文件 mutation 只产生一个分支可见 WIP commit。
- session 的第一次 move/delete/directory_create 不再重写用户基线 commit。
- 每个 mutation 的 checkpoint、diff hash、changed_files 和 restore 仍正确。
- 新 session、外部 Git 变化和本地可观测的共享 HEAD 一律新建 commit。
- 目标测试、Ruff、`git diff --check` 通过；仅提交本 Phase 文件。
- 完成后停止，不自动进入 Phase 3。

### Phase 2.5：mutation finalize CAS 与 external Git race hardening

#### Goal

封住 Git side effect 与 checkpoint finalize 之间的外部 Git 竞态，避免 Bridge
把外部 commit 错误持久化为当前 session 的成功归属证据；同时缩小 amend 前的
shared-ref 检查窗口，并统一“本地可观测 shared ref”与“远端发布不可证明”的安全边界。

#### Files / Modules

- `bridge/src/codemcp_bridge/mcp_server.py`
- `bridge/src/codemcp_bridge/checkpoint_service.py`
- `bridge/src/codemcp_bridge/git_guard.py`
- `bridge/tests/test_phase2_server.py`
- `bridge/tests/test_phase4_git.py`
- `docs/implementation-plan.md`
- `docs/architecture/architecture.md`
- `docs/architecture/git-policy.md`
- `README.md`
- `docs/releases/v0.1.0/phase-4-validation.md`

#### Changes

1. 六类文件 mutation 的 Git side effect、returned `new_head` 校验和
   `_finish_mutation(expected_after_head=...)` 必须保持在同一个 project mutation
   lock 内；registered command 的成功 finalize 同样使用 expected HEAD。
2. `CheckpointService.finalize()` 增加 expected after HEAD/branch CAS。实际状态不匹配
   时不写入 `after_data`，由 mutation 以 `UNKNOWN_SIDE_EFFECT` 结束并进入既有
   reconciliation 路径。
3. `GitGuard` 在 `AMEND_SESSION_WIP` 真正执行 `git commit --amend` 前二次校验
   branch、HEAD 和本地可观测的 branch/tag/remote-tracking shared refs；检查失败时
   不执行 amend，已发生的 worktree side effect 继续安全进入 unknown。
4. 不增加 schema、MCP 参数、依赖或 remote 查询；不声称本地 ref 检查可以证明任意
   远端 ref 未发布当前 WIP。active session WIP 禁止手动 push 仍是运维约束。

#### Risks

- project mutation lock 只能串行化 Bridge 自身请求，不能锁住外部 Git 进程；expected
  HEAD/branch CAS、amend 前二次 shared-ref 检查和 unknown fallback 只降低并发窗口，
  不能提供跨进程 Git 原子事务。
- remote-tracking ref 不能证明所有远端发布状态；未被本地观察到的远端发布必须由运维
  约束覆盖。

#### Validation

~~~powershell
uv run --project bridge pytest -q bridge/tests/test_phase2_server.py bridge/tests/test_phase4_git.py
uv run --project bridge ruff check bridge/src bridge/tests/test_phase2_server.py bridge/tests/test_phase4_git.py
~~~

覆盖 finalize 前外部 amend 竞态、expected HEAD/branch CAS、amend 前 shared-ref
二次检查、六类 mutation 正常 session 合并、跨 session 隔离和既有 checkpoint 行为。

#### Acceptance Criteria

- 外部 Git 在 commit 与 finalize 之间改变 HEAD 时，checkpoint 不持久化错误的
  `after.head` 或 session ownership，operation 进入 `unknown`。
- branch/HEAD/shared-ref 在 amend 前不一致时不执行 `git commit --amend`。
- 无外部干预的既有 session WIP 合并行为保持不变；无 schema migration、无新增依赖、
  无 MCP breaking change。
- 文档明确区分本地可观测 shared-ref 强保证与远端发布运维约束。
- 目标测试、Ruff、`git diff --check` 和 status 已检查；仅提交本 Phase 文件。
- 完成后停止，不自动进入 Phase 3。

### Phase 2.5.1：finalize terminal CAS

#### Goal

封住 `CheckpointService.finalize()` 内部首次 CAS 通过后、diff 计算完成前的最后
一个外部 Git 窗口，确保 checkpoint 的 `after.head`、`changed_files` 和 `diff_hash`
来自同一个固定 commit 状态。

#### Changes

1. expected-after finalize 使用固定的 `checkpoint_ref -> expected_after_head` commit
   diff，不再依赖 finalize 期间的当前 worktree 生成 mutation 审计 diff。
2. 固定 commit diff 完成后再次读取并校验 HEAD/branch；终态不一致时不写入
   `checkpoint.after_data`，继续进入 `UNKNOWN_SIDE_EFFECT` reconciliation 路径。
3. 增加首次 snapshot 后、diff 前外部 amend 的回归测试；不改变 schema、MCP 参数、
   依赖或既有非 mutation checkpoint diff 行为。

#### Validation

~~~powershell
uv run --project bridge pytest -q bridge/tests/test_phase2_server.py bridge/tests/test_phase4_git.py
uv run --project bridge ruff check bridge/src bridge/tests/test_phase2_server.py bridge/tests/test_phase4_git.py
~~~

#### Acceptance Criteria

- finalize 内部终态 HEAD/branch 变化不会写入相互矛盾的 checkpoint 审计数据。
- 外部 amend 在首次 snapshot 后、diff/SQLite finalize 前发生时，operation 为
  `unknown` 且 `checkpoint.after_data` 为空。
- 固定 commit diff 不改变正常六类 mutation、checkpoint diff/restore 和幂等行为。
- 目标测试、`git diff --check` 和 status 已检查；仅提交本 Phase 文件。
- 完成后停止，不自动进入 Phase 3。

### Phase 3：恢复回归、文档和完整验收

#### Goal

验证 session amend 与 restart、unknown reconciliation、rollback、WSL 兼容路径和远程
MCP 合同共存，并把新的提交语义写入运维与安全文档。

#### Files / Modules

- `bridge/tests/test_phase2_server.py`
- `bridge/tests/test_phase3_persistence.py`
- `bridge/tests/test_phase4_git.py`
- `tests/integration/test_codemcp_compatibility.py`
- `README.md`
- `docs/architecture/architecture.md`
- `docs/architecture/git-policy.md`
- `docs/releases/v0.1.0/phase-4-validation.md`
- `docs/implementation-plan.md`

#### Changes

1. 增加 commit 已发生但 checkpoint/operation 未完成时的 unknown 与 reconcile 回归测试。
2. 验证原 session 因重启 blocked、successor session 完成 reconcile 后，successor 的下一次
   mutation 新建自己的 WIP commit，不继承原 session amend 权限。
3. 验证 checkpoint restore 前创建 rollback safety ref，restore 后继续 mutation 时仍遵循
   footer、SQLite、session 和共享 ref 规则。
4. 验证 idempotent replay、取消和失败操作不会错误建立 commit 所有权。
5. 更新 README、architecture、git-policy 和 Phase 4 validation，明确“操作级 checkpoint、
   session 级 WIP commit”、安全 fallback 以及 checkpoint retention 不变。
6. 记录 rollout：既有 commit/checkpoint 因缺少新版 footer 不会被自动收养；无需数据库
   migration，回退代码也无需迁移数据。

#### Dependencies

- Phase 1 和 Phase 2 已独立完成并通过目标测试。
- 固定 `codemcp==0.3.0` 和当前 WSL2 worker 兼容基线。

#### Risks

- 用户在 Bridge session 中途手动 push，但本地 remote-tracking ref 尚未更新时，Bridge
  无法可靠知道该 commit 已发布；运维文档必须要求不要发布未结束 session 的 WIP。
- session 当前没有显式 close 工具，长期复用同一 session 会形成较大的单个 WIP commit。
- checkpoint refs 会继续固定每次 amend 前的 commit；磁盘对象和 `git log --all` 噪声
  不会因本改动减少。

#### Validation

~~~powershell
uv run --project bridge codemcp-bridge-server check
uv run --project bridge ruff check bridge/src bridge/tests tests/integration
uv run --project bridge pytest -q bridge/tests tests/integration
git diff --check
git status --short --branch
~~~

本项目没有浏览器 UI，本 Phase 不需要 Playwright；Tunnel 端到端合同只需确认工具 schema、
payload 和幂等行为未变化，不通过远程路径修改真实用户仓库做破坏性验收。

#### Acceptance Criteria

- 完整 Bridge 与 integration 测试通过，server check 和 Ruff 通过。
- restart/reconcile、checkpoint diff/restore、CAS 冲突和跨 session 场景全部有自动化覆盖。
- 文档准确区分 branch WIP commit 与 Bridge checkpoint ref。
- 无 schema migration、无新增依赖、无 MCP breaking change。
- `git diff --check` 和 status 已检查；仅提交本 Phase 文件。
- 完成后停止并报告 commit、文件、验证结果及残余风险。

#### Phase 3 compatibility boundary

本 Phase 只增加恢复回归、文档和验收覆盖，不改变 MCP 参数、SQLite schema、
checkpoint ref retention 或回退路径。既有 commit/checkpoint 因缺少
`Codemcp-Remote-Session` footer 不会被自动收养；它们会让后续 mutation
安全地 fallback 到 CREATE。代码回退无需数据库降级，也不自动删除新旧
checkpoint ref。

## Final Validation

最终验收必须同时满足：

- 安全不变量：逐 mutation checkpoint、clean workspace、project lock、CAS rollback、unknown
  reconciliation 和敏感路径保护均未弱化。
- 历史不变量：任何用户、其他 session、其他 branch、tag 或本地可观测 remote-tracking
  ref 共享的 commit 都不会被 Bridge amend；未同步到本地的远端发布状态不在证明范围内。
- 降噪目标：一个无外部干预的 active session，无论执行多少次受支持文件 mutation，
  当前分支相对 session 起点只增加一个 WIP commit。
- 可恢复目标：每个 amend 前版本仍由对应 checkpoint ref 固定，可单独 diff 和 restore。
- 兼容目标：已有数据库直接启动；既有操作结果可重放；现有 MCP 客户端无需改参数。
- 回退目标：代码回退不需要数据库降级，也不自动删除新旧 checkpoint 或修改 Git 历史。

## Open Risks

1. session 是现有最小边界，但缺少显式 close；如果未来需要“每个用户任务一个正式 commit”，
   应单独设计 change-set/finalize 工具，不能让 Bridge 自行推断任务结束。
2. 本计划不减少 checkpoint 数量。需要降低 ref/对象数量时，应另行设计 retention，并处理
   restore、审计保留期和数据库/ref 原子删除。
3. amend 会持续改变 WIP HEAD hash；依赖固定 HEAD 的外部工具必须使用最新 operation 结果，
   不能缓存旧 WIP HEAD。
4. 本地 remote-tracking ref 不能证明所有远端发布状态；“不要在 active session 中手动 push
   WIP”仍是运维约束。
5. Git hooks、签名策略或自定义 commit message cleanup 可能移除 footer；预期结果是安全地
   退化为更多新 commit，而不是放宽 amend。
