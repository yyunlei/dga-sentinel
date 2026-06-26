"""
报表数据路由 — /reports/stats
提供 30 天趋势、Top DGA 域名、Top 受影响主机、告警热力图
数据来源：ES dga-events-* 聚合查询
"""
from __future__ import annotations

import asyncio
import httpx
from fastapi import APIRouter, Depends, HTTPException, Query

from business.middleware.rbac import require_viewer
from common.config import get_settings
from common.constants import ES_INDEX_EVENTS
from common.observability import get_logger

router = APIRouter()
logger = get_logger(__name__)

_ES_V8_HEADERS = {
    "Accept": "application/vnd.elasticsearch+json;compatible-with=8",
    "Content-Type": "application/vnd.elasticsearch+json;compatible-with=8",
}


@router.get("/reports/stats", dependencies=[Depends(require_viewer)])
async def report_stats(
    days: int = Query(30, le=90),
    start_date: str | None = None,
    end_date: str | None = None,
):
    """报表统计：趋势、Top 域名/主机、热力图"""
    settings = get_settings()
    es_base = settings.es_hosts.split(",")[0].strip()
    wildcard = f"{ES_INDEX_EVENTS}-*"

    # Build date range filter: explicit dates take priority over `days`
    if start_date or end_date:
        ts_range: dict = {}
        if start_date:
            ts_range["gte"] = start_date
        if end_date:
            ts_range["lte"] = end_date
    else:
        ts_range = {"gte": f"now-{days}d"}

    date_range_filter = {"range": {"timestamp": ts_range}}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            # 1) 每日趋势
            trend_body = {
                "size": 0,
                "query": date_range_filter,
                "aggs": {
                    "per_day": {
                        "date_histogram": {"field": "timestamp", "calendar_interval": "day"},
                        "aggs": {"dga": {"filter": {"term": {"is_dga": True}}}},
                    }
                },
            }
            # 2) Top 10 DGA 域名
            top_domains_body = {
                "size": 0,
                "query": {"bool": {"must": [
                    date_range_filter,
                    {"term": {"is_dga": True}},
                ]}},
                "aggs": {"top": {"terms": {"field": "domain.keyword", "size": 10}}},
            }

            # 3) Top 10 受影响主机
            top_hosts_body = {
                "size": 0,
                "query": {"bool": {"must": [
                    date_range_filter,
                    {"term": {"is_dga": True}},
                ]}},
                "aggs": {
                    "top": {
                        "terms": {"field": "src_ip.keyword", "size": 10},
                        "aggs": {"unique_domains": {"cardinality": {"field": "domain.keyword"}}},
                    }
                },
            }

            # 4) 热力图 (hour_of_day × day_of_week)
            heatmap_body = {
                "size": 0,
                "query": date_range_filter,
                "aggs": {
                    "per_hour": {
                        "date_histogram": {"field": "timestamp", "calendar_interval": "hour"},
                    }
                },
            }

            # 并发请求
            r1, r2, r3, r4 = await asyncio.gather(
                client.post(f"{es_base}/{wildcard}/_search", json=trend_body, headers=_ES_V8_HEADERS),
                client.post(f"{es_base}/{wildcard}/_search", json=top_domains_body, headers=_ES_V8_HEADERS),
                client.post(f"{es_base}/{wildcard}/_search", json=top_hosts_body, headers=_ES_V8_HEADERS),
                client.post(f"{es_base}/{wildcard}/_search", json=heatmap_body, headers=_ES_V8_HEADERS),
            )

        # 解析趋势
        trend = []
        for b in r1.json()["aggregations"]["per_day"]["buckets"]:
            from datetime import datetime
            ts = datetime.fromisoformat(b["key_as_string"].replace("Z", "+00:00"))
            trend.append({
                "date": f"{ts.month}/{ts.day}",
                "total": b["doc_count"],
                "dga": b["dga"]["doc_count"],
            })

        # 解析 Top 域名
        top_domains = [
            {"rank": i + 1, "key": i, "domain": b["key"], "count": b["doc_count"], "family": ""}
            for i, b in enumerate(r2.json()["aggregations"]["top"]["buckets"])
        ]

        # 解析 Top 主机
        top_hosts = [
            {"rank": i + 1, "key": i, "src_ip": b["key"], "alerts": b["doc_count"],
             "unique_domains": b["unique_domains"]["value"]}
            for i, b in enumerate(r3.json()["aggregations"]["top"]["buckets"])
        ]

        # 解析热力图
        heatmap = []
        hour_day_counts: dict[tuple[int, int], int] = {}
        for b in r4.json()["aggregations"]["per_hour"]["buckets"]:
            from datetime import datetime
            ts = datetime.fromisoformat(b["key_as_string"].replace("Z", "+00:00"))
            key = (ts.hour, ts.weekday())
            hour_day_counts[key] = hour_day_counts.get(key, 0) + b["doc_count"]
        for h in range(24):
            for d in range(7):
                heatmap.append([h, d, hour_day_counts.get((h, d), 0)])

        return {"trend": trend, "topDomains": top_domains, "topHosts": top_hosts, "heatmap": heatmap}

    except Exception as e:
        logger.warning("reports_es_fallback", error=str(e))
        raise HTTPException(status_code=503, detail="Report data unavailable")
