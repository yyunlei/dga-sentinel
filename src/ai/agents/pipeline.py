"""
Pipeline 共享状态与逻辑模块

所有模块共享的三个全局对象在此集中管理：
  - _orchestrator        AgentOrchestrator 单例
  - _streams_redis       decode_responses=True 的 Redis 客户端（专用于 Streams）
  - _pipeline_semaphore  Kafka-driven pipeline 并发上限（默认 5）

其他模块通过 get_orchestrator() / get_streams_redis() 读取，
由 start_orchestrator() 在启动时初始化，确保全系统共用同一实例。
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone

from common.observability import get_logger

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


def get_orchestrator():
    """返回全局 AgentOrchestrator 单例（consumer / mcp_app 通过此读取）。"""
    return _orchestrator


def get_streams_redis():
    """返回全局 Streams Redis 客户端单例。"""
    return _streams_redis


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
# Pipeline — HTTP 与 Kafka consumer 共用
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


# ──────────────────────────────────────────────────────────────────────
# Orchestrator 初始化 — 设置共享全局
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
