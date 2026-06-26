"""IntentRouter — LLM 判断 4 种意图 → 分发到对应链
意图类型:
  - query: 数据查询 → Text2SQL
  - analyze: 告警分析 → Agent Pipeline
  - operate: 操作指令 → 配置/管理
  - knowledge: 知识检索 → RAG
"""
from __future__ import annotations

import re

from common.config import get_settings
from common.observability import get_logger

logger = get_logger(__name__)

INTENT_TYPES = ("query", "analyze", "operate", "knowledge")

# 关键词 → 意图映射（LLM 不可用时的回退策略）
_KEYWORD_MAP: dict[str, list[str]] = {
    "query": ["查询", "统计", "趋势", "多少", "数量"],
    "analyze": ["分析", "解释", "告警", "检测", "评估"],
    "operate": ["配置", "设置", "修改", "更新", "部署"],
    "knowledge": ["什么是", "如何", "知识", "家族", "特征"],
}

_CLASSIFY_PROMPT = (
    "你是一个意图分类器。根据用户问题，判断属于以下哪种意图：\n"
    "- query: 数据查询（统计、趋势、数量等）\n"
    "- analyze: 告警分析（分析、解释、检测、评估等）\n"
    "- operate: 操作指令（配置、设置、修改、部署等）\n"
    "- knowledge: 知识检索（什么是、如何、知识、家族特征等）\n\n"
    "只输出一个 JSON: {\"intent\": \"<类型>\", \"confidence\": <0-1>}\n\n"
    "用户问题: {question}"
)


class IntentRouter:
    """LLM 意图分类 + 关键词回退 → 分发到对应处理链"""

    def classify_intent(self, question: str) -> str:
        """同步关键词意图分类（返回意图字符串）"""
        return self._keyword_fallback(question)["intent"]

    def _keyword_fallback(self, question: str) -> dict:
        """基于关键词的意图分类回退"""
        for intent, keywords in _KEYWORD_MAP.items():
            if any(kw in question for kw in keywords):
                return {"intent": intent, "confidence": 0.6, "params": {}}
        return {"intent": "query", "confidence": 0.3, "params": {}}

    async def route(self, question: str) -> dict:
        """判断用户意图，返回 {"intent": str, "confidence": float, "params": dict}"""
        settings = get_settings()
        if not settings.deepseek_api_key:
            logger.info("intent_keyword_fallback", reason="no_api_key")
            return self._keyword_fallback(question)

        try:
            from langchain_openai import ChatOpenAI
            llm = ChatOpenAI(
                model=settings.deepseek_model,
                api_key=settings.deepseek_api_key,
                base_url=settings.deepseek_base_url,
                temperature=0,
            )
            resp = await llm.ainvoke(_CLASSIFY_PROMPT.format(question=question))
            text = resp.content.strip()
            # 从 markdown 代码块中提取 JSON
            match = re.search(r"\{.*?\}", text, re.DOTALL)
            if match:
                import json
                parsed = json.loads(match.group())
                intent = parsed.get("intent", "query")
                if intent not in INTENT_TYPES:
                    intent = "query"
                confidence = float(parsed.get("confidence", 0.8))
                return {"intent": intent, "confidence": confidence, "params": {}}
        except Exception as e:
            logger.warning("intent_llm_error", error=str(e))

        return self._keyword_fallback(question)

    async def dispatch(self, question: str) -> dict:
        """路由并调用对应处理链"""
        result = await self.route(question)
        intent = result["intent"]
        logger.info("intent_dispatch", intent=intent, confidence=result["confidence"])

        if intent == "query":
            from ai.agents.text2sql.engine import Text2SQLEngine
            engine = Text2SQLEngine()
            return await engine.query(question)

        if intent == "analyze":
            return {"intent": "analyze", "message": "请使用告警分析接口"}

        if intent == "operate":
            return {"intent": "operate", "message": "请使用管理接口"}

        if intent == "knowledge":
            try:
                from ai.agents.rag.engine import ThreatKnowledgeRAG
                rag = ThreatKnowledgeRAG()
                return await rag.query(question)
            except ImportError:
                logger.warning("rag_not_available")
                return {"intent": "knowledge", "message": "RAG 引擎尚未就绪"}

        return {"intent": intent, "message": "未知意图"}