"""
MCP Server — FastAPI :8002

暴露 7 个端点供外部调用：
  POST /dispatch             — 单 agent dispatch
  POST /dispatch/pipeline    — 全链路 pipeline
  GET  /agents               — 列出 agents + 运行指标
  GET  /agents/exec-history  — 执行历史（Redis Stream）
  GET  /agents/a2a-messages  — A2A 消息流（Redis Stream）
  POST /rag/query            — RAG 知识库查询
  POST /query                — Text2SQL 查询

共享全局（orchestrator、streams_redis）由 pipeline 模块持有。
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

import uvicorn

from ai.agents.orchestrator import DispatchRequest
from ai.agents.pipeline import (
    RUN_STREAM_MAXLEN,
    _read_a2a_messages,
    _read_run_history,
    _record_run,
    get_orchestrator,
    run_pipeline,
)
from common.observability import get_logger

logger = get_logger(__name__)


async def start_mcp_server():
    """启动 MCP Server on port 8002 — dispatch / 监控 / RAG / text2sql 接口"""
    from fastapi import HTTPException, Query

    from ai.agents.mcp.server import build_app

    app = build_app()

    @app.post("/dispatch")
    async def dispatch(req: DispatchRequest):
        orchestrator = get_orchestrator()
        if orchestrator is None:
            raise HTTPException(503, "Orchestrator not ready")
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        t0 = time.time()
        try:
            result = await orchestrator.dispatch(req.agent, req.payload, req.trace_id)
            await _record_run({
                "timestamp": ts, "agent": req.agent, "action": "dispatch",
                "duration_ms": int((time.time() - t0) * 1000),
                "status": "error" if result.get("error") else "success",
                "trace_id": req.trace_id or "",
            })
            return {"status": "ok", "result": result}
        except KeyError as e:
            raise HTTPException(404, str(e))
        except Exception as e:
            await _record_run({
                "timestamp": ts, "agent": req.agent, "action": "dispatch",
                "duration_ms": int((time.time() - t0) * 1000),
                "status": "error", "trace_id": req.trace_id or "",
            })
            logger.error("dispatch_error", agent=req.agent, error=str(e))
            raise HTTPException(500, str(e))

    @app.post("/dispatch/pipeline")
    async def dispatch_pipeline(req: DispatchRequest):
        if get_orchestrator() is None:
            raise HTTPException(503, "Orchestrator not ready")
        return await run_pipeline(req.payload, req.trace_id)

    @app.get("/agents")
    async def list_agents():
        orchestrator = get_orchestrator()
        if orchestrator is None:
            return {"agents": []}
        names = orchestrator.list_agents()
        records = await _read_run_history(RUN_STREAM_MAXLEN)
        agents_metrics: list[dict] = []
        for name in names:
            recs = [r for r in records if r["agent"] == name]
            n = len(recs)
            avg = (sum(r["duration_ms"] for r in recs) / n) if n else 0.0
            err = sum(1 for r in recs if r["status"] == "error")
            err_rate = (err / n * 100) if n else 0.0
            agents_metrics.append({
                "name": name,
                "status": "online",
                "execCount": n,
                "avgLatency": round(avg, 1),
                "errorRate": round(err_rate, 1),
            })
        return {"agents": agents_metrics}

    @app.get("/agents/exec-history")
    async def get_run_history(limit: int = Query(50, le=200)):
        return {"records": await _read_run_history(limit)}

    @app.get("/agents/a2a-messages")
    async def get_a2a_messages(limit: int = Query(20, le=100)):
        return {"messages": await _read_a2a_messages(limit)}

    @app.post("/rag/query")
    async def rag_query(body: dict):
        from ai.agents.rag.engine import ThreatKnowledgeRAG
        rag = ThreatKnowledgeRAG.get_instance()
        question = body.get("question", "")
        top_k = body.get("top_k", 5)
        if not question:
            return {"answer": "", "sources": [], "query": ""}
        return await rag.query(question, top_k=top_k)

    @app.post("/query")
    async def text2sql_query(body: dict):
        from ai.agents.text2sql.engine import Text2SQLEngine
        question = body.get("question", "")
        db_type = body.get("db_type", "starrocks")
        if not question:
            return {"sql": "", "data": [], "explanation": "", "error": "empty question"}
        try:
            engine = Text2SQLEngine(db_type=db_type)
            return await engine.query(question)
        except Exception as e:
            logger.error("text2sql_error", error=str(e))
            return {"sql": "", "data": [], "explanation": "", "error": str(e)}

    config = uvicorn.Config(app, host="0.0.0.0", port=8002, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()
