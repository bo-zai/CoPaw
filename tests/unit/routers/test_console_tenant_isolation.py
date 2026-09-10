# -*- coding: utf-8 -*-
"""Tenant isolation tests for console push message API."""

import importlib.util
import sys
import types
from unittest.mock import AsyncMock
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel
from swe.config.context import encode_scope_id

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

SRC_ROOT = Path(__file__).parent.parent.parent.parent / "src"
_CONSOLE_FILE = SRC_ROOT / "swe" / "app" / "routers" / "console.py"

_ORIGINAL_MODULES = {
    "swe.app.console_push_store": sys.modules.get(
        "swe.app.console_push_store",
    ),
    "swe.app.agent_context": sys.modules.get("swe.app.agent_context"),
}

console_push_store = types.ModuleType("swe.app.console_push_store")


async def _noop_get_recent(*args, **kwargs):
    return []


async def _noop_take(*args, **kwargs):
    return []


async def _noop_take_all(*args, **kwargs):
    return []


console_push_store.get_recent = _noop_get_recent
console_push_store.take = _noop_take
console_push_store.take_all = _noop_take_all
sys.modules["swe.app.console_push_store"] = console_push_store

agent_context = types.ModuleType("swe.app.agent_context")
agent_context.get_agent_and_config_for_request = lambda request: (None, None)
agent_context.get_agent_for_request = lambda request: None
agent_context.get_current_agent_id = lambda: "default"
agent_context.resolve_file_manager_source_scope_location = (
    lambda *args, **kwargs: None
)
agent_context.resolve_file_manager_workspace_dir = lambda *args, **kwargs: None
sys.modules["swe.app.agent_context"] = agent_context

agentscope_runtime = types.ModuleType("agentscope_runtime")
engine = types.ModuleType("agentscope_runtime.engine")
schemas = types.ModuleType("agentscope_runtime.engine.schemas")
agent_schemas = types.ModuleType(
    "agentscope_runtime.engine.schemas.agent_schemas",
)


class _Role:
    USER = "user"


class _ContentType:
    TEXT = "text"


class _RunStatus:
    Completed = "completed"


@dataclass
class _TextContent:
    type: str
    text: str


@dataclass
class _Message:
    type: str
    role: str
    content: list


class _AgentRequest(BaseModel):
    session_id: str | None = None
    user_id: str | None = None
    input: list | None = None
    channel: str | None = None


agent_schemas.AgentRequest = _AgentRequest
agent_schemas.ContentType = _ContentType
agent_schemas.Message = _Message
agent_schemas.Role = _Role
agent_schemas.RunStatus = _RunStatus
agent_schemas.TextContent = _TextContent
_ORIGINAL_AGENTSCOPE_MODULES = {
    "agentscope_runtime": sys.modules.get("agentscope_runtime"),
    "agentscope_runtime.engine": sys.modules.get(
        "agentscope_runtime.engine",
    ),
    "agentscope_runtime.engine.schemas": sys.modules.get(
        "agentscope_runtime.engine.schemas",
    ),
    "agentscope_runtime.engine.schemas.agent_schemas": sys.modules.get(
        "agentscope_runtime.engine.schemas.agent_schemas",
    ),
}
sys.modules["agentscope_runtime"] = agentscope_runtime
sys.modules["agentscope_runtime.engine"] = engine
sys.modules["agentscope_runtime.engine.schemas"] = schemas
sys.modules["agentscope_runtime.engine.schemas.agent_schemas"] = agent_schemas

spec = importlib.util.spec_from_file_location(
    "swe.app.routers.console",
    _CONSOLE_FILE,
)
assert spec is not None and spec.loader is not None
console_router = importlib.util.module_from_spec(spec)
sys.modules["swe.app.routers.console"] = console_router
spec.loader.exec_module(console_router)

for module_name, original_module in _ORIGINAL_AGENTSCOPE_MODULES.items():
    if original_module is None:
        sys.modules.pop(module_name, None)
    else:
        sys.modules[module_name] = original_module

for module_name, original_module in _ORIGINAL_MODULES.items():
    if original_module is None:
        sys.modules.pop(module_name, None)
    else:
        sys.modules[module_name] = original_module


app = FastAPI()


@app.middleware("http")
async def add_tenant_state(request, call_next):
    request.state.tenant_id = request.headers.get("X-Tenant-Id")
    request.state.scope_id = request.headers.get("X-Scope-Id")
    return await call_next(request)


app.include_router(console_router.router, prefix="/api")
client = TestClient(app)


def test_push_messages_api_returns_all_messages_when_session_id_missing():
    response = client.get(
        "/api/console/push-messages",
        headers={"X-Tenant-Id": "tenant-a"},
    )

    assert response.status_code == 200
    assert response.json() == {"messages": []}


def test_push_messages_api_prefers_request_scope_id(monkeypatch):
    observed = {}

    async def _take(session_id, tenant_id=None):
        observed["session_id"] = session_id
        observed["tenant_id"] = tenant_id
        return [{"id": "msg-1", "text": "hello", "sticky": False}]

    push_store_module = types.ModuleType("swe.app.console_push_store")
    push_store_module.take = AsyncMock(side_effect=_take)
    push_store_module.take_all = AsyncMock(return_value=[])
    push_store_module.get_recent = _noop_get_recent
    monkeypatch.setitem(
        sys.modules,
        "swe.app.console_push_store",
        push_store_module,
    )

    scope_id = encode_scope_id("tenant-a", "source-a")
    response = client.get(
        "/api/console/push-messages?session_id=session-1",
        headers={
            "X-Tenant-Id": "tenant-a",
            "X-Scope-Id": scope_id,
        },
    )

    assert response.status_code == 200
    assert observed == {
        "session_id": "session-1",
        "tenant_id": scope_id,
    }
