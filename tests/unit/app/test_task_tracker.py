# -*- coding: utf-8 -*-
"""Transport contract for answer-turn stream delivery."""

from __future__ import annotations

import asyncio
import json
import threading

import pytest

from swe.app.answer_turn.models import TurnIdentity
from swe.app.runner.task_tracker import TaskTracker
from swe.app.runner.tool_output_frames import (
    emit_tool_output_text,
    tool_output_invocation,
)


def _identity(
    chat_id: str = "chat-1",
    turn_id: str = "turn-1",
) -> TurnIdentity:
    return TurnIdentity(chat_id=chat_id, msgid="message-1", turn_id=turn_id)


@pytest.mark.asyncio
async def test_attach_or_start_binds_identity_and_replays_one_producer_stream():
    tracker = TaskTracker()
    release = asyncio.Event()
    received: list[tuple[TurnIdentity, object]] = []
    identity = _identity()

    async def producer(bound_identity, payload):
        received.append((bound_identity, payload))
        yield 'data: {"first": true}\n\n'
        await release.wait()

    first, is_new = await tracker.attach_or_start(
        identity,
        {"query": "hi"},
        producer,
    )
    assert is_new is True
    assert (
        await asyncio.wait_for(first.get(), timeout=1)
        == 'data: {"first": true}\n\n'
    )

    second, is_new = await tracker.attach_or_start(
        identity,
        {"ignored": True},
        producer,
    )
    assert is_new is False
    assert (
        await asyncio.wait_for(second.get(), timeout=1)
        == 'data: {"first": true}\n\n'
    )
    assert received == [(identity, {"query": "hi"})]

    release.set()
    await asyncio.wait_for(tracker.wait_all_done(timeout=1), timeout=2)


@pytest.mark.asyncio
async def test_attach_replays_buffer_and_stream_detaches_on_consumer_close():
    tracker = TaskTracker()
    release = asyncio.Event()
    identity = _identity()

    async def producer(_identity, _payload):
        yield 'data: {"first": true}\n\n'
        await release.wait()

    queue, _ = await tracker.attach_or_start(identity, {}, producer)
    assert await asyncio.wait_for(queue.get(), timeout=1)
    replay = await tracker.attach(identity)
    assert replay is not None
    stream = tracker.stream(identity, replay)
    assert await anext(stream) == 'data: {"first": true}\n\n'
    await stream.aclose()
    assert replay not in tracker._runs[identity.chat_id].queues

    release.set()
    await asyncio.wait_for(tracker.wait_all_done(timeout=1), timeout=2)


@pytest.mark.asyncio
async def test_producer_exception_is_delivered_then_ends_stream():
    tracker = TaskTracker()
    identity = _identity()

    async def producer(_identity, _payload):
        if _payload is not None:
            raise RuntimeError("boom")
        yield "data: {}\n\n"

    queue, _ = await tracker.attach_or_start(identity, {}, producer)
    events = [event async for event in tracker.stream(identity, queue)]
    assert events == ['data: {"error": "internal server error"}\n\n']
    assert await tracker.has_active_tasks() is False


@pytest.mark.asyncio
async def test_close_unblocks_subscribers_without_cancelling_producer():
    tracker = TaskTracker()
    release = asyncio.Event()
    identity = _identity()

    async def producer(_identity, _payload):
        yield 'data: {"first": true}\n\n'
        await release.wait()

    queue, _ = await tracker.attach_or_start(identity, {}, producer)
    assert await asyncio.wait_for(queue.get(), timeout=1)
    await tracker.close(identity)
    assert [event async for event in tracker.stream(identity, queue)] == []
    assert await tracker.has_active_tasks() is True
    with pytest.raises(
        RuntimeError,
        match="live stream belongs to another turn",
    ):
        await tracker.attach_or_start(
            _identity(turn_id="turn-2"),
            {},
            producer,
        )

    release.set()
    await asyncio.wait_for(tracker.wait_all_done(timeout=1), timeout=2)


@pytest.mark.asyncio
async def test_before_start_is_atomic_with_call_if_idle_for_one_chat():
    tracker = TaskTracker()
    identity = _identity("chat-serialized")
    callback_started = threading.Event()
    release_callback = threading.Event()
    durable_state = {"active": True}

    def recover():
        durable_state["active"] = False
        callback_started.set()
        assert release_callback.wait(timeout=2)
        return "recovered"

    recovery = asyncio.create_task(tracker.call_if_idle(identity, recover))
    assert await asyncio.to_thread(callback_started.wait, 1)

    async def producer(_identity, _payload):
        yield 'data: {"done": true}\n\n'

    def validate_claim():
        if not durable_state["active"]:
            raise RuntimeError("claim is no longer active")

    start = asyncio.create_task(
        tracker.attach_or_start(
            identity,
            {},
            producer,
            before_start=validate_claim,
        ),
    )
    await asyncio.sleep(0)
    assert start.done() is False
    release_callback.set()
    assert await recovery == (True, "recovered")
    with pytest.raises(RuntimeError, match="claim is no longer active"):
        await start


@pytest.mark.asyncio
async def test_active_task_helpers_and_progress_are_transport_support():
    tracker = TaskTracker()
    release = asyncio.Event()
    identity = _identity("chat-active")

    async def producer(_identity, _payload):
        yield 'data: {"started": true}\n\n'
        await release.wait()

    await tracker.attach_or_start(identity, {}, producer)
    await asyncio.sleep(0)
    assert await tracker.has_active_tasks() is True
    assert await tracker.list_active_tasks() == [identity.chat_id]

    payload = {"status": "running", "steps": [{"title": "work"}]}
    stored = await tracker.update_task_progress(identity.chat_id, payload)
    stored["steps"][0]["title"] = "changed"
    assert (await tracker.get_task_progress(identity.chat_id))["steps"][0][
        "title"
    ] == "work"

    release.set()
    assert await tracker.wait_all_done(timeout=1) is True
    assert await tracker.get_task_progress(identity.chat_id) is None


@pytest.mark.asyncio
async def test_tool_output_frames_are_broadcast_and_buffered_for_reconnect():
    tracker = TaskTracker()
    release = asyncio.Event()
    identity = _identity()

    async def producer(_identity, _payload):
        with tool_output_invocation(
            tool_call_id="call-1",
            tool_name="execute_shell_command",
        ):
            await emit_tool_output_text("stdout", "live output\n")
        await release.wait()
        yield "data: {}\n\n"

    queue, _ = await tracker.attach_or_start(identity, {}, producer)
    live_sse = await asyncio.wait_for(queue.get(), timeout=1)
    assert (
        json.loads(live_sse.removeprefix("data: ").strip())["text"]
        == "live output\n"
    )
    replay = await tracker.attach(identity)
    assert replay is not None
    replay_sse = await asyncio.wait_for(replay.get(), timeout=1)
    assert (
        json.loads(replay_sse.removeprefix("data: ").strip())["text"]
        == "live output\n"
    )

    release.set()
    await asyncio.wait_for(tracker.wait_all_done(timeout=1), timeout=2)


def test_tracker_has_no_answer_turn_stop_or_status_api():
    tracker = TaskTracker()
    for name in (
        "claim_stop",
        "request_stop",
        "mark_stopping",
        "get_status",
        "get_run_identity",
        "is_turn_stopping",
    ):
        assert not hasattr(tracker, name)


@pytest.mark.asyncio
async def test_different_identity_same_chat_cannot_start_second_producer():
    tracker = TaskTracker()
    release = asyncio.Event()

    async def producer(_identity, _payload):
        await release.wait()
        yield "data: {}\n\n"

    first = _identity(turn_id="turn-1")
    second = _identity(turn_id="turn-2")
    _, is_new = await tracker.attach_or_start(first, {}, producer)
    with pytest.raises(
        RuntimeError,
        match="live stream belongs to another turn",
    ):
        await tracker.attach_or_start(second, {}, producer)
    assert is_new is True
    release.set()
    await tracker.wait_all_done(timeout=1)
