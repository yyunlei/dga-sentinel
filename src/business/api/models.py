"""
模型管理路由 — /models /models/ab-test
"""

from __future__ import annotations

import asyncpg
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from business.infra.connections import get_pg_pool
from business.middleware.rbac import require_admin, require_viewer
from business.repositories.model_repo import ModelRepo
from business.services.model_service import ModelService

router = APIRouter()


class ModelInfo(BaseModel):
    model_id: str
    version: str
    status: str
    ab_weight: float
    metrics: dict = {}
    created_at: str | None = None
    deployed_at: str | None = None


class ABTestConfig(BaseModel):
    """支持前端格式 model_a / model_b / weight_a，或原 model_id + versions"""
    model_id: str | None = None
    versions: dict[str, float] | None = None
    model_a: str | None = None
    model_b: str | None = None
    weight_a: float | None = None


class RollbackBody(BaseModel):
    version: str  # 要回滚到的目标版本


def _make_service(pg: asyncpg.Pool | None) -> ModelService:
    return ModelService(repo=ModelRepo(pg))


@router.get("/models", dependencies=[Depends(require_viewer)])
async def list_models(pg: asyncpg.Pool | None = Depends(get_pg_pool)):
    """列出所有模型版本"""
    if not pg:
        raise HTTPException(status_code=503, detail="Database unavailable")
    try:
        models_data = await _make_service(pg).list_models()
        return {"models": [ModelInfo(**m) for m in models_data]}
    except Exception:
        raise HTTPException(status_code=503, detail="Database unavailable")


@router.post("/models/ab-test", dependencies=[Depends(require_admin)])
async def configure_ab_test(config: ABTestConfig, pg: asyncpg.Pool | None = Depends(get_pg_pool)):
    """配置 A/B 测试（支持 model_a/model_b/weight_a 或 model_id/versions）"""
    needs_db = (
        config.model_a is not None and config.model_b is not None and config.weight_a is not None
    ) or bool(config.model_id and config.versions)
    if needs_db and not pg:
        raise HTTPException(status_code=503, detail="Database unavailable")
    try:
        return await _make_service(pg).configure_ab_test(
            model_id=config.model_id,
            versions=config.versions,
            model_a=config.model_a,
            model_b=config.model_b,
            weight_a=config.weight_a,
        )
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to update AB test config")


@router.post("/models/{model_id}/rollback", dependencies=[Depends(require_admin)])
async def rollback_model(
    model_id: str,
    body: RollbackBody | None = None,
    version: str | None = None,
    pg: asyncpg.Pool | None = Depends(get_pg_pool),
):
    """回滚到指定版本（version 可在 body 或 query）"""
    to_version = (body.version if body else None) or version
    if not to_version:
        return {"ok": False, "error": "请提供 version（回滚目标版本）"}
    if not pg:
        raise HTTPException(status_code=503, detail="Database unavailable")
    try:
        return await _make_service(pg).rollback_model(model_id, to_version)
    except Exception:
        raise HTTPException(status_code=500, detail="Rollback failed")


@router.post("/models/{model_id}/deploy", dependencies=[Depends(require_admin)])
async def deploy_model(
    model_id: str,
    body: RollbackBody | None = None,
    version: str | None = None,
    pg: asyncpg.Pool | None = Depends(get_pg_pool),
):
    """将指定版本上线为 production（version 可在 body 或 query）"""
    to_version = (body.version if body else None) or version
    if not to_version:
        return {"ok": False, "error": "请提供 version（要上线的版本）"}
    if not pg:
        raise HTTPException(status_code=503, detail="Database unavailable")
    try:
        return await _make_service(pg).deploy_model(model_id, to_version)
    except Exception:
        raise HTTPException(status_code=500, detail="Deploy failed")


@router.post("/models/{model_id}/offline", dependencies=[Depends(require_admin)])
async def offline_model(model_id: str, pg: asyncpg.Pool | None = Depends(get_pg_pool)):
    """将当前 production 版本下线，改为 staging"""
    if not pg:
        raise HTTPException(status_code=503, detail="Database unavailable")
    try:
        return await _make_service(pg).offline_model(model_id)
    except Exception:
        raise HTTPException(status_code=500, detail="Offline failed")


@router.get("/models/{model_id}/history", dependencies=[Depends(require_viewer)])
async def model_history(model_id: str, limit: int = 50, pg: asyncpg.Pool | None = Depends(get_pg_pool)):
    """获取模型操作历史"""
    if not pg:
        return {"history": []}
    rows = await _make_service(pg).get_model_history(model_id, limit)
    return {"history": rows}


@router.get("/models/{model_id}/versions", dependencies=[Depends(require_viewer)])
async def list_model_versions(model_id: str, pg: asyncpg.Pool | None = Depends(get_pg_pool)):
    """列出模型所有版本（供回滚选择）"""
    if not pg:
        return {"versions": []}
    versions = await _make_service(pg).get_model_versions(model_id)
    return {"versions": versions}
