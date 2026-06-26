"""
Kafka 消费节点 — 从 Kafka topic 读取 DNS 日志
"""

from __future__ import annotations

from typing import Any

from dag_engine.nodes.base import BaseNode


class KafkaConsumerNode(BaseNode):
    """从 Kafka 消费消息（由运行时驱动，此节点处理单条消息）"""

    node_type = "kafka_consumer"

    async def process(self, state: dict[str, Any]) -> dict[str, Any]:
        # 运行时已将消息放入 state["raw_message"]
        # 此节点负责基础校验和元数据注入
        raw = state.get("raw_message", {})
        state["raw_data"] = raw
        state["source"] = "kafka"
        state["topic"] = self.config.get("topic", "unknown")
        return state
