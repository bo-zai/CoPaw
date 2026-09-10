# -*- coding: utf-8 -*-
from __future__ import annotations

from starlette.requests import Request

from swe.app.b3_headers import extract_b3_context
from swe.app.middleware.header_passthrough import HeaderPassthroughMiddleware


def _request_with_headers(headers: list[tuple[bytes, bytes]]) -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/console/chat",
            "headers": headers,
        },
    )


def test_header_passthrough_extracts_raw_b3_headers() -> None:
    middleware = HeaderPassthroughMiddleware(
        app=lambda scope, receive, send: None,
    )
    request = _request_with_headers(
        [
            (b"x-header-cookie", b"foo=bar"),
            (b"x-b3-traceid", b"8267fd70bacf497704fec30eaa353979"),
            (b"x-b3-spanid", b"32befd146889a61a"),
            (b"x-b3-parentspanid", b"5be42cd2b570b6da"),
            (b"x-b3-sampled", b"1"),
            (b"x-b3-debug", b"0"),
            (b"x-b3-businessid", b"LQ1303LMES-WEB"),
            (b"x-b3-timestamp", b"1782962021603"),
            (b"x-other", b"ignored"),
        ],
    )

    assert middleware._extract_passthrough_headers(request) == {
        "cookie": "foo=bar",
        "X-B3-Traceid": "8267fd70bacf497704fec30eaa353979",
        "X-B3-Spanid": "32befd146889a61a",
        "X-B3-Parentspanid": "5be42cd2b570b6da",
        "X-B3-Sampled": "1",
        "X-B3-Debug": "0",
        "X-B3-BusinessId": "LQ1303LMES-WEB",
        "X-B3-Timestamp": "1782962021603",
    }


def test_header_passthrough_canonicalizes_prefixed_b3_headers() -> None:
    middleware = HeaderPassthroughMiddleware(
        app=lambda scope, receive, send: None,
    )
    request = _request_with_headers(
        [
            (
                b"x-header-X-B3-Traceid",
                b"8267fd70bacf497704fec30eaa353979",
            ),
            (b"x-header-X-B3-Spanid", b"32befd146889a61a"),
        ],
    )

    assert middleware._extract_passthrough_headers(request) == {
        "X-B3-Traceid": "8267fd70bacf497704fec30eaa353979",
        "X-B3-Spanid": "32befd146889a61a",
    }


def test_extract_b3_context_keeps_supplied_identifiers_opaque() -> None:
    headers = {
        "X-B3-Traceid": "trace-id-from-frontend",
        "X-B3-Spanid": "span-id-from-frontend",
        "X-B3-Sampled": "1",
    }

    assert extract_b3_context(headers) == headers


def test_extract_b3_context_returns_none_when_frontend_omits_b3_headers() -> (
    None
):
    assert extract_b3_context({"X-Source-Id": "src-a"}) is None
