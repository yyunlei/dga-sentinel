"""
T089 集成测试 — RAG 知识库检索 + LLM 生成 + 来源引用
验证:
  - ThreatKnowledgeRAG 初始化
  - query 返回 {answer, sources, query} 结构
  - Embedding 维度 768
  - 知识文档加载与分块
  - ES 向量检索 mock
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── Embedding Tests ───────────────────────────────────────

class TestThreatEmbedding:

    def test_embedding_default_dim_768(self):
        from agent_layer.rag.embedding import ThreatEmbedding
        embedder = ThreatEmbedding()
        assert embedder.dim == 768

    def test_fallback_embed_produces_correct_dim(self):
        from agent_layer.rag.embedding import ThreatEmbedding
        embedder = ThreatEmbedding(dim=768)
        embedder._model = "fallback"
        vectors = embedder.embed(["test domain query"])
        assert len(vectors) == 1
        assert len(vectors[0]) == 768

    def test_fallback_embed_returns_float_list(self):
        """Fallback embedding returns a list of floats with correct dimension."""
        from agent_layer.rag.embedding import ThreatEmbedding
        embedder = ThreatEmbedding(dim=768)
        embedder._model = "fallback"
        vectors = embedder.embed(["hello world"])
        assert len(vectors) == 1
        assert len(vectors[0]) == 768
        assert all(isinstance(v, float) for v in vectors[0])


# ── Document Ingest Tests ─────────────────────────────────

class TestDocumentIngest:

    def test_load_documents_from_directory(self):
        from agent_layer.rag.ingest import load_documents
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "test.md"
            p.write_text("# Conficker\nDGA family info", encoding="utf-8")
            docs = load_documents(tmpdir)
            assert len(docs) == 1
            assert "Conficker" in docs[0]["content"]
            assert docs[0]["metadata"]["title"] == "test"

    def test_split_documents_chunking(self):
        from agent_layer.rag.ingest import split_documents
        docs = [{"content": "A" * 1000, "metadata": {"source": "test.md", "category": "dga", "title": "test"}}]
        chunks = split_documents(docs, chunk_size=200, overlap=50)
        assert len(chunks) > 1
        for chunk in chunks:
            assert len(chunk["content"]) <= 200
            assert "chunk_id" in chunk["metadata"]

    def test_split_preserves_metadata(self):
        from agent_layer.rag.ingest import split_documents
        docs = [{"content": "short text", "metadata": {"source": "a.md", "category": "intel", "title": "a"}}]
        chunks = split_documents(docs, chunk_size=512, overlap=50)
        assert len(chunks) == 1
        assert chunks[0]["metadata"]["source"] == "a.md"
        assert chunks[0]["metadata"]["category"] == "intel"


# ── RAG Engine Tests ──────────────────────────────────────

class TestThreatKnowledgeRAG:

    @patch("agent_layer.rag.engine.get_settings")
    def test_rag_initialization(self, mock_settings):
        mock_settings.return_value = MagicMock(
            es_hosts="http://localhost:9200",
            deepseek_api_key="",
        )
        from agent_layer.rag.engine import ThreatKnowledgeRAG
        rag = ThreatKnowledgeRAG()
        assert rag._es is None  # lazy init
        assert rag._embedder is not None

    @patch("agent_layer.rag.engine.get_settings")
    @patch("agent_layer.rag.engine.AsyncElasticsearch")
    @patch("agent_layer.rag.embedding.ThreatEmbedding.aembed")
    async def test_query_returns_answer_sources_structure(
        self, mock_aembed, mock_es_cls, mock_settings,
    ):
        mock_settings.return_value = MagicMock(
            es_hosts="http://localhost:9200",
            deepseek_api_key="",
        )
        mock_aembed.return_value = [[0.1] * 768]

        # Mock ES search responses
        mock_es = AsyncMock()
        mock_es.search = AsyncMock(return_value={
            "hits": {
                "hits": [
                    {
                        "_id": "doc1",
                        "_score": 0.95,
                        "_source": {
                            "content": "Conficker uses a DGA to generate domains",
                            "metadata": {"source": "conficker.md", "category": "dga_families"},
                        },
                    }
                ]
            }
        })
        mock_es.close = AsyncMock()
        mock_es_cls.return_value = mock_es

        from agent_layer.rag.engine import ThreatKnowledgeRAG
        rag = ThreatKnowledgeRAG()
        result = await rag.query("What is Conficker?")
        await rag.close()

        assert "answer" in result
        assert "sources" in result
        assert "query" in result
        assert result["query"] == "What is Conficker?"
        assert len(result["sources"]) >= 1
        assert "content" in result["sources"][0]
        assert "source" in result["sources"][0]

    @patch("agent_layer.rag.engine.get_settings")
    async def test_query_error_returns_empty(self, mock_settings):
        """When ES is unreachable, query should return empty answer gracefully."""
        mock_settings.return_value = MagicMock(
            es_hosts="http://localhost:9200",
            deepseek_api_key="",
        )
        from agent_layer.rag.engine import ThreatKnowledgeRAG
        rag = ThreatKnowledgeRAG()
        # Force ES to raise
        rag._es = AsyncMock()
        rag._es.search = AsyncMock(side_effect=Exception("connection refused"))
        rag._es.close = AsyncMock()

        result = await rag.query("anything")
        await rag.close()

        assert result["answer"] == ""
        assert result["sources"] == []
