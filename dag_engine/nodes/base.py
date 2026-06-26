"""
DAG 节点基类 — 所有节点继承此类
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any

from shared.observability import DAG_NODE_LATENCY, DAG_NODE_ERRORS, get_logger, get_tracer

logger = get_logger(__name__)
_tracer = get_tracer(__name__)


class BaseNode(ABC):
    """DAG 节点抽象基类"""

    node_type: str = "base"

    def __init__(self, node_id: str, config: dict, pipeline_id: str = ""):
        self.node_id = node_id
        self.config = config
        self.pipeline_id = pipeline_id

    @abstractmethod
    async def process(self, state: dict[str, Any]) -> dict[str, Any]:
        """
        处理输入状态，返回更新后的状态
        state 是 LangGraph 的状态字典，节点间通过 state 传递数据
        """
        ...

    async def safe_process(self, state: dict[str, Any]) -> dict[str, Any]:
        """带指标采集、OTel span 和错误处理的 process 包装"""
        start = time.perf_counter()

        # OTel span（如果 tracer 可用）
        span_ctx = None
        if _tracer:
            span_ctx = _tracer.start_as_current_span(
                f"dag.{self.node_id}",
                attributes={
                    "dag.pipeline_id": self.pipeline_id,
                    "dag.node_id": self.node_id,
                    "dag.node_type": self.node_type,
                },
            )

        try:
            if span_ctx:
                with span_ctx:
                    result = await self.process(state)
            else:
                result = await self.process(state)

            elapsed = time.perf_counter() - start
            DAG_NODE_LATENCY.labels(
                pipeline_id=self.pipeline_id, node_id=self.node_id
            ).observe(elapsed)
            return result
        except Exception as e:
            DAG_NODE_ERRORS.labels(
                pipeline_id=self.pipeline_id,
                node_id=self.node_id,
                error_type=type(e).__name__,
            ).inc()
            logger.error(
                "node_error",
                node_id=self.node_id,
                pipeline_id=self.pipeline_id,
                error=str(e),
            )
            # 将错误记录到 state 中，不中断 pipeline
            errors = state.get("errors", [])
            errors.append({"node_id": self.node_id, "error": str(e)})
            state["errors"] = errors
            return state
