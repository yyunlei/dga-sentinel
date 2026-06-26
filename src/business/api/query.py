"""查询路由 — /api/query
HTTP 层：解析请求 → 调 DetectionService.query_data → 包装响应/异常。
不包含 httpx 调用逻辑，均委托给 DetectionService。
"""
from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from business.middleware.rbac import require_analyst
from business.services.detection_service import DetectionService
from common.observability import get_logger

router = APIRouter()
logger = get_logger(__name__)

AGENT_LAYER_URL = "http://agent-layer:8002"


class QueryRequest(BaseModel):
    question: str
    db_type: str = "starrocks"  # "starrocks" or "postgres"


class QueryResponse(BaseModel):
    sql: str = ""
    data: list = []
    explanation: str = ""
    error: str | None = None
    trace_id: str = ""


def _service() -> DetectionService:
    """DI 工厂：构造仅用于 query 编排的 DetectionService。"""
    return DetectionService(agent_layer_url=AGENT_LAYER_URL)


@router.post("/query", response_model=QueryResponse, dependencies=[Depends(require_analyst)])
async def query_data(
    req: QueryRequest,
    request: Request,
    svc: DetectionService = Depends(_service),
):
    """自然语言查询数据 — 通过 HTTP dispatch 到 agent-layer"""
    trace_id = getattr(request.state, "trace_id", "")
    try:
        result = await svc.query_data(req.question, req.db_type, trace_id)
        return QueryResponse(**result)
    except httpx.HTTPStatusError as e:
        logger.error("query_dispatch_error", status=e.response.status_code)
        raise HTTPException(status_code=503, detail="Query service unavailable")
    except Exception as e:
        logger.error("query_error", error=str(e))
        raise HTTPException(status_code=503, detail="Query service unavailable")
