# -*- coding: utf-8 -*-
"""Skill scan history API contract tests."""

from __future__ import annotations

import asyncio

from fastapi import FastAPI
from fastapi.testclient import TestClient

from swe.app.routers import config as config_module
from swe.app.routers.config import router
from swe.security.skill_scanner.history import (
    BlockedSkillRecord,
    SkillScanHistoryPage,
)


class _Store:
    def __init__(self, *, available: bool = True) -> None:
        self.is_available = available
        self.list_calls: list[tuple[int, int, str]] = []
        self.warning_calls: list[tuple[str, str]] = []
        self.deleted: list[str] = []
        self.cleared = False

    async def list_page(self, *, page: int, page_size: int, source_id: str):
        self.list_calls.append((page, page_size, source_id))
        return SkillScanHistoryPage(
            items=[
                BlockedSkillRecord(
                    id="record-1",
                    skill_name="unsafe-skill",
                    blocked_at="2026-08-03T08:00:00+00:00",
                    max_severity="HIGH",
                    findings=[],
                    action="blocked",
                    source_id="source-a",
                    user_id="user-a",
                    bbk_id="bbk-a",
                ),
            ],
            total=5000,
            page=page,
            page_size=page_size,
        )

    async def delete(self, record_id: str) -> bool:
        self.deleted.append(record_id)
        return record_id == "record-1"

    async def get_latest_warning(self, skill_name: str, *, since: str):
        self.warning_calls.append((skill_name, since))
        if skill_name == "safe-skill":
            return None
        return BlockedSkillRecord(
            id="warning-1",
            skill_name=skill_name,
            blocked_at="2026-08-03T09:00:00+00:00",
            max_severity="HIGH",
            findings=[],
            action="warned",
            source_id="source-a",
            user_id="user-a",
            bbk_id="bbk-a",
        )

    async def clear(self) -> None:
        self.cleared = True


def _client(store: _Store | None) -> TestClient:
    app = FastAPI()
    app.state.skill_scan_history_store = store
    app.include_router(router)
    return TestClient(app)


def test_history_route_returns_requested_database_page():
    store = _Store()
    response = _client(store).get(
        "/config/security/skill-scanner/blocked-history?page=2&page_size=10",
        headers={"X-Source-Id": "source-a"},
    )

    assert response.status_code == 200
    assert store.list_calls == [(2, 10, "source-a")]
    assert response.json() == {
        "items": [
            {
                "id": "record-1",
                "skill_name": "unsafe-skill",
                "blocked_at": "2026-08-03T08:00:00+00:00",
                "max_severity": "HIGH",
                "findings": [],
                "content_hash": "",
                "action": "blocked",
                "source_id": "source-a",
                "user_id": "user-a",
                "bbk_id": "bbk-a",
            },
        ],
        "total": 5000,
        "page": 2,
        "page_size": 10,
    }


def test_history_route_defaults_and_validates_page_size():
    store = _Store()
    client = _client(store)

    assert (
        client.get(
            "/config/security/skill-scanner/blocked-history",
            headers={"X-Source-Id": "source-a"},
        ).status_code
        == 200
    )
    assert store.list_calls == [(1, 20, "source-a")]
    assert (
        client.get(
            "/config/security/skill-scanner/blocked-history?page_size=9",
            headers={"X-Source-Id": "source-a"},
        ).status_code
        == 422
    )
    assert (
        client.get(
            "/config/security/skill-scanner/blocked-history?page_size=101",
            headers={"X-Source-Id": "source-a"},
        ).status_code
        == 422
    )


def test_latest_warning_route_queries_only_the_requested_skill():
    store = _Store()
    client = _client(store)
    path = "/config/security/skill-scanner/blocked-history/latest-warning"

    since = "2026-08-03T08:30:00+00:00"
    response = client.get(
        path,
        params={"skill_name": "unsafe-skill", "since": since},
    )
    missing = client.get(
        path,
        params={"skill_name": "safe-skill", "since": since},
    )

    assert response.status_code == 200
    assert response.json()["id"] == "warning-1"
    assert response.json()["skill_name"] == "unsafe-skill"
    assert missing.status_code == 200
    assert missing.json() is None
    assert store.warning_calls == [
        ("unsafe-skill", since),
        ("safe-skill", since),
    ]


def test_warning_cursor_uses_server_utc_time():
    response = _client(_Store()).get(
        "/config/security/skill-scanner/warning-cursor",
    )

    assert response.status_code == 200
    cursor = response.json()["cursor"]
    assert cursor.endswith("+00:00")


def test_history_routes_return_503_when_store_is_unavailable():
    client = _client(_Store(available=False))
    path = "/config/security/skill-scanner/blocked-history"

    assert (
        client.get(path, headers={"X-Source-Id": "source-a"}).status_code
        == 503
    )
    assert (
        client.get(
            f"{path}/latest-warning",
            params={
                "skill_name": "unsafe-skill",
                "since": "2026-08-03T08:30:00+00:00",
            },
            headers={"X-Source-Id": "source-a"},
        ).status_code
        == 503
    )
    assert client.delete(path).status_code == 503
    assert client.delete(f"{path}/record-1").status_code == 503


def test_history_delete_uses_stable_id_and_clear_uses_database():
    store = _Store()
    client = _client(store)
    path = "/config/security/skill-scanner/blocked-history"

    removed = client.delete(f"{path}/record-1")
    missing = client.delete(f"{path}/missing")
    cleared = client.delete(path)

    assert removed.status_code == 200
    assert missing.status_code == 404
    assert store.deleted == ["record-1", "missing"]
    assert cleared.status_code == 200
    assert store.cleared is True


def test_history_route_returns_503_when_recorder_flush_times_out(
    monkeypatch,
):
    class _StalledRecorder:
        async def flush(self) -> None:
            await asyncio.Event().wait()

    app = FastAPI()
    app.state.skill_scan_history_store = _Store()
    app.state.skill_scan_history_recorder = _StalledRecorder()
    app.include_router(router)
    monkeypatch.setattr(
        config_module,
        "_SKILL_SCAN_HISTORY_FLUSH_TIMEOUT_SECONDS",
        0.01,
    )

    response = TestClient(app).get(
        "/config/security/skill-scanner/blocked-history",
        headers={"X-Source-Id": "source-a"},
    )

    assert response.status_code == 503
    assert "Timed out" in response.json()["detail"]
