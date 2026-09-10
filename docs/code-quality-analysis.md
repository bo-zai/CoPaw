# 代码质量问题整改方案

## 1. 结论与目标

本批 Sonar 告警集中在两类问题：

1. 流式处理、请求执行和 Goal 生命周期函数同时承担解析、状态转换、事件分发、错误处理和清理职责，导致认知复杂度超过 15。
2. `answer_turn/ports.py` 中的空方法是 `Protocol` 接口声明，并非遗漏的业务实现。

整改目标：

- 将每个编排函数收敛为“协调流程”，把分支细节下沉到职责单一的 helper；
- 保持现有 SSE、取消、重连、Stop、Goal settlement 和 trace 行为不变；
- 用针对状态边界的测试证明拆分前后行为一致；
- Sonar 复杂度降至授权阈值（≤15），而不是通过禁用规则隐藏问题。

## 2. 报告行号校准

当前工作树存在未提交修改，Sonar 报告行号可能与当前源码偏移：

- `runner.py:5488` 当前落在 `_stream_query_after_preflight` 的 `yield` 附近，实际高复杂度入口应核对 `AgentRunner.query_handler`；
- `session_lifecycle.py:67` 更可能是改名前的 `mark_stopped_turn_state`，当前 `mark_terminal_turn_state` 本身并不复杂。

在开始重构前，应先用当前提交重新运行 Sonar，记录新的函数名、行号和复杂度，避免对错误目标进行拆分。

## 3. 整改总览

| 优先级 | 目标 | 当前复杂度 | 主要问题 | 建议结果 |
| --- | --- | ---: | --- | --- |
| P0 | `answer_turn/ports.py` 9 个空方法 | Sonar 空实现 | Protocol 声明缺少意图说明 | 保留接口，增加嵌套注释/省略号 |
| P1 | `_turn_state_messages_from_state` | 16 | 校验、过滤、模型构造混合 | 提取单 entry 转换 helper |
| P1 | `_extract_assistant_response` | 18 | memory 扫描与诊断日志混合 | 提取 entry 迭代、摘要和候选查找 |
| P1 | `mark_stopped_turn_state` | 旧报告 19 | 查找 anchor 与修改 assistant 混合 | 提取 anchor 查找和 assistant 标注 |
| P2 | `_selected_expert_follow_up` | 18 | 多个工具状态分支集中 | 按 `start/get/wait` 分派 handler |
| P2 | `_resolve_current_recovery_chat` | 17 | 多候选查找和授权校验混合 | 提取授权查找 helper |
| P3 | `_stream_with_tracker` | 18 | payload、事件、完成和异常全耦合 | 拆分 stream context、事件处理、收尾 |
| P3 | `AgentRunner.query_handler` | 22 | trace、执行路径、outcome、清理混合 | 提取上下文、frame stream、outcome 管理 |
| P3 | `_dispatch_console_stream` | 24 | reconnect、新建、snapshot 分支混合 | 提取 target resolver 与 response builder |
| P3 | `_stream_goal_completion_lifecycle` | 23 | Goal 状态机和 finalization 混合 | 按状态阶段拆分 |

## 4. 具体改造方案

### 4.1 `BaseChannel._stream_with_tracker`（复杂度 18）

位置：`src/swe/app/channels/base.py:470`

职责应拆为四层：

```text
_prepare_stream_context(identity, payload)
_serialize_stream_event(event)
_handle_stream_event(request, event, ...)
_finalize_stream(request, to_handle, send_meta, last_response)
```

主函数只保留：

```text
prepare → before_consume → async stream → finalize
                         └→ CancelledError / Exception
```

必须保持：

- `dict` 和 `AgentRequest` 的 metadata 注入规则；
- `model_dump_json`、`json` 和普通对象三种序列化路径；
- response 错误优先于正常完成回调；
- 取消时 `process_iterator.aclose()` 后重新抛出 `CancelledError`。

测试重点：事件序列化、message completed、response error、正常完成、取消清理和普通异常通知。

### 4.2 `console._resolve_current_recovery_chat`（复杂度 17）

位置：`src/swe/app/routers/console.py:1018`

建议提取：

```text
_is_recovery_chat_authorized(...)
_get_authorized_chat_by_id(manager, candidate_id, ...)
_resolve_recovery_chat_by_session(manager, ...)
```

保留查找优先级：`requested_chat_id → session_id → get_chat_by_session()`。授权失败必须表现为“未找到”，不能泄露 chat 存在性。

测试应覆盖用户、channel、source、agent 不匹配，以及候选失败后的回退行为。

### 4.3 `console._dispatch_console_stream`（复杂度 24）

位置：`src/swe/app/routers/console.py:1801`

将三种入口分别封装：

```text
_resolve_current_reconnect_target(...)
_resolve_reconnect_target(...)
_start_console_stream_target(...)
```

统一返回 `queue、run_key、stream_identity、msgid`，另用可选的 terminal snapshot 表示“已结束、无需继续消费”。这样 dispatcher 只负责选择响应类型和创建 SSE generator。

必须回归：当前 reconnect 不新建 chat、普通 reconnect、terminal snapshot、新建失败时 suppression 回滚，以及 keep-alive 行为。

### 4.4 `AgentRunner.query_handler`（复杂度 22）

位置：`src/swe/app/runner/runner.py:5510`（报告行号可能偏移）

建议提取：

```text
_build_query_turn_context(request, query)
_build_trace_fields(request, identity, ...)
_stream_query_frames(...)
_report_query_terminal_outcome(...)
```

保留统一的 `try / except CancelledError / except Exception / else / finally` 结构，避免 outcome 重复报告。

行为约束：scheduled request 不创建 Agent trace；`_query_execution` 存在时不走旧 admission 路径；每个 frame 附带 trace id；task/runtime 在 finally 中清理。

现有 trace、B3、query execution、auth header、hook 和 answer-turn contract 测试应作为重构后的回归集。

### 4.5 `runner._extract_assistant_response`（复杂度 18）

位置：`src/swe/app/runner/runner.py:1375`

建议提取：

```text
_iter_memory_entries(memory, memory_start)
_describe_memory_entry(entry, index)
_find_candidate_assistant_response(entries)
_log_extraction_failure(...)
```

现有 `[STOP-DEBUG]` 诊断日志不应删除；应把日志摘要构造移出主流程。保持对非法 entry、live assistant event、不同 content 类型和空结果的防御行为。

### 4.6 `ToolGuardMixin._selected_expert_follow_up`（复杂度 18）

位置：`src/swe/agents/tool_guard_mixin.py:2334`

按工具名拆分：

```text
_handle_selected_expert_start(...)
_handle_selected_expert_get(...)
_handle_selected_expert_wait(...)
```

主函数只负责 stop 检查、读取 `tool_name` 和分派。必须保留：启动失败错误、terminal 清理、inactive 时 `get_subagent`、active 时 `wait_subagent`，以及 stop 优先级。

### 4.7 `runner.api._turn_state_messages_from_state`（复杂度 16）

位置：`src/swe/app/runner/api.py:257`

提取单条记录转换：

```python
def _turn_state_to_message(
    turn_id, turn_state, *, session_id, chat_id
) -> ChatMessage | None:
    ...
```

helper 负责类型、chat id、role、content 校验和 `ChatMessage` 构造；外层函数只遍历并收集非 `None` 结果。保留字符串 content 转 text block 和 `original_id` metadata。

### 4.8 `session_lifecycle.mark_stopped_turn_state`（旧报告复杂度 19）

位置：`src/swe/app/runner/session_lifecycle.py:84`（需以重新扫描结果为准）

建议提取：

```text
_find_turn_anchor_index(content, turn_id)
_mark_latest_assistant_stopped(content, anchor_index)
```

不要为了旧行号修改当前低复杂度的 `mark_terminal_turn_state()`。先确认 Sonar 是否仍然报告该函数。

### 4.9 `turn_lifecycle._stream_goal_completion_lifecycle`（复杂度 23）

位置：`src/swe/app/runner/turn_lifecycle.py:421`

这是 Goal 状态机，建议按阶段拆分：

```text
_stream_one_goal_turn(...)
_resolve_goal_settlement(...)
_handle_waiting_goal_wake(...)
_stream_goal_finalization(...)
```

可将内部状态明确为：

```text
TURN → SETTLE → FOLLOW_UP → WAIT → FINALIZE → DONE
```

必须保持：取消时 `abandon_turn`；WAITING 唤醒后可回到 ACTIVE；INTERRUPTED 不进入 finalization；Stop hook 可重试；stop budget 耗尽后输出 incomplete；finalization 按配置缓冲或流式发送。

## 5. Protocol 空方法处理

位置：`src/swe/app/answer_turn/ports.py`

9 个 `pass` 是接口声明，不应补充业务实现。建议保留异步签名，增加说明性嵌套注释，并使用 `...`：

```python
async def close(self, identity: TurnIdentity) -> None:
    # Protocol declaration; the concrete coordinator owns stream cleanup.
    ...
```

注释应明确实现者分别属于 coordinator、Runner、session adapter、Goal service、subagent manager 或 approval service。不要改为 `raise NotImplementedError`，否则会把类型协议误变成可运行的抽象基类。

## 6. 分阶段执行计划

### 阶段 0：校准与基线

1. 在当前提交重新运行 Sonar，确认函数名和行号。
2. 运行相关现有测试，记录基线结果。
3. 对每个目标执行 GitNexus `impact(..., direction="upstream")`；若出现 HIGH/CRITICAL，应先评估调用方和兼容策略。

### 阶段 1：低风险纯函数

处理 `ports.py`、`_turn_state_messages_from_state`、`_extract_assistant_response` 和 `mark_stopped_turn_state`。每次只拆一个职责，并增加 helper 单元测试。

### 阶段 2：分支分派

处理 `_selected_expert_follow_up` 和 `_resolve_current_recovery_chat`，重点验证状态清理、授权边界和回退顺序。

### 阶段 3：流式与生命周期编排

最后处理 `_stream_with_tracker`、`_dispatch_console_stream`、`query_handler` 和 `_stream_goal_completion_lifecycle`。优先提取“目标解析”和“阶段处理”，不要同时改变业务规则。

## 7. 验收标准

- Sonar 重新扫描后，目标函数复杂度均不超过 15；Protocol 空方法不再产生空实现告警；
- 现有测试全部通过，新增边界测试覆盖取消、重连、Stop、Goal wake 和 terminal 状态；
- SSE 事件顺序、keep-alive、trace id、outcome 持久化和错误语义不变；
- 重构后的 helper 具有明确输入输出，不依赖隐式可变共享状态；
- 提交前执行：

```bash
venv/bin/python -m pytest
pre-commit run --all-files
```

- 提交前执行 GitNexus `detect_changes()`，确认变更只影响预期符号和执行流。
