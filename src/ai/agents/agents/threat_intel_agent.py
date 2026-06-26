"""
威胁情报 Agent — IOC 查询、黑名单匹配
继承 BaseAgent，实现 5 阶段生命周期
使用 ThreatIntelTool + Redis 直查实现多源情报融合
"""

from __future__ import annotations

from typing import Any

import redis.asyncio as aioredis

from agent_layer.base_agent import BaseAgent, AgentState
from agent_layer.a2a.bus import AgentBus
from agent_layer.mcp.tools.threat_intel import ThreatIntelTool
from shared.config import get_settings
from shared.observability import get_logger

logger = get_logger(__name__)


class ThreatIntelAgent(BaseAgent):
    """
    威胁情报 Agent：
    1. perceive  — 提取 domain / ip
    2. plan      — 规划检查步骤（Redis 黑名单、外部 API）
    3. act       — 调用 ThreatIntelTool + Redis 直查
    4. reflect   — 根据黑名单命中和情报源数量评估威胁等级
    5. format_output — 构建标准化输出
    """

    name = "threat_intel"

    def __init__(self, bus: AgentBus | None = None, tools: list[Any] | None = None):
        if tools is None:
            tools = [ThreatIntelTool()]
        super().__init__(bus=bus, tools=tools)

    # ---- perceive --------------------------------------------------------

    async def perceive(self, state: AgentState) -> AgentState:
        data = state.get("input_data", {})
        state["context"] = {
            "domain": data.get("domain", ""),
            "ip": data.get("ip", data.get("src_ip", "")),
        }
        logger.info(
            "threat_intel_perceive",
            domain=state["context"]["domain"],
            ip=state["context"]["ip"],
        )
        return state
    # ---- plan ------------------------------------------------------------

    async def plan(self, state: AgentState) -> AgentState:
        steps = ["redis_blacklist_lookup"]
        domain = state["context"].get("domain", "")
        ip = state["context"].get("ip", "")
        if domain or ip:
            steps.append("threat_intel_tool_query")
        state["plan"] = steps
        logger.info("threat_intel_plan", steps=steps)
        return state

    # ---- act -------------------------------------------------------------

    async def act(self, state: AgentState) -> AgentState:
        ctx = state["context"]
        domain = ctx.get("domain", "")
        ip = ctx.get("ip", "")
        results: list[dict] = []

        # 1) Redis 黑名单直查
        settings = get_settings()
        try:
            r = aioredis.from_url(settings.redis_url)
            try:
                redis_result = {"source": "redis_direct", "blacklisted": False}
                if domain:
                    hit = await r.sismember("dga:blacklist:domains", domain)
                    if hit:
                        redis_result["blacklisted"] = True
                        redis_result["matched_field"] = "domain"
                if ip:
                    hit = await r.sismember("dga:blacklist:ips", ip)
                    if hit:
                        redis_result["blacklisted"] = True
                        redis_result["matched_field"] = "ip"
                results.append(redis_result)
            finally:
                await r.aclose()
        except Exception as e:
            logger.error("threat_intel_redis_error", error=str(e))
            results.append({"source": "redis_direct", "error": str(e)})

        # 2) ThreatIntelTool 查询
        tool: ThreatIntelTool | None = next(
            (t for t in self.tools if isinstance(t, ThreatIntelTool)), None
        )
        if tool:
            try:
                tool_result = await tool.run(domain=domain, ip=ip)
                tool_result["source"] = "threat_intel_tool"
                results.append(tool_result)
            except Exception as e:
                logger.error("threat_intel_tool_error", error=str(e))
                results.append({"source": "threat_intel_tool", "error": str(e)})

        state["tool_results"] = results
        logger.info("threat_intel_act", result_count=len(results))
        return state

    # ---- reflect ---------------------------------------------------------

    async def reflect(self, state: AgentState) -> AgentState:
        results = state.get("tool_results", [])
        blacklisted = any(r.get("blacklisted") for r in results)
        sources = [
            r["source"] for r in results
            if r.get("blacklisted") and "source" in r
        ]
        source_count = len(sources)

        if blacklisted and source_count >= 2:
            threat_level = "critical"
            confidence = 0.95
        elif blacklisted:
            threat_level = "high"
            confidence = 0.80
        else:
            threat_level = "low"
            confidence = 0.60

        state["reflection"] = (
            f"blacklisted={blacklisted}, sources={source_count}, "
            f"threat_level={threat_level}"
        )
        state["confidence"] = confidence
        # 暂存供 format_output 使用
        state["context"]["_threat_level"] = threat_level
        state["context"]["_blacklisted"] = blacklisted
        state["context"]["_sources"] = sources
        logger.info(
            "threat_intel_reflect",
            threat_level=threat_level,
            confidence=confidence,
        )
        return state

    # ---- format_output ---------------------------------------------------

    async def format_output(self, state: AgentState) -> AgentState:
        ctx = state["context"]
        results = state.get("tool_results", [])

        # 聚合 tags
        tags: list[str] = []
        for r in results:
            tags.extend(r.get("tags", []))
        tags = list(dict.fromkeys(tags))  # 去重保序

        # 聚合 sources
        all_sources: list[str] = []
        for r in results:
            all_sources.extend(r.get("sources", []))
            if r.get("blacklisted") and r.get("source"):
                all_sources.append(r["source"])
        all_sources = list(dict.fromkeys(all_sources))

        state["output"] = {
            "domain": ctx.get("domain", ""),
            "ip": ctx.get("ip", ""),
            "blacklisted": ctx.get("_blacklisted", False),
            "sources": all_sources,
            "tags": tags,
            "threat_level": ctx.get("_threat_level", "low"),
        }
        logger.info(
            "threat_intel_output",
            domain=state["output"]["domain"],
            threat_level=state["output"]["threat_level"],
        )
        return state
