"""
AgentOrchestrator — Agent 注册表与调度中心
管理所有 Agent 的生命周期，提供 HTTP dispatch API
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from agent_layer.a2a.bus import AgentBus
from agent_layer.base_agent import BaseAgent, AgentState
from shared.observability import get_logger

logger = get_logger(__name__)


class DispatchRequest(BaseModel):
    agent: str
    payload: dict = {}
    trace_id: str = ""


class AgentOrchestrator:
    """
    Agent 编排器：
    - 维护 Agent 注册表
    - 提供 dispatch() 调度接口
    - 管理 Agent 生命周期 (start_all / stop_all)
    """

    def __init__(self, bus: AgentBus):
        self.bus = bus
        self._agents: dict[str, BaseAgent] = {}
        self._listen_tasks: list[asyncio.Task] = []

    def register(self, agent: BaseAgent) -> None:
        self._agents[agent.name] = agent
        logger.info("agent_registered", agent=agent.name)

    def get_agent(self, name: str) -> BaseAgent | None:
        return self._agents.get(name)

    def list_agents(self) -> list[str]:
        return list(self._agents.keys())

    async def dispatch(self, agent_name: str, payload: dict, trace_id: str = "") -> AgentState:
        agent = self._agents.get(agent_name)
        if not agent:
            raise KeyError(f"Agent '{agent_name}' not registered")
        return await agent.run(payload, trace_id=trace_id)

    async def start_all(self) -> None:
        """启动所有 Agent 的 A2A 监听"""
        for name in self._agents:
            task = asyncio.create_task(self.bus.listen(name))
            self._listen_tasks.append(task)
        logger.info("orchestrator_started", agents=self.list_agents())

    async def stop_all(self) -> None:
        for task in self._listen_tasks:
            task.cancel()
        self._listen_tasks.clear()
        logger.info("orchestrator_stopped")

    def create_app(self) -> FastAPI:
        """创建 dispatch HTTP API"""
        app = FastAPI(title="Agent Orchestrator")

        @app.get("/agents")
        async def list_agents():
            return {"agents": self.list_agents()}

        @app.post("/dispatch")
        async def dispatch(req: DispatchRequest):
            try:
                result = await self.dispatch(req.agent, req.payload, req.trace_id)
                return {"status": "ok", "result": result}
            except KeyError as e:
                raise HTTPException(status_code=404, detail=str(e))
            except Exception as e:
                logger.error("dispatch_error", agent=req.agent, error=str(e))
                raise HTTPException(status_code=500, detail=str(e))

        @app.get("/health")
        async def health():
            return {"status": "ok", "agents": self.list_agents()}

        return app
