# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.swe.app.routers import console as console_router


def test_console_stop_idle_response_is_a_fresh_legacy_payload() -> None:
    first = console_router._console_stop_idle_response()
    second = console_router._console_stop_idle_response()

    assert first == {"stopped": False, "accepted": False, "status": "idle"}
    assert first is not second


from swe.app.answer_turn.models import StopClaim, TurnIdentity, TurnLease


class _FakeConsoleChannel:
    def resolve_session_id(self, sender_id: str, channel_meta: dict) -> str:
        return channel_meta.get("session_id") or f"console:{sender_id}"

    async def stream_one(self, payload):
        yield payload


class _FakeChannelManager:
    async def get_channel(self, name: str):
        assert name == "console"
        return _FakeConsoleChannel()


class _FakeChatManager:
    def __init__(self) -> None:
        self.get_or_create_calls: list[tuple[str, str, str, str]] = []
        self.get_chat_id_by_session_calls: list[tuple[str, str]] = []

    async def get_chat(self, chat_id: str):
        if chat_id == "chat-existing":
            return SimpleNamespace(
                id="chat-existing",
                session_id="session-existing",
                user_id="user-1",
                channel="console",
                name="Existing Chat",
            )
        return None

    async def get_chat_by_session(
        self,
        session_id: str,
        channel: str,
        user_id: str | None = None,
    ):
        assert user_id in (None, "user-1")
        if session_id == "session-existing" and channel == "console":
            return await self.get_chat("chat-existing")
        return None

    async def get_chat_id_by_session(self, session_id: str, channel: str):
        self.get_chat_id_by_session_calls.append((session_id, channel))
        if session_id == "session-existing" and channel == "console":
            return "chat-existing"
        return None

    async def get_or_create_chat(
        self,
        session_id: str,
        user_id: str,
        channel_id: str,
        name: str,
        _meta=None,
    ):
        self.get_or_create_calls.append(
            (session_id, user_id, channel_id, name),
        )
        return SimpleNamespace(
            id=f"chat:{session_id}",
            session_id=session_id,
            user_id=user_id,
            channel=channel_id,
            name=name,
        )


class _FakeTaskTracker:
    async def attach_or_start(self, run_key, payload, stream_fn):
        raise AssertionError("attach_or_start should not run during reconnect")

    async def attach(self, identity):
        if identity.chat_id == "chat-existing":
            return object()
        return None

    async def stream(self, _identity, _queue):
        await asyncio.sleep(0)
        yield 'data: {"done": true}\n\n'


class _FakeCoordinator:
    def __init__(self, tracker):
        self.tracker = tracker
        self.identity = TurnIdentity(
            chat_id="chat-existing",
            msgid="msg-1",
            turn_id="turn-1",
        )

    async def attach(self, chat_id, *, msgid=None):
        if chat_id != self.identity.chat_id:
            return None
        if msgid is not None and msgid != self.identity.msgid:
            return None
        queue = await self.tracker.attach(self.identity)
        return TurnLease(self.identity, queue, False) if queue else None

    async def current_identity(self, chat_id):
        return self.identity if chat_id == self.identity.chat_id else None

    async def claim_stop(self, identity, *, msgid=None, internal=False):
        _ = internal
        if msgid is not None and msgid != identity.msgid:
            return StopClaim(False, identity=identity)
        return StopClaim(True, identity=identity, status="stopping")


def _workspace_with_tracker(chat_manager, tracker):
    return SimpleNamespace(
        channel_manager=_FakeChannelManager(),
        chat_manager=chat_manager,
        task_tracker=tracker,
        answer_turn_coordinator=_FakeCoordinator(tracker),
    )


def test_console_chat_reconnect_waits_for_recently_started_run() -> None:
    class _EventuallyAvailableChatManager:
        def __init__(self) -> None:
            self.lookup_count = 0

        async def get_chat(self, _chat_id: str):
            return None

        async def get_chat_id_by_session(self, session_id: str, channel: str):
            assert session_id == "1777001065201000"
            assert channel == "console"
            self.lookup_count += 1
            if self.lookup_count == 1:
                return None
            return "chat-real-1"

    class _EventuallyAvailableTaskTracker:
        async def attach(self, identity):
            if identity.chat_id == "chat-real-1":
                return object()
            return None

    class _EventuallyCoordinator:
        async def attach(self, chat_id, *, msgid=None):
            _ = msgid
            if chat_id != "chat-real-1":
                return None
            identity = TurnIdentity(
                chat_id=chat_id,
                msgid="msg-1",
                turn_id="turn-1",
            )
            return TurnLease(identity, object(), False)

    async def _run() -> tuple[object, str, int]:
        chat_manager = _EventuallyAvailableChatManager()
        # pylint: disable=protected-access
        queue, run_key, _identity = (
            await console_router._attach_reconnect_queue(
                SimpleNamespace(
                    chat_manager=chat_manager,
                    answer_turn_coordinator=_EventuallyCoordinator(),
                ),
                _EventuallyAvailableTaskTracker(),
                "1777001065201000",
                "console",
            )
        )
        return queue, run_key, chat_manager.lookup_count

    queue, run_key, lookup_count = asyncio.run(_run())

    assert queue is not None
    assert run_key == "chat-real-1"
    assert lookup_count == 2


def test_console_chat_reconnect_accepts_chat_id_without_creating_new_chat(
    monkeypatch,
) -> None:
    app = FastAPI()
    app.include_router(console_router.router)

    chat_manager = _FakeChatManager()
    workspace = _workspace_with_tracker(chat_manager, _FakeTaskTracker())

    async def _fake_get_agent_for_request(_request):
        return workspace

    monkeypatch.setattr(
        console_router,
        "get_agent_for_request",
        _fake_get_agent_for_request,
    )

    client = TestClient(app)

    with client.stream(
        "POST",
        "/console/chat",
        headers={"X-Source-Id": "src-a"},
        json={
            "reconnect": True,
            "session_id": "chat-existing",
            "user_id": "user-1",
            "channel": "console",
        },
    ) as response:
        assert response.status_code == 200
        assert "X-Swe-Msgid" not in response.headers
        assert list(response.iter_lines()) == [
            ": keep-alive",
            "",
            'data: {"done": true}',
            "",
        ]

    assert not chat_manager.get_or_create_calls


def test_current_reconnect_returns_server_owned_turn_headers(
    monkeypatch,
) -> None:
    app = FastAPI()
    app.include_router(console_router.router)

    chat_manager = _FakeChatManager()
    workspace = _workspace_with_tracker(chat_manager, _FakeTaskTracker())

    async def _fake_get_agent_for_request(_request):
        return workspace

    monkeypatch.setattr(
        console_router,
        "get_agent_for_request",
        _fake_get_agent_for_request,
    )

    with TestClient(app).stream(
        "POST",
        "/console/chat",
        headers={"X-Source-Id": "src-a"},
        json={
            "reconnect": True,
            "reconnect_mode": "current",
            "chat_id": "chat-existing",
            "session_id": "chat-existing",
            "user_id": "user-1",
            "channel": "console",
        },
    ) as response:
        assert response.status_code == 200
        assert response.headers["X-Swe-Chatid"] == "chat-existing"
        assert response.headers["X-Swe-Sessionid"] == "session-existing"
        assert response.headers["X-Swe-Msgid"] == "msg-1"


def test_current_reconnect_falls_back_when_optional_chat_id_is_unknown(
    monkeypatch,
) -> None:
    app = FastAPI()
    app.include_router(console_router.router)
    chat_manager = _FakeChatManager()
    workspace = _workspace_with_tracker(chat_manager, _FakeTaskTracker())

    async def _fake_get_agent_for_request(_request):
        return workspace

    monkeypatch.setattr(
        console_router,
        "get_agent_for_request",
        _fake_get_agent_for_request,
    )

    response = TestClient(app).post(
        "/console/chat",
        headers={"X-Source-Id": "src-a"},
        json={
            "reconnect_mode": "current",
            "chat_id": "unknown-chat-id",
            "session_id": "session-existing",
            "user_id": "user-1",
            "channel": "console",
        },
    )

    assert response.status_code == 200
    assert response.headers["X-Swe-Chatid"] == "chat-existing"


def test_current_reconnect_returns_terminal_snapshot_event(
    monkeypatch,
) -> None:
    app = FastAPI()
    app.include_router(console_router.router)
    chat_manager = _FakeChatManager()
    workspace = _workspace_with_tracker(chat_manager, _FakeTaskTracker())

    class _TerminalCoordinator:
        async def attach(self, _chat_id):
            return None

    workspace.answer_turn_coordinator = _TerminalCoordinator()

    async def _fake_get_agent_for_request(_request):
        return workspace

    async def _terminal_snapshot(_workspace, chat):
        assert chat.id == "chat-existing"
        return (
            {"chat": {"id": chat.id}, "messages": []},
            "msg-last",
            "completed",
        )

    monkeypatch.setattr(
        console_router,
        "get_agent_for_request",
        _fake_get_agent_for_request,
    )
    monkeypatch.setattr(
        console_router,
        "_current_recovery_terminal_snapshot",
        _terminal_snapshot,
        raising=False,
    )

    response = TestClient(app).post(
        "/console/chat",
        headers={"X-Source-Id": "src-a"},
        json={
            "reconnect_mode": "current",
            "session_id": "chat-existing",
            "user_id": "user-1",
            "channel": "console",
        },
    )

    assert response.status_code == 200
    assert response.headers["X-Swe-Msgid"] == "msg-last"
    assert response.text == (
        "event: chat.snapshot\n"
        'data: {"object": "chat_snapshot", "chat_id": "chat-existing", '
        '"msgid": "msg-last", "turn_status": "completed", '
        '"history": {"chat": {"id": "chat-existing"}, "messages": []}}\n\n'
    )


def test_console_chat_reconnect_with_agent_request_shape_does_not_start_run(
    monkeypatch,
) -> None:
    app = FastAPI()
    app.include_router(console_router.router)

    chat_manager = _FakeChatManager()
    workspace = _workspace_with_tracker(chat_manager, _FakeTaskTracker())

    async def _fake_get_agent_for_request(_request):
        return workspace

    monkeypatch.setattr(
        console_router,
        "get_agent_for_request",
        _fake_get_agent_for_request,
    )

    client = TestClient(app)

    with client.stream(
        "POST",
        "/console/chat",
        headers={"X-Source-Id": "src-a"},
        json={
            "reconnect": True,
            "input": [
                {
                    "role": "user",
                    "content": [{"type": "text", "text": "ignored"}],
                },
            ],
            "session_id": "chat-existing",
            "user_id": "user-1",
            "channel": "console",
        },
    ) as response:
        assert response.status_code == 200
        assert "X-Swe-Msgid" not in response.headers
        assert list(response.iter_lines()) == [
            ": keep-alive",
            "",
            'data: {"done": true}',
            "",
        ]

    assert not chat_manager.get_or_create_calls


def test_console_chat_reconnect_accepts_logical_session_id(
    monkeypatch,
) -> None:
    app = FastAPI()
    app.include_router(console_router.router)

    chat_manager = _FakeChatManager()
    workspace = _workspace_with_tracker(chat_manager, _FakeTaskTracker())

    async def _fake_get_agent_for_request(_request):
        return workspace

    monkeypatch.setattr(
        console_router,
        "get_agent_for_request",
        _fake_get_agent_for_request,
    )

    client = TestClient(app)

    with client.stream(
        "POST",
        "/console/chat",
        headers={"X-Source-Id": "src-a"},
        json={
            "reconnect": True,
            "session_id": "session-existing",
            "user_id": "user-1",
            "channel": "console",
        },
    ) as response:
        assert response.status_code == 200
        assert "X-Swe-Msgid" not in response.headers
        assert list(response.iter_lines()) == [
            ": keep-alive",
            "",
            'data: {"done": true}',
            "",
        ]

    assert chat_manager.get_chat_id_by_session_calls == [
        ("session-existing", "console"),
    ]
    assert not chat_manager.get_or_create_calls


def test_console_chat_stop_returns_turn_bound_claim(monkeypatch) -> None:
    app = FastAPI()
    app.include_router(console_router.router)

    class _StopChatManager:
        async def get_chat(self, chat_id: str):
            if chat_id == "chat-1":
                return SimpleNamespace(
                    id=chat_id,
                    user_id="user-1",
                    channel="console",
                )
            return None

    class _StopCoordinator:
        async def current_identity(self, chat_id):
            return TurnIdentity(
                chat_id=chat_id,
                msgid="msg-1",
                turn_id="turn-1",
            )

        async def claim_stop(self, identity, *, msgid=None, internal=False):
            _ = internal
            assert identity.chat_id == "chat-1"
            assert msgid == "msg-1"
            return StopClaim(True, identity=identity, status="stopping")

    workspace = SimpleNamespace(
        chat_manager=_StopChatManager(),
        task_tracker=SimpleNamespace(),
        answer_turn_coordinator=_StopCoordinator(),
    )

    async def _fake_get_agent_for_request(_request):
        return workspace

    monkeypatch.setattr(
        console_router,
        "get_agent_for_request",
        _fake_get_agent_for_request,
    )

    response = TestClient(app).post(
        "/console/chat/stop",
        params={"chat_id": "chat-1", "msgid": "msg-1"},
        headers={"X-User-Id": "user-1"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "stopped": True,
        "accepted": True,
        "status": "stopping",
        "chat_id": "chat-1",
        "msgid": "msg-1",
    }


def test_cancel_console_turn_subagents_does_not_cancel_goal_history() -> None:
    cancelled_turns: list[tuple[str, str, str]] = []
    cancelled_runs: list[str] = []

    class _Supervisor:
        async def cancel_turn_runs(self, scope, *, chat_id: str, msgid: str):
            assert scope is not None
            cancelled_turns.append(("scope", chat_id, msgid))

        async def cancel(self, _scope, run_id: str):
            cancelled_runs.append(run_id)

    workspace = SimpleNamespace(
        config=SimpleNamespace(),
        tenant_id="tenant-1",
        agent_id="agent-1",
        subagent_supervisor=_Supervisor(),
    )

    asyncio.run(
        console_router._cancel_console_turn_subagents(
            workspace,
            "chat-1",
            "msg-current",
        ),
    )

    assert cancelled_turns == [("scope", "chat-1", "msg-current")]
    assert cancelled_runs == []


def test_console_chat_stop_without_caller_identity_is_an_idle_noop(
    monkeypatch,
) -> None:
    app = FastAPI()
    app.include_router(console_router.router)

    class _StopChatManager:
        async def get_chat(self, _chat_id: str):
            return SimpleNamespace(
                id="chat-1",
                user_id="user-1",
                channel="console",
            )

    class _StopCoordinator:
        async def current_identity(self, *_args, **_kwargs):
            raise AssertionError(
                "unauthenticated Stop must not reach coordinator",
            )

    workspace = SimpleNamespace(
        chat_manager=_StopChatManager(),
        task_tracker=SimpleNamespace(),
        answer_turn_coordinator=_StopCoordinator(),
    )

    async def _fake_get_agent_for_request(_request):
        return workspace

    monkeypatch.setattr(
        console_router,
        "get_agent_for_request",
        _fake_get_agent_for_request,
    )

    response = TestClient(app).post(
        "/console/chat/stop",
        params={"chat_id": "chat-1", "msgid": "msg-1"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "stopped": False,
        "accepted": False,
        "status": "idle",
    }


def test_console_chat_stop_session_fallback_rejects_ambiguous_active_turns(
    monkeypatch,
) -> None:
    app = FastAPI()
    app.include_router(console_router.router)

    class _StopChatManager:
        async def list_chats(self, user_id: str, channel: str):
            assert (user_id, channel) == ("user-1", "console")
            return [
                SimpleNamespace(
                    id="chat-1",
                    session_id="session-early",
                    user_id="user-1",
                    channel="console",
                ),
                SimpleNamespace(
                    id="chat-2",
                    session_id="session-early",
                    user_id="user-1",
                    channel="console",
                ),
            ]

        async def get_chat(self, _chat_id: str):
            raise AssertionError(
                "ambiguous early Stop must not resolve a chat",
            )

    class _StopCoordinator:
        async def current_identity(self, chat_id):
            return TurnIdentity(
                chat_id=chat_id,
                msgid=f"msg-{chat_id}",
                turn_id=f"turn-{chat_id}",
            )

    workspace = SimpleNamespace(
        chat_manager=_StopChatManager(),
        task_tracker=SimpleNamespace(),
        answer_turn_coordinator=_StopCoordinator(),
    )

    async def _fake_get_agent_for_request(_request):
        return workspace

    monkeypatch.setattr(
        console_router,
        "get_agent_for_request",
        _fake_get_agent_for_request,
    )

    response = TestClient(app).post(
        "/console/chat/stop",
        params={"session_id": "session-early"},
        headers={"X-User-Id": "user-1"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "stopped": False,
        "accepted": False,
        "status": "idle",
    }
