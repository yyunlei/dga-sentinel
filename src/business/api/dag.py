"""
DAG 管理路由 — /dag/pipelines /dag/replay /dag/status
HTTP 层：仅处理依赖注入、参数解析、异常映射。业务逻辑见 PipelineService。
"""

from __future__ import annotations

import asyncpg
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from business.infra.connections import get_pg_pool, get_redis_client, get_es_client
from business.middleware.rbac import require_admin, require_analyst, require_viewer

from business.repositories.pipeline_repo import PipelineRepo
from business.services.pipeline_service import (
    PipelineService,
    PipelineNotFoundError,
    DatabaseUnavailableError,
    PipelineSaveError,
)

router = APIRouter()


class PipelineInfo(BaseModel):
    pipeline_id: str
    name: str
    mode: str
    status: str
    version: str
    created_at: str | None = None


class CreatePipelineRequest(BaseModel):
    name: str
    mode: str = "stream"
    yaml_content: str


class UpdatePipelineRequest(BaseModel):
    yaml_content: str
    name: str | None = None
    mode: str | None = None


class RollbackRequest(BaseModel):
    version: int


class ReplayRequest(BaseModel):
    pipeline: str = "dga-batch-v1"
    date: str  # "2026-02-10"
    hour: int | None = None  # 可选：指定小时


class ReplayResponse(BaseModel):
    replay_id: str
    status: str
    stats: dict = {}


# ---------------------------------------------------------------------------
# Service 工厂依赖
# ---------------------------------------------------------------------------


def get_pipeline_service(
    pg: asyncpg.Pool | None = Depends(get_pg_pool),
    redis=Depends(get_redis_client),
    es=Depends(get_es_client),
) -> PipelineService:
    repo = PipelineRepo(pg=pg, redis=redis, es=es)
    return PipelineService(repo=repo)


# ---------------------------------------------------------------------------
# 端点：Pipeline 列表 / 统计 / 详情
# ---------------------------------------------------------------------------


@router.get("/dag/pipelines", dependencies=[Depends(require_viewer)])
async def list_pipelines(svc: PipelineService = Depends(get_pipeline_service)):
    """列出所有 DAG pipeline"""
    return await svc.list_pipelines()


@router.get("/dag/pipelines/stats", dependencies=[Depends(require_viewer)])
async def pipeline_stats(svc: PipelineService = Depends(get_pipeline_service)):
    """Pipeline 统计概览：计数、告警分布、家族 Top10"""
    return await svc.pipeline_stats()


@router.get("/dag/pipelines/{pipeline_id}", dependencies=[Depends(require_viewer)])
async def get_pipeline(
    pipeline_id: str,
    svc: PipelineService = Depends(get_pipeline_service),
):
    """获取 pipeline 详情（含 YAML 配置 + 结构化节点/边）"""
    try:
        return await svc.get_pipeline(pipeline_id)
    except PipelineNotFoundError:
        raise HTTPException(status_code=404, detail="Pipeline not found")


# ---------------------------------------------------------------------------
# 端点：Pipeline CRUD
# ---------------------------------------------------------------------------


@router.post("/dag/pipelines", dependencies=[Depends(require_admin)])
async def create_pipeline(
    req: CreatePipelineRequest,
    svc: PipelineService = Depends(get_pipeline_service),
):
    """创建新的 pipeline 配置"""
    try:
        return await svc.create_pipeline(req.name, req.mode, req.yaml_content)
    except DatabaseUnavailableError:
        raise HTTPException(status_code=503, detail="Database unavailable")
    except PipelineSaveError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/dag/pipelines/{pipeline_id}", dependencies=[Depends(require_admin)])
async def delete_pipeline(
    pipeline_id: str,
    svc: PipelineService = Depends(get_pipeline_service),
):
    """删除 pipeline 及其所有版本"""
    try:
        return await svc.delete_pipeline(pipeline_id)
    except DatabaseUnavailableError:
        raise HTTPException(status_code=503, detail="Database unavailable")
    except PipelineNotFoundError:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    except PipelineSaveError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/dag/pipelines/{pipeline_id}", dependencies=[Depends(require_admin)])
async def update_pipeline(
    pipeline_id: str,
    req: UpdatePipelineRequest,
    svc: PipelineService = Depends(get_pipeline_service),
):
    """更新 pipeline 配置（版本号 +1，原地更新）"""
    try:
        return await svc.update_pipeline(
            pipeline_id, req.yaml_content, name=req.name, mode=req.mode
        )
    except DatabaseUnavailableError:
        raise HTTPException(status_code=503, detail="Database unavailable")
    except PipelineNotFoundError:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    except PipelineSaveError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/dag/pipelines/{pipeline_id}/rollback", dependencies=[Depends(require_admin)])
async def rollback_pipeline(
    pipeline_id: str,
    req: RollbackRequest,
    svc: PipelineService = Depends(get_pipeline_service),
):
    """回滚 pipeline 到指定版本（通过操作历史恢复）"""
    try:
        return await svc.rollback_pipeline(pipeline_id, req.version)
    except DatabaseUnavailableError:
        raise HTTPException(status_code=503, detail="Database unavailable")
    except PipelineNotFoundError:
        raise HTTPException(status_code=404, detail="Pipeline not found")


# ---------------------------------------------------------------------------
# 端点：Pipeline 状态流转
# ---------------------------------------------------------------------------


@router.post("/dag/pipelines/{pipeline_id}/start", dependencies=[Depends(require_analyst)])
async def start_pipeline(
    pipeline_id: str,
    svc: PipelineService = Depends(get_pipeline_service),
):
    """启动 pipeline（写入期望状态，供 DAG 引擎消费）"""
    return await svc.start_pipeline(pipeline_id)


@router.post("/dag/pipelines/{pipeline_id}/stop", dependencies=[Depends(require_analyst)])
async def stop_pipeline(
    pipeline_id: str,
    svc: PipelineService = Depends(get_pipeline_service),
):
    """停止 pipeline"""
    return await svc.stop_pipeline(pipeline_id)


# ---------------------------------------------------------------------------
# 端点：Replay / Status / History
# ---------------------------------------------------------------------------


@router.post("/dag/replay", response_model=ReplayResponse, dependencies=[Depends(require_analyst)])
async def trigger_replay(
    req: ReplayRequest,
    svc: PipelineService = Depends(get_pipeline_service),
):
    """触发批量回放/补算"""
    result = await svc.trigger_replay(req.pipeline, req.date, req.hour)
    return ReplayResponse(**result)


@router.get("/dag/status", dependencies=[Depends(require_viewer)])
async def dag_status(svc: PipelineService = Depends(get_pipeline_service)):
    """获取 DAG 引擎运行状态"""
    return await svc.dag_status()


@router.get("/dag/pipelines/{pipeline_id}/history", dependencies=[Depends(require_viewer)])
async def pipeline_history(
    pipeline_id: str,
    limit: int = 50,
    svc: PipelineService = Depends(get_pipeline_service),
):
    """获取 pipeline 操作历史"""
    return await svc.pipeline_history(pipeline_id, limit)
