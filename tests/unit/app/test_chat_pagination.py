# -*- coding: utf-8 -*-
from __future__ import annotations

import base64
from datetime import datetime, timezone
import json
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from swe.app.runner.api import get_chat_manager, get_workspace, router
from swe.app.runner.manager import ChatManager
from swe.app.runner.models import ChatSpec, ChatsFile
from swe.app.runner.repo import BaseChatRepository
from swe.app.routers.agent_scoped import create_agent_scoped_router
from swe.app.answer_turn.models import TurnStatus


def _chat(
    chat_id: str,
    updated_at: str,
    *,
    created_at: str | None = None,
    user_id: str = "user-1",
    channel: str = "console",
) -> ChatSpec:
    return ChatSpec(
        id=chat_id,
        name=chat_id,
        session_id=f"session-{chat_id}",
        user_id=user_id,
        channel=channel,
        created_at=datetime.fromisoformat(created_at or updated_at),
        updated_at=datetime.fromisoformat(updated_at),
    )


class _InMemoryChatRepository(BaseChatRepository):
    def __init__(self, chats: list[ChatSpec]) -> None:
        self.path = "<memory>"
        self._state = ChatsFile(chats=chats)

    async def load(self) -> ChatsFile:
        return self._state.model_copy(deep=True)

    async def save(self, chats_file: ChatsFile) -> None:
        self._state = chats_file.model_copy(deep=True)


def _stored_chats() -> list[ChatSpec]:
    return [
        _chat("chat-old", "2026-06-01T00:00:00+00:00"),
        _chat("chat-a", "2026-06-03T00:00:00+00:00"),
        _chat("chat-z", "2026-06-03T00:00:00+00:00"),
        _chat(
            "chat-other-user",
            "2026-06-04T00:00:00+00:00",
            user_id="user-2",
        ),
        _chat(
            "chat-other-channel",
            "2026-06-05T00:00:00+00:00",
            channel="discord",
        ),
    ]


async def test_repository_paginates_filtered_chats_newest_first() -> None:
    repo = _InMemoryChatRepository(_stored_chats())

    page = await repo.paginate_chats(
        user_id="user-1",
        channel="console",
        page=1,
        page_size=2,
    )

    assert [chat.id for chat in page.items] == ["chat-z", "chat-a"]
    assert page.total == 3
    assert page.page == 1
    assert page.page_size == 2
    assert page.has_more is True


async def test_repository_returns_empty_page_after_last_result() -> None:
    repo = _InMemoryChatRepository(_stored_chats())

    page = await repo.paginate_chats(
        user_id="user-1",
        channel="console",
        page=3,
        page_size=2,
    )

    assert page.items == []
    assert page.total == 3
    assert page.has_more is False


async def test_repository_cursor_pagination_is_best_effort_when_updated_at_changes() -> (
    None
):
    repo = _InMemoryChatRepository(_stored_chats())

    first_page = await repo.paginate_chats_cursor(
        user_id="user-1",
        channel="console",
        page_size=2,
        cursor=None,
    )
    assert [chat.id for chat in first_page.items] == ["chat-z", "chat-a"]
    assert first_page.next_cursor is not None

    repo._state.chats[0].updated_at = datetime.fromisoformat(
        "2026-06-12T00:00:00+00:00",
    )
    second_page = await repo.paginate_chats_cursor(
        user_id="user-1",
        channel="console",
        page_size=2,
        cursor=first_page.next_cursor,
    )

    assert second_page.items == []
    assert second_page.has_more is False


async def test_repository_page_orders_by_last_update_not_creation() -> None:
    repo = _InMemoryChatRepository(
        [
            _chat(
                "created-last",
                "2026-06-01T00:00:00+00:00",
                created_at="2026-06-03T00:00:00+00:00",
            ),
            _chat(
                "updated-last",
                "2026-06-03T00:00:00+00:00",
                created_at="2026-06-01T00:00:00+00:00",
            ),
        ],
    )

    page = await repo.paginate_chats(page=1, page_size=2)

    assert [chat.id for chat in page.items] == [
        "updated-last",
        "created-last",
    ]


async def test_repository_cursor_orders_by_last_update_not_creation() -> None:
    repo = _InMemoryChatRepository(
        [
            _chat(
                "created-last",
                "2026-06-01T00:00:00+00:00",
                created_at="2026-06-03T00:00:00+00:00",
            ),
            _chat(
                "updated-last",
                "2026-06-03T00:00:00+00:00",
                created_at="2026-06-01T00:00:00+00:00",
            ),
        ],
    )

    page = await repo.paginate_chats_cursor(page_size=2)

    assert [chat.id for chat in page.items] == [
        "updated-last",
        "created-last",
    ]


async def test_repository_cursor_uses_id_boundary_for_equal_update_times() -> (
    None
):
    repo = _InMemoryChatRepository(
        [
            _chat("chat-a", "2026-06-03T00:00:00+00:00"),
            _chat("chat-z", "2026-06-03T00:00:00+00:00"),
        ],
    )

    first_page = await repo.paginate_chats_cursor(page_size=1)
    assert [chat.id for chat in first_page.items] == ["chat-z"]
    assert first_page.next_cursor is not None

    second_page = await repo.paginate_chats_cursor(
        page_size=1,
        cursor=first_page.next_cursor,
    )

    assert [chat.id for chat in second_page.items] == ["chat-a"]
    assert second_page.next_cursor is None


async def test_repository_cursor_continues_legacy_creation_time_payload() -> (
    None
):
    repo = _InMemoryChatRepository(
        [
            _chat(
                "page-one",
                "2026-06-01T00:00:00+00:00",
                created_at="2026-06-03T00:00:00+00:00",
            ),
            _chat(
                "omitted-by-recency",
                "2026-06-10T00:00:00+00:00",
                created_at="2026-06-02T00:00:00+00:00",
            ),
            _chat(
                "page-two",
                "2026-06-02T00:00:00+00:00",
                created_at="2026-06-01T00:00:00+00:00",
            ),
        ],
    )
    legacy_cursor = base64.urlsafe_b64encode(
        json.dumps(
            ["2026-06-03T00:00:00+00:00", "page-one"],
            separators=(",", ":"),
        ).encode("utf-8"),
    ).decode("ascii")

    first_legacy_page = await repo.paginate_chats_cursor(
        page_size=1,
        cursor=legacy_cursor,
    )

    assert [chat.id for chat in first_legacy_page.items] == [
        "omitted-by-recency",
    ]
    assert first_legacy_page.next_cursor is not None
    assert json.loads(
        base64.urlsafe_b64decode(first_legacy_page.next_cursor),
    ) == ["2026-06-02T00:00:00+00:00", "omitted-by-recency"]

    second_legacy_page = await repo.paginate_chats_cursor(
        page_size=1,
        cursor=first_legacy_page.next_cursor,
    )

    assert [chat.id for chat in second_legacy_page.items] == ["page-two"]


async def test_manager_exposes_repository_pagination() -> None:
    manager = ChatManager(repo=_InMemoryChatRepository(_stored_chats()))

    page = await manager.list_chats_page(
        user_id="user-1",
        channel="console",
        page=2,
        page_size=2,
    )

    assert [chat.id for chat in page.items] == ["chat-old"]
    assert page.total == 3
    assert page.has_more is False


class _FakeTaskTracker:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def read_status(self, chat_id: str) -> str:
        self.calls.append(chat_id)
        return "running" if chat_id == "chat-z" else "idle"


class _FakeCoordinator:
    def __init__(self, tracker: _FakeTaskTracker) -> None:
        self.tracker = tracker

    async def status(self, chat_id: str) -> TurnStatus | None:
        status = await self.tracker.read_status(chat_id)
        return TurnStatus.RUNNING if status == "running" else None


def _api_client(
    chats: list[ChatSpec] | None = None,
) -> tuple[TestClient, _FakeTaskTracker]:
    manager = ChatManager(
        repo=_InMemoryChatRepository(
            _stored_chats() if chats is None else chats,
        ),
    )
    tracker = _FakeTaskTracker()
    workspace = SimpleNamespace(
        chat_manager=manager,
        task_tracker=tracker,
        answer_turn_coordinator=_FakeCoordinator(tracker),
    )
    app = FastAPI()
    app.include_router(router)

    async def _get_workspace():
        return workspace

    async def _get_chat_manager():
        return manager

    app.dependency_overrides[get_workspace] = _get_workspace
    app.dependency_overrides[get_chat_manager] = _get_chat_manager
    return TestClient(app), tracker


def _agent_scoped_api_client() -> tuple[TestClient, _FakeTaskTracker]:
    manager = ChatManager(repo=_InMemoryChatRepository(_stored_chats()))
    tracker = _FakeTaskTracker()
    workspace = SimpleNamespace(
        chat_manager=manager,
        task_tracker=tracker,
        answer_turn_coordinator=_FakeCoordinator(tracker),
    )
    app = FastAPI()
    app.include_router(create_agent_scoped_router(), prefix="/api")

    async def _get_workspace():
        return workspace

    async def _get_chat_manager():
        return manager

    app.dependency_overrides[get_workspace] = _get_workspace
    app.dependency_overrides[get_chat_manager] = _get_chat_manager
    return TestClient(app), tracker


def test_chat_list_without_pagination_orders_by_last_update() -> None:
    client, tracker = _api_client()

    response = client.get(
        "/chats",
        params={"user_id": "user-1", "channel": "console"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, list)
    assert [chat["id"] for chat in payload] == [
        "chat-z",
        "chat-a",
        "chat-old",
    ]
    assert tracker.calls == ["chat-z", "chat-a", "chat-old"]


def test_chat_list_with_pagination_returns_metadata_and_page_statuses() -> (
    None
):
    client, tracker = _api_client()

    response = client.get(
        "/chats",
        params={
            "user_id": "user-1",
            "channel": "console",
            "page": 1,
            "page_size": 2,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert [chat["id"] for chat in payload["items"]] == ["chat-z", "chat-a"]
    assert payload["items"][0]["status"] == "running"
    assert payload["total"] == 3
    assert payload["page"] == 1
    assert payload["page_size"] == 2
    assert payload["has_more"] is True
    assert tracker.calls == ["chat-z", "chat-a"]


def test_chat_list_supports_best_effort_cursor_pagination() -> None:
    client, tracker = _api_client()

    first_response = client.get(
        "/chats",
        params={"page_size": 2, "cursor": ""},
    )

    assert first_response.status_code == 200
    first_page = first_response.json()
    assert [chat["id"] for chat in first_page["items"]] == [
        "chat-other-channel",
        "chat-other-user",
    ]
    assert first_page["next_cursor"]

    second_response = client.get(
        "/chats",
        params={
            "page_size": 2,
            "cursor": first_page["next_cursor"],
        },
    )

    assert second_response.status_code == 200
    assert [chat["id"] for chat in second_response.json()["items"]] == [
        "chat-z",
        "chat-a",
    ]
    assert tracker.calls == [
        "chat-other-channel",
        "chat-other-user",
        "chat-z",
        "chat-a",
    ]


def test_chat_list_rejects_invalid_cursor() -> None:
    client, tracker = _api_client()

    response = client.get(
        "/chats",
        params={"page_size": 2, "cursor": "not-a-valid-cursor"},
    )

    assert response.status_code == 422
    assert tracker.calls == []


def test_large_chat_history_bounds_page_payload_and_status_lookups() -> None:
    chats = [
        _chat(
            f"chat-{index:04d}",
            "2026-06-10T00:00:00+00:00",
        )
        for index in range(1000)
    ]
    client, tracker = _api_client(chats)

    response = client.get(
        "/chats",
        params={"page": 1, "page_size": 50},
    )

    assert response.status_code == 200
    payload = response.json()
    item_ids = [chat["id"] for chat in payload["items"]]
    assert payload["total"] == 1000
    assert payload["has_more"] is True
    assert len(item_ids) == 50
    assert item_ids[0] == "chat-0999"
    assert item_ids[-1] == "chat-0950"
    assert tracker.calls == item_ids


def test_chat_list_requires_pagination_parameters_together() -> None:
    client, tracker = _api_client()

    response = client.get("/chats", params={"page": 1})

    assert response.status_code == 422
    assert tracker.calls == []


def test_chat_list_validates_minimum_pagination_boundaries() -> None:
    client, _ = _api_client()

    assert (
        client.get(
            "/chats",
            params={"page": 0, "page_size": 20},
        ).status_code
        == 422
    )
    assert (
        client.get(
            "/chats",
            params={"page": 1, "page_size": 0},
        ).status_code
        == 422
    )
    assert (
        client.get(
            "/chats",
            params={"page": 1, "page_size": 501},
        ).status_code
        == 200
    )


def test_agent_scoped_chat_list_supports_pagination() -> None:
    client, tracker = _agent_scoped_api_client()

    response = client.get(
        "/api/agents/agent-a/chats",
        params={
            "user_id": "user-1",
            "channel": "console",
            "page": 2,
            "page_size": 2,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert [chat["id"] for chat in payload["items"]] == ["chat-old"]
    assert payload["total"] == 3
    assert payload["has_more"] is False
    assert tracker.calls == ["chat-old"]
