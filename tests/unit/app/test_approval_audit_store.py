# -*- coding: utf-8 -*-
"""审批审计落表测试。"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from swe.app.approvals.external import (
    ExternalApprovalDecision,
    notify_cron_approval_pending,
    submit_external_approval_decision,
)
from swe.app.approvals.service import ApprovalService
from swe.app.answer_turn.models import TurnIdentity, TurnLease
from swe.app.approvals.store import ApprovalAuditStore
from swe.app.source_system_config.models import (
    EffectiveSourceSystemConfig,
    SourceSystemConfig,
)
from swe.app.source_system_config.runtime import bind_source_system_config
from swe.config.context import tenant_context
from swe.security.tool_guard.approval import ApprovalDecision


class _Db:
    def __init__(self):
        self.is_connected = True
        self.executed: list[tuple[str, Any]] = []

    async def execute(self, query, params=None):
        self.executed.append((query, params))
        return 1


class _Result:
    findings: list[Any] = []
    findings_count = 2


class _AuditStore:
    def __init__(self) -> None:
        self.upserts: list[dict[str, Any]] = []
        self.events: list[dict[str, Any]] = []

    async def upsert_request(self, pending, **kwargs):
        self.upserts.append(
            {
                "request_id": pending.request_id,
                "status": pending.status,
                "consumed": pending.consumed,
                **kwargs,
            },
        )

    async def add_event(self, pending, event_type: str, **kwargs):
        self.events.append(
            {
                "request_id": pending.request_id,
                "event_type": event_type,
                "status": kwargs.get("status"),
                "actor_channel": kwargs.get("actor_channel"),
                "actor_user_id": kwargs.get("actor_user_id"),
                "details": kwargs.get("details"),
            },
        )


class _ConsoleChannel:
    async def stream_one(self, payload):
        yield payload


class _ZhaohuChannel:
    async def send_cron_approval_card(self, **_kwargs):
        return (0, "pending sent")

    async def send_cron_approval_result(self, **_kwargs):
        return (0, "result sent")


class _ChannelManager:
    def __init__(self) -> None:
        self.console = _ConsoleChannel()
        self.zhaohu = _ZhaohuChannel()

    async def get_channel(self, name: str):
        if name == "console":
            return self.console
        if name == "zhaohu":
            return self.zhaohu
        return None


class _ChatManager:
    async def get_or_create_chat(
        self,
        session_id: str,
        user_id: str,
        channel: str,
        name: str = "New Chat",
        meta: dict[str, Any] | None = None,
    ):
        return SimpleNamespace(
            id=f"chat:{session_id}",
            session_id=session_id,
            user_id=user_id,
            channel=channel,
            name=name,
            meta=meta or {},
        )


class _TaskTracker:
    async def status(self, _run_key: str) -> str:
        return "idle"

    async def attach_or_start(
        self,
        _identity,
        _payload,
        _stream_fn,
        **_kwargs,
    ):
        return object(), True

    async def attach(self, _identity):
        return None


class _Coordinator:
    def __init__(self, tracker: _TaskTracker) -> None:
        self.tracker = tracker

    async def start_or_attach(self, chat_id, payload, producer, **kwargs):
        identity = TurnIdentity(
            chat_id=chat_id,
            msgid=kwargs.get("msgid") or "msg-1",
            turn_id="turn-1",
        )
        queue, is_new = await self.tracker.attach_or_start(
            identity,
            payload,
            producer,
        )
        return TurnLease(identity, queue, is_new)


def _workspace() -> SimpleNamespace:
    tracker = _TaskTracker()
    workspace = SimpleNamespace(
        agent_id="agent-a",
        channel_manager=_ChannelManager(),
        chat_manager=_ChatManager(),
        task_tracker=tracker,
    )
    workspace.answer_turn_coordinator = _Coordinator(tracker)
    return workspace


def _source_config_with_zhaohu_notifications() -> EffectiveSourceSystemConfig:
    raw_config = SourceSystemConfig.model_validate(
        {
            "approval_notifications": {
                "zhaohu_tool_guard_enabled": True,
            },
        },
    )
    return EffectiveSourceSystemConfig(
        source_id="source-a",
        config=raw_config.merged_with_defaults(),
        raw_config=raw_config,
        version=1,
    )


async def _pending(service: ApprovalService):
    with tenant_context(tenant_id="tenant-a", source_id="source-a"):
        return await service.create_pending(
            session_id="session-1",
            user_id="user-1",
            channel="console",
            tool_name="execute_shell_command",
            result=_Result(),
            extra={
                "agent_id": "agent-a",
                "tenant_id": "tenant-a",
                "source_id": "source-a",
                "approval_kind": "tool_guard",
                "tool_call": {
                    "id": "tool-1",
                    "name": "execute_shell_command",
                    "input": {"cmd": "echo hi"},
                },
            },
        )


@pytest.mark.asyncio
async def test_approval_audit_store_initialize_sql():
    db = _Db()
    store = ApprovalAuditStore(db)

    await store.initialize()

    sql = "\n".join(query for query, _params in db.executed)
    assert "CREATE TABLE IF NOT EXISTS swe_tool_approval_requests" in sql
    assert "CREATE TABLE IF NOT EXISTS swe_tool_approval_events" in sql
    assert "PRIMARY KEY (request_id)" in sql
    assert "INDEX idx_tool_approval_events_request" in sql


@pytest.mark.asyncio
async def test_approval_service_writes_create_resolve_and_consume_audit():
    service = ApprovalService()
    audit_store = _AuditStore()
    service.set_store(audit_store)

    pending = await _pending(service)
    with tenant_context(tenant_id="tenant-a", source_id="source-a"):
        await service.resolve_request(
            pending.request_id,
            ApprovalDecision.APPROVED,
        )
        await service.consume_approval(
            "session-1",
            "execute_shell_command",
            tool_params={"cmd": "echo hi"},
        )

    assert [event["event_type"] for event in audit_store.events] == [
        "created",
        "resolved",
        "consumed",
    ]
    assert audit_store.events[1]["status"] == "approved"
    assert audit_store.upserts[-1]["consumed"] is True


@pytest.mark.asyncio
async def test_external_submission_and_notifications_write_audit_events(
    monkeypatch,
):
    service = ApprovalService()
    audit_store = _AuditStore()
    service.set_store(audit_store)
    monkeypatch.setattr(
        "swe.app.approvals.service._approval_service",
        service,
    )
    pending = await _pending(service)
    workspace = _workspace()

    with tenant_context(tenant_id="tenant-a", source_id="source-a"):
        with bind_source_system_config(
            _source_config_with_zhaohu_notifications(),
        ):
            await notify_cron_approval_pending(
                pending,
                channel_manager=workspace.channel_manager,
            )
            await submit_external_approval_decision(
                workspace=workspace,
                pending=pending,
                decision=ExternalApprovalDecision.APPROVE,
                source_channel="zhaohu",
                source_user_id="approver-1",
                source_message_id="message-1",
                source_id="source-a",
            )
    event_types = [event["event_type"] for event in audit_store.events]
    assert event_types == [
        "created",
        "pending_notified",
        "decision_submitted",
        "result_notified",
    ]
    assert audit_store.events[2]["actor_channel"] == "zhaohu"
    assert audit_store.events[2]["actor_user_id"] == "approver-1"
