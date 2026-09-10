# Goal Runtime 一期设计

**日期：** 2026-08-22
**范围：** 单 Goal 的持久化执行控制层；不含多 Goal 编排、任务图或跨实例接管。

## 目标

Goal Runtime 让一个已确认的用户目标跨越多个 Main Agent Turn 持续推进，而不是把一次 Agent Turn 的自然结束视为任务结束。

它必须保证：

- Goal Contract 的完成条件可由真实环境状态确定性复核；
- 自动续轮、等待、暂停、恢复、取消和预算边界由 Host Runtime 决定；
- Main Agent 仍负责当前回合的推理、工具调用和 SubAgent 委派；
- Goal 不提升既有工具、数据、审批或沙箱权限；
- Chat 沿用现有 Main Agent/工具的过程展示，Goal 仅控制请求何时继续或结束。

## 非目标

- 多 Goal 并行、Task Graph、Agent Team 编排；
- 跨 Pod 调度、租约接管或独立 Goal Scheduler；
- 计量 token、成本、工具调用或 SubAgent 数量预算；
- LLM Judge、主观验收或通用无进展评分；
- Goal 专属权限系统或自然语言约束编译器。

## 核心模型

```text
Goal = 用户最终要达成的稳定结果
Goal Contract = 一个 Revision 的用户确认验收与边界
Plan = Main Agent 私有、可反复调整的执行方法
Main Agent Turn = 当前一轮做什么
SubAgent Run = 有界的局部委派
```

Goal Contract 包含：

- `objective`
- `completion_criteria`：每项为 requirement、observable assertion、verification method、expected outcome
- `constraints`：`must_preserve` 与 `must_not_do`
- `autonomy_boundary`

每项 Completion Criterion 都是强制项。`COMPLETE` 只在全部条件都有当前 Revision 的有效确定性验证证据时允许。

`Initial Execution Plan` 不属于 Contract，不在用户确认卡中展示；它由 Main Agent 在 Contract 确认后私有生成和重规划。

## 总体架构

```text
Chat Request / SSE
  → Goal Runtime（Host Controller）
    → Main Agent Turn
      → existing Tools / Tool Guard / Approval
      → existing Background SubAgent
    ← Structured Goal Turn Resolution
  → Goal Runtime settlement
    → continue / wait / verify / finalize
```

职责划分：

| 组件 | 职责 |
| --- | --- |
| Main Agent | 当前回合推理、调用工具、委派 SubAgent、更新私有 Plan、返回结构化决议 |
| Goal Runtime | Contract、状态转换、续轮、回合预算、控制命令、验证调度、请求结束 |
| Verification Run | 按 Contract 的验证方法独立执行只读确定性检查 |
| Background SubAgent | 既有有界局部任务；Main Agent 自行通过现有工具获取结果 |
| Tool Guard / Approval | 继续执行权限、路径边界与审批判断，不被 Goal 绕过 |

Goal Runtime 包在现有 `AgentRunner` 外层，不实现第二套 Agent、工具、SubAgent 或审批系统。

## 入口、Proposal 与确认

Goal Mode 与 Plan Mode、Explicit Expert Selection 互斥。

两条入口使用同一种 `Goal-ready Proposal`：

1. 用户在 Composer 显式选择 Goal Mode；
2. Plan Mode 中的 `submit_proposed_plan`。

`submit_proposed_plan` 从旧的 `title/summary/steps/risks/verification` 形状改为直接输出 Goal Contract Draft。它不做旧计划字段到 Contract 的映射。

当目标、验收、验证、约束或自主边界尚不明确时，Main Agent 可复用 `ask_plan_clarification`；在所有材料可形成有效 Contract Draft 前不得创建 Goal。

### Contract Confirmation Card

Proposal 通过 Composer 中的确认卡呈现，不作为助手时间线消息。用户可以在创建前直接编辑 Contract Draft 的所有字段：

- objective；
- 每条 Completion Criterion 与验证定义；
- constraints；
- autonomy boundary。

每次编辑后重新校验整份 Contract。拒绝或退出不创建 Goal；确认后才创建持久化 Goal 并启动首个 Main Agent Turn。

## 生命周期与请求边界

Goal 状态：`ACTIVE`、`WAITING`、`PAUSED`、`BLOCKED`、`LIMITED`、`INTERRUPTED`、`COMPLETE`、`CANCELLED`。

`COMPLETE` 与 `CANCELLED` 是终态。其余状态保留 Goal 控制权，阻止同一 Chat 创建下一个 Goal。

```text
Contract confirmation
  → ACTIVE
      ├─ continue → next Main Agent Turn
      ├─ wait → WAITING
      │          └─ SubAgent completion / approval / Steering → ACTIVE
      ├─ propose_completion → Verification Run
      │          ├─ all criteria pass → COMPLETE → Finalization → close request
      │          └─ failure → ACTIVE; same criterion fails 3 times → BLOCKED
      ├─ blocked → BLOCKED → Finalization → close request
      ├─ turn budget exhausted → LIMITED → Finalization → close request
      ├─ pause → PAUSED → Finalization → close request
      ├─ cancel → CANCELLED → Finalization → close request and release Goal Mode
      └─ owner instance lost → INTERRUPTED → request lost

PAUSED / BLOCKED / LIMITED / INTERRUPTED
  └─ explicit resume → ACTIVE in a new sticky request
```

语义：

- `WAITING`：没有立即可做的工作，且存在明确唤醒事件；不运行 LLM、不轮询。
- `PAUSED`：用户暂停；当前回合结算后关闭请求。
- `BLOCKED`：当前无有效推进动作；三次同条件验证失败也会进入此状态。
- `LIMITED`：固定 Main Agent Turn 上限耗尽；不是完成。
- `INTERRUPTED`：Goal Execution Owner 实例中断；无 Finalization Turn、无自动跨实例接管。

`ACTIVE` 与 `WAITING` 保持当前 SSE 请求。`PAUSED`、`BLOCKED`、`LIMITED` 在 Finalization Turn 后关闭请求；`INTERRUPTED` 因实例失去请求而直接结束。

普通 Main Agent 回合完成在 Goal Mode 下只是内部回合边界。它不能向前端发出 Chat 完成事件；只有 Finalization Turn 才能结束流。

## Main Agent 回合协议

每个正常 Main Agent Turn 都必须返回受运行时校验的 JSON envelope：

```text
decision: continue | wait | propose_completion | blocked
summary
next_focus
evidence_refs
wake_conditions       # wait only
completion_proposal   # propose_completion only
blocker               # blocked only
affected_criteria     # environment write occurred in this turn
```

无法解析或不符合状态的 envelope 不触发继续或完成；Runtime 保存快照并结束当前请求，等待用户恢复。

下一轮的 `Goal Continuation Context` 只包含：

- active Contract 与 Revision；
- 未消费 Steering；
- 已验证与未完成的 Completion Criteria；
- 相关验证失败；
- next focus。

它不重放完整聊天，也不注入 SubAgent 的结果、ID 或状态。Goal Runtime 仅内部维护 Goal-owned SubAgent link 以等待唤醒；Main Agent 继续通过既有 SubAgent 工具和自身对话上下文按需获取信息。

## 控制命令与 Steering

普通用户消息在 `ACTIVE` 或 `WAITING` 时按到达顺序进入 Steering Queue，不能发起平行普通 Agent 请求。

`WAITING` 中的新 Steering 同时唤醒 Goal，供下一回合读取。普通文本永远不能修改 Contract。

显式控制由 Goal Monitor 发出：pause、resume、cancel、Direct Goal Edit。控制命令都在当前 Main Agent Turn 的自然结算边界生效，不抢占正在执行的工具。

同一边界存在多个命令时，只应用最高优先级：

```text
CANCEL > Direct Goal Edit > PAUSE > RESUME
```

低优先级命令记录为 superseded。

## Direct Goal Edit 与 Revision

Goal 创建后，Contract 仅允许用户通过 Goal Monitor 的 Direct Goal Edit 修改。Main Agent 不可提议、预填、推断或通过 Steering 修改任何 Contract 字段。

Direct Goal Edit 的规则：

- 用户直接编辑完整 Contract 并提交；提交即确认，不再要求第二个确认卡；
- 校验失败返回字段级错误，不产生部分 Revision，也不改变当前运行状态；
- 运行中 Main Agent Turn 存在时，编辑成为 Pending Revision，在该回合结算处原子激活；旧回合的决议、验证和完成提议不作用于新 Revision；
- 没有运行中 Main Agent Turn 时，编辑立即生效；若原状态为 `WAITING`，立即转 `ACTIVE` 并启动下一回合，避免旧等待条件卡住新 Contract；
- `PAUSED`、`BLOCKED`、`LIMITED`、`INTERRUPTED` 不因编辑自动 Resume；
- Revision 切换清空旧 Revision 的验证通过证据和验证失败计数，但不重置整个 Goal 的回合预算；
- 旧 Revision 的 SubAgent / Verification Run 可按既有能力自然收敛，但其结果不能自动满足新 Revision。若 Main Agent 想复用其内容，必须为新 Revision 再次验证。

整个 Goal 的 Tenant、Source、Agent Profile 与 effective Model 在创建时冻结，Direct Goal Edit 不能改变执行身份。

## 确定性验证

Main Agent 的 `propose_completion` 仅是完成建议，不能结束请求。

Goal Runtime 为每个未满足的 Criterion 运行独立 `Verification Run`：

- 使用 Contract-bound Verification Method 和 Expected Outcome；
- 经由受控 Verification Adapter 调用现有只读工具；
- 保留 Tool Guard、路径边界和审批机制；
- 若审批待决，Goal 进入 `WAITING`，审批结果唤醒同一 Goal；
- 全部强制条件通过后才能转 `COMPLETE`。

发生环境写入的 Main Agent Turn 在 envelope 中声明受影响 Criterion；Runtime 只重验这些条件，未受影响的当前 Revision 证据继续有效。某个 Criterion 连续三次验证失败时，Goal 转 `BLOCKED`。条件通过会清零自身失败计数。

每个新的 Revision 的所有 Criterion 初始都为未验证。

## Finalization

所有关闭当前 Chat 请求的正常路径都使用 `Goal Finalization Turn`：

- `COMPLETE`：只在全部验证成功后，生成正式交付回复；
- `PAUSED`、`BLOCKED`、`LIMITED`、`CANCELLED`：生成简短状态、原因和下一步说明；
- Finalization Turn 是只读、无工具、不计 Main Agent Turn Budget，且不得推进 Goal。

Finalization Turn 产出的当前轮 `assistant` 文本是唯一的 Goal Stop 候选：它在关闭流前触发一次 Stop。`block` 只能发起无工具的 Finalization 重试，使用独立于 Goal Turn Budget 的 `max_stop_turns` 计数；重试不得重新执行、验证或变更 Goal 状态。若 Finalization Turn 因模型或基础设施失败无法产生文本，Runtime 不重试、不改变 Goal 状态，发送固定的最小系统提示并关闭请求；该 Fallback 不是 Stop 候选，用户可在 Monitor 查看真实状态。

## 持久化与运行所有权

Goal Store 使用 MySQL 作为唯一权威源。建议表：

| 表 | 主要内容 |
| --- | --- |
| `goals` | Goal ID、冻结 Scope/Model、状态、当前 Revision、Budget Cycle、已用回合、next focus、最后状态原因 |
| `goal_revisions` | 每版 Contract、创建/激活信息 |
| `goal_criteria` | 断言、验证方法、预期结果、当前验证状态、连续失败数、证据引用 |
| `goal_steering` | 到达顺序及未消费 Steering |
| `goal_subagent_links` | `goal_id + revision + subagent_run_id` |
| `goal_control_commands` | pause/resume/cancel/edit 与 superseded 状态 |

回合结算必须以一个事务保存：回合消耗、结构化决议、状态、Progress、受影响 Criterion、控制命令和 Pending Revision 激活。

不建 MySQL 审计表。Goal 创建、回合决议、验证、状态转换、控制命令、实例中断/恢复都输出结构化日志，至少关联 `goal_id`、`revision` 与 `turn_id`；不要求记录完整 prompt 或工具原始输出。

Goal Execution Owner 是创建 Goal 的粘性请求所在实例。该实例在请求内运行异步 Goal Event Loop；不做独立 Scheduler 或跨实例接管。实例中断后只保存最后一次结算快照，用户通过 Monitor 显式 Resume 后在新的粘性请求中继续。

## Console 设计

Goal 的可见交互参考现有 `SubAgentRunMonitor` 模式，而不是在聊天时间线添加新消息：

- 在 Chat 中提供紧凑的 Goal Monitor 快捷入口，位置与已有 Background SubAgent 监控入口一致；
- 入口沿用其“紧凑触发器 → 可折叠状态面板 → 面板头部收起”的交互节奏，并复用现有的事件触发刷新、活动状态轮询和操作失败提示模式；Goal 仅替换数据源、状态文案和可用控制，不能伪装成 SubAgent Run；
- 点击后加载当前 Chat 最近一个非终态 Goal；没有非终态时展示最近一个历史 Goal；
- 面板显示 Contract 摘要、生命周期状态、已通过/未通过条件、最近验证失败或等待/阻塞原因、当前回合序号；
- 面板提供 pause、resume、cancel、Direct Goal Edit；
- 不显示内部 Plan、模型推理、原始工具输出或原始 SubAgent 日志；
- Goal 中间状态不创建 Chat timeline message；Chat 继续显示 Main Agent 和工具已有的过程卡片。

同一 Chat 可顺序执行多个 Goal，但只有 `COMPLETE` 或 `CANCELLED` 后才能创建下一个 Goal。非终态 Goal 不可被绕过。

## API

```text
GET  /goals/{goal_id}          # Goal Runtime Snapshot + allowed actions
POST /goals/{goal_id}/pause
POST /goals/{goal_id}/resume
POST /goals/{goal_id}/cancel
POST /goals/{goal_id}/edit     # Direct Goal Edit full Contract submission
```

`edit` 不是通用 PATCH，要求完整 Contract、严格字段校验与 Revision 语义。所有接口按 Goal Scope 校验 Tenant、Source、Agent Profile 与 Chat 归属。

## 不变量

- Goal 不提升 Tool Permission、Data Access Scope、Sandbox 或 Approval；
- 一个 Goal 同时最多一个 Main Agent Turn；
- 一个 Chat 同时最多一个非终态 Goal；
- Plan 可以重规划，Contract 只能由用户 Direct Goal Edit 创建新 Revision；
- 旧 Revision 的 SubAgent、验证结果和完成建议不能完成新 Revision；
- 预算耗尽绝不代表 `COMPLETE`；
- 每条 Completion Criterion 都必须有有效确定性验证证据；
- Goal Runtime 决定生命周期转换；Main Agent 只返回建议；
- 普通 Agent Turn 的完成不结束 Chat 请求；仅 Finalization Turn 能结束请求；
- 除 `WAITING` 的允许事件外，不允许 LLM 轮询等待。

## 验收与测试重点

- Contract Draft 的创建前编辑、字段校验、拒绝不创建 Goal；
- Plan Mode 的 `submit_proposed_plan` 和 Goal Mode 使用同一 Proposal Schema；
- 自动续轮不向 SSE 发出中间终结帧；Finalization 才终结请求；
- pause/resume/cancel/edit 的回合边界优先级与幂等性；
- Direct Goal Edit 在 ACTIVE、WAITING、PAUSED、BLOCKED、LIMITED、INTERRUPTED 的 Revision 生效语义；
- Revision 切换后旧 SubAgent、旧 Verification Run 不能完成新 Revision；
- 每种 Verification Adapter 通过、失败、审批等待、三次失败熔断；
- LIMITED Resume 重置预算而 Direct Goal Edit 不重置；
- Goal Monitor 沿用 SubAgent Monitor 的旁路入口模式，且不产生 Goal timeline message；
- 实例中断后只可显式 Resume，不跨实例自动接管。
