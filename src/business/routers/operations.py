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

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from business.db import get_pg_pool
from business.middleware.auth import verify_token
from business.middleware.rbac import require_analyst
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


def _row_to_item(r: dict) -> dict:
    detail = r["detail"]
    if isinstance(detail, str):
        try:
            detail = json.loads(detail)
        except Exception:  # noqa: BLE001
            detail = {"raw": detail}
    return {
        "id": r["id"],
        "pipeline_id": r["pipeline_id"],
        "operation": r["operation"],
        "operator": r["operator"],
        "status": r["status"],
        "detail": detail or {},
        "created_at": r["created_at"].isoformat() if r["created_at"] else "",
    }


@router.get("/operations/pending", dependencies=[Depends(require_analyst)])
async def list_pending(
    op_type: str | None = Query(None, description="过滤特定 operation 类型"),
    limit: int = Query(50, le=200),
    pg=Depends(get_pg_pool),
):
    """列出所有 pending 状态的推荐（按时间倒序）。"""
    if not pg:
        return {"items": [], "total": 0}

    if op_type:
        rows = await pg.fetch(
            """
            SELECT id, pipeline_id, operation, operator, status, detail, created_at
            FROM pipeline_operations
            WHERE status = 'pending' AND operation = $1
            ORDER BY id DESC LIMIT $2
            """,
            op_type, limit,
        )
    else:
        rows = await pg.fetch(
            """
            SELECT id, pipeline_id, operation, operator, status, detail, created_at
            FROM pipeline_operations
            WHERE status = 'pending'
            ORDER BY id DESC LIMIT $1
            """,
            limit,
        )

    items = [_row_to_item(dict(r)) for r in rows]
    return {"items": items, "total": len(items)}


@router.get("/operations/recent", dependencies=[Depends(require_analyst)])
async def list_recent(
    limit: int = Query(100, le=500),
    pg=Depends(get_pg_pool),
):
    """列出近期所有状态的 operation（含已 acknowledged / dismissed），用于审计/历史浏览。"""
    if not pg:
        return {"items": [], "total": 0}
    rows = await pg.fetch(
        """
        SELECT id, pipeline_id, operation, operator, status, detail, created_at
        FROM pipeline_operations
        ORDER BY id DESC LIMIT $1
        """,
        limit,
    )
    items = [_row_to_item(dict(r)) for r in rows]
    return {"items": items, "total": len(items)}


@router.get("/operations/stats", dependencies=[Depends(require_analyst)])
async def stats(pg=Depends(get_pg_pool)):
    """聚合计数（用于侧边栏 badge / 仪表）。"""
    if not pg:
        return {"by_status": {}, "by_operation_pending": {}, "pending_total": 0}
    by_status = await pg.fetch(
        "SELECT status, COUNT(*)::int AS n FROM pipeline_operations GROUP BY status"
    )
    by_op_pending = await pg.fetch(
        "SELECT operation, COUNT(*)::int AS n FROM pipeline_operations "
        "WHERE status = 'pending' GROUP BY operation"
    )
    status_map = {r["status"]: r["n"] for r in by_status}
    return {
        "by_status": status_map,
        "by_operation_pending": {r["operation"]: r["n"] for r in by_op_pending},
        "pending_total": status_map.get("pending", 0),
    }


async def _transition(
    op_id: int,
    new_status: str,
    actor: dict[str, Any],
    pg,
) -> dict:
    if not pg:
        raise HTTPException(503, "DB unavailable")

    rec = await pg.fetchrow(
        "SELECT id, status FROM pipeline_operations WHERE id = $1",
        op_id,
    )
    if not rec:
        raise HTTPException(404, f"Operation {op_id} not found")
    if rec["status"] != "pending":
        raise HTTPException(409, f"Operation {op_id} is already {rec['status']}")

    await pg.execute(
        "UPDATE pipeline_operations SET status = $1 WHERE id = $2",
        new_status, op_id,
    )
    user_id = actor.get("sub") or actor.get("username") or "analyst"
    await pg.execute(
        """
        INSERT INTO audit_log (user_id, action, resource, detail)
        VALUES ($1, $2, $3, $4::jsonb)
        """,
        user_id,
        f"operation_{new_status}",
        str(op_id),
        json.dumps({"new_status": new_status, "by": user_id}),
    )
    logger.info(
        "operation_status_changed",
        id=op_id, new_status=new_status, by=user_id,
    )
    return {"id": op_id, "status": new_status, "by": user_id}


@router.post("/operations/{op_id}/acknowledge", dependencies=[Depends(require_analyst)])
async def acknowledge(
    op_id: int,
    token: dict = Depends(verify_token),
    pg=Depends(get_pg_pool),
):
    """标记一条 pending 推荐为 acknowledged（分析师认可，会手动跟进）。"""
    return await _transition(op_id, "acknowledged", token, pg)


@router.post("/operations/{op_id}/dismiss", dependencies=[Depends(require_analyst)])
async def dismiss(
    op_id: int,
    token: dict = Depends(verify_token),
    pg=Depends(get_pg_pool),
):
    """标记一条 pending 推荐为 dismissed（分析师认为推荐不准，忽略）。"""
    return await _transition(op_id, "dismissed", token, pg)
