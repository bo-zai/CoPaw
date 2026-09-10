# -*- coding: utf-8 -*-
"""Market scan history writer for the shared SWE database table."""

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


@dataclass(frozen=True)
class BlockedSkillRecord:
    """Market-facing blocked record using the shared SWE table fields."""

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


class MarketSkillScanHistoryWriter:
    """Write Market scan alerts into ``swe_skill_scan_history``."""

    def __init__(self, db: Any) -> None:
        self._db = db
        try:
            self._loop: asyncio.AbstractEventLoop | None = (
                asyncio.get_running_loop()
            )
        except RuntimeError:
            self._loop = None
        self._pending: set[asyncio.Future[None]] = set()
        self._lock = threading.Lock()

    def submit(self, record: BlockedSkillRecord) -> bool:
        """Schedule one insert on the current event loop."""
        if self._db is None or not getattr(self._db, "is_connected", False):
            logger.error("Market skill scan history database is unavailable")
            return False
        loop = self._loop
        if loop is None or loop.is_closed():
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                logger.error(
                    "Market skill scan history requires an event loop",
                )
                return False
            self._loop = loop

        if loop.is_closed():
            return False

        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None
        if current_loop is loop:
            self._schedule(loop, record)
        else:
            loop.call_soon_threadsafe(self._schedule, loop, record)
        return True

    async def flush(self) -> None:
        """Wait for all records accepted before this call."""
        await asyncio.sleep(0)
        with self._lock:
            pending = list(self._pending)
        if not pending:
            return
        await asyncio.gather(*pending, return_exceptions=True)

    def _forget(self, future: asyncio.Future[None]) -> None:
        with self._lock:
            self._pending.discard(future)
        if future.cancelled():
            return
        try:
            future.result()
        except Exception:
            logger.error(
                "Failed to persist Market skill scan history",
                exc_info=True,
            )

    def _schedule(
        self,
        loop: asyncio.AbstractEventLoop,
        record: BlockedSkillRecord,
    ) -> None:
        future = loop.create_task(self._insert(record))
        with self._lock:
            self._pending.add(future)
        future.add_done_callback(self._forget)

    async def _insert(self, record: BlockedSkillRecord) -> None:
        await self._db.execute(
            """
            INSERT INTO swe_skill_scan_history (
                id, skill_name, blocked_at, max_severity,
                findings_json, content_hash, action,
                source_id, user_id, bbk_id
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
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


def _to_database_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed
