# -*- coding: utf-8 -*-
"""Database-backed skill scan history tests."""

from __future__ import annotations

import asyncio
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from swe.security import skill_scanner
from swe.security.skill_scanner import history as history_module
from swe.security.skill_scanner.history import (
    BlockedSkillRecord,
    SkillScanHistoryRecorder,
    SkillScanHistoryStore,
    SkillScanHistoryStoreUnavailable,
)
from swe.security.skill_scanner.models import (
    Finding,
    ScanResult,
    Severity,
    ThreatCategory,
)


def _record(record_id: str = "record-1") -> BlockedSkillRecord:
    return BlockedSkillRecord(
        id=record_id,
        skill_name="unsafe-skill",
        blocked_at="2026-08-03T08:00:00+00:00",
        max_severity="HIGH",
        findings=[
            {
                "severity": "HIGH",
                "title": "Unsafe command",
                "description": "Runs an unsafe command",
                "file_path": "SKILL.md",
                "line_number": 3,
                "rule_id": "RULE-1",
            },
        ],
        content_hash="a" * 64,
        action="blocked",
        source_id="source-a",
        user_id="user-a",
        bbk_id="bbk-a",
    )


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.is_connected = True
    db.execute = AsyncMock(return_value=1)
    db.fetch_one = AsyncMock(return_value={"total": 0})
    db.fetch_all = AsyncMock(return_value=[])
    return db


@pytest.mark.asyncio
async def test_store_initialization_does_not_manage_database_schema(mock_db):
    store = SkillScanHistoryStore(mock_db)

    await store.initialize()

    mock_db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_store_round_trips_insert_and_bounded_page(mock_db):
    store = SkillScanHistoryStore(mock_db)
    record = _record()
    mock_db.fetch_one.return_value = {"total": 21}
    mock_db.fetch_all.return_value = [
        {
            "id": record.id,
            "skill_name": record.skill_name,
            "blocked_at": datetime(2026, 8, 3, 8, 0, 0),
            "max_severity": record.max_severity,
            "findings_json": json.dumps(record.findings),
            "content_hash": record.content_hash,
            "action": record.action,
            "source_id": record.source_id,
            "user_id": record.user_id,
            "bbk_id": record.bbk_id,
        },
    ]

    await store.insert(record)
    page = await store.list_page(page=2, page_size=10, source_id="source-a")

    insert_query, insert_params = mock_db.execute.await_args_list[-1].args
    assert "INSERT INTO swe_skill_scan_history" in insert_query
    assert insert_params[0] == record.id
    assert insert_params[-3:] == (
        record.source_id,
        record.user_id,
        record.bbk_id,
    )
    assert page.total == 21
    assert page.page == 2
    assert page.page_size == 10
    assert page.items[0].id == record.id
    assert page.items[0].source_id == "source-a"
    assert page.items[0].user_id == "user-a"
    assert page.items[0].bbk_id == "bbk-a"
    assert page.items[0].blocked_at == "2026-08-03T08:00:00+00:00"
    query, params = mock_db.fetch_all.await_args.args
    assert "ORDER BY blocked_at DESC, id DESC" in query
    assert "LIMIT %s OFFSET %s" in query
    assert params == ("source-a", 10, 10)


@pytest.mark.asyncio
async def test_store_queries_latest_warning_for_one_skill(mock_db):
    record = _record("latest-warning")
    mock_db.fetch_one.return_value = {
        "id": record.id,
        "skill_name": record.skill_name,
        "blocked_at": datetime(2026, 8, 3, 8, 0, 0),
        "max_severity": record.max_severity,
        "findings_json": json.dumps(record.findings),
        "content_hash": record.content_hash,
        "action": "warned",
        "source_id": record.source_id,
        "user_id": record.user_id,
        "bbk_id": record.bbk_id,
    }
    store = SkillScanHistoryStore(mock_db)

    warning = await store.get_latest_warning(
        record.skill_name,
        since="2026-08-03T07:59:00+00:00",
    )

    assert warning is not None
    assert warning.id == "latest-warning"
    assert warning.source_id == "source-a"
    assert warning.user_id == "user-a"
    assert warning.bbk_id == "bbk-a"
    query, params = mock_db.fetch_one.await_args.args
    assert "WHERE skill_name = %s AND action = 'warned'" in query
    assert "blocked_at >= %s" in query
    assert "ORDER BY blocked_at DESC, id DESC" in query
    assert "LIMIT 1" in query
    assert params == (
        record.skill_name,
        datetime(2026, 8, 3, 7, 59, 0),
    )


@pytest.mark.asyncio
async def test_store_delete_clear_and_unavailable_behavior(mock_db):
    store = SkillScanHistoryStore(mock_db)

    assert await store.delete("record-1") is True
    await store.clear()

    assert "WHERE id = %s" in mock_db.execute.await_args_list[0].args[0]
    assert mock_db.execute.await_args_list[0].args[1] == ("record-1",)
    assert "DELETE FROM swe_skill_scan_history" in (
        mock_db.execute.await_args_list[1].args[0]
    )

    unavailable = SkillScanHistoryStore(None)
    with pytest.raises(SkillScanHistoryStoreUnavailable):
        await unavailable.list_page(
            page=1,
            page_size=20,
            source_id="source-a",
        )


class _RecordingStore:
    def __init__(self, *, fail: bool = False) -> None:
        self.records: list[BlockedSkillRecord] = []
        self.fail = fail

    async def insert(self, record: BlockedSkillRecord) -> None:
        if self.fail:
            raise RuntimeError("database down")
        self.records.append(record)


class _GatedRecordingStore:
    def __init__(self) -> None:
        self.started: dict[str, asyncio.Event] = {}
        self.releases: dict[str, asyncio.Event] = {}
        self.records: list[BlockedSkillRecord] = []

    async def insert(self, record: BlockedSkillRecord) -> None:
        started = self.started.setdefault(record.id, asyncio.Event())
        release = self.releases.setdefault(record.id, asyncio.Event())
        started.set()
        await release.wait()
        self.records.append(record)


@pytest.mark.asyncio
async def test_recorder_accepts_loop_and_worker_thread_submissions():
    store = _RecordingStore()
    recorder = SkillScanHistoryRecorder(store, queue_size=10)
    await recorder.start()

    assert recorder.submit(_record("loop-record")) is True
    assert (
        await asyncio.to_thread(
            recorder.submit,
            _record("thread-record"),
        )
        is True
    )
    await asyncio.sleep(0)
    await recorder.flush()
    assert [record.id for record in store.records] == [
        "loop-record",
        "thread-record",
    ]
    await recorder.stop()

    assert [record.id for record in store.records] == [
        "loop-record",
        "thread-record",
    ]


@pytest.mark.asyncio
async def test_flush_and_stop_wait_for_acknowledged_worker_submission():
    store = _RecordingStore()
    recorder = SkillScanHistoryRecorder(store, queue_size=10)
    await recorder.start()
    accepted: list[bool] = []

    thread = threading.Thread(
        target=lambda: accepted.append(
            recorder.submit(_record("thread-race")),
        ),
    )
    thread.start()
    thread.join()

    await recorder.flush()
    assert accepted == [True]
    assert [record.id for record in store.records] == ["thread-race"]
    await recorder.stop()
    assert [record.id for record in store.records] == ["thread-race"]


@pytest.mark.asyncio
async def test_flush_fence_is_not_extended_by_later_submissions():
    store = _GatedRecordingStore()
    recorder = SkillScanHistoryRecorder(store, queue_size=10)
    await recorder.start()

    assert recorder.submit(_record("before-flush")) is True
    while "before-flush" not in store.started:
        await asyncio.sleep(0)
    await store.started["before-flush"].wait()

    flush_task = asyncio.create_task(recorder.flush())
    await asyncio.sleep(0)
    assert recorder.submit(_record("after-flush")) is True

    store.releases["before-flush"].set()
    await asyncio.wait_for(flush_task, timeout=0.5)
    while "after-flush" not in store.started:
        await asyncio.sleep(0)
    assert not store.releases["after-flush"].is_set()

    store.releases["after-flush"].set()
    await recorder.stop()
    assert [record.id for record in store.records] == [
        "before-flush",
        "after-flush",
    ]


@pytest.mark.asyncio
async def test_recorder_logs_write_failure_without_raising(monkeypatch):
    log_error = MagicMock()
    monkeypatch.setattr(history_module.logger, "error", log_error)
    recorder = SkillScanHistoryRecorder(
        _RecordingStore(fail=True),
        queue_size=10,
    )
    await recorder.start()
    assert recorder.submit(_record()) is True

    await recorder.stop()

    assert log_error.call_args.args[0] == (
        "Failed to persist skill scan history"
    )


@pytest.mark.asyncio
async def test_recorder_rejects_when_bounded_queue_is_full():
    store = _RecordingStore()
    recorder = SkillScanHistoryRecorder(store, queue_size=1)
    await recorder.start()

    assert recorder.submit(_record("first")) is True
    assert recorder.submit(_record("overflow")) is False
    await recorder.stop()

    assert [record.id for record in store.records] == ["first"]


def test_scanner_preserves_result_when_recorder_is_absent(monkeypatch):
    log_error = MagicMock()
    monkeypatch.setattr(skill_scanner.logger, "error", log_error)
    skill_scanner.install_skill_scan_history_recorder(None)
    result = ScanResult(
        skill_name="unsafe-skill",
        skill_directory="/tmp/unsafe-skill",
    )

    skill_scanner._record_blocked_skill(result, Path("/missing"))

    assert "recorder is unavailable" in log_error.call_args.args[0]


def test_scanner_submits_history_without_touching_legacy_json(
    tmp_path: Path,
) -> None:
    legacy = tmp_path / "skill_scanner_blocked.json"
    legacy.write_text('[{"legacy": true}]', encoding="utf-8")
    skill_dir = tmp_path / "unsafe-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("unsafe", encoding="utf-8")
    submitted: list[BlockedSkillRecord] = []

    class _Recorder:
        def submit(self, record: BlockedSkillRecord) -> bool:
            submitted.append(record)
            return True

    result = ScanResult(
        skill_name="unsafe-skill",
        skill_directory=str(skill_dir),
        findings=[
            Finding(
                id="finding-1",
                rule_id="RULE-1",
                category=ThreatCategory.COMMAND_INJECTION,
                severity=Severity.HIGH,
                title="Unsafe command",
                description="Runs an unsafe command",
            ),
        ],
    )

    skill_scanner.install_skill_scan_history_recorder(_Recorder())
    try:
        skill_scanner._record_blocked_skill(result, skill_dir)
    finally:
        skill_scanner.install_skill_scan_history_recorder(None)

    assert len(submitted) == 1
    assert submitted[0].skill_name == "unsafe-skill"
    assert legacy.read_text(encoding="utf-8") == '[{"legacy": true}]'
