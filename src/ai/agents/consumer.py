"""
Kafka Alert Consumer

订阅 dga-alerts topic，对每条告警异步触发一次 run_pipeline。
共享全局（orchestrator、semaphore）由 pipeline 模块持有。
"""

from __future__ import annotations

import asyncio
import json

from common.observability import get_logger
from ai.agents.pipeline import _bounded_pipeline, get_orchestrator

logger = get_logger(__name__)


async def run_alert_consumer():
    """订阅 Kafka dga-alerts topic，每条告警异步触发一次 pipeline。"""
    from aiokafka import AIOKafkaConsumer
    from common.config import get_settings

    settings = get_settings()
    bootstrap = settings.kafka_bootstrap_servers
    topic = settings.kafka_alert_topic

    while get_orchestrator() is None:
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
