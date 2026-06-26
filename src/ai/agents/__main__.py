"""
Agent Layer 容器入口

并行启动四个长生命周期 task：
1. AgentOrchestrator   — 注册 4 个 Agent + Redis Pub/Sub A2A 监听
2. MCP Server          — uvicorn :8002，对外暴露 dispatch + agent 监控接口
3. Alert Kafka Consumer — 订阅 dga-alerts，每条告警自动跑一次 pipeline
4. Feedback Aggregator  — 运行反馈聚合器

共享全局（orchestrator / streams_redis / pipeline_semaphore）集中在
ai.agents.pipeline 模块，consumer 与 mcp_app 均从该模块读取，
确保进程内只有一个实例。
"""

from __future__ import annotations

import asyncio

from common.observability import setup_logging, get_logger

from ai.agents.pipeline import start_orchestrator
from ai.agents.consumer import run_alert_consumer
from ai.agents.mcp_app import start_mcp_server

logger = get_logger(__name__)


async def main():
    setup_logging()
    logger.info("agent_layer_starting")
    from ai.agents.feedback_loop import start_feedback_aggregator
    await asyncio.gather(
        start_mcp_server(),
        start_orchestrator(),
        run_alert_consumer(),
        start_feedback_aggregator(),
    )


if __name__ == "__main__":
    asyncio.run(main())
