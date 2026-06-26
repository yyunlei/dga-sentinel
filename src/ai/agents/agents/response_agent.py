"""
响应 Agent — 基于告警严重度生成自动化响应动作
继承 BaseAgent，实现 5 阶段生命周期
根据 severity 级别生成 block_dns / isolate_host / create_incident / log_event 动作
"""

from __future__ import annotations

from typing import Any

from ai.agents.base_agent import BaseAgent, AgentState
from ai.agents.a2a.bus import AgentBus
from common.observability import get_logger

logger = get_logger(__name__)

# 严重度 → 允许的动作类型映射
_SEVERITY_ACTION_MAP: dict[str, list[str]] = {
    "CRITICAL": ["block_dns", "isolate_host", "create_incident", "log_event"],
    "HIGH": ["block_dns", "isolate_host", "log_event"],
    "MEDIUM": ["block_dns", "log_event"],
    "LOW": ["log_event"],
}


class ResponseAgent(BaseAgent):
    """
    响应 Agent：
    1. perceive  — 提取告警数据（severity, domain, src_ip）
    2. plan      — 根据 severity 确定响应动作列表
    3. act       — 生成具体动作（block_dns, isolate_host, create_incident, log_event）
    4. reflect   — 校验动作与严重度是否匹配
    5. format_output — 构建标准化输出
    """

    name = "response"

    def __init__(self, bus: AgentBus | None = None, tools: list[Any] | None = None):
        super().__init__(bus=bus, tools=tools)

    # ---- perceive --------------------------------------------------------

    async def perceive(self, state: AgentState) -> AgentState:
        data = state.get("input_data", {})
        state["context"] = {
            "severity": data.get("severity", "LOW").upper(),
            "domain": data.get("domain", ""),
            "src_ip": data.get("src_ip", ""),
            "alert_id": data.get("alert_id", ""),
            "family": data.get("family", "unknown"),
        }
        logger.info(
            "response_perceive",
            severity=state["context"]["severity"],
            domain=state["context"]["domain"],
        )
        return state
    # ---- plan ------------------------------------------------------------

    async def plan(self, state: AgentState) -> AgentState:
        severity = state["context"].get("severity", "LOW")
        planned_actions = _SEVERITY_ACTION_MAP.get(severity, ["log_event"])
        state["plan"] = planned_actions
        logger.info("response_plan", severity=severity, actions=planned_actions)
        return state

    # ---- RAG SOP 知识库 ------------------------------------------------

    async def _get_sop_context(self, severity: str, family: str) -> str:
        """查询 RAG 知识库获取 SOC SOP 处置规则（无有效 key 时跳过）。"""
        from common.config import has_valid_llm_key
        if not has_valid_llm_key():
            return ""
        try:
            from ai.agents.rag.engine import ThreatKnowledgeRAG
            rag = ThreatKnowledgeRAG.get_instance()
            result = await rag.query(
                f"SOC SOP {severity} {family} 处置规则", top_k=3,
            )
            sources = result.get("sources", [])
            if not sources:
                return ""
            lines = []
            for s in sources:
                lines.append(f"- [{s['category']}] {s['content'][:200]}")
            return "\n".join(lines)
        except Exception as e:
            logger.warning("response_sop_context_error", error=str(e))
            return ""

    # ---- act -------------------------------------------------------------

    async def act(self, state: AgentState) -> AgentState:
        ctx = state["context"]
        severity = ctx["severity"]
        domain = ctx["domain"]
        src_ip = ctx["src_ip"]
        family = ctx.get("family", "unknown")
        planned = state.get("plan", ["log_event"])
        actions: list[dict] = []

        # RAG: 查询 SOP 处置规则
        sop_context = await self._get_sop_context(severity, family)

        for action_type in planned:
            if action_type == "block_dns":
                actions.append({
                    "type": "block_dns",
                    "target": domain,
                    "description": f"在 DNS 防火墙中封禁域名 {domain}",
                    "auto_execute": severity == "CRITICAL",
                })
            elif action_type == "isolate_host":
                actions.append({
                    "type": "isolate_host",
                    "target": src_ip,
                    "description": f"隔离源主机 {src_ip} 进行调查",
                    "auto_execute": False,
                })
            elif action_type == "create_incident":
                actions.append({
                    "type": "create_incident",
                    "target": domain,
                    "description": "创建安全事件工单，通知 SOC 团队",
                    "auto_execute": True,
                })
            elif action_type == "log_event":
                actions.append({
                    "type": "log_event",
                    "target": domain or src_ip,
                    "description": "记录到 SIEM 事件日志",
                    "auto_execute": True,
                })

        state["tool_results"] = [{"actions": actions, "sop_context": sop_context}]
        logger.info("response_act", severity=severity, action_count=len(actions))
        return state

    # ---- reflect ---------------------------------------------------------

    async def reflect(self, state: AgentState) -> AgentState:
        severity = state["context"].get("severity", "LOW")
        actions = state.get("tool_results", [{}])[0].get("actions", [])
        action_types = {a["type"] for a in actions}
        expected = set(_SEVERITY_ACTION_MAP.get(severity, ["log_event"]))

        if action_types == expected:
            state["reflection"] = (
                f"Actions match severity={severity}: {sorted(action_types)}"
            )
            state["confidence"] = 0.95
        else:
            missing = expected - action_types
            extra = action_types - expected
            state["reflection"] = (
                f"Mismatch for severity={severity}: "
                f"missing={sorted(missing)}, extra={sorted(extra)}"
            )
            state["confidence"] = 0.60

        logger.info(
            "response_reflect",
            severity=severity,
            confidence=state["confidence"],
        )
        return state

    # ---- format_output ---------------------------------------------------

    async def format_output(self, state: AgentState) -> AgentState:
        tool_result = state.get("tool_results", [{}])[0]
        actions = tool_result.get("actions", [])
        sop_context = tool_result.get("sop_context", "")

        output = {
            "severity": state["context"].get("severity", "LOW"),
            "domain": state["context"].get("domain", ""),
            "src_ip": state["context"].get("src_ip", ""),
            "actions": actions,
            "action_count": len(actions),
        }

        if sop_context:
            output["sop_references"] = sop_context

        state["output"] = output
        logger.info(
            "response_output",
            severity=state["output"]["severity"],
            action_count=state["output"]["action_count"],
        )
        return state
