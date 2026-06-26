"""MCP Tool — Elasticsearch 查询"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from elasticsearch import AsyncElasticsearch
from shared.config import get_settings
from shared.observability import get_logger

logger = get_logger(__name__)


class ESQueryTool:
    """查询 Elasticsearch 中的告警和事件"""
    name = "es_query"
    description = "查询 Elasticsearch 中的 DGA 告警和事件数据"
    input_schema = {
        "type": "object",
        "properties": {
            "index": {"type": "string", "default": "dga-events-*", "description": "ES index pattern"},
            "query": {"type": "object", "description": "ES query DSL"},
            "size": {"type": "integer", "default": 10, "description": "Max results"},
            "sort": {"type": "object", "description": "Sort specification"},
        },
        "required": ["query"],
    }

    async def run(self, **kwargs) -> dict:
        settings = get_settings()
        index = kwargs.get("index", f"{settings.es_index_prefix}-*")
        query = kwargs.get("query", {"match_all": {}})
        size = kwargs.get("size", 10)
        sort = kwargs.get("sort", {"@timestamp": "desc"})
        try:
            es = AsyncElasticsearch(hosts=[settings.es_hosts])
            try:
                resp = await es.search(index=index, query=query, size=size, sort=sort)
                hits = [{"_id": h["_id"], **h["_source"]} for h in resp["hits"]["hits"]]
                return {"hits": hits, "total": resp["hits"]["total"]["value"]}
            finally:
                await es.close()
        except Exception as e:
            logger.error("es_query_error", error=str(e))
            return {"hits": [], "total": 0, "error": str(e)}
