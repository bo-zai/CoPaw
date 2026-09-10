# -*- coding: utf-8 -*-
"""Tests for the W+ SOP stage-level rendering and validation scripts.

Covers the M3 deliverable: validate_stage_sop.py, validate_cumulative_sop.py
and deterministic reuse of render_md.py / render_sop.py on stage and
cumulative specs (design decisions A2/A5).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys

import pytest

_SCRIPTS = Path(__file__).resolve().parents[4] / "skills" / "wplus-sop-miner" / "scripts"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(
        f"wplus_{name}",
        _SCRIPTS / f"{name}.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


stage_validator = _load("validate_stage_sop")
cumulative_validator = _load("validate_cumulative_sop")
render_md = _load("render_md")
render_sop = _load("render_sop")


def _stage(
    stage_id: str,
    name: str,
    *,
    status: str = "complete",
    verification: str = "user_confirmed",
) -> dict:
    return {
        "id": stage_id,
        "name": name,
        "status": status,
        "verification_mode": verification,
        "entry_point": "工作台",
        "data_scope": {"table": "customers"},
        "decision_logic": "筛选高价值客户",
        "output": "名单",
        "next_action": "交付",
        "trial_notes": ["已预跑，结果符合预期"],
        "execution": {
            "mode": "analysis",
            "capability_ids": [],
            "parameter_bindings": {},
        },
    }


def _spec(
    *,
    title: str = "SOP",
    status: str = "in_progress",
    stages: list[dict] | None = None,
    request_summary: str = "客户筛选",
) -> dict:
    return {
        "schema_version": "1.1",
        "title": title,
        "request_summary": request_summary,
        "queue_confirmed": True,
        "status": status,
        "trigger": "资产变化",
        "actor": "理财经理",
        "stages": stages or [],
        "capability_snapshot": [],
        "open_questions": [],
        "memory_candidates": [],
    }


def test_stage_report_accepts_single_in_progress_stage() -> None:
    report = _spec(
        title="环节一报告",
        status="in_progress",
        stages=[
            _stage(
                "s1",
                "需求确认",
                status="awaiting_stage_confirmation",
                verification="trial_run",
            ),
        ],
    )
    assert stage_validator.validate_stage_report(report) == []


def test_stage_report_rejects_more_than_one_stage() -> None:
    report = _spec(
        stages=[_stage("s1", "一"), _stage("s2", "二")],
    )
    errors = stage_validator.validate_stage_report(report)
    assert any("exactly one stage" in error for error in errors)


def test_stage_report_rejects_missing_required_fields() -> None:
    errors = stage_validator.validate_stage_report({"schema_version": "1.1"})
    assert any("missing required field" in error for error in errors)


def test_stage_report_flags_sensitive_values() -> None:
    report = _spec(
        stages=[_stage("s1", "一")],
    )
    report["stages"][0]["data_scope"] = {"custuid": "PNCIF1234567"}
    errors = stage_validator.validate_stage_report(report)
    assert any("sensitive" in error for error in errors)


def test_cumulative_accepts_single_confirmed_stage() -> None:
    cumulative = _spec(
        title="累计一环节",
        stages=[_stage("s1", "需求确认")],
    )
    assert cumulative_validator.validate_cumulative(cumulative) == []


def test_cumulative_accepts_multiple_confirmed_stages() -> None:
    cumulative = _spec(
        title="累计两环节",
        stages=[
            _stage("s1", "需求确认"),
            _stage("s2", "生成结果"),
        ],
    )
    assert cumulative_validator.validate_cumulative(cumulative) == []


def test_cumulative_rejects_unconfirmed_stage() -> None:
    cumulative = _spec(
        stages=[
            _stage("s1", "需求确认"),
            _stage(
                "s2",
                "未确认环节",
                status="clarifying",
                verification="original",
            ),
        ],
    )
    errors = cumulative_validator.validate_cumulative(cumulative)
    assert any("must be complete" in error for error in errors)
    assert any("must be user_confirmed" in error for error in errors)


def test_cumulative_rejects_empty_stage_list() -> None:
    errors = cumulative_validator.validate_cumulative(_spec())
    assert any("at least one confirmed stage" in error for error in errors)


def test_render_is_deterministic_and_carries_stage_content() -> None:
    cumulative = _spec(
        stages=[_stage("s1", "需求确认")],
    )
    first_md = render_md.render_md(cumulative)
    second_md = render_md.render_md(cumulative)
    first_html = render_sop.render_html(cumulative)
    second_html = render_sop.render_html(cumulative)
    assert first_md == second_md
    assert first_html == second_html
    assert "需求确认" in first_md
    assert "需求确认" in first_html
    assert "触发场景" in first_md
    assert "触发场景" in first_html


def test_validator_cli_exit_codes(tmp_path: Path) -> None:
    good = tmp_path / "stage.json"
    good.write_text(
        __import__("json").dumps(
            _spec(
                stages=[
                    _stage(
                        "s1",
                        "需求确认",
                        status="awaiting_stage_confirmation",
                        verification="trial_run",
                    ),
                ],
            ),
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, str(_SCRIPTS / "validate_stage_sop.py"), str(good)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert '"valid": true' in result.stdout
