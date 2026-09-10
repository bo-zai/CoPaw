# -*- coding: utf-8 -*-
"""市场 MCP 浏览路由."""

from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query, Request

from ...marketplace.schemas import MarketMCPDetail, MarketMCPItem
from ..deps import require_source_id

router = APIRouter()


@router.get("/market/mcp", response_model=list[MarketMCPItem])
async def list_market_mcp(
    request: Request,
    category_id: Optional[int] = None,
    bbk_ids: Optional[str] = Query(
        default=None,
        description="逗号分隔的分行ID列表",
    ),
    x_source_id: Optional[str] = Header(default=None, alias="X-Source-Id"),
    x_bbk_id: Optional[str] = Header(default=None, alias="X-Bbk-Id"),
    x_manager: Optional[str] = Header(default=None, alias="X-Manager"),
    x_user_role: Optional[str] = Header(default=None, alias="X-User-Role"),
):
    """浏览市场 MCP 列表（按 category_id + bbk_ids 过滤）。"""
    source_id = require_source_id(x_source_id)
    user_bbk_id = x_bbk_id or "100"
    is_manager = x_manager == "true" or x_user_role == "admin"
    # 解析 bbk_ids 参数（逗号分隔）
    parsed_bbk_ids = None
    if bbk_ids:
        parsed_bbk_ids = [b.strip() for b in bbk_ids.split(",") if b.strip()]
    svc = request.app.state.marketplace
    return await svc.list_mcp_items(
        source_id,
        user_bbk_id,
        category_id=category_id,
        bbk_ids=parsed_bbk_ids,
        is_manager=is_manager,
    )


@router.get("/market/mcp/{item_id}", response_model=MarketMCPDetail)
async def get_market_mcp_detail(
    item_id: str,
    request: Request,
    x_source_id: Optional[str] = Header(default=None, alias="X-Source-Id"),
    x_bbk_id: Optional[str] = Header(default=None, alias="X-Bbk-Id"),
):
    """获取市场 MCP 详情."""
    source_id = require_source_id(x_source_id)
    user_bbk_id = x_bbk_id or "100"
    svc = request.app.state.marketplace
    detail = await svc.get_mcp_detail(source_id, item_id, user_bbk_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="MCP not found")
    return detail
