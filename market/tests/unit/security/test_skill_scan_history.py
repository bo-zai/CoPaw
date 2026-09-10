# -*- coding: utf-8 -*-
"""Market skill scan history persistence tests."""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest


def _unsafe_skill(tmp_path: Path) -> Path:
    skill_dir = tmp_path / "unsafe"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("# Unsafe\n", encoding="utf-8")
    (skill_dir / "run.py").write_text("eval('1 + 1')\n", encoding="utf-8")
    return skill_dir


def test_market_scanner_submits_database_history_context_without_legacy_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from market.security import skill_scanner

    legacy = tmp_path / "swe" / "skill_scanner_blocked.json"
    monkeypatch.setenv("MARKET_SWE_ROOT", str(tmp_path / "swe"))
    submitted = []

    class _Recorder:
        def submit(self, record):
            submitted.append(record)
            return True

    skill_scanner.install_skill_scan_history_recorder(_Recorder())
    try:
        with pytest.raises(skill_scanner.SkillScanError):
            skill_scanner.scan_skill_directory(
                _unsafe_skill(tmp_path),
                skill_name="unsafe",
                block=True,
                source_id="source-a",
                user_id="user-a",
                bbk_id="bbk-a",
            )
    finally:
        skill_scanner.install_skill_scan_history_recorder(None)

    assert not legacy.exists()
    assert len(submitted) == 1
    record = submitted[0]
    assert record.source_id == "source-a"
    assert record.user_id == "user-a"
    assert record.bbk_id == "bbk-a"
    assert datetime.fromisoformat(record.blocked_at).tzinfo is not None


def test_market_scanner_imports_without_swe_package_dependency() -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).parents[3] / "src")

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import market.security.skill_scanner; print('ok')",
        ],
        check=False,
        capture_output=True,
        env=env,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"


@pytest.mark.asyncio
async def test_market_history_writer_inserts_without_managing_schema() -> None:
    from market.security.skill_scanner.history import (
        BlockedSkillRecord,
        MarketSkillScanHistoryWriter,
    )

    class _Db:
        is_connected = True

        def __init__(self) -> None:
            self.queries: list[str] = []
            self.params: list[tuple] = []

        async def execute(self, query: str, params: tuple = ()) -> int:
            self.queries.append(query)
            self.params.append(params)
            return 1

    db = _Db()
    writer = MarketSkillScanHistoryWriter(db)
    record = BlockedSkillRecord(
        skill_name="unsafe",
        blocked_at=datetime.now(timezone.utc).isoformat(),
        max_severity="HIGH",
        source_id="source-a",
        user_id="user-a",
        bbk_id="bbk-a",
    )

    assert writer.submit(record) is True
    await writer.flush()

    assert len(db.queries) == 1
    assert "INSERT INTO swe_skill_scan_history" in db.queries[0]
    assert "CREATE TABLE" not in db.queries[0]
    assert "ALTER TABLE" not in db.queries[0]
    assert db.params[0][-3:] == ("source-a", "user-a", "bbk-a")


@pytest.mark.asyncio
async def test_market_history_writer_flush_does_not_raise_insert_failures() -> (
    None
):
    from market.security.skill_scanner.history import (
        BlockedSkillRecord,
        MarketSkillScanHistoryWriter,
    )

    class _Db:
        is_connected = True

        async def execute(self, query: str, params: tuple = ()) -> int:
            raise RuntimeError("table missing")

    writer = MarketSkillScanHistoryWriter(_Db())

    assert (
        writer.submit(
            BlockedSkillRecord(
                skill_name="unsafe",
                blocked_at=datetime.now(timezone.utc).isoformat(),
                max_severity="HIGH",
            ),
        )
        is True
    )
    await writer.flush()
