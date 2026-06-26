"""
Agent 消息总线 — 基于 Redis Pub/Sub 的 A2A 通信
"""

from __future__ import annotations

import asyncio
from typing import Callable, Awaitable

from agent_layer.a2a.protocol import A2AMessage
from shared.observability import get_logger

logger = get_logger(__name__)


class AgentBus:
    """
    Agent 消息总线
    使用 Redis Pub/Sub 实现 Agent 间异步通信
    """

    def __init__(self, redis_client=None, on_send=None):
        self.redis = redis_client
        self._handlers: dict[str, Callable] = {}
        self._on_send: Callable | None = on_send

    async def send(self, msg: A2AMessage) -> None:
        """发送消息到目标 Agent"""
        if self._on_send:
            self._on_send(msg)

        channel = f"agent:{msg.to_agent}:inbox"
        if self.redis:
            await self.redis.publish(channel, msg.to_json())
            logger.info("a2a_sent", from_agent=msg.from_agent, to_agent=msg.to_agent, action=msg.action)
        else:
            # 无 Redis 时直接调用本地 handler
            handler = self._handlers.get(msg.to_agent)
            if handler:
                await handler(msg)
            else:
                logger.warning("a2a_no_handler", to_agent=msg.to_agent)

    def register_handler(self, agent_name: str, handler: Callable[[A2AMessage], Awaitable]) -> None:
        """注册 Agent 消息处理器"""
        self._handlers[agent_name] = handler
        logger.info("agent_handler_registered", agent=agent_name)

    async def listen(self, agent_name: str) -> None:
        """监听 Agent 收件箱（需要 Redis）"""
        if not self.redis:
            logger.warning("a2a_listen_no_redis", agent=agent_name)
            return

        channel = f"agent:{agent_name}:inbox"
        pubsub = self.redis.pubsub()
        await pubsub.subscribe(channel)

        logger.info("a2a_listening", agent=agent_name, channel=channel)
        async for message in pubsub.listen():
            if message["type"] == "message":
                a2a_msg = A2AMessage.from_json(message["data"])
                handler = self._handlers.get(agent_name)
                if handler:
                    await handler(a2a_msg)
