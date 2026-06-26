"""FanOutNode — 并行写入多个 sink (asyncio.gather)"""
from __future__ import annotations

import asyncio
from typing import Any

from dag_engine.nodes.base import BaseNode
from shared.observability import get_logger

logger = get_logger(__name__)


class FanOutNode(BaseNode):
    """并行 fan-out 节点：同时写入多个 sink"""

    node_type = "fan_out"

    def __init__(
        self,
        node_id: str,
        config: dict,
        pipeline_id: str = "",
        children: list[BaseNode] | None = None,
    ):
        super().__init__(node_id=node_id, config=config, pipeline_id=pipeline_id)
        self.children = children or []

    def add_child(self, node: BaseNode):
        self.children.append(node)

    async def process(self, state: dict[str, Any]) -> dict[str, Any]:
        """并行执行所有子 sink 节点"""
        if not self.children:
            logger.warning("fan_out_no_children", node_id=self.node_id)
            return state

        tasks = [child.safe_process(dict(state)) for child in self.children]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        sinks_written = list(state.get("sinks_written", []))
        errors = list(state.get("errors", []))

        for child, result in zip(self.children, results):
            if isinstance(result, Exception):
                errors.append({"node_id": child.node_id, "error": str(result)})
                logger.error("fan_out_child_error", child=child.node_id, error=str(result))
            else:
                sinks_written.extend(result.get("sinks_written", []))

        state["sinks_written"] = sinks_written
        state["errors"] = errors
        logger.info("fan_out_complete", node_id=self.node_id, children=len(self.children))
        return state
