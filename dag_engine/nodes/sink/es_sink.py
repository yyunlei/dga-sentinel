"""
Elasticsearch 输出节点
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from dag_engine.nodes.base import BaseNode, logger


class ESSinkNode(BaseNode):
    """将事件写入 Elasticsearch"""

    node_type = "es_sink"

    async def process(self, state: dict[str, Any]) -> dict[str, Any]:
        condition = self.config.get("condition", "always")
        if condition != "always" and not state.get("is_dga", False):
            return state

        index_pattern = self.config.get("index", "dga-events-{date}")
        today = datetime.now(timezone.utc).strftime("%Y.%m.%d")
        index = index_pattern.replace("{date}", today)

        doc = {
            "trace_id": state.get("trace_id", ""),
            "event_id": state.get("event_id", ""),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "domain": state.get("domain", ""),
            "src_ip": state.get("src_ip", ""),
            "score": state.get("score", 0.0),
            "is_dga": state.get("is_dga", False),
            "family": state.get("family"),
            "family_confidence": state.get("family_confidence"),
            "model_version": state.get("model_version", ""),
            "pipeline_id": self.pipeline_id,
            "severity": state.get("severity", "LOW"),
            "features": state.get("features", {}),
            "rules_applied": state.get("rules_applied", []),
            "tenant_id": state.get("tenant_id", "default"),
        }

        es_client = state.get("_es_client")
        if es_client:
            await es_client.index(index=index, document=doc, id=doc["event_id"])
            logger.info("es_sink_indexed", index=index, domain=state.get("domain"))
        else:
            logger.debug("es_sink_dry_run", index=index, domain=state.get("domain"))

        state.setdefault("sinks_written", []).append(f"es:{index}")
        return state
