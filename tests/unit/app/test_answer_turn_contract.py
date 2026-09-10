# -*- coding: utf-8 -*-
"""Console answer-turn contract after coordinator extraction."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from swe.app.answer_turn.coordinator import AnswerTurnCoordinator
from swe.app.answer_turn.in_memory import (
    InMemoryApproval,
    InMemoryExecution,
    InMemoryGoal,
    InMemorySession,
    InMemorySubagent,
)
from swe.app.answer_turn.models import (
    StopClaim,
    TurnIdentity,
    TurnOutcome,
    TurnStatus,
)
from swe.app.routers import console as console_router
from swe.app.runner.task_tracker import TaskTracker


class _ChatManager:
    def __init__(self, chat_id: str = "chat-1") -> None:
        self.chat = SimpleNamespace(
            id=chat_id,
            channel="console",
            user_id="user-1",
            meta={"source_id": "source-1"},
        )

    async def get_or_create_chat(self, *_args, **_kwargs):
        return self.chat

    async def get_chat(self, chat_id: str):
        return self.chat if chat_id == self.chat.id else None


class _BlockingConsoleChannel:
    def __init__(self) -> None:
        self.producer_calls = 0
        self.release = asyncio.Event()

    async def stream_one(self, _payload):
        self.producer_calls += 1
        yield 'data: {"started": true}\n\n'
        await self.release.wait()


def _payload() -> dict:
    return {
        "sender_id": "user-1",
        "channel_id": "console",
        "content_parts": [],
        "meta": {"session_id": "session-1"},
    }


def _coordinator(tracker: TaskTracker) -> AnswerTurnCoordinator:
    return AnswerTurnCoordinator(
        stream=tracker,
        execution=InMemoryExecution(),
        session=InMemorySession(),
        goal=InMemoryGoal(),
        subagent=InMemorySubagent(),
        approval=InMemoryApproval(),
        hard_cancel_delay=0.01,
    )


@pytest.mark.asyncio
async def test_console_duplicate_submission_attaches_to_one_server_owned_turn():
    tracker = TaskTracker()
    coordinator = _coordinator(tracker)
    channel = _BlockingConsoleChannel()
    workspace = SimpleNamespace(
        agent_id="agent-1",
        chat_manager=_ChatManager(),
        answer_turn_coordinator=coordinator,
    )

    first_queue, chat_id, first_msgid, first_is_new = (
        await console_router._start_new_chat(
            workspace,
            tracker,
            channel,
            "session-1",
            _payload(),
            include_run_status=True,
        )
    )
    await asyncio.wait_for(first_queue.get(), timeout=1)

    second_queue, second_chat_id, second_msgid, second_is_new = (
        await console_router._start_new_chat(
            workspace,
            tracker,
            channel,
            "session-1",
            _payload(),
            include_run_status=True,
        )
    )

    assert chat_id == second_chat_id == "chat-1"
    assert first_is_new is True
    assert second_is_new is False
    assert second_msgid == first_msgid
    active = await coordinator.current_identity(chat_id)
    assert active is not None
    assert active.msgid == first_msgid
    assert channel.producer_calls == 1
    assert await asyncio.wait_for(second_queue.get(), timeout=1) == (
        'data: {"started": true}\n\n'
    )

    channel.release.set()
    await asyncio.wait_for(tracker.wait_all_done(timeout=1), timeout=2)
    await coordinator.settle(TurnOutcome.completed(active))


@pytest.mark.asyncio
async def test_coordinator_stop_enters_stopping_until_settlement():
    tracker = TaskTracker()
    coordinator = _coordinator(tracker)
    channel = _BlockingConsoleChannel()

    async def producer(identity, payload):
        async for event in channel.stream_one(payload):
            yield event

    lease = await coordinator.start_or_attach(
        "chat-stop",
        {},
        producer,
        msgid="turn-1",
    )
    await asyncio.wait_for(lease.queue.get(), timeout=1)

    claim = await coordinator.claim_stop(lease.identity, msgid="turn-1")

    assert claim == StopClaim(
        accepted=True,
        identity=lease.identity,
        status=TurnStatus.STOPPING,
    )
    assert await coordinator.status(lease.identity) == TurnStatus.STOPPING
    assert await coordinator.current_identity("chat-stop") == lease.identity

    await coordinator.settle(TurnOutcome.cancelled(lease.identity))
    assert await coordinator.current_identity("chat-stop") is None
    channel.release.set()
    await asyncio.wait_for(tracker.wait_all_done(timeout=1), timeout=2)


@pytest.mark.asyncio
async def test_submission_waits_for_terminal_outcome_persistence() -> None:
    tracker = TaskTracker()
    persistence_started = asyncio.Event()
    release_persistence = asyncio.Event()

    class _BlockingSession(InMemorySession):
        async def persist_outcome(self, outcome):
            persistence_started.set()
            await release_persistence.wait()
            await super().persist_outcome(outcome)

    coordinator = AnswerTurnCoordinator(
        stream=tracker,
        execution=InMemoryExecution(),
        session=_BlockingSession(),
        goal=InMemoryGoal(),
        subagent=InMemorySubagent(),
        approval=InMemoryApproval(),
    )

    async def producer(_identity, _payload):
        if False:
            yield None

    first = await coordinator.start_or_attach("chat-1", {}, producer)
    settlement = asyncio.create_task(
        coordinator.settle(TurnOutcome.completed(first.identity)),
    )
    await asyncio.wait_for(persistence_started.wait(), timeout=1)

    following = asyncio.create_task(
        coordinator.start_or_attach("chat-1", {}, producer),
    )
    await asyncio.sleep(0)
    assert following.done() is False

    release_persistence.set()
    await settlement
    assert (await following).is_new_run is True


@pytest.mark.asyncio
async def test_failed_settlement_blocks_following_submission_until_retry() -> (
    None
):
    tracker = TaskTracker()
    attempts = 0

    class _FlakySession(InMemorySession):
        async def persist_outcome(self, outcome):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise OSError("disk unavailable")
            await super().persist_outcome(outcome)

    coordinator = AnswerTurnCoordinator(
        stream=tracker,
        execution=InMemoryExecution(),
        session=_FlakySession(),
        goal=InMemoryGoal(),
        subagent=InMemorySubagent(),
        approval=InMemoryApproval(),
    )

    async def producer(_identity, _payload):
        if False:
            yield None

    first = await coordinator.start_or_attach("chat-1", {}, producer)
    await coordinator.settle(TurnOutcome.completed(first.identity))

    with pytest.raises(Exception, match="settlement"):
        await coordinator.start_or_attach("chat-1", {}, producer)

    await asyncio.sleep(0.2)
    assert attempts >= 2


@pytest.mark.asyncio
async def test_stop_with_mismatched_msgid_leaves_the_active_turn_running():
    tracker = TaskTracker()
    coordinator = _coordinator(tracker)
    release = asyncio.Event()

    async def producer(_identity, _payload):
        yield 'data: {"started": true}\n\n'
        await release.wait()

    lease = await coordinator.start_or_attach(
        "chat-mismatch",
        {},
        producer,
        msgid="turn-active",
    )
    await asyncio.wait_for(lease.queue.get(), timeout=1)

    claim = await coordinator.claim_stop(lease.identity, msgid="turn-stale")

    assert claim.accepted is False
    assert claim.status == TurnStatus.RUNNING
    assert await coordinator.status(lease.identity) == TurnStatus.RUNNING
    assert (
        await coordinator.current_identity("chat-mismatch") == lease.identity
    )

    await coordinator.settle(TurnOutcome.cancelled(lease.identity))
    release.set()
    await asyncio.wait_for(tracker.wait_all_done(timeout=1), timeout=2)


def test_console_stop_delegates_to_bound_turn_coordinator(monkeypatch) -> None:
    identity = TurnIdentity(
        chat_id="chat-1",
        msgid="turn-1",
        turn_id="turn-1",
    )
    calls: list[tuple[TurnIdentity, str | None]] = []

    class _Coordinator:
        async def current_identity(self, chat_id):
            assert chat_id == "chat-1"
            return identity

        async def claim_stop(
            self,
            turn_identity,
            *,
            msgid=None,
            internal=False,
        ):
            assert internal is False
            calls.append((turn_identity, msgid))
            return StopClaim(
                accepted=True,
                identity=turn_identity,
                status=TurnStatus.STOPPING,
            )

    workspace = SimpleNamespace(
        answer_turn_coordinator=_Coordinator(),
        chat_manager=_ChatManager(),
    )

    async def get_workspace(_request):
        return workspace

    monkeypatch.setattr(console_router, "get_agent_for_request", get_workspace)

    app = FastAPI()
    app.include_router(console_router.router)
    response = TestClient(app).post(
        "/console/chat/stop?chat_id=chat-1&msgid=turn-1",
        headers={"X-User-Id": "user-1", "X-Source-Id": "source-1"},
    )

    assert response.json() == {
        "stopped": True,
        "accepted": True,
        "status": "stopping",
        "chat_id": "chat-1",
        "msgid": "turn-1",
    }
    assert calls == [(identity, "turn-1")]


@pytest.mark.asyncio
async def test_reconnect_replays_buffered_events_without_restarting_execution():
    tracker = TaskTracker()
    coordinator = _coordinator(tracker)
    channel = _BlockingConsoleChannel()

    async def producer(identity, payload):
        async for event in channel.stream_one(payload):
            yield event

    lease = await coordinator.start_or_attach(
        "chat-reconnect",
        {},
        producer,
        msgid="turn-1",
    )
    first_event = await asyncio.wait_for(lease.queue.get(), timeout=1)

    reconnect = await coordinator.attach("chat-reconnect", msgid="turn-1")

    assert reconnect is not None
    assert (
        await asyncio.wait_for(reconnect.queue.get(), timeout=1) == first_event
    )
    assert channel.producer_calls == 1
    assert reconnect.identity == lease.identity

    channel.release.set()
    await asyncio.wait_for(tracker.wait_all_done(timeout=1), timeout=2)
    await coordinator.settle(TurnOutcome.completed(lease.identity))
