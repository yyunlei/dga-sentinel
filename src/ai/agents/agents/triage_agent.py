"""
分诊 Agent — 告警关联分析、严重度评估
继承 BaseAgent，实现 5 阶段生命周期
使用 ESQueryTool 执行真实 ES 关联查询
"""

from __future__ import annotations

from ai.agents.base_agent import BaseAgent, AgentState
from ai.agents.a2a.bus import AgentBus
from ai.agents.a2a.protocol import A2AMessage
from ai.agents.mcp.tools.es_query import ESQueryTool
from common.observability import get_logger

logger = get_logger(__name__)


class TriageAgent(BaseAgent):
    """
    分诊 Agent：
    1. perceive  — 提取告警数据，构建上下文
    2. plan      — 确定需要执行的 ES 关联查询
    3. act       — 执行 ES 查询，查找同 src_ip 5 分钟窗口内的关联告警
    4. reflect   — 基于 score + 关联数量评估严重度
    5. format_output — 构建输出，向 threat_intel / explain 发送 A2A 消息
    """

    name = "triage"

    def __init__(self, bus: AgentBus | None = None):
        super().__init__(bus=bus, tools=[ESQueryTool()])

    # ---- lifecycle --------------------------------------------------------

    async def perceive(self, state: AgentState) -> AgentState:
        alert = state.get("input_data", {})
        state["context"] = {
            "domain": alert.get("domain", ""),
            "src_ip": alert.get("src_ip", ""),
            "score": float(alert.get("score", 0)),
            "family": alert.get("family", "unknown"),
            "timestamp": alert.get("@timestamp", ""),
        }
        logger.info(
            "triage_perceive",
            domain=state["context"]["domain"],
            src_ip=state["context"]["src_ip"],
        )
        return state

    async def plan(self, state: AgentState) -> AgentState:
        ctx = state.get("context", {})
        src_ip = ctx.get("src_ip", "")
        ts = ctx.get("timestamp", "")

        steps = []
        if src_ip:
            steps.append(f"es_correlate_by_src_ip:{src_ip}:window=5m")
        if not steps:
            steps.append("skip_correlation:no_src_ip")

        state["plan"] = steps
        logger.info("triage_plan", steps=steps, timestamp=ts)
        return state

    async def act(self, state: AgentState) -> AgentState:
        ctx = state.get("context", {})
        src_ip = ctx.get("src_ip", "")
        ts = ctx.get("timestamp", "")
        tool_results: list[dict] = []

        if not src_ip:
            state["tool_results"] = [{"correlated_alerts": [], "total": 0}]
            return state

        # Try LLM-driven tool calling first (bind_tools)
        result = await self._try_llm_tool_call(ctx)
        if result is None:
            # Fallback: direct ES query
            result = await self._direct_es_query(src_ip, ts)

        tool_results.append(result)
        state["tool_results"] = tool_results
        logger.info("triage_act", src_ip=src_ip, correlated_total=result.get("total", 0))
        return state

    async def _try_llm_tool_call(self, ctx: dict) -> dict | None:
        """尝试通过 LLM bind_tools 自主调用 es_query"""
        try:
            from common.config import get_settings, has_valid_llm_key
            if not has_valid_llm_key():
                return None
            settings = get_settings()

            from langchain_openai import ChatOpenAI
            from langchain_core.messages import HumanMessage, ToolMessage
            from ai.agents.mcp.server import MCPServer
            from ai.agents.fc_bridge import MCPFunctionCallingBridge

            server = MCPServer()
            server.register_defaults()
            bridge = MCPFunctionCallingBridge(server, whitelist={"es_query"})
            lc_tools = bridge.get_langchain_tools()
            if not lc_tools:
                return None

            llm = ChatOpenAI(
                model=settings.deepseek_model,
                api_key=settings.deepseek_api_key,
                base_url=settings.deepseek_base_url,
                temperature=0,
            ).bind_tools(lc_tools)

            prompt = (
                f"查询 Elasticsearch 中与 src_ip={ctx.get('src_ip', '')} 相关的 DGA 告警，"
                f"时间窗口为最近 5 分钟。使用 es_query 工具。"
            )
            messages = [HumanMessage(content=prompt)]
            response = await llm.ainvoke(messages)

            if response.tool_calls:
                for tc in response.tool_calls:
                    tool = next((t for t in lc_tools if t.name == tc["name"]), None)
                    if tool:
                        return await tool.ainvoke(tc["args"])
            return None
        except Exception as e:
            logger.debug("triage_llm_tool_fallback", error=str(e))
            return None

    async def _direct_es_query(self, src_ip: str, ts: str) -> dict:
        """直接调用 ESQueryTool 进行关联查询"""
        if ts:
            es_query = {
                "bool": {
                    "must": [{"term": {"src_ip": src_ip}}],
                    "filter": [
                        {"range": {"@timestamp": {"gte": f"{ts}||-5m", "lte": f"{ts}||+5m"}}}
                    ],
                }
            }
        else:
            es_query = {"bool": {"must": [{"term": {"src_ip": src_ip}}]}}

        es_tool: ESQueryTool = self.tools[0]  # type: ignore[assignment]
        result = await es_tool.run(query=es_query, size=50)
        return result

    async def reflect(self, state: AgentState) -> AgentState:
        ctx = state.get("context", {})
        score = ctx.get("score", 0.0)
        results = state.get("tool_results", [{}])
        correlated_count = results[0].get("total", 0) if results else 0

        if score >= 0.95 or correlated_count >= 5:
            severity = "CRITICAL"
            confidence = 0.95
        elif score >= 0.85 or correlated_count >= 3:
            severity = "HIGH"
            confidence = 0.85
        elif score >= 0.7:
            severity = "MEDIUM"
            confidence = 0.7
        else:
            severity = "LOW"
            confidence = 0.5

        state["reflection"] = severity
        state["confidence"] = confidence
        logger.info(
            "triage_reflect",
            severity=severity,
            score=score,
            correlated_count=correlated_count,
        )
        return state

    async def format_output(self, state: AgentState) -> AgentState:
        ctx = state.get("context", {})
        severity = state.get("reflection", "LOW")
        results = state.get("tool_results", [{}])
        correlated_alerts = results[0].get("hits", []) if results else []
        correlated_count = results[0].get("total", 0) if results else 0

        state["output"] = {
            "severity": severity,
            "domain": ctx.get("domain", ""),
            "src_ip": ctx.get("src_ip", ""),
            "score": ctx.get("score", 0.0),
            "family": ctx.get("family", "unknown"),
            "correlated_alerts": correlated_alerts,
            "correlated_count": correlated_count,
        }

        # Send A2A messages for HIGH / CRITICAL alerts
        # Skip when called from pipeline dispatch (避免双重触发)
        skip_a2a = state.get("input_data", {}).get("_skip_a2a", False)
        if self.bus and not skip_a2a and severity in ("HIGH", "CRITICAL"):
            trace_id = state.get("trace_id", "")
            payload = state["output"]

            await self.bus.send(A2AMessage(
                from_agent=self.name,
                to_agent="threat_intel",
                action="query_ioc",
                payload={"domain": ctx.get("domain", ""), "src_ip": ctx.get("src_ip", "")},
                trace_id=trace_id,
            ))
            await self.bus.send(A2AMessage(
                from_agent=self.name,
                to_agent="explain",
                action="explain_alert",
                payload=payload,
                trace_id=trace_id,
            ))

        logger.info("triage_output", severity=severity, correlated_count=correlated_count)
        return state
