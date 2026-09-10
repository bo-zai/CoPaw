# -*- coding: utf-8 -*-
from types import SimpleNamespace

import pytest

from swe.app.approvals.service import ApprovalService
from swe.config.context import tenant_context
from swe.security.tool_guard.approval import ApprovalDecision


def _result():
    return SimpleNamespace(findings=[], findings_count=0)


@pytest.mark.asyncio
async def test_supersede_pending_for_turn_only_affects_that_chat_turn() -> (
    None
):
    service = ApprovalService()
    with tenant_context(tenant_id="tenant-a", source_id="source-a"):
        target = await service.create_pending(
            session_id="session-1",
            user_id="user-1",
            channel="console",
            tool_name="read_file",
            result=_result(),
            extra={"chat_id": "chat-a", "msgid": "turn-a"},
        )
        same_chat_other_turn = await service.create_pending(
            session_id="session-1",
            user_id="user-1",
            channel="console",
            tool_name="read_file",
            result=_result(),
            extra={"chat_id": "chat-a", "msgid": "turn-b"},
        )
        other_chat_same_turn = await service.create_pending(
            session_id="session-1",
            user_id="user-1",
            channel="console",
            tool_name="read_file",
            result=_result(),
            extra={"chat_id": "chat-b", "msgid": "turn-a"},
        )

        count = await service.supersede_pending_for_turn("chat-a", "turn-a")

    assert count == 1
    assert target.status == "superseded"
    assert target.future.result() == ApprovalDecision.TIMEOUT
    assert same_chat_other_turn.status == "pending"
    assert other_chat_same_turn.status == "pending"
