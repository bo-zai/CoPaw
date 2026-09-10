# -*- coding: utf-8 -*-
"""Documented shutdown import used by the FastAPI lifespan test."""

from . import _records
from ._impl import global_tracer as _global_tracer


def start_as_current_span(*args, **kwargs):
    return _global_tracer.start_as_current_span(*args, **kwargs)


def shutdown_global_tracer() -> None:
    _records.shutdown_calls += 1
