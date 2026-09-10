# -*- coding: utf-8 -*-
"""Helpers for B3 tracing headers passed through SWE request flows."""

from __future__ import annotations

from typing import Any

HEADER_PREFIX = "x-header-"
B3_TRACE_ID_HEADER = "X-B3-Traceid"
B3_SPAN_ID_HEADER = "X-B3-Spanid"
B3_SAMPLED_HEADER = "X-B3-Sampled"
B3_TRACE_ID_META_KEY = "b3_trace_id"
PASSTHROUGH_HEADERS_META_KEY = "passthrough_headers"
B3_CONTEXT_META_KEY = "b3_context"
B3_REQUIRED_HEADER_NAMES = (
    B3_TRACE_ID_HEADER,
    B3_SPAN_ID_HEADER,
    B3_SAMPLED_HEADER,
)
_B3_SAMPLED_VALUES = frozenset({"0", "1", "true", "false"})
B3_HEADER_NAMES = {
    "x-b3-businessid": "X-B3-BusinessId",
    "x-b3-debug": "X-B3-Debug",
    "x-b3-parentspanid": "X-B3-Parentspanid",
    "x-b3-sampled": "X-B3-Sampled",
    "x-b3-spanid": "X-B3-Spanid",
    "x-b3-timestamp": "X-B3-Timestamp",
    "x-b3-traceid": B3_TRACE_ID_HEADER,
}


def extract_b3_headers(headers: Any) -> dict[str, str]:
    """Extract whitelisted B3 headers from a mapping-like header object."""
    if headers is None:
        return {}
    items = getattr(headers, "items", None)
    if not callable(items):
        return {}

    extracted: dict[str, str] = {}
    for name, value in items():
        name_lower = str(name).lower()
        header_name = (
            name_lower[len(HEADER_PREFIX) :]
            if name_lower.startswith(HEADER_PREFIX)
            else name_lower
        )
        canonical_name = B3_HEADER_NAMES.get(header_name)
        if canonical_name is None:
            continue
        header_value = str(value).strip()
        if header_value:
            extracted[canonical_name] = header_value
    return extracted


def extract_b3_trace_id(headers: Any) -> str | None:
    trace_id = extract_b3_headers(headers).get(B3_TRACE_ID_HEADER)
    return trace_id or None


def extract_b3_context(headers: Any) -> dict[str, str] | None:
    """Return a complete B3 parent context when one is supplied."""
    b3_headers = extract_b3_headers(headers)
    present_headers = {
        name: b3_headers[name]
        for name in B3_REQUIRED_HEADER_NAMES
        if name in b3_headers
    }
    if not present_headers:
        return None
    if len(present_headers) != len(B3_REQUIRED_HEADER_NAMES):
        raise ValueError("Incomplete B3 trace context")
    if present_headers[B3_SAMPLED_HEADER].lower() not in _B3_SAMPLED_VALUES:
        raise ValueError("Invalid X-B3-Sampled")
    return present_headers


def build_b3_dispatch_meta(headers: Any) -> dict[str, Any]:
    """Build per-execution cron metadata from B3 request headers."""
    b3_headers = extract_b3_headers(headers)
    if not b3_headers:
        return {}

    meta: dict[str, Any] = {
        PASSTHROUGH_HEADERS_META_KEY: b3_headers,
    }
    trace_id = b3_headers.get(B3_TRACE_ID_HEADER)
    if trace_id:
        meta[B3_TRACE_ID_META_KEY] = trace_id
    return meta
