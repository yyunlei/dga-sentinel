"""
ExplainAgent — 4 维度告警智能解释 (DeepSeek LLM)

继承 BaseAgent，实现 perceive → plan → act → reflect → format_output
四个分析维度:
  1. 字符特征分析
  2. 熵值分析
  3. DGA 家族模式匹配
  4. 网络行为关联
"""

from __future__ import annotations

import math
from collections import Counter
from typing import Any

from agent_layer.base_agent import BaseAgent, AgentState
from agent_layer.a2a.bus import AgentBus
from shared.config import get_settings, has_valid_llm_key
from shared.observability import get_logger

logger = get_logger(__name__)


class ExplainAgent(BaseAgent):
    """4 维度 DGA 告警解释 Agent，使用 DeepSeek LLM 生成分析报告。"""

    name: str = "explain"

    def __init__(self, bus: AgentBus | None = None, tools: list[Any] | None = None):
        super().__init__(bus=bus, tools=tools)
        self._lc_tools_cache: list | None = None

    # ------------------------------------------------------------------ #
    #  perceive — 提取告警关键字段
    # ------------------------------------------------------------------ #
    async def perceive(self, state: AgentState) -> AgentState:
        data = state.get("input_data", {})
        state["context"] = {
            "domain": data.get("domain", "unknown"),
            "score": float(data.get("score", 0.0)),
            "family": data.get("family", "unknown"),
            "src_ip": data.get("src_ip", "N/A"),
        }
        logger.info("explain_perceive", domain=state["context"]["domain"])
        return state

    # ------------------------------------------------------------------ #
    #  plan — 制定 4 维度分析计划
    # ------------------------------------------------------------------ #
    async def plan(self, state: AgentState) -> AgentState:
        state["plan"] = [
            "字符特征分析 — 域名长度、数字/辅音占比、n-gram 异常度",
            "熵值分析 — 计算 Shannon 熵并与合法域名基线对比",
            "DGA家族模式匹配 — 与已知家族生成算法特征比对",
            "网络行为关联 — 源 IP 历史请求频率与异常模式",
        ]
        return state

    # ------------------------------------------------------------------ #
    #  RAG 知识库上下文
    # ------------------------------------------------------------------ #
    async def _get_rag_context(self, family: str, domain: str) -> str:
        """查询 RAG 知识库获取家族特征参考信息（5s 超时保护）。"""
        import asyncio
        try:
            from agent_layer.rag.engine import ThreatKnowledgeRAG
            rag = ThreatKnowledgeRAG.get_instance()
            try:
                result = await asyncio.wait_for(
                    rag.query(f"{family} DGA 家族特征 {domain}", top_k=3),
                    timeout=5.0,
                )
                sources = result.get("sources", [])
                if not sources:
                    return ""
                lines = []
                for s in sources:
                    lines.append(f"- [{s['category']}] {s['content'][:200]}")
                return "\n".join(lines)
            except Exception:
                pass  # fall through to outer handlers
        except asyncio.TimeoutError:
            logger.warning("explain_rag_context_timeout")
            return ""
        except Exception as e:
            logger.warning("explain_rag_context_error", error=str(e))
            return ""

    # ------------------------------------------------------------------ #
    #  act — 调用 DeepSeek LLM (with bind_tools) 或回退模板
    # ------------------------------------------------------------------ #
    async def act(self, state: AgentState) -> AgentState:
        ctx = state["context"]
        domain = ctx["domain"]
        score = ctx["score"]
        family = ctx["family"]
        src_ip = ctx["src_ip"]

        entropy = self._shannon_entropy(domain.split(".")[0])

        # 无有效 LLM key 时直接走模板分析，跳过 RAG / LLM
        if not has_valid_llm_key():
            explanation = self._template_analysis(domain, score, family, src_ip, entropy)
            state["tool_results"] = [{"source": "template", "text": explanation}]
            return state

        settings = get_settings()

        # RAG 知识库上下文 enrichment（仅在有有效 key 时才查询）
        rag_context = await self._get_rag_context(family, domain)

        try:
            from langchain_openai import ChatOpenAI
            from langchain_core.messages import HumanMessage

            llm = ChatOpenAI(
                model=settings.deepseek_model,
                api_key=settings.deepseek_api_key,
                base_url=settings.deepseek_base_url,
                temperature=0.3,
                max_tokens=1024,
            )

            # Bind MCP tools via fc_bridge if available
            lc_tools = self._get_langchain_tools()
            if lc_tools:
                llm_with_tools = llm.bind_tools(lc_tools)
            else:
                llm_with_tools = llm

            prompt = self._build_prompt(domain, score, family, src_ip, entropy, rag_context=rag_context)
            messages = [HumanMessage(content=prompt)]
            tool_call_results = []

            # Multi-turn tool calling loop (max 3 rounds)
            for _ in range(3):
                response = await llm_with_tools.ainvoke(messages)
                messages.append(response)

                if not response.tool_calls:
                    break

                # Execute tool calls
                from langchain_core.messages import ToolMessage
                for tc in response.tool_calls:
                    tool = self._find_tool(tc["name"], lc_tools)
                    if tool:
                        result = await tool.ainvoke(tc["args"])
                        tool_call_results.append({"tool": tc["name"], "result": str(result)[:500]})
                        messages.append(ToolMessage(content=str(result), tool_call_id=tc["id"]))

            explanation = response.content or ""
            state["tool_results"] = [
                {"source": "deepseek", "text": explanation, "tool_calls": tool_call_results}
            ]
        except Exception as e:
            logger.error("explain_llm_error", error=str(e))
            explanation = self._template_analysis(domain, score, family, src_ip, entropy)
            state["tool_results"] = [{"source": "template_fallback", "text": explanation}]

        return state

    def _get_langchain_tools(self) -> list:
        """获取 LangChain 工具（通过 fc_bridge），结果缓存"""
        if self._lc_tools_cache is not None:
            return self._lc_tools_cache
        try:
            from agent_layer.mcp.server import MCPServer
            from agent_layer.fc_bridge import MCPFunctionCallingBridge
            server = MCPServer()
            server.register_defaults()
            bridge = MCPFunctionCallingBridge(
                server, whitelist={"es_query", "threat_intel", "dns_resolve"}
            )
            self._lc_tools_cache = bridge.get_langchain_tools()
            return self._lc_tools_cache
        except Exception:
            return []

    @staticmethod
    def _find_tool(name: str, tools: list):
        for t in tools:
            if t.name == name:
                return t
        return None

    # ------------------------------------------------------------------ #
    #  reflect — 校验解释质量
    # ------------------------------------------------------------------ #
    async def reflect(self, state: AgentState) -> AgentState:
        results = state.get("tool_results", [])
        text = results[0]["text"] if results else ""
        length = len(text)

        if length == 0:
            state["reflection"] = "解释为空，质量不合格"
            state["confidence"] = 0.0
        elif length < 50:
            state["reflection"] = "解释过短，可能缺少关键维度"
            state["confidence"] = 0.3
        elif length > 2000:
            state["reflection"] = "解释过长，可能包含冗余信息"
            state["confidence"] = 0.6
        else:
            state["reflection"] = "解释长度合理，质量可接受"
            state["confidence"] = 0.85 if results[0].get("source") == "deepseek" else 0.6

        return state

    # ------------------------------------------------------------------ #
    #  format_output — 构建最终输出
    # ------------------------------------------------------------------ #
    async def format_output(self, state: AgentState) -> AgentState:
        results = state.get("tool_results", [])
        explanation = results[0]["text"] if results else "无法生成解释"
        ctx = state.get("context", {})

        dimensions = self._parse_dimensions(explanation, ctx)

        state["output"] = {
            "explanation": explanation,
            "dimensions": dimensions,
            "confidence": state.get("confidence", 0.0),
        }
        return state

    @staticmethod
    def _parse_dimensions(text: str, ctx: dict) -> list[dict[str, str]]:
        """从分析文本中提取四维内容；解析失败时用 ctx 生成兜底。"""
        markers = ["字符特征分析", "熵值分析", "DGA家族模式匹配", "网络行为关联"]
        dims: list[dict[str, str]] = []

        for i, marker in enumerate(markers):
            start = text.find(f"【{marker}】")
            if start == -1:
                continue
            content_start = start + len(f"【{marker}】")
            # find next marker or end
            next_start = len(text)
            for j in range(i + 1, len(markers)):
                pos = text.find(f"【{markers[j]}】", content_start)
                if pos != -1:
                    next_start = pos
                    break
            content = text[content_start:next_start].strip()
            if content:
                dims.append({"title": marker, "content": content})

        if len(dims) >= 2:
            return dims

        # Fallback: generate from context
        domain = ctx.get("domain", "unknown")
        score = ctx.get("score", 0.0)
        family = ctx.get("family", "unknown")
        src_ip = ctx.get("src_ip", "N/A")
        sld = domain.split(".")[0]
        digit_ratio = sum(c.isdigit() for c in sld) / max(len(sld), 1)
        entropy = ExplainAgent._shannon_entropy(sld)

        return [
            {"title": "字符特征分析", "content": f"域名 '{domain}' 二级域长度 {len(sld)}，数字占比 {digit_ratio:.1%}，{'机器生成特征明显' if digit_ratio > 0.3 or len(sld) > 15 else '接近人工注册特征'}。"},
            {"title": "熵值分析", "content": f"Shannon 熵 {entropy:.2f}，{'高于' if entropy > 3.5 else '接近'}合法域名基线（2.5-3.5），随机性{'较强' if entropy > 3.5 else '一般'}。"},
            {"title": "DGA家族模式匹配", "content": f"疑似家族 {family}，风险评分 {score:.4f}，建议与 {family} 已知种子/字典做进一步比对。"},
            {"title": "网络行为关联", "content": f"源 IP {src_ip} 发起该域名查询，建议检查该 IP 近期 DNS 请求频率及批量随机域名查询行为。"},
        ]

    # ================================================================== #
    #  Private helpers
    # ================================================================== #
    @staticmethod
    def _shannon_entropy(text: str) -> float:
        """计算字符串的 Shannon 熵。"""
        if not text:
            return 0.0
        freq = Counter(text)
        length = len(text)
        return -sum(
            (count / length) * math.log2(count / length)
            for count in freq.values()
        )

    @staticmethod
    def _build_prompt(
        domain: str, score: float, family: str, src_ip: str, entropy: float,
        *, rag_context: str = "",
    ) -> str:
        rag_section = ""
        if rag_context:
            rag_section = f"【知识库参考】\n{rag_context}\n\n"

        return (
            "你是一名资深网络安全分析师，请对以下 DGA 检测告警进行 4 维度深度分析。\n\n"
            f"【告警信息】\n"
            f"  域名: {domain}\n"
            f"  风险评分: {score:.4f}\n"
            f"  疑似 DGA 家族: {family}\n"
            f"  源 IP: {src_ip}\n"
            f"  域名熵值: {entropy:.4f}\n\n"
            f"{rag_section}"
            "请严格按照以下 4 个维度输出分析，每个维度 2-3 句话：\n\n"
            "1. 字符特征分析：分析域名长度、数字占比、辅音占比、"
            "是否包含可读音节等字符层面特征。\n"
            "2. 熵值分析：结合上述熵值，与合法域名平均熵值（约 2.5-3.5）对比，"
            "判断随机性程度。\n"
            "3. DGA 家族模式匹配：结合疑似家族信息，分析该域名与已知 DGA 家族"
            "（如 Conficker、Necurs、Suppobox 等）生成算法的相似度。\n"
            "4. 网络行为关联：基于源 IP 和域名特征，推测可能的 C2 通信模式"
            "及建议的响应措施。\n"
        )

    @staticmethod
    def _template_analysis(
        domain: str, score: float, family: str, src_ip: str, entropy: float,
    ) -> str:
        """无 API key 时的模板回退分析。"""
        sld = domain.split(".")[0]
        digit_ratio = sum(c.isdigit() for c in sld) / max(len(sld), 1)
        vowels = set("aeiou")
        consonant_ratio = sum(
            c.isalpha() and c.lower() not in vowels for c in sld
        ) / max(len(sld), 1)

        risk = "高" if score >= 0.8 else ("中" if score >= 0.5 else "低")

        return (
            f"【字符特征分析】域名 '{domain}' 二级域长度 {len(sld)}，"
            f"数字占比 {digit_ratio:.1%}，辅音占比 {consonant_ratio:.1%}，"
            f"整体呈现{'机器生成' if digit_ratio > 0.3 or len(sld) > 15 else '人工注册'}特征。\n"
            f"【熵值分析】Shannon 熵 {entropy:.2f}，"
            f"{'高于' if entropy > 3.5 else '接近'}合法域名基线（2.5-3.5），"
            f"随机性{'较强' if entropy > 3.5 else '一般'}。\n"
            f"【DGA家族模式匹配】疑似家族 {family}，风险评分 {score:.4f}（{risk}风险），"
            f"建议与 {family} 已知种子/字典做进一步比对。\n"
            f"【网络行为关联】源 IP {src_ip} 发起该域名查询，"
            f"建议检查该 IP 近期 DNS 请求频率及是否存在批量随机域名查询行为。"
        )
