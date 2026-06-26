"""M3 测试 — RAG 检索准确性、Embedding、Ingest"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("APP_ENV", "development")

import pytest

from ai.agents.rag.embedding import ThreatEmbedding
from ai.agents.rag.ingest import load_documents, split_documents


# ------------------------------------------------------------------ #
#  T1: ThreatEmbedding
# ------------------------------------------------------------------ #

class TestThreatEmbedding:
    """Embedding 维度、批量、确定性、空列表。"""

    def setup_method(self):
        self.emb = ThreatEmbedding(dim=768)
        # Force fallback so tests don't need the real model
        self.emb._model = "fallback"

    def test_embed_returns_correct_dim(self):
        vecs = self.emb.embed(["test"])
        assert len(vecs) == 1
        assert len(vecs[0]) == 768

    def test_embed_multiple(self):
        vecs = self.emb.embed(["a", "b"])
        assert len(vecs) == 2
        assert all(len(v) == 768 for v in vecs)

    def test_fallback_embed_deterministic(self):
        v1 = self.emb.embed(["same text"])[0]
        v2 = self.emb.embed(["same text"])[0]
        assert v1 == v2

    def test_embed_empty_list(self):
        assert self.emb.embed([]) == []


# ------------------------------------------------------------------ #
#  T2: Ingest — load / split
# ------------------------------------------------------------------ #
class TestIngest:
    """文档加载与分块。"""

    def test_load_documents_from_knowledge_dir(self):
        knowledge_dir = os.path.join(
            os.path.dirname(__file__), os.pardir, os.pardir, "docs", "knowledge"
        )
        knowledge_dir = os.path.normpath(knowledge_dir)
        docs = load_documents(knowledge_dir)
        assert len(docs) > 0
        for doc in docs:
            assert "content" in doc
            assert "metadata" in doc

    def test_load_documents_from_tmp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "a.md").write_text("hello world", encoding="utf-8")
            (Path(tmpdir) / "b.md").write_text("foo bar", encoding="utf-8")
            docs = load_documents(tmpdir)
            assert len(docs) == 2
            assert all("content" in d and "metadata" in d for d in docs)

    def test_split_documents_chunking(self):
        docs = [{"content": "x" * 250, "metadata": {"source": "test"}}]
        chunks = split_documents(docs, chunk_size=100, overlap=20)
        # 250 chars, chunk_size=100, step=80 → ceil(250/80)=4 chunks
        assert len(chunks) >= 3
        for ch in chunks:
            assert len(ch["content"]) <= 100

    def test_split_preserves_metadata(self):
        docs = [{"content": "a" * 200, "metadata": {"source": "s1", "category": "c1"}}]
        chunks = split_documents(docs, chunk_size=100, overlap=20)
        for ch in chunks:
            assert ch["metadata"]["source"] == "s1"
            assert ch["metadata"]["category"] == "c1"
            assert "chunk_id" in ch["metadata"]


# ------------------------------------------------------------------ #
#  T3: ThreatKnowledgeRAG
# ------------------------------------------------------------------ #

class TestThreatKnowledgeRAG:
    """RAG 引擎初始化与查询结构。"""

    def test_rag_engine_init(self):
        from ai.agents.rag.engine import ThreatKnowledgeRAG
        rag = ThreatKnowledgeRAG()
        assert rag is not None
        assert rag._embedder is not None

    @pytest.mark.asyncio
    async def test_rag_query_returns_structure(self):
        from ai.agents.rag.engine import ThreatKnowledgeRAG
        rag = ThreatKnowledgeRAG()

        # Mock ES to avoid real connection
        mock_es = AsyncMock()
        mock_es.search = AsyncMock(return_value={"hits": {"hits": []}})
        rag._es = mock_es

        # Mock _vector_search and _bm25_search to return empty
        rag._vector_search = AsyncMock(return_value=[])
        rag._bm25_search = AsyncMock(return_value=[])
        # Mock _generate_answer to return a canned answer
        rag._generate_answer = AsyncMock(return_value="test answer")

        result = await rag.query("什么是 conficker")
        assert "answer" in result
        assert "sources" in result
        assert "query" in result


# ------------------------------------------------------------------ #
#  T4: IntentRouter
# ------------------------------------------------------------------ #
class TestIntentRouter:
    """意图路由关键词匹配。"""

    @pytest.fixture(autouse=True)
    def _router(self):
        from ai.agents.intent_router import IntentRouter
        self.router = IntentRouter()

    def test_keyword_routing_query(self):
        intent = self.router.classify_intent("过去24小时告警数量")
        assert intent == "query"

    def test_keyword_routing_analyze(self):
        intent = self.router.classify_intent("分析这个告警")
        assert intent == "analyze"

    def test_keyword_routing_operate(self):
        intent = self.router.classify_intent("修改配置")
        assert intent == "operate"

    def test_keyword_routing_knowledge(self):
        intent = self.router.classify_intent("什么是conficker")
        assert intent == "knowledge"

    def test_default_intent(self):
        intent = self.router.classify_intent("hello")
        assert intent == "query"
