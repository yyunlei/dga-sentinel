"""
Agent Layer 容器入口

并行启动三个长生命周期 task：
1. AgentOrchestrator   — 注册 4 个 Agent + Redis Pub/Sub A2A 监听
2. MCP Server          — uvicorn :8002，对外暴露 dispatch + agent 监控接口
3. Alert Kafka Consumer — 订阅 dga-alerts，每条告警自动跑一次 pipeline

Agent 监控数据（执行历史 / A2A 消息流）持久化在 Redis Streams，
重启不丢失，多消费者可同时读：
  - agent:run_history   (MAXLEN ~ 200)
  - agent:a2a_messages  (MAXLEN ~ 100)
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone

import uvicorn

from ai.agents.orchestrator import DispatchRequest
from common.observability import setup_logging, get_logger

logger = get_logger(__name__)

# 全局引用 — 由 start_orchestrator 初始化
_orchestrator = None
_streams_redis = None  # decode_responses=True client，专用于 Streams 读写
_pipeline_semaphore = asyncio.Semaphore(5)  # Kafka-driven pipeline 并发上限

# Redis Stream 常量
RUN_STREAM = "agent:run_history"
A2A_STREAM = "agent:a2a_messages"
RUN_STREAM_MAXLEN = 200
A2A_STREAM_MAXLEN = 100


# ──────────────────────────────────────────────────────────────────────
# Stream helpers — 读写 Agent 监控数据
# ──────────────────────────────────────────────────────────────────────


async def _record_run(record: dict) -> None:
    """写一条运行历史到 Redis stream；Redis 不可用时静默丢弃。"""
    if _streams_redis is None:
        return
    try:
        clean = {k: ("" if v is None else str(v)) for k, v in record.items()}
        await _streams_redis.xadd(
            RUN_STREAM, clean, maxlen=RUN_STREAM_MAXLEN, approximate=True,
        )
    except Exception as e:
        logger.warning("run_record_failed", error=str(e))


async def _record_a2a_entry(entry: dict) -> None:
    """写一条 A2A 消息到 Redis stream。"""
    if _streams_redis is None:
        return
    try:
        clean = {k: ("" if v is None else str(v)) for k, v in entry.items()}
        await _streams_redis.xadd(
            A2A_STREAM, clean, maxlen=A2A_STREAM_MAXLEN, approximate=True,
        )
    except Exception as e:
        logger.warning("a2a_record_failed", error=str(e))


async def _read_run_history(limit: int) -> list[dict]:
    if _streams_redis is None:
        return []
    try:
        entries = await _streams_redis.xrevrange(RUN_STREAM, count=limit)
    except Exception as e:
        logger.warning("run_read_failed", error=str(e))
        return []
    out: list[dict] = []
    for _id, fields in entries:
        try:
            out.append({
                "timestamp": fields.get("timestamp", ""),
                "agent": fields.get("agent", ""),
                "action": fields.get("action", ""),
                "duration_ms": int(fields.get("duration_ms") or 0),
                "status": fields.get("status", "success"),
                "trace_id": fields.get("trace_id", ""),
            })
        except Exception:
            continue
    return out


async def _read_a2a_messages(limit: int) -> list[dict]:
    if _streams_redis is None:
        return []
    try:
        entries = await _streams_redis.xrevrange(A2A_STREAM, count=limit)
    except Exception as e:
        logger.warning("a2a_read_failed", error=str(e))
        return []
    return [
        {
            "timestamp": fields.get("timestamp", ""),
            "from_agent": fields.get("from_agent", ""),
            "to_agent": fields.get("to_agent", ""),
            "message": fields.get("message", ""),
        }
        for _id, fields in entries
    ]


def _record_a2a_sync(msg) -> None:
    """AgentBus.on_send 同步回调；后台 task 写 Redis stream。"""
    try:
        asyncio.create_task(_record_a2a_entry({
            "timestamp": msg.timestamp,
            "from_agent": msg.from_agent,
            "to_agent": msg.to_agent,
            "message": f"[{msg.action}] {msg.payload.get('domain', '')}",
        }))
    except RuntimeError:
        pass


# ──────────────────────────────────────────────────────────────────────
# Pipeline — 模块级，HTTP 与 Kafka consumer 共用
# ──────────────────────────────────────────────────────────────────────


async def run_pipeline(payload: dict, trace_id: str = "") -> dict:
    """
    链式调用: triage → (explain + threat_intel 并行) → response

    所有阶段执行结果都写入 RUN_STREAM；
    阶段间 A2A 消息写入 A2A_STREAM。
    """
    if _orchestrator is None:
        raise RuntimeError("Orchestrator not ready")

    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    domain = payload.get("domain", "")
    results: dict = {}

    # 1) triage — _skip_a2a 让 agent 不再自动广播 A2A，由本函数集中记录
    t0 = time.time()
    triage_payload = {**payload, "_skip_a2a": True}
    triage_result = await _orchestrator.dispatch("triage", triage_payload, trace_id)
    await _record_run({
        "timestamp": ts, "agent": "triage", "action": "pipeline",
        "duration_ms": int((time.time() - t0) * 1000),
        "status": "error" if triage_result.get("error") else "success",
        "trace_id": trace_id,
    })
    results["triage"] = triage_result
    severity = triage_result.get("output", {}).get("severity", "LOW")

    await _record_a2a_entry({
        "timestamp": ts, "from_agent": "triage", "to_agent": "explain",
        "message": f"[explain_alert] {domain}",
    })
    await _record_a2a_entry({
        "timestamp": ts, "from_agent": "triage", "to_agent": "threat_intel",
        "message": f"[query_ioc] {domain}",
    })

    # 2) explain + threat_intel 并行（共享 wall-clock 计时）
    explain_payload = {**payload, "severity": severity}
    intel_payload = {"domain": domain, "src_ip": payload.get("src_ip", "")}
    t_par = time.time()
    explain_result, intel_result = await asyncio.gather(
        _orchestrator.dispatch("explain", explain_payload, trace_id),
        _orchestrator.dispatch("threat_intel", intel_payload, trace_id),
    )
    d_par = int((time.time() - t_par) * 1000)
    await _record_run({
        "timestamp": ts, "agent": "explain", "action": "pipeline",
        "duration_ms": d_par,
        "status": "error" if explain_result.get("error") else "success",
        "trace_id": trace_id,
    })
    await _record_run({
        "timestamp": ts, "agent": "threat_intel", "action": "pipeline",
        "duration_ms": d_par,
        "status": "error" if intel_result.get("error") else "success",
        "trace_id": trace_id,
    })
    results["explain"] = explain_result
    results["threat_intel"] = intel_result

    threat_level = intel_result.get("output", {}).get("threat_level", "low")
    await _record_a2a_entry({
        "timestamp": ts, "from_agent": "explain", "to_agent": "response",
        "message": f"[suggest_response] {domain}",
    })
    await _record_a2a_entry({
        "timestamp": ts, "from_agent": "threat_intel", "to_agent": "response",
        "message": f"[enrich_response] {domain} threat={threat_level}",
    })

    # 3) response
    resp_payload = {**payload, "severity": severity}
    t0 = time.time()
    response_result = await _orchestrator.dispatch("response", resp_payload, trace_id)
    await _record_run({
        "timestamp": ts, "agent": "response", "action": "pipeline",
        "duration_ms": int((time.time() - t0) * 1000),
        "status": "error" if response_result.get("error") else "success",
        "trace_id": trace_id,
    })
    results["response"] = response_result

    return {"status": "ok", "results": results, "severity": severity}


# ──────────────────────────────────────────────────────────────────────
# Long-lived tasks
# ──────────────────────────────────────────────────────────────────────


async def start_orchestrator():
    """初始化 Agent Orchestrator + AgentBus + Streams Redis 客户端。"""
    global _orchestrator, _streams_redis

    from ai.agents.a2a.bus import AgentBus
    from ai.agents.orchestrator import AgentOrchestrator
    from ai.agents.agents.triage_agent import TriageAgent
    from ai.agents.agents.explain_agent import ExplainAgent
    from ai.agents.agents.threat_intel_agent import ThreatIntelAgent
    from ai.agents.agents.response_agent import ResponseAgent
    from common.config import get_settings

    settings = get_settings()

    try:
        import redis.asyncio as aioredis
        bus_redis = aioredis.from_url(settings.redis_url)
        _streams_redis = aioredis.from_url(settings.redis_url, decode_responses=True)
        bus = AgentBus(redis_client=bus_redis, on_send=_record_a2a_sync)
    except Exception as e:
        logger.warning("redis_unavailable_for_bus", error=str(e))
        _streams_redis = None
        bus = AgentBus(on_send=_record_a2a_sync)

    orchestrator = AgentOrchestrator(bus)
    orchestrator.register(TriageAgent(bus))
    orchestrator.register(ExplainAgent(bus))
    orchestrator.register(ThreatIntelAgent(bus))
    orchestrator.register(ResponseAgent(bus))

    _orchestrator = orchestrator
    await orchestrator.start_all()
    logger.info("orchestrator_running", agents=orchestrator.list_agents())

    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        await orchestrator.stop_all()


async def start_alert_consumer():
    """订阅 Kafka dga-alerts topic，每条告警异步触发一次 pipeline。"""
    from aiokafka import AIOKafkaConsumer
    from common.config import get_settings

    settings = get_settings()
    bootstrap = settings.kafka_bootstrap_servers
    topic = settings.kafka_alert_topic

    while _orchestrator is None:
        await asyncio.sleep(0.5)

    consumer = AIOKafkaConsumer(
        topic,
        bootstrap_servers=bootstrap,
        group_id="agent-layer-pipeline",
        auto_offset_reset="latest",
        enable_auto_commit=True,
        value_deserializer=lambda m: json.loads(m.decode("utf-8")) if m else {},
    )

    for attempt in range(30):
        try:
            await consumer.start()
            break
        except Exception as e:
            logger.warning(
                "kafka_consumer_connect_retry", attempt=attempt, error=str(e),
            )
            await asyncio.sleep(2)
    else:
        logger.error("kafka_consumer_connect_failed", topic=topic)
        return

    logger.info("alert_consumer_started", topic=topic, bootstrap=bootstrap)

    try:
        async for msg in consumer:
            event = msg.value or {}
            domain = event.get("domain", "")
            if not domain:
                continue
            trace_id = event.get("trace_id") or event.get("event_id") or ""
            payload = {
                "domain": domain,
                "src_ip": event.get("src_ip", ""),
                "score": event.get("score", 0.0),
                "family": event.get("family"),
                "severity": event.get("severity", "LOW"),
                "event_id": event.get("event_id", ""),
            }
            asyncio.create_task(_bounded_pipeline(payload, trace_id))
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error("alert_consumer_loop_error", error=str(e))
    finally:
        await consumer.stop()
        logger.info("alert_consumer_stopped")


async def _bounded_pipeline(payload: dict, trace_id: str) -> None:
    """Semaphore 限流 + 异常隔离的 pipeline 包装器。"""
    async with _pipeline_semaphore:
        try:
            await run_pipeline(payload, trace_id)
        except Exception as e:
            logger.error(
                "auto_pipeline_failed",
                domain=payload.get("domain", ""), error=str(e),
            )


async def start_mcp_server():
    """启动 MCP Server on port 8002 — dispatch / 监控 / RAG / text2sql 接口"""
    from ai.agents.mcp.server import build_app
    from fastapi import HTTPException, Query

    app = build_app()

    @app.post("/dispatch")
    async def dispatch(req: DispatchRequest):
        if _orchestrator is None:
            raise HTTPException(503, "Orchestrator not ready")
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        t0 = time.time()
        try:
            result = await _orchestrator.dispatch(req.agent, req.payload, req.trace_id)
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
        if _orchestrator is None:
            raise HTTPException(503, "Orchestrator not ready")
        return await run_pipeline(req.payload, req.trace_id)

    @app.get("/agents")
    async def list_agents():
        if _orchestrator is None:
            return {"agents": []}
        names = _orchestrator.list_agents()
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


async def main():
    setup_logging()
    logger.info("agent_layer_starting")
    from ai.agents.feedback_loop import start_feedback_aggregator
    await asyncio.gather(
        start_mcp_server(),
        start_orchestrator(),
        start_alert_consumer(),
        start_feedback_aggregator(),
    )


if __name__ == "__main__":
    asyncio.run(main())
