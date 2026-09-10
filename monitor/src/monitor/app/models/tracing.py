# -*- coding: utf-8 -*-
"""Tracing data models.

Defines Trace, Span, EventType, and related models for tracing events.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, ConfigDict


class EventType(str, Enum):
    """Event types for tracing."""

    SESSION_START = "session_start"
    SESSION_END = "session_end"
    LLM_INPUT = "llm_input"
    LLM_OUTPUT = "llm_output"
    TOOL_CALL_START = "tool_call_start"
    TOOL_CALL_END = "tool_call_end"
    SKILL_INVOCATION = "skill_invocation"


class TraceStatus(str, Enum):
    """Trace status."""

    RUNNING = "running"
    COMPLETED = "completed"
    ERROR = "error"
    CANCELLED = "cancelled"


class Span(BaseModel):
    """Span represents a single operation within a trace.

    A span can be an LLM call, tool execution, or skill invocation.
    """

    model_config = ConfigDict(use_enum_values=True)

    span_id: str = Field(description="Unique span identifier")
    trace_id: str = Field(description="Parent trace identifier")
    source_id: str = Field(description="Source identifier for data isolation")
    name: str = Field(description="Span name/operation name")
    event_type: EventType = Field(description="Type of event")
    start_time: datetime = Field(description="Start timestamp")
    end_time: Optional[datetime] = Field(
        default=None,
        description="End timestamp",
    )
    duration_ms: Optional[int] = Field(
        default=None,
        description="Duration in milliseconds",
    )
    user_id: str = Field(default="", description="User identifier")
    user_name: Optional[str] = Field(default=None, description="User name")
    bbk_id: Optional[str] = Field(default=None, description="BBK identifier")
    session_id: str = Field(default="", description="Session identifier")
    channel: str = Field(default="", description="Channel identifier")
    model_name: Optional[str] = Field(
        default=None,
        description="Model name for LLM events",
    )
    input_tokens: Optional[int] = Field(
        default=None,
        description="Input token count",
    )
    output_tokens: Optional[int] = Field(
        default=None,
        description="Output token count",
    )
    tool_name: Optional[str] = Field(
        default=None,
        description="Tool name for tool events",
    )
    skill_name: Optional[str] = Field(
        default=None,
        description="Skill name for skill events",
    )
    skill_id: Optional[str] = Field(
        default=None,
        description="Skill unique identifier",
    )
    mcp_server: Optional[str] = Field(
        default=None,
        description="MCP server name if this tool is from MCP",
    )
    tool_input: Optional[dict[str, Any]] = Field(
        default=None,
        description="Tool input (sanitized)",
    )
    tool_output: Optional[str] = Field(
        default=None,
        description="Tool output (truncated)",
    )
    error: Optional[str] = Field(
        default=None,
        description="Error message if failed",
    )


class Trace(BaseModel):
    """Trace represents a complete request/session trace.

    A trace contains multiple spans and represents the full lifecycle
    of a user request.
    """

    model_config = ConfigDict(use_enum_values=True)

    trace_id: str = Field(description="Unique trace identifier")
    b3_trace_id: Optional[str] = Field(
        default=None,
        description="External B3 trace identifier for distributed correlation",
    )
    source_id: str = Field(description="Source identifier for data isolation")
    user_id: str = Field(description="User identifier")
    user_name: Optional[str] = Field(default=None, description="User name")
    bbk_id: Optional[str] = Field(default=None, description="BBK identifier")
    session_id: str = Field(description="Session identifier")
    session_name: Optional[str] = Field(
        default=None,
        description="Session name",
    )
    channel: str = Field(description="Channel identifier")
    start_time: datetime = Field(description="Trace start timestamp")
    end_time: Optional[datetime] = Field(
        default=None,
        description="Trace end timestamp",
    )
    duration_ms: Optional[int] = Field(
        default=None,
        description="Total duration in milliseconds",
    )
    model_name: Optional[str] = Field(
        default=None,
        description="Primary model used",
    )
    total_input_tokens: int = Field(
        default=0,
        description="Total input tokens",
    )
    total_output_tokens: int = Field(
        default=0,
        description="Total output tokens",
    )
    tools_used: list[str] = Field(
        default_factory=list,
        description="Tools used in trace",
    )
    skills_used: list[str] = Field(
        default_factory=list,
        description="Skills used in trace",
    )
    status: TraceStatus = Field(
        default=TraceStatus.RUNNING,
        description="Trace status",
    )
    error: Optional[str] = Field(
        default=None,
        description="Error message if failed",
    )
    user_message: Optional[str] = Field(
        default=None,
        description="User's input message (truncated)",
    )
    model_output: Optional[str] = Field(
        default=None,
        description="Model's output message (from ES)",
    )


# API Response Models


class ModelUsage(BaseModel):
    """Model usage statistics."""

    model_name: str
    count: int = 0
    total_tokens: int = 0
    input_tokens: int = 0
    output_tokens: int = 0


class ToolUsage(BaseModel):
    """Tool usage statistics."""

    tool_name: str
    count: int = 0
    avg_duration_ms: int = 0
    error_count: int = 0


class SkillUsage(BaseModel):
    """Skill usage statistics with weighted attribution."""

    skill_name: str
    skill_id: Optional[str] = Field(
        default=None,
        description="技能唯一标识符",
    )
    cn_name: Optional[str] = Field(
        default=None,
        description="技能中文名（来自 swe_skills，由前端决定如何回退展示）",
    )
    skill_description: Optional[str] = Field(
        default=None,
        description="技能描述",
    )
    count: int = 0
    weighted_count: float = 0.0
    avg_duration_ms: int = 0
    weighted_duration_ms: int = 0
    tool_attribution: dict[str, float] = Field(
        default_factory=dict,
        description="Tool name -> weighted usage count mapping",
    )


class MCPToolUsage(BaseModel):
    """MCP tool usage statistics."""

    tool_name: str
    mcp_server: str
    count: int = 0
    avg_duration_ms: int = 0
    error_count: int = 0


class MCPServerUsage(BaseModel):
    """MCP server usage statistics."""

    server_name: str
    tool_count: int = 0
    total_calls: int = 0
    avg_duration_ms: int = 0
    error_count: int = 0
    tools: list[MCPToolUsage] = Field(default_factory=list)


class MCPSummary(BaseModel):
    """MCP 全局调用汇总统计."""

    total_calls: int = 0  # 总调用次数
    error_count: int = 0  # 报错次数
    server_count: int = 0  # MCP server 数量


class DailyStats(BaseModel):
    """Daily statistics."""

    date: str
    total_users: int = 0
    active_users: int = 0
    total_tokens: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    session_count: int = 0
    conversation_count: int = 0
    avg_duration_ms: int = 0


class OverviewStats(BaseModel):
    """Overview dashboard statistics."""

    online_users: int = 0
    online_user_ids: list[str] = Field(default_factory=list)
    total_users: int = 0
    it_users: int = 0  # IT人员数量（80/IT开头的用户ID）
    business_users: int = 0  # 业务人员数量（其他用户）
    model_distribution: list[ModelUsage] = Field(default_factory=list)
    total_tokens: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_sessions: int = 0
    total_conversations: int = 0
    total_skill_calls: int = 0  # 技能调用总次数
    # 客户点击统计
    plan_customers: int = 0  # 查看方案客户数
    insight_customers: int = 0  # 去洞察客户数
    phone_customers: int = 0  # 去电访客户数
    avg_duration_ms: int = 0
    top_tools: list[ToolUsage] = Field(default_factory=list)
    top_skills: list[SkillUsage] = Field(default_factory=list)
    top_mcp_tools: list[MCPToolUsage] = Field(default_factory=list)
    mcp_servers: list[MCPServerUsage] = Field(default_factory=list)
    daily_trend: list[DailyStats] = Field(default_factory=list)
    growth_stats: dict[str, float | None] = Field(default_factory=dict)
    branch_breakdown: "OverviewBranchBreakdown" = Field(
        default_factory=lambda: OverviewBranchBreakdown(),  # pylint: disable=unnecessary-lambda
    )


class BranchMetricItem(BaseModel):
    """Single branch metric item used in dashboard breakdowns."""

    bbk_id: str = ""
    bbk_name: str = ""
    value: float = 0
    percent: float = 0


class OverviewBranchBreakdown(BaseModel):
    """Branch breakdowns for each overview metric card."""

    users: list[BranchMetricItem] = Field(default_factory=list)
    conversations: list[BranchMetricItem] = Field(default_factory=list)
    sessions: list[BranchMetricItem] = Field(default_factory=list)
    tokens: list[BranchMetricItem] = Field(default_factory=list)
    skills: list[BranchMetricItem] = Field(default_factory=list)
    cron_tasks: list[BranchMetricItem] = Field(default_factory=list)
    customers: list[BranchMetricItem] = Field(default_factory=list)


class TaskStatusBreakdown(BaseModel):
    """Task execution status summary for dashboard donut chart."""

    success: int = 0
    failed: int = 0
    running: int = 0


class TaskStatusSummary(BaseModel):
    """定时任务执行汇总统计."""

    total_tasks: int = 0  # 总执行次数
    success: int = 0  # 成功次数（status='success' AND async_status='success'）
    running: int = 0  # 运行中次数（status='success' AND async_status IS NULL）
    failed: int = 0  # 失败次数（综合判断）
    cancelled: int = 0  # 已取消/跳过次数
    read_count: int = 0  # 已读次数


class ModelErrorCodeCount(BaseModel):
    """模型报错错误码计数."""

    code: str = Field(description="错误码")
    count: int = Field(description="数量")


class ErrorSummary(BaseModel):
    """报错分析汇总统计."""

    total_errors: int = 0  # 报错总数
    model_errors: int = 0  # 模型报错（llm_input）
    tool_errors: int = 0  # 工具报错（tool_call_end）
    model_error_codes: list[ModelErrorCodeCount] = Field(
        default_factory=list,
        description="模型报错错误码 Top 10",
    )


class ErrorItem(BaseModel):
    """单个错误记录."""

    trace_id: str = Field(description="关联对话 ID")
    span_id: str = Field(description="事件 ID")
    event_type: str = Field(description="事件类型: llm_input / tool_call_end")
    error: str = Field(description="错误信息")
    user_id: str = Field(description="用户 ID")
    user_name: Optional[str] = Field(default=None, description="用户名称")
    bbk_id: Optional[str] = Field(default=None, description="分行 ID")
    session_id: str = Field(default="", description="会话 ID")
    session_name: Optional[str] = Field(default=None, description="会话名称")
    model_name: Optional[str] = Field(
        default=None,
        description="模型名称（模型报错）",
    )
    tool_name: Optional[str] = Field(
        default=None,
        description="工具名称（工具报错）",
    )
    mcp_server: Optional[str] = Field(default=None, description="MCP 服务名称")
    start_time: datetime = Field(description="发生时间")
    duration_ms: Optional[int] = Field(
        default=None,
        description="持续时间（毫秒）",
    )
    input_tokens: Optional[int] = Field(default=None, description="输入 Token")
    output_tokens: Optional[int] = Field(
        default=None,
        description="输出 Token",
    )


class ErrorListResponse(BaseModel):
    """错误列表响应."""

    items: list[ErrorItem] = Field(
        default_factory=list,
        description="错误列表",
    )
    total: int = Field(default=0, description="总数")
    page: int = Field(default=1, description="当前页码")
    page_size: int = Field(default=10, description="每页数量")


class UserStats(BaseModel):
    """User-specific statistics."""

    user_id: str
    model_usage: list[ModelUsage] = Field(default_factory=list)
    total_tokens: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_sessions: int = 0
    total_conversations: int = 0
    avg_duration_ms: int = 0
    tools_used: list[ToolUsage] = Field(default_factory=list)
    skills_used: list[SkillUsage] = Field(default_factory=list)
    mcp_tools_used: list[MCPToolUsage] = Field(default_factory=list)


class ToolCall(BaseModel):
    """Tool call details in a trace."""

    tool_name: str
    tool_input: Optional[dict[str, Any]] = None
    tool_output: Optional[str] = None
    duration_ms: Optional[int] = None
    error: Optional[str] = None


class TraceFeedback(BaseModel):
    """终端用户提交的对话反馈。"""

    id: int
    source_id: Optional[str] = None
    feedback_user_name: Optional[str] = None
    feedback_user_sap: Optional[str] = None
    feedback_branch: Optional[str] = None
    feedback_sub_branch: Optional[str] = None
    feedback_position: Optional[str] = None
    cron_task_name: Optional[str] = None
    cron_task_id: Optional[str] = None
    response_id: Optional[str] = None
    trace_id: Optional[str] = None
    chat_id: Optional[str] = None
    session_id: Optional[str] = None
    feedback_options: list[str] = Field(default_factory=list)
    feedback_content: str = ""
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class TraceDetail(BaseModel):
    """Detailed trace with spans."""

    trace: Trace
    spans: list[Span] = Field(default_factory=list)
    llm_duration_ms: int = 0
    tool_duration_ms: int = 0
    tools_called: list[dict[str, Any]] = Field(default_factory=list)
    feedback: Optional[TraceFeedback] = None


# Timeline models for hierarchical display


class ToolCallInSkill(BaseModel):
    """Tool call within a skill invocation."""

    span_id: str
    tool_name: str
    mcp_server: Optional[str] = None
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_ms: int = 0
    status: str = "success"  # success / error
    error: Optional[str] = None
    skill_weight: Optional[float] = None


class SkillCallTimeline(BaseModel):
    """Skill invocation in timeline with tool hierarchy."""

    span_id: str
    skill_name: str
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_ms: int = 0
    confidence: float = 1.0
    trigger_reason: str = "declared"  # declared / inferred / keyword

    # Tools called within this skill (hierarchical)
    tools: list[ToolCallInSkill] = Field(default_factory=list)

    # Statistics
    total_tool_calls: int = 0
    tool_duration_ms: int = 0


class TimelineEvent(BaseModel):
    """Timeline event with hierarchical structure.

    Supports nested events for skill -> tool hierarchy.
    """

    event_type: str  # skill_invocation / tool_call / llm_call
    span_id: Optional[str] = None
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_ms: int = 0

    # Skill invocation fields
    skill_name: Optional[str] = None
    confidence: Optional[float] = None
    trigger_reason: Optional[str] = None

    # Tool call fields
    tool_name: Optional[str] = None
    mcp_server: Optional[str] = None
    skill_weight: Optional[float] = None

    # LLM call fields
    model_name: Optional[str] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None

    # Hierarchical children (tools under skill)
    children: list["TimelineEvent"] = Field(default_factory=list)


# Update forward reference for recursive model
TimelineEvent.model_rebuild()


class TraceDetailWithTimeline(BaseModel):
    """Trace detail with hierarchical timeline.

    Provides both flat spans (backward compatible) and
    hierarchical timeline for enhanced visualization.
    """

    trace: Trace
    feedback: Optional[TraceFeedback] = None

    # Flat list (backward compatible)
    spans: list[Span] = Field(default_factory=list)

    # Hierarchical timeline
    timeline: list[TimelineEvent] = Field(default_factory=list)

    # Skill invocations summary
    skill_invocations: list[SkillCallTimeline] = Field(default_factory=list)

    # Statistics
    llm_duration_ms: int = 0
    tool_duration_ms: int = 0
    skill_duration_ms: int = 0
    total_skills: int = 0
    total_tools: int = 0
    total_llm_calls: int = 0


class UserListItem(BaseModel):
    """User list item with stats."""

    user_id: str
    user_name: Optional[str] = Field(default=None, description="User name")
    bbk_id: Optional[str] = Field(default=None, description="BBK identifier")
    total_sessions: int = 0
    total_conversations: int = 0
    total_tokens: int = 0
    total_skills: int = 0
    last_active: Optional[datetime] = None
    # 四个口径统计字段
    manual_calls: int = Field(default=0, description="主动使用次数")
    cron_executions: int = Field(default=0, description="任务执行数")
    cron_success: int = Field(default=0, description="任务成功数")
    cron_reads: int = Field(default=0, description="结果查看数")


class TraceListItem(BaseModel):
    """Trace list item."""

    trace_id: str
    source_id: str
    user_id: str
    user_name: Optional[str] = Field(default=None, description="User name")
    bbk_id: Optional[str] = Field(default=None, description="BBK identifier")
    session_id: str
    channel: str
    start_time: datetime
    duration_ms: Optional[int] = None
    total_tokens: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    model_name: Optional[str] = None
    status: str
    skills_count: int = 0
    feedback: Optional[TraceFeedback] = None


class SessionListItem(BaseModel):
    """Session list item with stats."""

    session_id: str
    session_name: Optional[str] = Field(
        default=None,
        description="Session name (from first message)",
    )
    user_id: str
    user_name: Optional[str] = Field(default=None, description="User name")
    bbk_id: Optional[str] = Field(default=None, description="BBK identifier")
    channel: str
    total_traces: int = 0
    total_tokens: int = 0
    total_skills: int = 0
    first_active: Optional[datetime] = None
    last_active: Optional[datetime] = None


class SessionStats(BaseModel):
    """Session-specific statistics."""

    session_id: str
    user_id: str
    channel: str
    model_usage: list[ModelUsage] = Field(default_factory=list)
    total_tokens: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_traces: int = 0
    avg_duration_ms: int = 0
    tools_used: list[ToolUsage] = Field(default_factory=list)
    skills_used: list[SkillUsage] = Field(default_factory=list)
    mcp_tools_used: list[MCPToolUsage] = Field(default_factory=list)
    first_active: Optional[datetime] = None
    last_active: Optional[datetime] = None


class UserMessageItem(BaseModel):
    """User message for cost analysis."""

    trace_id: str
    source_id: str
    user_id: str
    user_name: Optional[str] = Field(default=None, description="User name")
    bbk_id: Optional[str] = Field(default=None, description="BBK identifier")
    session_id: str
    channel: str
    user_message: Optional[str] = None
    model_name: Optional[str] = None
    start_time: datetime
    duration_ms: Optional[int] = None


class ModelOutputRequest(BaseModel):
    """Model output 写入请求."""

    trace_id: str = Field(description="追踪 ID")
    model_output: str = Field(description="模型输出文本")


class ExtractCustomerNamesRequest(BaseModel):
    """提取客户姓名请求."""

    skill_names: list[str] = Field(
        ...,
        description="技能名称列表",
        min_length=1,
    )
    user_ids: Optional[list[str]] = Field(
        default=None,
        description="用户 ID 列表筛选",
    )
    bbk_id: Optional[str] = Field(
        default=None,
        description="分行 ID 筛选",
    )
    start_date: Optional[str] = Field(
        default=None,
        description="开始日期 (YYYY-MM-DD)",
    )
    end_date: Optional[str] = Field(
        default=None,
        description="结束日期 (YYYY-MM-DD)",
    )


class ExtractCustomerNamesResponse(BaseModel):
    """提取客户姓名响应."""

    total_traces: int = Field(default=0, description="处理的 trace 总数")
    names_extracted: int = Field(
        default=0,
        description="提取的姓名总数",
    )
    user_message_names: int = Field(
        default=0,
        description="用户消息中提取的姓名数",
    )
    model_output_names: int = Field(
        default=0,
        description="模型输出中提取的姓名数",
    )


class SessionRoundTrace(BaseModel):
    """Session 中单轮对话的摘要信息."""

    trace_id: str = Field(description="Trace ID")
    round_number: int = Field(description="轮次编号（从1开始）")
    start_time: datetime = Field(description="开始时间")
    duration_ms: Optional[int] = Field(default=None, description="耗时毫秒")
    model_name: Optional[str] = Field(default=None, description="模型名称")
    status: str = Field(description="状态: completed / error")
    user_message: Optional[str] = Field(default=None, description="用户消息")
    model_output: Optional[str] = Field(default=None, description="模型响应")
    input_tokens: int = Field(default=0, description="输入 Token")
    output_tokens: int = Field(default=0, description="输出 Token")
    tools_used: list[str] = Field(
        default_factory=list,
        description="使用的工具",
    )
    error: Optional[str] = Field(default=None, description="错误信息")
    is_error_round: bool = Field(default=False, description="是否是报错轮次")


class SessionTracesResponse(BaseModel):
    """Session 所有轮次对话响应."""

    session_id: str = Field(description="会话 ID")
    session_name: Optional[str] = Field(default=None, description="会话名称")
    user_id: str = Field(description="用户 ID")
    user_name: Optional[str] = Field(default=None, description="用户名称")
    traces: list[SessionRoundTrace] = Field(
        default_factory=list,
        description="所有轮次",
    )
    total_rounds: int = Field(default=0, description="总轮次")
    error_round_index: Optional[int] = Field(
        default=None,
        description="报错轮次索引（从0开始）",
    )


class InputTokensMismatchItem(BaseModel):
    """单条 input_tokens 不匹配的 trace 信息."""

    trace_id: str = Field(description="对话ID")
    trace_input_tokens: int = Field(description="trace 表记录的输入 token")
    span_input_sum: int = Field(description="span 表汇总的输入 token")
    input_diff: int = Field(
        description="差值 (span_input_sum - trace_input_tokens)",
    )
    user_id: Optional[str] = Field(default=None, description="用户ID")
    start_time: Optional[datetime] = Field(
        default=None,
        description="对话开始时间",
    )


class InputTokensFixItem(BaseModel):
    """单条修复结果."""

    trace_id: str = Field(description="对话ID")
    old_input_tokens: int = Field(description="修复前的输入 token")
    new_input_tokens: int = Field(description="修复后的输入 token")
    span_input_sum: int = Field(description="span 汇总值（作为修复依据）")


class InitSpanSkillIdRequest(BaseModel):
    """历史 span skill_id 初始化请求."""

    source_id: Optional[str] = Field(
        default=None,
        description="限定数据源；为空表示全部",
    )
    batch_size: int = Field(
        default=1000,
        ge=1,
        le=10000,
        description="每批处理 span 数量",
    )
    dry_run: bool = Field(
        default=True,
        description="仅匹配，不写库",
    )


class InitSpanSkillIdResponse(BaseModel):
    """历史 span skill_id 初始化响应."""

    dry_run: bool
    scanned: int = Field(default=0, description="扫描的待初始化 span 数量")
    matched: int = Field(default=0, description="唯一匹配并回填的数量")
    updated: int = Field(default=0, description="实际写入数据库的数量")
    unmatched: int = Field(default=0, description="无技能表匹配的数量")
    skipped: int = Field(default=0, description="未写入的 span 数量")
    ambiguous: int = Field(
        default=0,
        description="同一 source_id+skill_name 存在多个候选的数量",
    )
    selected_from_ambiguous: int = Field(
        default=0,
        description="歧义时按稳定规则选一个并写入的数量",
    )
    samples: list[dict] = Field(
        default_factory=list,
        description="未匹配和歧义样本（最多 20 条）",
    )
    errors: list[dict] = Field(
        default_factory=list,
        description="处理过程中的异常",
    )
