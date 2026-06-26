"""
Operations / Recommendations 路由 — 把 pipeline_operations 表里的
pending 推荐暴露给分析师，让他们 acknowledge / dismiss。

分析师对每条推荐有两种动作：
  * acknowledge — "我看到了，会按建议手动处理（如调阈值、触发重训练）"
  * dismiss    — "推荐不准，忽略"

**故意不在这里执行实际动作**（不直接改 pipeline YAML / 不触发重训练）—
高风险动作必须人工执行，平台只做"决策支持 + 审计追踪"。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from business.infra.connections import get_pg_pool
from business.middleware.auth import verify_token
from business.middleware.rbac import require_analyst
from business.repositories.operations_repo import OperationsRepo
from business.services.operations_service import OperationsService
from common.observability import get_logger

router = APIRouter()
logger = get_logger(__name__)


class OperationItem(BaseModel):
    id: int
    pipeline_id: str
    operation: str
    operator: str
    status: str
    detail: dict
    created_at: str


class OperationsListResponse(BaseModel):
    items: list[OperationItem]
    total: int


def _make_service(pg) -> OperationsService:
    return OperationsService(repo=OperationsRepo(pg))


@router.get("/operations/pending", dependencies=[Depends(require_analyst)])
async def list_pending(
    op_type: str | None = Query(None, description="过滤特定 operation 类型"),
    limit: int = Query(50, le=200),
    pg=Depends(get_pg_pool),
):
    """列出所有 pending 状态的推荐（按时间倒序）。"""
    if not pg:
        return {"items": [], "total": 0}
    return await _make_service(pg).list_pending(op_type, limit)


@router.get("/operations/recent", dependencies=[Depends(require_analyst)])
async def list_recent(
    limit: int = Query(100, le=500),
    pg=Depends(get_pg_pool),
):
    """列出近期所有状态的 operation（含已 acknowledged / dismissed），用于审计/历史浏览。"""
    if not pg:
        return {"items": [], "total": 0}
    return await _make_service(pg).list_recent(limit)


@router.get("/operations/stats", dependencies=[Depends(require_analyst)])
async def stats(pg=Depends(get_pg_pool)):
    """聚合计数（用于侧边栏 badge / 仪表）。"""
    if not pg:
        return {"by_status": {}, "by_operation_pending": {}, "pending_total": 0}
    return await _make_service(pg).get_stats()


@router.post("/operations/{op_id}/acknowledge", dependencies=[Depends(require_analyst)])
async def acknowledge(
    op_id: int,
    token: dict = Depends(verify_token),
    pg=Depends(get_pg_pool),
):
    """标记一条 pending 推荐为 acknowledged（分析师认可，会手动跟进）。"""
    if not pg:
        raise HTTPException(503, "DB unavailable")
    result = await _make_service(pg).transition(op_id, "acknowledged", token)
    if "_error" in result:
        raise HTTPException(result["_error"], result["detail"])
    logger.info("operation_status_changed", id=op_id, new_status="acknowledged", by=result.get("by"))
    return result


@router.post("/operations/{op_id}/dismiss", dependencies=[Depends(require_analyst)])
async def dismiss(
    op_id: int,
    token: dict = Depends(verify_token),
    pg=Depends(get_pg_pool),
):
    """标记一条 pending 推荐为 dismissed（分析师认为推荐不准，忽略）。"""
    if not pg:
        raise HTTPException(503, "DB unavailable")
    result = await _make_service(pg).transition(op_id, "dismissed", token)
    if "_error" in result:
        raise HTTPException(result["_error"], result["detail"])
    logger.info("operation_status_changed", id=op_id, new_status="dismissed", by=result.get("by"))
    return result
