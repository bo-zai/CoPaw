# -*- coding: utf-8 -*-
import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from ...app.deps import DbDep
from ...marketplace.models import CategoryItem
from ...utils.logging_utils import log_params

router = APIRouter()
logger = logging.getLogger(__name__)


class CreateCategoryRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)


@router.get("/market/categories", response_model=list[CategoryItem])
async def get_categories(
    request: Request,
    db: DbDep,
    x_source_id: Optional[str] = Header(default=None, alias="X-Source-Id"),
):
    """获取当前 source-id 下的分类列表，按 sort_order 升序."""
    if not x_source_id:
        raise HTTPException(
            status_code=400,
            detail="X-Source-Id header is required",
        )

    log_params(logger, request.method, request.url.path, source_id=x_source_id)
    if not db.is_connected:
        raise HTTPException(status_code=503, detail="Database unavailable")

    rows = await db.fetch_all(
        "SELECT id, source_id, name, sort_order, created_at "
        "FROM swe_marketplace_categories "
        "WHERE source_id = %s ORDER BY sort_order ASC",
        (x_source_id,),
    )
    return [CategoryItem(**row) for row in rows]


@router.post(
    "/market/categories",
    response_model=CategoryItem,
    status_code=201,
)
async def create_category(
    request: Request,
    req: CreateCategoryRequest,
    db: DbDep,
    x_source_id: Optional[str] = Header(default=None, alias="X-Source-Id"),
):
    """创建新分类."""
    if not x_source_id:
        raise HTTPException(
            status_code=400,
            detail="X-Source-Id header is required",
        )

    log_params(
        logger,
        request.method,
        request.url.path,
        source_id=x_source_id,
        name=req.name,
    )
    if not db.is_connected:
        raise HTTPException(status_code=503, detail="Database unavailable")

    name = req.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="分类名称不能为空")

    # 检查同名分类是否已存在
    existing = await db.fetch_one(
        "SELECT id FROM swe_marketplace_categories WHERE source_id = %s AND name = %s",
        (x_source_id, name),
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"分类 '{name}' 已存在",
        )

    # 获取当前最大 sort_order
    row = await db.fetch_one(
        "SELECT COALESCE(MAX(sort_order), -1) AS max_order "
        "FROM swe_marketplace_categories WHERE source_id = %s",
        (x_source_id,),
    )
    max_order = row["max_order"] if row else -1

    # 插入新分类
    await db.execute(
        "INSERT INTO swe_marketplace_categories (source_id, name, sort_order) "
        "VALUES (%s, %s, %s)",
        (x_source_id, name, max_order + 1),
    )

    # 查询刚插入的记录获取完整信息
    new_row = await db.fetch_one(
        "SELECT id, source_id, name, sort_order, created_at "
        "FROM swe_marketplace_categories WHERE source_id = %s AND name = %s",
        (x_source_id, name),
    )

    if new_row is None:
        raise RuntimeError(f"Failed to fetch newly inserted category '{name}'")

    return CategoryItem(**new_row)
