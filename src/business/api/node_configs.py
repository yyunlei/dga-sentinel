"""
节点配置管理路由 — /node-configs CRUD
提供 19 种 DAG 节点类型的配置 schema 查询与持久化管理
HTTP 层：仅处理依赖注入、参数解析、异常映射。业务逻辑见 PipelineService。
"""

from __future__ import annotations

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from business.infra.connections import get_pg_pool
from business.middleware.rbac import require_admin, require_viewer

from business.repositories.pipeline_repo import PipelineRepo
from business.services.pipeline_service import (
    PipelineService,
    DatabaseUnavailableError,
    NodeTypeUnknownError,
    NodeConfigNotFoundError,
)

router = APIRouter()


# ── Pydantic Models ────────────────────────────────────────────────


class NodeConfigCreate(BaseModel):
    node_type: str
    name: str
    config: dict = {}
    description: str = ""


class NodeConfigUpdate(BaseModel):
    config: dict | None = None
    name: str | None = None
    description: str | None = None


# ---------------------------------------------------------------------------
# Service 工厂依赖（node-configs 端点仅需 pg）
# ---------------------------------------------------------------------------


def get_pipeline_service(
    pg: asyncpg.Pool | None = Depends(get_pg_pool),
) -> PipelineService:
    repo = PipelineRepo(pg=pg)
    return PipelineService(repo=repo)


# ── Schema 查询 ───────────────────────────────────────────────────


@router.get("/node-configs/schemas", dependencies=[Depends(require_viewer)])
async def list_schemas(svc: PipelineService = Depends(get_pipeline_service)):
    return svc.list_schemas()


@router.get("/node-configs/schemas/{node_type}", dependencies=[Depends(require_viewer)])
async def get_schema(
    node_type: str,
    svc: PipelineService = Depends(get_pipeline_service),
):
    try:
        return svc.get_schema(node_type)
    except NodeTypeUnknownError as e:
        raise HTTPException(404, str(e))


# ── CRUD ──────────────────────────────────────────────────────────


@router.get("/node-configs", dependencies=[Depends(require_viewer)])
async def list_configs(
    node_type: str | None = Query(None),
    category: str | None = Query(None),
    svc: PipelineService = Depends(get_pipeline_service),
):
    return await svc.list_node_configs(node_type, category)


@router.post("/node-configs", dependencies=[Depends(require_admin)])
async def create_config(
    req: NodeConfigCreate,
    svc: PipelineService = Depends(get_pipeline_service),
):
    try:
        return await svc.create_node_config(req.node_type, req.name, req.config, req.description)
    except NodeTypeUnknownError as e:
        raise HTTPException(400, str(e))
    except DatabaseUnavailableError:
        raise HTTPException(503, "Database unavailable")
    except asyncpg.UniqueViolationError:
        raise HTTPException(409, f"Config '{req.name}' already exists for {req.node_type}")


@router.get("/node-configs/{config_id}", dependencies=[Depends(require_viewer)])
async def get_config(
    config_id: int,
    svc: PipelineService = Depends(get_pipeline_service),
):
    try:
        return await svc.get_node_config(config_id)
    except DatabaseUnavailableError:
        raise HTTPException(503, "Database unavailable")
    except NodeConfigNotFoundError:
        raise HTTPException(404, "Config not found")


@router.put("/node-configs/{config_id}", dependencies=[Depends(require_admin)])
async def update_config(
    config_id: int,
    req: NodeConfigUpdate,
    svc: PipelineService = Depends(get_pipeline_service),
):
    try:
        return await svc.update_node_config(
            config_id, name=req.name, config=req.config, description=req.description
        )
    except DatabaseUnavailableError:
        raise HTTPException(503, "Database unavailable")
    except NodeConfigNotFoundError:
        raise HTTPException(404, "Config not found")


@router.delete("/node-configs/{config_id}", dependencies=[Depends(require_admin)])
async def delete_config(
    config_id: int,
    svc: PipelineService = Depends(get_pipeline_service),
):
    try:
        return await svc.delete_node_config(config_id)
    except DatabaseUnavailableError:
        raise HTTPException(503, "Database unavailable")
    except NodeConfigNotFoundError:
        raise HTTPException(404, "Config not found")
