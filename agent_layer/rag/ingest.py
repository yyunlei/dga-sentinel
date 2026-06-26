"""知识库导入脚本 — 文档分块 + Embedding + 写入 ES"""
from __future__ import annotations
import asyncio
from pathlib import Path
from elasticsearch import AsyncElasticsearch
from agent_layer.rag.embedding import ThreatEmbedding
from shared.config import get_settings
from shared.observability import get_logger

logger = get_logger(__name__)

INDEX_NAME = "threat-knowledge-vectors"

def load_documents(directory: str) -> list[dict]:
    """加载目录下所有 .md 文件"""
    docs = []
    for path in Path(directory).rglob("*.md"):
        content = path.read_text(encoding="utf-8")
        docs.append({
            "content": content,
            "metadata": {
                "source": str(path),
                "category": path.parent.name,
                "title": path.stem,
            },
        })
    return docs

def split_documents(docs: list[dict], chunk_size: int = 512, overlap: int = 50) -> list[dict]:
    """递归字符分块"""
    chunks = []
    for doc in docs:
        text = doc["content"]
        meta = doc["metadata"]
        start = 0
        chunk_id = 0
        while start < len(text):
            end = min(start + chunk_size, len(text))
            chunk_text = text[start:end]
            chunks.append({
                "content": chunk_text,
                "metadata": {**meta, "chunk_id": chunk_id},
            })
            start += chunk_size - overlap
            chunk_id += 1
    return chunks

async def ingest(knowledge_dir: str = "docs/knowledge"):
    settings = get_settings()
    embedder = ThreatEmbedding()
    es = AsyncElasticsearch(hosts=[settings.es_hosts])
    try:
        docs = load_documents(knowledge_dir)
        logger.info("ingest_loaded", doc_count=len(docs))
        chunks = split_documents(docs)
        logger.info("ingest_chunked", chunk_count=len(chunks))
        texts = [c["content"] for c in chunks]
        embeddings = await embedder.aembed(texts)
        # Bulk index
        for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
            await es.index(index=INDEX_NAME, document={
                "content": chunk["content"],
                "embedding": emb,
                "metadata": chunk["metadata"],
            })
        logger.info("ingest_complete", indexed=len(chunks))
    finally:
        await es.close()

if __name__ == "__main__":
    import sys
    d = sys.argv[1] if len(sys.argv) > 1 else "docs/knowledge"
    asyncio.run(ingest(d))
