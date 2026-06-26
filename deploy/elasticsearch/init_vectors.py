"""创建 ES 向量索引 threat-knowledge-vectors"""
import asyncio
from elasticsearch import AsyncElasticsearch

INDEX_NAME = "threat-knowledge-vectors"

MAPPING = {
    "mappings": {
        "properties": {
            "content": {"type": "text", "analyzer": "ik_max_word", "search_analyzer": "ik_smart"},
            "embedding": {"type": "dense_vector", "dims": 768, "index": True, "similarity": "cosine"},
            "metadata": {
                "properties": {
                    "source": {"type": "keyword"},
                    "category": {"type": "keyword"},
                    "title": {"type": "text"},
                    "chunk_id": {"type": "integer"},
                }
            },
        }
    },
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
        "index.knn": True,
    },
}

async def create_index(es_hosts: str = "http://localhost:9200"):
    es = AsyncElasticsearch(hosts=[es_hosts])
    try:
        exists = await es.indices.exists(index=INDEX_NAME)
        if not exists:
            await es.indices.create(index=INDEX_NAME, body=MAPPING)
            print(f"Created index: {INDEX_NAME}")
        else:
            print(f"Index already exists: {INDEX_NAME}")
    finally:
        await es.close()

if __name__ == "__main__":
    import sys
    hosts = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:9200"
    asyncio.run(create_index(hosts))
