"""
Kafka 输出节点 — 将告警写入 Kafka topic
"""

from __future__ import annotations

from typing import Any

from common.schemas import DGAEvent
from dag.nodes.base import BaseNode, logger


class KafkaSinkNode(BaseNode):
    """将告警事件写入 Kafka topic"""

    node_type = "kafka_sink"

    async def process(self, state: dict[str, Any]) -> dict[str, Any]:
        condition = self.config.get("condition", "score >= threshold")

        if not self._check_condition(state, condition):
            return state

        topic = self.config.get("topic", "dga-alerts")
        event = self._build_event(state)

        # 实际 Kafka 生产者由运行时注入
        producer = state.get("_kafka_producer")
        if producer:
            await producer.send_and_wait(topic, event.model_dump_json().encode())
            logger.info("kafka_sink_sent", topic=topic, domain=event.domain)
        else:
            logger.debug("kafka_sink_dry_run", topic=topic, domain=event.domain)

        state.setdefault("sinks_written", []).append(f"kafka:{topic}")
        return state

    @staticmethod
    def _build_event(state: dict) -> DGAEvent:
        """从 pipeline state 构造 DGAEvent(dag→agents 告警契约)。"""
        kwargs: dict[str, Any] = {
            "domain": state.get("domain", ""),
            "src_ip": state.get("src_ip", ""),
            "score": state.get("score", 0.0),
            "is_dga": state.get("is_dga", False),
            "family": state.get("family"),
            "model_version": state.get("model_version", ""),
            "severity": state.get("severity", "LOW"),
            "rules_applied": state.get("rules_applied", []),
            "pipeline_id": state.get("pipeline_id", ""),
            "tenant_id": state.get("tenant_id", "default"),
        }
        # 仅在 state 中存在时覆盖 uuid 默认值,避免空字符串污染
        if state.get("trace_id"):
            kwargs["trace_id"] = state["trace_id"]
        if state.get("event_id"):
            kwargs["event_id"] = state["event_id"]
        return DGAEvent(**kwargs)

    @staticmethod
    def _check_condition(state: dict, condition: str) -> bool:
        if condition == "always":
            return True
        if condition == "score >= threshold":
            return state.get("score", 0) >= state.get("threshold", 0.7)
        return state.get("is_dga", False)
