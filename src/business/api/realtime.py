"""
实时数据 WebSocket 端点 — /ws/realtime
消费 Kafka dga-alerts topic，通过 WebSocket 推送真实告警 JSON
"""

from __future__ import annotations

import json
import asyncio
from contextlib import suppress

import httpx
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jose import JWTError, jwt
from common.config import get_settings
from common.observability import get_logger
from common.utils.es_compat import ES8_HEADERS
from common.utils.time import events_index_wildcard

logger = get_logger(__name__)

router = APIRouter()

# Connected WebSocket clients
_clients: set[WebSocket] = set()


async def _send_recent_alerts(websocket: WebSocket, limit: int = 50, min_score: float = 0.7) -> None:
    """WS 建连后立即推送最近 N 条历史告警，避免冷启动空白。

    顺序：按 timestamp asc 推送（旧→新），前端 unshift 后最新自然落在顶部。
    """
    settings = get_settings()
    es_base = settings.es_hosts.split(",")[0].strip()
    url = f"{es_base}/{events_index_wildcard()}/_search"
    body = {
        "query": {"range": {"score": {"gte": min_score}}},
        "sort": [{"timestamp": "desc"}],
        "size": limit,
        "_source": [
            "event_id", "timestamp", "domain", "src_ip", "score",
            "severity", "family", "is_dga", "acknowledged", "pipeline_id",
        ],
    }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.post(url, json=body, headers=ES8_HEADERS)
            r.raise_for_status()
            hits = r.json().get("hits", {}).get("hits", [])
    except Exception as e:
        logger.warning("ws_history_query_failed", error=str(e))
        return

    # asc 顺序推送：最旧的先发，最新的最后到，前端 unshift 后最新位于顶部
    for h in reversed(hits):
        src = h.get("_source", {})
        with suppress(Exception):
            await websocket.send_json({"type": "alert", "data": src})

    logger.info("ws_history_sent", count=len(hits))


async def _kafka_consumer_loop():
    """Background task: consume Kafka dga-alerts and broadcast to WebSocket clients."""
    settings = get_settings()
    try:
        from aiokafka import AIOKafkaConsumer
    except ImportError:
        logger.warning("aiokafka_not_installed, skipping kafka consumer")
        return

    consumer = AIOKafkaConsumer(
        settings.kafka_alert_topic,
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id="gateway-ws-realtime",
        auto_offset_reset="latest",
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
    )
    try:
        await consumer.start()
        logger.info("kafka_ws_consumer_started", topic=settings.kafka_alert_topic)
        async for msg in consumer:
            alert_json = msg.value
            payload = {"type": "alert", "data": alert_json}
            dead: list[WebSocket] = []
            for ws in _clients.copy():
                try:
                    await ws.send_json(payload)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                _clients.discard(ws)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error("kafka_ws_consumer_error", error=str(e))
    finally:
        with suppress(Exception):
            await consumer.stop()


# Start Kafka consumer as a background task on first import
_kafka_task: asyncio.Task | None = None


def _ensure_kafka_task():
    global _kafka_task
    if _kafka_task is None or _kafka_task.done():
        try:
            loop = asyncio.get_running_loop()
            _kafka_task = loop.create_task(_kafka_consumer_loop())
        except RuntimeError:
            pass


@router.websocket("/ws/realtime")
async def websocket_realtime(websocket: WebSocket):
    """实时数据 WebSocket 端点 — 推送 Kafka dga-alerts 告警"""
    # WebSocket 认证：从 query param 读取 token
    settings = get_settings()
    token = websocket.query_params.get("token", "")
    if not settings.is_dev:
        if not token:
            await websocket.close(code=4001, reason="Missing token")
            return
        try:
            jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        except JWTError:
            await websocket.close(code=4003, reason="Invalid token")
            return

    await websocket.accept()
    _clients.add(websocket)
    _ensure_kafka_task()
    logger.info("websocket_connected", client=str(websocket.client))

    try:
        await websocket.send_json({
            "type": "stats",
            "data": {
                "totalToday": 0,
                "dgaHits": 0,
                "hitRate": 0,
                "p95Latency": 0,
            }
        })

        # 冷启动填充：推送最近 50 条历史告警，避免面板初始为空
        await _send_recent_alerts(websocket, limit=50, min_score=0.7)

        # Keep connection alive, listen for client messages
        while True:
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=30)
            except asyncio.TimeoutError:
                # Send heartbeat
                await websocket.send_json({"type": "heartbeat"})
    except WebSocketDisconnect:
        logger.info("websocket_disconnected", client=str(websocket.client))
    except Exception as e:
        logger.error("websocket_error", error=str(e))
        with suppress(Exception):
            await websocket.close()
    finally:
        _clients.discard(websocket)
