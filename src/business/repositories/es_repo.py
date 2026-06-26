"""
告警/事件 ES 数据访问。
封装索引命名、ES8 兼容头、查询构造。业务规则不在此处。
"""
from __future__ import annotations

import httpx
from datetime import datetime, timezone

from common.constants import ES_INDEX_EVENTS

# ES 8 服务不接受 compatible-with=9，用兼容头直接请求
ES8_HEADERS = {
    "Accept": "application/vnd.elasticsearch+json;compatible-with=8",
    "Content-Type": "application/vnd.elasticsearch+json;compatible-with=8",
}


def _events_index_today() -> str:
    """当日索引名（score 写入用）"""
    return f"{ES_INDEX_EVENTS}-{datetime.now(timezone.utc).strftime('%Y.%m.%d')}"


def _events_index_wildcard() -> str:
    """通配符索引名，查询跨多天数据"""
    return f"{ES_INDEX_EVENTS}-*"


def _build_filter_query(
    severity: str | None = None,
    family: str | None = None,
    acknowledged: bool | None = None,
    domain: str | None = None,
    src_ip: str | None = None,
    source: str | None = None,
    pipeline_id: str | None = None,
    score_min: float | None = None,
    score_max: float | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
) -> dict:
    """构建 ES bool query，list_alerts 和 list_alerts_grouped 共用。"""
    must: list[dict] = []
    if severity:
        must.append({"term": {"severity.keyword": severity}})
    if family:
        must.append({"term": {"family.keyword": family}})
    if acknowledged is False:
        must.append({"term": {"acknowledged": False}})
    elif acknowledged is True:
        must.append({"term": {"acknowledged": True}})
    if domain:
        must.append({"wildcard": {"domain.keyword": {"value": f"*{domain}*"}}})
    if src_ip:
        must.append({"term": {"src_ip.keyword": src_ip}})
    if source == "manual":
        must.append(
            {
                "bool": {
                    "should": [
                        {"term": {"pipeline_id.keyword": "gateway"}},
                        {"bool": {"must_not": {"exists": {"field": "pipeline_id"}}}},
                    ],
                    "minimum_should_match": 1,
                }
            }
        )
    elif source == "dag":
        must.append({"exists": {"field": "pipeline_id"}})
        must.append(
            {"bool": {"must_not": {"term": {"pipeline_id.keyword": "gateway"}}}}
        )
    if pipeline_id:
        must.append({"term": {"pipeline_id.keyword": pipeline_id}})
    if score_min is not None or score_max is not None:
        range_q: dict = {}
        if score_min is not None:
            range_q["gte"] = score_min
        if score_max is not None:
            range_q["lte"] = score_max
        must.append({"range": {"score": range_q}})
    if start_time or end_time:
        time_range: dict = {}
        if start_time:
            time_range["gte"] = start_time
        if end_time:
            time_range["lte"] = end_time
        must.append({"range": {"timestamp": time_range}})
    return {"bool": {"must": must}} if must else {"match_all": {}}


class AlertRepo:
    """告警/事件 ES 仓储：只做 ES 交互，不含业务规则。"""

    def __init__(self, es, es_base: str) -> None:
        """
        :param es: AsyncElasticsearch 实例（用于存活判断，由调用方检查是否 None）
        :param es_base: ES HTTP 基础地址，如 http://localhost:9200
        """
        self._es = es
        self._es_base = es_base

    # ------------------------------------------------------------------
    # 告警列表
    # ------------------------------------------------------------------

    async def search_alerts(
        self,
        *,
        severity: str | None = None,
        family: str | None = None,
        acknowledged: bool | None = None,
        domain: str | None = None,
        src_ip: str | None = None,
        source: str | None = None,
        pipeline_id: str | None = None,
        score_min: float | None = None,
        score_max: float | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        """返回原始 ES 响应 dict。"""
        query = _build_filter_query(
            severity=severity,
            family=family,
            acknowledged=acknowledged,
            domain=domain,
            src_ip=src_ip,
            source=source,
            pipeline_id=pipeline_id,
            score_min=score_min,
            score_max=score_max,
            start_time=start_time,
            end_time=end_time,
        )
        url = f"{self._es_base}/{_events_index_wildcard()}/_search"
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(
                url,
                json={
                    "query": query,
                    "sort": [{"timestamp": "desc"}],
                    "from": offset,
                    "size": limit,
                },
                headers=ES8_HEADERS,
            )
            r.raise_for_status()
            return r.json()

    # ------------------------------------------------------------------
    # 按域名分组聚合
    # ------------------------------------------------------------------

    async def search_alerts_grouped(
        self,
        *,
        severity: str | None = None,
        family: str | None = None,
        acknowledged: bool | None = None,
        domain: str | None = None,
        src_ip: str | None = None,
        source: str | None = None,
        pipeline_id: str | None = None,
        score_min: float | None = None,
        score_max: float | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        size: int = 200,
    ) -> dict:
        """返回包含 aggregations 的原始 ES 响应 dict。"""
        query = _build_filter_query(
            severity=severity,
            family=family,
            acknowledged=acknowledged,
            domain=domain,
            src_ip=src_ip,
            source=source,
            pipeline_id=pipeline_id,
            score_min=score_min,
            score_max=score_max,
            start_time=start_time,
            end_time=end_time,
        )
        body = {
            "size": 0,
            "query": query,
            "aggs": {
                "by_domain": {
                    "terms": {
                        "field": "domain.keyword",
                        "size": size,
                        "order": {"_count": "desc"},
                    },
                    "aggs": {
                        "unique_src_ips": {
                            "terms": {"field": "src_ip.keyword", "size": 10}
                        },
                        "src_ip_count": {"cardinality": {"field": "src_ip.keyword"}},
                        "max_severity_bucket": {
                            "terms": {"field": "severity.keyword", "size": 4}
                        },
                        "max_score": {"max": {"field": "score"}},
                        "family_top": {"terms": {"field": "family.keyword", "size": 1}},
                        "first_seen": {"min": {"field": "timestamp"}},
                        "last_seen": {"max": {"field": "timestamp"}},
                        "unacknowledged_count": {
                            "filter": {"term": {"acknowledged": False}}
                        },
                    },
                },
                "total_unique_domains": {"cardinality": {"field": "domain.keyword"}},
            },
        }
        url = f"{self._es_base}/{_events_index_wildcard()}/_search"
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(url, json=body, headers=ES8_HEADERS)
            r.raise_for_status()
            return r.json()

    # ------------------------------------------------------------------
    # 按域名批量确认
    # ------------------------------------------------------------------

    async def acknowledge_by_domain(self, domains: list[str]) -> int:
        """返回已更新的文档数。"""
        url = f"{self._es_base}/{_events_index_wildcard()}/_update_by_query"
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(
                url,
                json={
                    "query": {
                        "bool": {
                            "must": [
                                {"terms": {"domain.keyword": domains}},
                                {"term": {"acknowledged": False}},
                            ]
                        }
                    },
                    "script": {"source": "ctx._source.acknowledged = true"},
                },
                headers=ES8_HEADERS,
            )
            r.raise_for_status()
            return r.json().get("updated", 0)

    # ------------------------------------------------------------------
    # 统计汇总
    # ------------------------------------------------------------------

    async def alert_stats(self) -> dict:
        """返回包含 aggregations 的原始 ES 响应 dict。"""
        wildcard = _events_index_wildcard()
        body = {
            "size": 0,
            "query": {"match_all": {}},
            "aggs": {
                "total": {"value_count": {"field": "event_id.keyword"}},
                "pending": {
                    "filter": {"term": {"acknowledged": False}},
                },
                "acknowledged_count": {
                    "filter": {"term": {"acknowledged": True}},
                },
                "by_severity": {
                    "terms": {"field": "severity.keyword", "size": 10},
                },
                "yesterday": {
                    "filter": {
                        "range": {
                            "timestamp": {
                                "gte": "now-1d/d",
                                "lt": "now/d",
                            }
                        }
                    },
                },
            },
        }
        url = f"{self._es_base}/{wildcard}/_search"
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(url, json=body, headers=ES8_HEADERS)
            r.raise_for_status()
            return r.json()

    # ------------------------------------------------------------------
    # 单条告警
    # ------------------------------------------------------------------

    async def get_alert(self, event_id: str) -> dict | None:
        """返回 _source dict 或 None（不存在时）。"""
        url = f"{self._es_base}/{_events_index_wildcard()}/_search"
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(
                url,
                json={"query": {"term": {"event_id.keyword": event_id}}, "size": 1},
                headers=ES8_HEADERS,
            )
            r.raise_for_status()
            hits = r.json()["hits"]["hits"]
            return hits[0]["_source"] if hits else None

    # ------------------------------------------------------------------
    # 确认单条告警
    # ------------------------------------------------------------------

    async def acknowledge_alert(self, event_id: str) -> None:
        """通过 update_by_query 将单条告警标记为已确认。"""
        url = f"{self._es_base}/{_events_index_wildcard()}/_update_by_query"
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(
                url,
                json={
                    "query": {"term": {"event_id.keyword": event_id}},
                    "script": {"source": "ctx._source.acknowledged = true"},
                },
                headers=ES8_HEADERS,
            )
            r.raise_for_status()
