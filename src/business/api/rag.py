"""RAG 知识库检索路由 — /rag/query
POST {question, top_k?} → {answer, sources, query}
通过 HTTP 调用 agent-layer 的 ThreatKnowledgeRAG 引擎
"""
from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from business.middleware.rbac import require_analyst
from common.observability import get_logger

router = APIRouter()
logger = get_logger(__name__)

AGENT_LAYER_URL = "http://agent-layer:8002"


class RAGRequest(BaseModel):
    question: str
    top_k: int = 5


class RAGSource(BaseModel):
    content: str
    source: str
    category: str
    score: float


class RAGResponse(BaseModel):
    answer: str = ""
    sources: list[RAGSource] = []
    query: str = ""
    trace_id: str = ""


@router.post("/rag/query", response_model=RAGResponse, dependencies=[Depends(require_analyst)])
async def rag_query(req: RAGRequest, request: Request):
    """知识库检索 — 混合检索 + LLM 生成 + 来源引用"""
    trace_id = getattr(request.state, "trace_id", "")
    try:
        # 180s: BGE-M3 首次会从 HuggingFace 下载 ~2GB embedding 模型
        async with httpx.AsyncClient(timeout=180.0) as client:
            resp = await client.post(
                f"{AGENT_LAYER_URL}/rag/query",
                json={"question": req.question, "top_k": req.top_k},
            )
            resp.raise_for_status()
            result = resp.json()
            return RAGResponse(
                answer=result.get("answer", ""),
                sources=result.get("sources", []),
                query=result.get("query", req.question),
                trace_id=trace_id,
            )
    except httpx.HTTPStatusError as e:
        logger.error("rag_dispatch_error", status=e.response.status_code)
        raise HTTPException(status_code=503, detail="RAG service unavailable")
    except Exception as e:
        logger.error("rag_error", error=str(e))
        raise HTTPException(status_code=503, detail="RAG service unavailable")
