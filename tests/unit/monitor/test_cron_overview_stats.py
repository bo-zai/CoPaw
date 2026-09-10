# -*- coding: utf-8 -*-
"""定时任务概览统计测试。"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from monitor.app.services.cron.query_service import QueryService


@pytest.mark.asyncio
async def test_get_overview_stats_includes_report_metrics(monkeypatch):
    """概览统计应返回查看方案及按钮行为指标。"""
    service = QueryService()
    mock_db = MagicMock()
    monkeypatch.setattr(
        "monitor.app.services.cron.query_service.get_db_connection",
        lambda: mock_db,
    )

    service._fetch_overview_task_count = AsyncMock(return_value=20)
    service._fetch_overview_branch_tenant_counts = AsyncMock(
        return_value=(12, 86),
    )
    service._fetch_overview_execution_counts = AsyncMock(
        return_value={
            "total_executions": 2480,
            "executed_job_count": 100,
            "success_count": 2112,
            "running_count": 24,
            "error_count": 154,
        },
    )
    service._fetch_overview_read_tasks = AsyncMock(return_value=61)
    service._fetch_overview_report_behavior_counts = AsyncMock(
        return_value={
            "report_count": 35,
            "insight_count": 12,
            "phone_count": 5,
        },
    )
    service._fetch_overview_new_cron_tasks = AsyncMock(return_value=3)

    result = await service.get_overview_stats(
        start_date="2026-06-01",
        end_date="2026-06-30",
    )

    assert result.read_rate == 2.46
    assert result.report_rate == 1.41
    assert result.report_count == 35
    assert result.insight_count == 12
    assert result.phone_count == 5


@pytest.mark.asyncio
async def test_fetch_overview_report_behavior_counts_reads_directly_from_click_events():
    """概览卡片的查看方案/洞察/电访任务数应直接来自 HTML 点击表。"""
    db = MagicMock()
    db.fetch_one = AsyncMock(
        return_value={
            "report_count": 8,
            "insight_count": 3,
            "phone_count": 1,
        },
    )
    service = QueryService()

    result = await service._fetch_overview_report_behavior_counts(
        db=db,
        start_time=MagicMock(),
        end_time=MagicMock(),
        bbk_filter_sql=" AND j.bbk_id IN (%s, %s)",
        bbk_filter_params=["100", "V00"],
        source_filter_sql=" AND j.source_id = %s",
        source_filter_params=["src-1"],
    )

    click_sql, click_params = db.fetch_one.await_args.args

    assert "FROM swe_html_preview_click_events c" in click_sql
    assert "COUNT(DISTINCT CASE" in click_sql
    assert "WHEN c.button_type = 'plan' THEN c.cron_task_id" in click_sql
    assert "WHEN c.button_type = 'insight' THEN c.cron_task_id" in click_sql
    assert "WHEN c.button_type = 'phone' THEN c.cron_task_id" in click_sql
    assert "c.clicked_at >= %s AND c.clicked_at <= %s" in click_sql
    assert "c.event_type = 'button_click'" in click_sql
    assert "AND c.bbk_id IN (%s, %s)" in click_sql
    assert "AND c.source_id = %s" in click_sql
    assert list(click_params[2:]) == ["100", "V00", "src-1"]

    assert result == {"report_count": 8, "insight_count": 3, "phone_count": 1}


@pytest.mark.asyncio
async def test_fetch_overview_read_tasks_counts_read_executions():
    """任务已读数应按已读执行次数统计，不再按任务去重。"""
    db = MagicMock()
    db.fetch_one = AsyncMock(return_value={"read_tasks": 9})
    service = QueryService()

    result = await service._fetch_overview_read_tasks(
        db=db,
        start_time=MagicMock(),
        end_time=MagicMock(),
        bbk_filter_sql="",
        bbk_filter_params=[],
        source_filter_sql="",
        source_filter_params=[],
    )

    sql, _ = db.fetch_one.await_args.args
    assert "COUNT(*) AS read_tasks" in sql
    assert "COUNT(DISTINCT e.job_id)" not in sql
    assert result == 9


@pytest.mark.asyncio
async def test_fetch_branch_click_counts_reads_directly_from_click_events():
    """分行按钮点击统计应直接来自 HTML 点击表。"""
    db = MagicMock()
    db.fetch_all = AsyncMock(
        return_value=[
            {
                "bbk_id": "100",
                "button_type": "plan",
                "task_count": 6,
                "total_clicks": 9,
            },
        ],
    )
    service = QueryService()

    result = await service._fetch_branch_click_counts(
        db=db,
        start_time=MagicMock(),
        end_time=MagicMock(),
        source_id="src-1",
    )

    sql, params = db.fetch_all.await_args.args

    assert "FROM swe_html_preview_click_events" in sql
    assert "COUNT(DISTINCT cron_task_id) AS task_count" in sql
    assert "COUNT(*) AS total_clicks" in sql
    assert "clicked_at >= %s AND clicked_at <= %s" in sql
    assert "event_type = 'button_click'" in sql
    assert "cron_task_id IS NOT NULL" in sql
    assert "bbk_id IS NOT NULL" in sql
    assert "bbk_id != ''" in sql
    assert params[-1] == "src-1"
    assert result == {
        "100": {
            "plan": {
                "task_count": 6,
                "total_clicks": 9,
            },
        },
    }


@pytest.mark.asyncio
async def test_fetch_branch_execution_stats_counts_read_executions():
    """分行综合排行的已读任务数应按已读执行次数统计，不再按任务去重。"""
    db = MagicMock()
    db.fetch_one = AsyncMock(
        return_value={
            "total_executions": 12,
            "success_count": 8,
            "read_tasks": 5,
            "error_count": 2,
        },
    )
    service = QueryService()

    result = await service._fetch_branch_execution_stats(
        db=db,
        start_time=MagicMock(),
        end_time=MagicMock(),
        job_ids=["job-1", "job-2"],
    )

    sql, _ = db.fetch_one.await_args.args
    assert "SUM(CASE WHEN is_read = 1 THEN 1 ELSE 0 END) AS read_tasks" in sql
    assert "COUNT(DISTINCT CASE WHEN is_read = 1 THEN job_id END)" not in sql
    assert result["read_tasks"] == 5


@pytest.mark.asyncio
async def test_fetch_manager_click_stats_matches_skill_view_click_scope():
    """客户经理明细的客户数统计不应额外限制点击必须落在执行窗口内。"""
    db = MagicMock()
    db.fetch_all = AsyncMock(
        return_value=[
            {
                "user_id": "u-1",
                "button_type": "plan",
                "customer_count": 4,
            },
        ],
    )
    service = QueryService()

    result = await service._fetch_manager_click_stats(
        db=db,
        bbk_id="100",
        start_time=MagicMock(),
        end_time=MagicMock(),
        source_id="src-1",
    )

    sql, params = db.fetch_all.await_args.args
    assert "FROM swe_html_preview_click_events c" in sql
    assert "JOIN swe_cron_jobs j ON c.cron_task_id = j.id" in sql
    assert "c.clicked_at >= e.actual_time" not in sql
    assert "c.clicked_at <= COALESCE(e.end_time" not in sql
    assert "c.event_type = 'button_click'" in sql
    assert params[-1] == "src-1"
    assert result == {"u-1": {"plan": 4}}


@pytest.mark.asyncio
async def test_fetch_branch_manager_click_counts_filters_button_click_only():
    """分行客户经理点击统计应只统计按钮点击事件。"""
    db = MagicMock()
    db.fetch_all = AsyncMock(
        return_value=[
            {
                "button_type": "plan",
                "manager_count": 2,
            },
        ],
    )
    service = QueryService()

    await service._fetch_branch_manager_click_counts(
        db=db,
        bbk_id="100",
        start_time=MagicMock(),
        end_time=MagicMock(),
        source_id="src-1",
    )

    sql, _ = db.fetch_all.await_args.args
    assert "event_type = 'button_click'" in sql


@pytest.mark.asyncio
async def test_fetch_branch_customer_click_counts_filters_button_click_only():
    """分行客户点击统计应只统计按钮点击事件。"""
    db = MagicMock()
    db.fetch_all = AsyncMock(
        return_value=[
            {
                "button_type": "plan",
                "customer_count": 2,
            },
        ],
    )
    service = QueryService()

    await service._fetch_branch_customer_click_counts(
        db=db,
        bbk_id="100",
        start_time=MagicMock(),
        end_time=MagicMock(),
        source_id="src-1",
    )

    sql, _ = db.fetch_all.await_args.args
    assert "event_type = 'button_click'" in sql
