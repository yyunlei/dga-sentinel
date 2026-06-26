"""
模型管理路由 — /models /models/ab-test
"""

from __future__ import annotations

import json

import asyncpg
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from gateway.db import get_pg_pool
from gateway.middleware.auth import verify_token
from gateway.middleware.rbac import require_admin, require_viewer

router = APIRouter()


class ModelInfo(BaseModel):
    model_id: str
    version: str
    status: str
    ab_weight: float
    metrics: dict = {}
    created_at: str | None = None
    deployed_at: str | None = None


async def _log_model_op(pg: asyncpg.Pool | None, model_id: str, action: str, detail: dict) -> None:
    if not pg:
        return
    try:
        await pg.execute(
            "INSERT INTO audit_log (user_id, action, resource, detail) VALUES ($1, $2, $3, $4::jsonb)",
            "admin", action, model_id, json.dumps(detail),
        )
    except Exception:
        pass


@router.get("/models", dependencies=[Depends(require_viewer)])
async def list_models(pg: asyncpg.Pool | None = Depends(get_pg_pool)):
    """列出所有模型版本"""
    if not pg:
        raise HTTPException(status_code=503, detail="Database unavailable")
    try:
        if pg:
            rows = await pg.fetch(
                "SELECT model_id, version, status, ab_weight, metrics, created_at, deployed_at "
                "FROM model_versions ORDER BY model_id, version"
            )
            models = [
                ModelInfo(
                    model_id=r["model_id"],
                    version=r["version"],
                    status=r["status"],
                    ab_weight=float(r["ab_weight"]),
                    metrics=json.loads(r["metrics"]) if isinstance(r.get("metrics"), str) else (dict(r["metrics"]) if r.get("metrics") else {}),
                    created_at=str(r["created_at"]) if r.get("created_at") else None,
                    deployed_at=str(r["deployed_at"]) if r.get("deployed_at") else None,
                )
                for r in rows
            ]
            return {"models": models}
    except Exception:
        raise HTTPException(status_code=503, detail="Database unavailable")


class ABTestConfig(BaseModel):
    """支持前端格式 model_a / model_b / weight_a，或原 model_id + versions"""
    model_id: str | None = None
    versions: dict[str, float] | None = None
    model_a: str | None = None
    model_b: str | None = None
    weight_a: float | None = None


@router.post("/models/ab-test", dependencies=[Depends(require_admin)])
async def configure_ab_test(config: ABTestConfig, pg: asyncpg.Pool | None = Depends(get_pg_pool)):
    """配置 A/B 测试（支持 model_a/model_b/weight_a 或 model_id/versions）"""
    if config.model_a is not None and config.model_b is not None and config.weight_a is not None:
        # 前端格式：按版本权重写入，不依赖 model_id
        if not pg:
            raise HTTPException(status_code=503, detail="Database unavailable")
        try:
            async with pg.acquire() as conn:
                await conn.execute(
                    "UPDATE model_versions SET ab_weight=$1 WHERE version=$2",
                    config.weight_a, config.model_a,
                )
                await conn.execute(
                    "UPDATE model_versions SET ab_weight=$1 WHERE version=$2",
                    1.0 - config.weight_a, config.model_b,
                )
        except Exception:
            raise HTTPException(status_code=500, detail="Failed to update AB test config")
        return {"ok": True, "status": "configured"}
    if config.model_id and config.versions:
        if not pg:
            raise HTTPException(status_code=503, detail="Database unavailable")
        try:
            async with pg.acquire() as conn:
                for version, weight in config.versions.items():
                    await conn.execute(
                        "UPDATE model_versions SET ab_weight=$1 WHERE model_id=$2 AND version=$3",
                        weight, config.model_id, version,
                    )
        except Exception:
            raise HTTPException(status_code=500, detail="Failed to update AB test config")
        return {"ok": True, "status": "configured"}
    return {"ok": True, "status": "configured", "note": "no config applied"}


class RollbackBody(BaseModel):
    version: str  # 要回滚到的目标版本


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
        async with pg.acquire() as conn:
            await conn.execute(
                "UPDATE model_versions SET status='archived' WHERE model_id=$1 AND status='production'",
                model_id,
            )
            await conn.execute(
                "UPDATE model_versions SET status='production', deployed_at=NOW() WHERE model_id=$1 AND version=$2",
                model_id, to_version,
            )
    except Exception:
        raise HTTPException(status_code=500, detail="Rollback failed")
    await _log_model_op(pg, model_id, "model_rollback", {"to_version": to_version})
    return {"ok": True, "model_id": model_id, "rolled_back_to": to_version}


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
        async with pg.acquire() as conn:
            await conn.execute(
                "UPDATE model_versions SET status='staging' WHERE model_id=$1 AND status='production'",
                model_id,
            )
            await conn.execute(
                "UPDATE model_versions SET status='production', deployed_at=NOW() WHERE model_id=$1 AND version=$2",
                model_id, to_version,
            )
    except Exception:
        raise HTTPException(status_code=500, detail="Deploy failed")
    await _log_model_op(pg, model_id, "model_deploy", {"version": to_version})
    return {"ok": True, "model_id": model_id, "deployed_version": to_version}


@router.post("/models/{model_id}/offline", dependencies=[Depends(require_admin)])
async def offline_model(model_id: str, pg: asyncpg.Pool | None = Depends(get_pg_pool)):
    """将当前 production 版本下线，改为 staging"""
    if not pg:
        raise HTTPException(status_code=503, detail="Database unavailable")
    try:
        async with pg.acquire() as conn:
            await conn.execute(
                "UPDATE model_versions SET status='staging', deployed_at=NULL WHERE model_id=$1 AND status='production'",
                model_id,
            )
    except Exception:
        raise HTTPException(status_code=500, detail="Offline failed")
    await _log_model_op(pg, model_id, "model_offline", {"model_id": model_id})
    return {"ok": True, "model_id": model_id, "status": "staging"}


@router.get("/models/{model_id}/history", dependencies=[Depends(require_viewer)])
async def model_history(model_id: str, limit: int = 50, pg: asyncpg.Pool | None = Depends(get_pg_pool)):
    """获取模型操作历史"""
    if not pg:
        return {"history": []}
    rows = await pg.fetch(
        "SELECT id, user_id, action, detail, created_at FROM audit_log "
        "WHERE resource=$1 AND action LIKE 'model_%' ORDER BY created_at DESC LIMIT $2",
        model_id, limit,
    )
    return {
        "history": [
            {
                "id": r["id"], "user_id": r["user_id"], "action": r["action"],
                "detail": json.loads(r["detail"]) if isinstance(r.get("detail"), str) else (dict(r["detail"]) if r.get("detail") else {}),
                "created_at": str(r["created_at"]),
            }
            for r in rows
        ]
    }


@router.get("/models/{model_id}/versions", dependencies=[Depends(require_viewer)])
async def list_model_versions(model_id: str, pg: asyncpg.Pool | None = Depends(get_pg_pool)):
    """列出模型所有版本（供回滚选择）"""
    if not pg:
        return {"versions": []}
    rows = await pg.fetch(
        "SELECT version, status, created_at, deployed_at FROM model_versions "
        "WHERE model_id=$1 ORDER BY created_at DESC",
        model_id,
    )
    return {
        "versions": [
            {
                "version": r["version"], "status": r["status"],
                "created_at": str(r["created_at"]) if r.get("created_at") else None,
                "deployed_at": str(r["deployed_at"]) if r.get("deployed_at") else None,
            }
            for r in rows
        ]
    }
