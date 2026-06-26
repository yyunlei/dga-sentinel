"""ThreatKnowledgeRAG — 混合检索 (向量+BM25) + 重排序 + LLM 生成 + 来源引用"""
from __future__ import annotations

from typing import Any

from elasticsearch import AsyncElasticsearch

from agent_layer.rag.embedding import ThreatEmbedding
from shared.config import get_settings, has_valid_llm_key
from shared.observability import get_logger

logger = get_logger(__name__)

INDEX_NAME = "threat-knowledge-vectors"


class ThreatKnowledgeRAG:
    """混合检索 RAG 引擎：向量 kNN + BM25 文本检索，分数融合重排序，DeepSeek LLM 生成。"""

    _instance: ThreatKnowledgeRAG | None = None

    @classmethod
    def get_instance(cls) -> ThreatKnowledgeRAG:
        """获取单例实例，避免重复初始化 embedding 模型。"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self._settings = get_settings()
        self._embedder = ThreatEmbedding()
        self._es: AsyncElasticsearch | None = None

    async def _get_es(self) -> AsyncElasticsearch:
        if self._es is None:
            self._es = AsyncElasticsearch(hosts=[self._settings.es_hosts])
        return self._es

    async def close(self) -> None:
        if self._es is not None:
            await self._es.close()
            self._es = None

    # ------------------------------------------------------------------ #
    #  Public API
    # ------------------------------------------------------------------ #

    async def query(self, question: str, top_k: int = 5) -> dict:
        """混合检索 + 重排序 + LLM 生成，返回标准化结果。"""
        try:
            # 1. 向量检索 + BM25 检索
            vector_hits = await self._vector_search(question, top_k=top_k * 2)
            bm25_hits = await self._bm25_search(question, top_k=top_k * 2)

            # 2. 分数融合重排序
            fused = self._fuse_scores(vector_hits, bm25_hits)
            top_results = fused[:top_k]

            sources = [
                {
                    "content": r["content"],
                    "source": r["metadata"].get("source", "unknown"),
                    "category": r["metadata"].get("category", "unknown"),
                    "score": round(r["fused_score"], 4),
                }
                for r in top_results
            ]

            # 3. LLM 生成（无 key 则回退原始 chunks）
            answer = await self._generate_answer(question, top_results)

            return {"answer": answer, "sources": sources, "query": question}

        except Exception as e:
            logger.error("rag_query_error", error=str(e), question=question)
            return {"answer": "", "sources": [], "query": question}

    # ------------------------------------------------------------------ #
    #  向量检索
    # ------------------------------------------------------------------ #

    async def _vector_search(self, question: str, top_k: int = 10) -> list[dict]:
        es = await self._get_es()
        embedding = (await self._embedder.aembed([question]))[0]
        body = {
            "knn": {
                "field": "embedding",
                "query_vector": embedding,
                "k": top_k,
                "num_candidates": top_k * 5,
            },
            "_source": ["content", "metadata"],
        }
        try:
            resp = await es.search(index=INDEX_NAME, body=body)
            return [
                {
                    "content": hit["_source"]["content"],
                    "metadata": hit["_source"].get("metadata", {}),
                    "vector_score": hit["_score"] or 0.0,
                    "doc_id": hit["_id"],
                }
                for hit in resp["hits"]["hits"]
            ]
        except Exception as e:
            logger.warning("vector_search_error", error=str(e))
            return []

    # ------------------------------------------------------------------ #
    #  BM25 文本检索
    # ------------------------------------------------------------------ #

    async def _bm25_search(self, question: str, top_k: int = 10) -> list[dict]:
        es = await self._get_es()
        body = {
            "query": {"match": {"content": {"query": question, "analyzer": "standard"}}},
            "size": top_k,
            "_source": ["content", "metadata"],
        }
        try:
            resp = await es.search(index=INDEX_NAME, body=body)
            return [
                {
                    "content": hit["_source"]["content"],
                    "metadata": hit["_source"].get("metadata", {}),
                    "bm25_score": hit["_score"] or 0.0,
                    "doc_id": hit["_id"],
                }
                for hit in resp["hits"]["hits"]
            ]
        except Exception as e:
            logger.warning("bm25_search_error", error=str(e))
            return []

    # ------------------------------------------------------------------ #
    #  分数融合重排序 (0.7 * vector + 0.3 * bm25)
    # ------------------------------------------------------------------ #

    @staticmethod
    def _fuse_scores(
        vector_hits: list[dict], bm25_hits: list[dict],
    ) -> list[dict]:
        merged: dict[str, dict] = {}

        # Normalize scores to [0, 1]
        v_max = max((h["vector_score"] for h in vector_hits), default=1.0) or 1.0
        b_max = max((h["bm25_score"] for h in bm25_hits), default=1.0) or 1.0

        for h in vector_hits:
            doc_id = h["doc_id"]
            merged[doc_id] = {
                "content": h["content"],
                "metadata": h["metadata"],
                "vector_score": h["vector_score"] / v_max,
                "bm25_score": 0.0,
            }

        for h in bm25_hits:
            doc_id = h["doc_id"]
            if doc_id in merged:
                merged[doc_id]["bm25_score"] = h["bm25_score"] / b_max
            else:
                merged[doc_id] = {
                    "content": h["content"],
                    "metadata": h["metadata"],
                    "vector_score": 0.0,
                    "bm25_score": h["bm25_score"] / b_max,
                }

        for doc in merged.values():
            doc["fused_score"] = 0.7 * doc["vector_score"] + 0.3 * doc["bm25_score"]

        return sorted(merged.values(), key=lambda d: d["fused_score"], reverse=True)

    # ------------------------------------------------------------------ #
    #  LLM 生成（DeepSeek）/ 回退原始 chunks
    # ------------------------------------------------------------------ #

    async def _generate_answer(self, question: str, results: list[dict]) -> str:
        if not results:
            return ""

        context_text = "\n\n".join(
            f"[来源: {r['metadata'].get('source', '?')}]\n{r['content']}"
            for r in results
        )

        # 无有效 LLM key 时回退：拼接原始 chunks
        if not has_valid_llm_key():
            logger.info("rag_no_llm_key_fallback")
            return context_text

        try:
            from langchain_openai import ChatOpenAI
            from langchain_core.messages import HumanMessage

            llm = ChatOpenAI(
                model=self._settings.deepseek_model,
                api_key=self._settings.deepseek_api_key,
                base_url=self._settings.deepseek_base_url,
                temperature=0.2,
                max_tokens=1024,
            )
            prompt = (
                "你是一名网络安全威胁情报分析师。根据以下知识库内容回答问题，"
                "请引用来源。如果知识库中没有相关信息，请如实说明。\n\n"
                f"【问题】{question}\n\n"
                f"【知识库内容】\n{context_text}\n\n"
                "请给出简洁准确的回答："
            )
            response = await llm.ainvoke([HumanMessage(content=prompt)])
            return response.content or context_text
        except Exception as e:
            logger.error("rag_llm_generate_error", error=str(e))
            return context_text
