"""
BaseAgent — Agent 抽象基类
6 阶段生命周期: perceive → plan → act → reflect → output
基于 LangGraph StateGraph 实现状态机驱动
"""

from __future__ import annotations

import abc
import time
from typing import Any, TypedDict

from langgraph.graph import StateGraph, END

from agent_layer.a2a.bus import AgentBus
from agent_layer.a2a.protocol import A2AMessage
from shared.observability import get_logger

logger = get_logger(__name__)


class AgentState(TypedDict, total=False):
    """Agent 通用状态"""
    # 输入
    input_data: dict
    trace_id: str
    # 感知阶段
    context: dict
    # 规划阶段
    plan: list[str]
    # 执行阶段
    tool_results: list[dict]
    # 反思阶段
    reflection: str
    confidence: float
    # 输出阶段
    output: dict
    error: str | None
    # 元数据
    agent_name: str
    start_time: float
    duration_ms: float


class BaseAgent(abc.ABC):
    """
    Agent 抽象基类 — 6 阶段生命周期

    子类必须实现:
    - perceive(): 感知输入，构建上下文
    - plan(): 制定执行计划
    - act(): 执行工具调用
    - reflect(): 反思结果质量
    - format_output(): 格式化最终输出
    """

    name: str = "base"

    def __init__(self, bus: AgentBus | None = None, tools: list[Any] | None = None):
        self.bus = bus
        self.tools = tools or []
        self._graph = self._build_graph()
        self.compiled = self._graph.compile()
        if bus:
            bus.register_handler(self.name, self._handle_a2a)

    def _build_graph(self) -> StateGraph:
        graph = StateGraph(AgentState)

        graph.add_node("perceive", self._perceive_wrapper)
        graph.add_node("plan", self._plan_wrapper)
        graph.add_node("act", self._act_wrapper)
        graph.add_node("reflect", self._reflect_wrapper)
        graph.add_node("output", self._output_wrapper)

        graph.set_entry_point("perceive")
        graph.add_edge("perceive", "plan")
        graph.add_edge("plan", "act")
        graph.add_edge("act", "reflect")
        graph.add_edge("reflect", "output")
        graph.add_edge("output", END)

        return graph

    # --- Lifecycle wrappers (add logging + error handling) ---

    async def _perceive_wrapper(self, state: AgentState) -> AgentState:
        state["start_time"] = time.time()
        state["agent_name"] = self.name
        try:
            return await self.perceive(state)
        except Exception as e:
            logger.error("agent_perceive_error", agent=self.name, error=str(e))
            state["error"] = str(e)
            return state

    async def _plan_wrapper(self, state: AgentState) -> AgentState:
        if state.get("error"):
            return state
        try:
            return await self.plan(state)
        except Exception as e:
            logger.error("agent_plan_error", agent=self.name, error=str(e))
            state["error"] = str(e)
            return state

    async def _act_wrapper(self, state: AgentState) -> AgentState:
        if state.get("error"):
            return state
        try:
            return await self.act(state)
        except Exception as e:
            logger.error("agent_act_error", agent=self.name, error=str(e))
            state["error"] = str(e)
            return state

    async def _reflect_wrapper(self, state: AgentState) -> AgentState:
        if state.get("error"):
            return state
        try:
            return await self.reflect(state)
        except Exception as e:
            logger.error("agent_reflect_error", agent=self.name, error=str(e))
            state["error"] = str(e)
            return state

    async def _output_wrapper(self, state: AgentState) -> AgentState:
        try:
            state = await self.format_output(state)
        except Exception as e:
            logger.error("agent_output_error", agent=self.name, error=str(e))
            state["error"] = str(e)
        state["duration_ms"] = (time.time() - state.get("start_time", time.time())) * 1000
        logger.info(
            "agent_completed",
            agent=self.name,
            duration_ms=state["duration_ms"],
            has_error=bool(state.get("error")),
        )
        return state

    # --- Abstract lifecycle methods ---

    @abc.abstractmethod
    async def perceive(self, state: AgentState) -> AgentState:
        """感知阶段：解析输入，收集上下文"""
        ...

    @abc.abstractmethod
    async def plan(self, state: AgentState) -> AgentState:
        """规划阶段：制定执行计划"""
        ...

    @abc.abstractmethod
    async def act(self, state: AgentState) -> AgentState:
        """执行阶段：调用工具/LLM"""
        ...

    @abc.abstractmethod
    async def reflect(self, state: AgentState) -> AgentState:
        """反思阶段：评估结果质量"""
        ...

    @abc.abstractmethod
    async def format_output(self, state: AgentState) -> AgentState:
        """输出阶段：格式化最终结果"""
        ...

    # --- Public API ---

    async def run(self, input_data: dict, trace_id: str = "") -> AgentState:
        """运行 Agent 完整生命周期"""
        initial: AgentState = {"input_data": input_data, "trace_id": trace_id}
        return await self.compiled.ainvoke(initial)

    async def _handle_a2a(self, msg: A2AMessage) -> None:
        """处理 A2A 消息 — 仅处理原始请求，不回复回复消息（防止无限循环）"""
        if msg.reply_to:
            return
        result = await self.run(msg.payload, trace_id=msg.trace_id)
        if self.bus:
            reply = msg.reply(result.get("output", {}))
            await self.bus.send(reply)
