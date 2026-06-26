"""
统一运行时 — 同一套 DAG 支持 stream 和 batch 两种模式
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

from dag.engine import DAGEngine
from dag.loader import PipelineDefinition, load_pipeline
from dag.checkpoint import CheckpointManager
from common.observability import get_logger, ACTIVE_PIPELINES

logger = get_logger(__name__)


class StreamRuntime:
    """
    Stream 模式运行时 — Kafka 消费驱动
    每条消息触发一次 DAG 执行
    """

    def __init__(self, engine: DAGEngine, kafka_config: dict):
        self.engine = engine
        self.kafka_config = kafka_config
        self._running = False

    async def start(self, **context):
        """启动 Kafka 消费循环"""
        from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
        from elasticsearch import AsyncElasticsearch

        topic = self.kafka_config.get("topic", "dns-query-logs")
        group_id = self.kafka_config.get("group_id", f"dga-{self.engine.pipeline.name}")
        bootstrap = self.kafka_config.get("bootstrap_servers") or os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")

        consumer = AIOKafkaConsumer(
            topic,
            bootstrap_servers=bootstrap,
            group_id=group_id,
            auto_offset_reset=self.kafka_config.get("auto_offset_reset", "latest"),
            value_deserializer=lambda m: json.loads(m.decode()),
        )

        # 创建 Kafka Producer 和 ES Client 注入到 DAG 上下文
        producer = AIOKafkaProducer(bootstrap_servers=bootstrap)
        es_hosts = self.kafka_config.get("es_hosts", "http://elasticsearch:9200")
        es_client = AsyncElasticsearch(es_hosts)

        await consumer.start()
        await producer.start()
        self._running = True
        ACTIVE_PIPELINES.inc()
        logger.info("stream_runtime_started", pipeline=self.engine.pipeline.name, topic=topic)

        ctx = {
            **context,
            "kafka_producer": producer,
            "es_client": es_client,
        }

        try:
            async for msg in consumer:
                if not self._running:
                    break
                try:
                    await self.engine.run(msg.value, **ctx)
                    await self.engine.checkpoint.save_offset(
                        msg.topic, msg.partition, msg.offset
                    )
                except Exception as e:
                    logger.error("stream_process_error", error=str(e), offset=msg.offset)
        finally:
            await producer.stop()
            await es_client.close()
            await consumer.stop()
            ACTIVE_PIPELINES.dec()
            logger.info("stream_runtime_stopped", pipeline=self.engine.pipeline.name)

    def stop(self):
        self._running = False


class BatchRuntime:
    """
    Batch 模式运行时 — 文件/分区扫描驱动
    按天/小时重跑历史数据
    """

    def __init__(self, engine: DAGEngine):
        self.engine = engine

    async def run_file(self, file_path: str, **context) -> dict:
        """处理单个文件"""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        total = 0
        alerts = 0
        errors = 0

        ACTIVE_PIPELINES.inc()
        logger.info("batch_runtime_started", pipeline=self.engine.pipeline.name, file=file_path)

        try:
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    total += 1
                    try:
                        # 尝试 JSON 解析，否则当作纯文本
                        try:
                            message = json.loads(line)
                        except json.JSONDecodeError:
                            message = line

                        result = await self.engine.run(message, **context)
                        if result.get("is_dga"):
                            alerts += 1
                    except Exception as e:
                        errors += 1
                        logger.error("batch_process_error", error=str(e), line_num=total)
        finally:
            ACTIVE_PIPELINES.dec()

        stats = {"total": total, "alerts": alerts, "errors": errors}
        logger.info("batch_runtime_completed", pipeline=self.engine.pipeline.name, **stats)
        return stats

    async def run_directory(self, dir_path: str, pattern: str = "*.json", **context) -> dict:
        """处理目录下所有匹配文件"""
        path = Path(dir_path)
        total_stats = {"total": 0, "alerts": 0, "errors": 0, "files": 0}

        for file in sorted(path.glob(pattern)):
            stats = await self.run_file(str(file), **context)
            total_stats["total"] += stats["total"]
            total_stats["alerts"] += stats["alerts"]
            total_stats["errors"] += stats["errors"]
            total_stats["files"] += 1

        return total_stats


if __name__ == "__main__":
    import os
    from common.observability import setup_logging

    setup_logging()

    pipeline_file = os.environ.get(
        "DAG_PIPELINE", "dag_engine/pipelines/dga_realtime.yaml"
    )
    kafka_bootstrap = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
    es_hosts = os.environ.get("ES_HOSTS", "http://elasticsearch:9200")

    logger.info("dag_engine_starting", pipeline=pipeline_file)

    pipeline_def = load_pipeline(pipeline_file)
    ckpt = CheckpointManager(key_prefix=f"ckpt:{pipeline_def.name}:")
    engine = DAGEngine(pipeline_def, ckpt)

    kafka_cfg = {
        "topic": "dns-query-logs",
        "group_id": f"dga-{pipeline_def.name}",
        "bootstrap_servers": kafka_bootstrap,
        "auto_offset_reset": "latest",
        "es_hosts": es_hosts,
    }

    runtime = StreamRuntime(engine, kafka_cfg)
    asyncio.run(runtime.start())
