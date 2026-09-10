# -*- coding: utf-8 -*-
"""Goal Runtime monitor and explicit-control API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from ..runner.api import get_workspace
from .models import GoalContract, GoalControlAction, GoalScope, GoalSnapshot
from .service import GoalConflictError, GoalNotFoundError, GoalService
from .store import MySqlGoalStore
from .registry import get_goal_service

router = APIRouter(prefix="/goals", tags=["goals"])


class _StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateGoalRequest(_StrictRequest):
    chat_id: str = Field(min_length=1)
    contract: GoalContract


class EditGoalRequest(_StrictRequest):
    contract: GoalContract


class SteeringRequest(_StrictRequest):
    content: str = Field(min_length=1, max_length=16000)


async def _service(request: Request) -> GoalService:
    service = get_goal_service()
    if service is not None:
        return service
    db = getattr(request.app.state, "db_connection", None)
    store = MySqlGoalStore(db)
    if not store.is_available:
        raise HTTPException(
            status_code=503,
            detail="Goal Runtime database is unavailable",
        )
    return GoalService(store)


async def _chat(workspace: Any, chat_id: str) -> Any:
    manager = getattr(workspace, "chat_manager", None)
    chat = await manager.get_chat(chat_id) if manager is not None else None
    if chat is None:
        raise HTTPException(status_code=404, detail="chat not found")
    return chat


def _scope(
    workspace: Any,
    chat: Any,
    *,
    source_id: str | None = None,
) -> GoalScope:
    config = getattr(workspace, "config", None)
    source_id = str(
        source_id or getattr(config, "source_id", "") or "default",
    )
    tenant_id = str(getattr(workspace, "tenant_id", "") or "default")
    model = ""
    provider_id = ""
    try:
        from ...providers.provider_manager import ProviderManager

        active = ProviderManager.get_instance(tenant_id).get_active_model()
        if active is not None:
            provider_id = str(getattr(active, "provider_id", "") or "")
            model = str(getattr(active, "model", "") or "")
    except Exception:  # noqa: BLE001
        provider_id = ""
        model = ""
    if not provider_id or not model:
        raise ValueError("Goal creation requires an active effective model")
    return GoalScope(
        tenant_id=tenant_id,
        source_id=source_id,
        agent_profile_id=str(getattr(workspace, "agent_id", "") or "default"),
        chat_id=chat.id,
        effective_model=model,
        effective_model_provider_id=provider_id,
    )


async def _owned_goal(
    service: GoalService,
    workspace: Any,
    goal_id: str,
    chat_id: str,
) -> GoalSnapshot:
    try:
        goal = await service.get(goal_id)
    except GoalNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if (
        goal.scope.tenant_id
        != str(getattr(workspace, "tenant_id", "") or "default")
        or goal.scope.agent_profile_id
        != str(getattr(workspace, "agent_id", "") or "default")
        or goal.scope.source_id
        != str(
            getattr(getattr(workspace, "config", None), "source_id", "")
            or "default",
        )
    ):
        raise HTTPException(status_code=404, detail="goal not found")
    if goal.scope.chat_id != chat_id:
        raise HTTPException(status_code=404, detail="goal not found")
    # A Goal is owned by the Chat as well as its profile/source scope.  Asking
    # the workspace manager for that Chat prevents an id from another Chat
    # under the same agent profile becoming a control capability.
    await _chat(workspace, goal.scope.chat_id)
    return goal


@router.post("", response_model=GoalSnapshot, status_code=201)
async def create_goal(
    body: CreateGoalRequest,
    request: Request,
    workspace: Any = Depends(get_workspace),
) -> GoalSnapshot:
    chat = await _chat(workspace, body.chat_id)
    try:
        return await (await _service(request)).create_goal(
            scope=_scope(
                workspace,
                chat,
                source_id=getattr(request.state, "source_id", None),
            ),
            contract=body.contract,
        )
    except (GoalConflictError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/recent", response_model=GoalSnapshot | None)
async def recent_goal(
    request: Request,
    workspace: Any = Depends(get_workspace),
    chat_id: str = Query(..., min_length=1),
) -> GoalSnapshot | None:
    chat = await _chat(workspace, chat_id)
    goal = await (await _service(request)).recent_for_chat(chat.id)
    if goal is None:
        return None
    return await _owned_goal(
        await _service(request),
        workspace,
        goal.goal_id,
        chat.id,
    )


@router.get("/{goal_id}", response_model=GoalSnapshot)
async def get_goal(
    goal_id: str,
    request: Request,
    workspace: Any = Depends(get_workspace),
    chat_id: str = Query(..., min_length=1),
) -> GoalSnapshot:
    return await _owned_goal(
        await _service(request),
        workspace,
        goal_id,
        chat_id,
    )


@router.post("/{goal_id}/pause", response_model=GoalSnapshot)
async def pause_goal(
    goal_id: str,
    request: Request,
    workspace: Any = Depends(get_workspace),
    chat_id: str = Query(..., min_length=1),
) -> GoalSnapshot:
    service = await _service(request)
    await _owned_goal(service, workspace, goal_id, chat_id)
    return await service.request_control(goal_id, GoalControlAction.PAUSE)


@router.post("/{goal_id}/resume", response_model=GoalSnapshot)
async def resume_goal(
    goal_id: str,
    request: Request,
    workspace: Any = Depends(get_workspace),
    chat_id: str = Query(..., min_length=1),
) -> GoalSnapshot:
    service = await _service(request)
    await _owned_goal(service, workspace, goal_id, chat_id)
    return await service.resume(goal_id)


@router.post("/{goal_id}/cancel", response_model=GoalSnapshot)
async def cancel_goal(
    goal_id: str,
    request: Request,
    workspace: Any = Depends(get_workspace),
    chat_id: str = Query(..., min_length=1),
) -> GoalSnapshot:
    service = await _service(request)
    await _owned_goal(service, workspace, goal_id, chat_id)
    return await service.request_control(goal_id, GoalControlAction.CANCEL)


@router.post("/{goal_id}/edit", response_model=GoalSnapshot)
async def edit_goal(
    goal_id: str,
    body: EditGoalRequest,
    request: Request,
    workspace: Any = Depends(get_workspace),
    chat_id: str = Query(..., min_length=1),
) -> GoalSnapshot:
    service = await _service(request)
    await _owned_goal(service, workspace, goal_id, chat_id)
    return await service.request_edit(goal_id, body.contract)


@router.post("/{goal_id}/steering", response_model=GoalSnapshot)
async def enqueue_goal_steering(
    goal_id: str,
    body: SteeringRequest,
    request: Request,
    workspace: Any = Depends(get_workspace),
    chat_id: str = Query(..., min_length=1),
) -> GoalSnapshot:
    """Queue ordinary Goal steering; it never changes the Contract."""
    service = await _service(request)
    await _owned_goal(service, workspace, goal_id, chat_id)
    try:
        return await service.enqueue_steering(goal_id, body.content)
    except GoalConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
