# -*- coding: utf-8 -*-
"""Root conftest: ensure worktree src is importable before collection."""

import sys
from pathlib import Path

_TESTS_DIR = Path(__file__).resolve().parent
_WORKTREE_SRC = str(_TESTS_DIR.parent / "src")
_TEST_FAKES = str(_TESTS_DIR / "fakes")

# Prepend worktree src so it takes priority over the installed package.
if _WORKTREE_SRC not in sys.path:
    sys.path.insert(0, _WORKTREE_SRC)

# Make documented test fakes, such as trace_sdk, available during collection.
if _TEST_FAKES not in sys.path:
    sys.path.insert(0, _TEST_FAKES)

# Evict any already-cached swe modules so they reload from worktree src.
_stale = [k for k in sys.modules if k == "swe" or k.startswith("swe.")]
for k in _stale:
    del sys.modules[k]
