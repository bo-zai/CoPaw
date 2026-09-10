# -*- coding: utf-8 -*-
"""Database-backed persistence for skill scanner alert history."""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

_TABLE = "swe_skill_scan_history"
_STOP = object()


class SkillScanHistoryStoreUnavailable(RuntimeError):
    """Raised when scan history requires an unavailable database store."""


@dataclass(frozen=True)
class BlockedSkillRecord:
    """A blocked or warned skill scan alert."""

    skill_name: str
    blocked_at: str
    max_severity: str
    findings: list[dict[str, Any]] = field(default_factory=list)
    content_hash: str = ""
    action: str = "blocked"
    source_id: str = ""
    user_id: str = ""
    bbk_id: str = ""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self) -> dict[str, Any]:
        """Return the stable API representation."""
        return {
            "id": self.id,
            "skill_name": self.skill_name,
            "blocked_at": self.blocked_at,
            "max_severity": self.max_severity,
            "findings": self.findings,
            "content_hash": self.content_hash,
            "action": self.action,
            "source_id": self.source_id,
            "user_id": self.user_id,
            "bbk_id": self.bbk_id,
        }


@dataclass(frozen=True)
class SkillScanHistoryPage:
    """One bounded page of scan history."""

    items: list[BlockedSkillRecord]
    total: int
    page: int
    page_size: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "items": [item.to_dict() for item in self.items],
            "total": self.total,
            "page": self.page,
            "page_size": self.page_size,
        }


@dataclass(frozen=True)
class _QueuedRecord:
    sequence: int
    record: BlockedSkillRecord


class SkillScanHistoryStore:
    """Async MySQL-compatible scan history store."""

    def __init__(self, db: Any | None = None) -> None:
        self.db = db

    @property
    def is_available(self) -> bool:
        return self.db is not None and bool(
            getattr(self.db, "is_connected", False),
        )

    def _require_available(self) -> None:
        if not self.is_available:
            raise SkillScanHistoryStoreUnavailable(
                "Skill scan history database is unavailable",
            )

    async def initialize(self) -> None:
        """Validate that the externally-managed history store is available."""
        self._require_available()

    async def insert(self, record: BlockedSkillRecord) -> None:
        """Persist one scan alert."""
        self._require_available()
        await self.db.execute(
            _INSERT_RECORD,
            (
                record.id,
                record.skill_name,
                _to_database_datetime(record.blocked_at),
                record.max_severity,
                json.dumps(record.findings, ensure_ascii=False),
                record.content_hash,
                record.action,
                record.source_id,
                record.user_id,
                record.bbk_id,
            ),
        )

    async def list_page(
        self,
        *,
        page: int,
        page_size: int,
        source_id: str,
    ) -> SkillScanHistoryPage:
        """Return one newest-first page and the total record count."""
        self._require_available()
        try:
            count_row = await self.db.fetch_one(
                _COUNT_RECORDS_BY_SOURCE,
                (source_id,),
            )
            total = int(count_row.get("total", 0)) if count_row else 0
            offset = (page - 1) * page_size
            rows = await self.db.fetch_all(
                _LIST_RECORDS_BY_SOURCE,
                (source_id, page_size, offset),
            )
        except Exception as exc:
            raise SkillScanHistoryStoreUnavailable(
                "Skill scan history database query failed",
            ) from exc
        return SkillScanHistoryPage(
            items=[_row_to_record(row) for row in rows],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def delete(self, record_id: str) -> bool:
        """Delete exactly one record by stable ID."""
        self._require_available()
        try:
            affected = await self.db.execute(_DELETE_RECORD, (record_id,))
        except Exception as exc:
            raise SkillScanHistoryStoreUnavailable(
                "Skill scan history database delete failed",
            ) from exc
        return affected > 0

    async def get_latest_warning(
        self,
        skill_name: str,
        *,
        since: str,
    ) -> BlockedSkillRecord | None:
        """Return the newest warned record for one skill after a cursor."""
        self._require_available()
        try:
            row = await self.db.fetch_one(
                _GET_LATEST_WARNING,
                (skill_name, _to_database_datetime(since)),
            )
        except Exception as exc:
            raise SkillScanHistoryStoreUnavailable(
                "Skill scan history database query failed",
            ) from exc
        return _row_to_record(row) if row else None

    async def clear(self) -> None:
        """Delete all scan history records."""
        self._require_available()
        try:
            await self.db.execute(_CLEAR_RECORDS)
        except Exception as exc:
            raise SkillScanHistoryStoreUnavailable(
                "Skill scan history database clear failed",
            ) from exc


class SkillScanHistoryRecorder:
    """Bridge synchronous scanner calls to one async database writer."""

    def __init__(
        self,
        store: Any,
        *,
        queue_size: int = 1000,
    ) -> None:
        self._store = store
        self._queue_size = queue_size
        self._queue: asyncio.Queue[object] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._worker: asyncio.Task[None] | None = None
        self._accepting = False
        self._state_lock = threading.Lock()
        self._outstanding = 0
        self._accepted_sequence = 0
        self._completed_through = 0
        self._completed_out_of_order: set[int] = set()
        self._progress: asyncio.Event | None = None

    async def start(self) -> None:
        """Bind the recorder to the current application event loop."""
        if self._worker is not None:
            return
        self._loop = asyncio.get_running_loop()
        self._queue = asyncio.Queue(maxsize=self._queue_size)
        self._progress = asyncio.Event()
        with self._state_lock:
            self._accepting = True
            self._outstanding = 0
            self._accepted_sequence = 0
            self._completed_through = 0
            self._completed_out_of_order.clear()
        self._worker = asyncio.create_task(
            self._consume(),
            name="skill-scan-history-recorder",
        )

    def submit(self, record: BlockedSkillRecord) -> bool:
        """Submit from the application loop or any worker thread."""
        with self._state_lock:
            loop = self._loop
            queue = self._queue
            if (
                not self._accepting
                or loop is None
                or queue is None
                or loop.is_closed()
            ):
                return False
            if self._outstanding >= self._queue_size:
                logger.error(
                    "Skill scan history queue is full; record %s was dropped",
                    record.id,
                )
                return False
            self._outstanding += 1
            self._accepted_sequence += 1
            sequence = self._accepted_sequence

        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None

        if current_loop is loop:
            return self._enqueue_reserved(sequence, record)

        try:
            loop.call_soon_threadsafe(
                self._enqueue_reserved,
                sequence,
                record,
            )
            return True
        except RuntimeError:
            self._release_reserved(sequence)
            return False

    async def stop(self) -> None:
        """Stop accepting records and drain accepted work."""
        worker = self._worker
        queue = self._queue
        if worker is None or queue is None:
            with self._state_lock:
                self._accepting = False
            return

        with self._state_lock:
            self._accepting = False
        try:
            await self.flush()
            await queue.put(_STOP)
            await worker
        except asyncio.CancelledError:
            worker.cancel()
            try:
                await worker
            except asyncio.CancelledError:
                pass
            raise
        finally:
            self._worker = None
            self._queue = None
            self._loop = None
            self._progress = None
            with self._state_lock:
                self._outstanding = 0
                self._completed_out_of_order.clear()

    async def flush(self) -> None:
        """Wait for records accepted through this call's sequence fence."""
        with self._state_lock:
            target_sequence = self._accepted_sequence
            progress = self._progress
        if progress is None:
            return

        while True:
            progress.clear()
            with self._state_lock:
                if self._completed_through >= target_sequence:
                    return
                if self._progress is not progress:
                    return
            await progress.wait()

    def _enqueue_reserved(
        self,
        sequence: int,
        record: BlockedSkillRecord,
    ) -> bool:
        queue = self._queue
        if queue is None:
            self._release_reserved(sequence)
            return False
        try:
            queue.put_nowait(_QueuedRecord(sequence, record))
            return True
        except asyncio.QueueFull:
            logger.error(
                "Skill scan history queue is full; record %s was dropped",
                record.id,
            )
            self._release_reserved(sequence)
            return False

    def _release_reserved(self, sequence: int) -> None:
        with self._state_lock:
            if self._outstanding > 0:
                self._outstanding -= 1
            if sequence == self._completed_through + 1:
                self._completed_through = sequence
                while self._completed_through + 1 in (
                    self._completed_out_of_order
                ):
                    self._completed_out_of_order.remove(
                        self._completed_through + 1,
                    )
                    self._completed_through += 1
            elif sequence > self._completed_through:
                self._completed_out_of_order.add(sequence)
            progress = self._progress
            loop = self._loop

        if progress is None or loop is None or loop.is_closed():
            return
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None
        if current_loop is loop:
            progress.set()
        else:
            try:
                loop.call_soon_threadsafe(progress.set)
            except RuntimeError:
                return

    async def _consume(self) -> None:
        queue = self._queue
        if queue is None:
            return
        while True:
            item = await queue.get()
            try:
                if item is _STOP:
                    return
                if not isinstance(item, _QueuedRecord):
                    logger.error("Invalid skill scan history queue item")
                    continue
                try:
                    await self._store.insert(item.record)
                except Exception:
                    logger.error(
                        "Failed to persist skill scan history",
                        exc_info=True,
                    )
            finally:
                queue.task_done()
                if isinstance(item, _QueuedRecord):
                    self._release_reserved(item.sequence)


def _to_database_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _to_api_datetime(value: Any) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        else:
            value = value.astimezone(timezone.utc)
        return value.isoformat()
    return str(value)


def _row_to_record(row: dict[str, Any]) -> BlockedSkillRecord:
    try:
        findings = json.loads(row.get("findings_json") or "[]")
    except (TypeError, ValueError, json.JSONDecodeError):
        findings = []
    if not isinstance(findings, list):
        findings = []
    return BlockedSkillRecord(
        id=str(row["id"]),
        skill_name=str(row.get("skill_name") or ""),
        blocked_at=_to_api_datetime(row.get("blocked_at") or ""),
        max_severity=str(row.get("max_severity") or ""),
        findings=findings,
        content_hash=str(row.get("content_hash") or ""),
        action=str(row.get("action") or "blocked"),
        source_id=str(row.get("source_id") or ""),
        user_id=str(row.get("user_id") or ""),
        bbk_id=str(row.get("bbk_id") or ""),
    )


_INSERT_RECORD = f"""
    INSERT INTO {_TABLE} (
        id, skill_name, blocked_at, max_severity,
        findings_json, content_hash, action,
        source_id, user_id, bbk_id
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

_COUNT_RECORDS_BY_SOURCE = f"""
    SELECT COUNT(*) AS total FROM {_TABLE}
    WHERE source_id = %s
"""

_GET_LATEST_WARNING = f"""
    SELECT
        id, skill_name, blocked_at, max_severity,
        findings_json, content_hash, action, source_id, user_id, bbk_id
    FROM {_TABLE}
    WHERE skill_name = %s AND action = 'warned' AND blocked_at >= %s
    ORDER BY blocked_at DESC, id DESC
    LIMIT 1
"""

_LIST_RECORDS_BY_SOURCE = f"""
    SELECT id, skill_name, blocked_at, max_severity,
           findings_json, content_hash, action, source_id, user_id, bbk_id
    FROM {_TABLE}
    WHERE source_id = %s
    ORDER BY blocked_at DESC, id DESC
    LIMIT %s OFFSET %s
"""

_DELETE_RECORD = f"DELETE FROM {_TABLE} WHERE id = %s"
_CLEAR_RECORDS = f"DELETE FROM {_TABLE}"
