# -*- coding: utf-8 -*-
"""Regression tests for the opt-in development AgentTraceSDK fallback."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
_BLOCK_TRACE_SDK_IMPORT = """
import builtins

_real_import = builtins.__import__


def _blocked_import(name, *args, **kwargs):
    if name == "trace_sdk" or name.startswith("trace_sdk."):
        raise ModuleNotFoundError(f"No module named {name!r}", name=name)
    return _real_import(name, *args, **kwargs)


builtins.__import__ = _blocked_import
"""


def _import_app_without_trace_sdk(
    *,
    allow_fallback: bool,
    additional_code: str = "",
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT / "src")
    if allow_fallback:
        env["SWE_ALLOW_MISSING_TRACE_SDK"] = "true"
    else:
        env.pop("SWE_ALLOW_MISSING_TRACE_SDK", None)

    return subprocess.run(
        [
            sys.executable,
            "-c",
            _BLOCK_TRACE_SDK_IMPORT
            + "\nimport swe.app._app"
            + additional_code,
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_app_imports_when_missing_trace_sdk_is_explicitly_allowed() -> None:
    result = _import_app_without_trace_sdk(allow_fallback=True)

    assert result.returncode == 0, result.stderr


def test_fallback_trace_fields_accept_source_id() -> None:
    result = _import_app_without_trace_sdk(
        allow_fallback=True,
        additional_code=(
            "\nfrom swe.tracing.agent_trace_sdk import TraceFields"
            "\nfields = TraceFields("
            "'task-1', 'user-1', 'session-1', 'agent-1', '1.0', 'source-a'"
            ")"
            "\nassert fields.source_id == 'source-a'"
        ),
    )

    assert result.returncode == 0, result.stderr


def test_fallback_b3_context_is_callable_with_complete_headers() -> None:
    result = _import_app_without_trace_sdk(
        allow_fallback=True,
        additional_code=(
            "\nfrom swe.tracing.agent_trace_sdk import ("
            "TraceFields, use_b3_trace_context)"
            "\nfields = TraceFields("
            "'task-1', 'user-1', 'session-1', 'agent-1', '1.0', 'source-a'"
            ")"
            "\nwith use_b3_trace_context({"
            "'X-B3-Traceid': 'trace-id',"
            "'X-B3-Spanid': 'span-id',"
            "'X-B3-Sampled': '1'"
            "}, fields):"
            "\n    pass"
        ),
    )

    assert result.returncode == 0, result.stderr


def test_app_keeps_missing_trace_sdk_as_a_startup_error_by_default() -> None:
    result = _import_app_without_trace_sdk(allow_fallback=False)

    assert result.returncode != 0
    assert "ModuleNotFoundError" in result.stderr
    assert "trace_sdk" in result.stderr
