"""查询路由 — /api/query
POST {question, db_type} → {sql, data, explanation}
通过 HTTP 调用 agent-layer 的 Text2SQL 引擎
"""
from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from gateway.middleware.auth import verify_token
from gateway.middleware.rbac import require_analyst
from shared.observability import get_logger

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


@router.post("/query", response_model=QueryResponse, dependencies=[Depends(require_analyst)])
async def query_data(req: QueryRequest, request: Request):
    """自然语言查询数据 — 通过 HTTP dispatch 到 agent-layer"""
    trace_id = getattr(request.state, "trace_id", "")
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            # text2sql 不是 dispatch agent，是 agent-layer 的独立 endpoint /query
            resp = await client.post(
                f"{AGENT_LAYER_URL}/query",
                json={"question": req.question, "db_type": req.db_type},
            )
            resp.raise_for_status()
            result = resp.json()
            return QueryResponse(
                sql=result.get("sql", ""),
                data=result.get("data", []),
                explanation=result.get("explanation", ""),
                error=result.get("error"),
                trace_id=trace_id,
            )
    except httpx.HTTPStatusError as e:
        logger.error("query_dispatch_error", status=e.response.status_code)
        raise HTTPException(status_code=503, detail="Query service unavailable")
    except Exception as e:
        logger.error("query_error", error=str(e))
        raise HTTPException(status_code=503, detail="Query service unavailable")
