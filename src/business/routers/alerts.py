"""
告警路由 — /alerts /incidents
"""

from __future__ import annotations

from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from elasticsearch import AsyncElasticsearch

from business.db import get_es_client
from business.middleware.rbac import require_analyst, require_write
from common.config import get_settings
from common.constants import ES_INDEX_EVENTS

# ES 8 服务不接受 compatible-with=9，用兼容头直接请求
_ES_V8_HEADERS = {
    "Accept": "application/vnd.elasticsearch+json;compatible-with=8",
    "Content-Type": "application/vnd.elasticsearch+json;compatible-with=8",
}


def _events_index_today() -> str:
    """当日索引名（score 写入用）"""
    return f"{ES_INDEX_EVENTS}-{datetime.now(timezone.utc).strftime('%Y.%m.%d')}"


def _events_index_wildcard() -> str:
    """通配符索引名，查询跨多天数据"""
    return f"{ES_INDEX_EVENTS}-*"


router = APIRouter()

SEVERITIES = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]
FAMILIES = ["qakbot", "necurs", "conficker", "suppobox", "ramnit", "matsnu"]
TLDS = ["xyz", "top", "club", "info", "net", "com"]

_SEVERITY_PRIORITY = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}


# ---------------------------------------------------------------------------
# Shared filter builder
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class AlertSummary(BaseModel):
    event_id: str
    domain: str
    score: float
    family: str | None
    severity: str
    timestamp: str
    src_ip: str = ""
    is_dga: bool = True
    acknowledged: bool = False
    pipeline_id: str = ""


class AlertListResponse(BaseModel):
    total: int
    alerts: list[AlertSummary]


class DomainGroupItem(BaseModel):
    domain: str
    alert_count: int
    unique_src_ips: list[str] = []
    unique_src_ip_count: int = 0
    max_severity: str = "LOW"
    max_score: float = 0.0
    family: str | None = None
    first_seen: str = ""
    last_seen: str = ""
    all_acknowledged: bool = False


class DomainGroupResponse(BaseModel):
    total_domains: int
    groups: list[DomainGroupItem]


class AckByDomainRequest(BaseModel):
    domains: list[str]


# ---------------------------------------------------------------------------
# List alerts (raw)
# ---------------------------------------------------------------------------


@router.get(
    "/alerts", response_model=AlertListResponse, dependencies=[Depends(require_analyst)]
)
async def list_alerts(
    severity: str | None = Query(None),
    family: str | None = Query(None),
    acknowledged: bool | None = Query(
        None, description="仅待处理: false；仅已确认: true"
    ),
    domain: str | None = Query(None, description="域名模糊搜索"),
    src_ip: str | None = Query(None, description="源 IP 精确匹配"),
    source: str | None = Query(
        None, description="来源: manual=手动评分, dag=DAG实时监测"
    ),
    pipeline_id: str | None = Query(None, description="Pipeline ID 精确匹配"),
    score_min: float | None = Query(None, description="最低分数"),
    score_max: float | None = Query(None, description="最高分数"),
    start_time: str | None = Query(None, description="开始时间 ISO 格式"),
    end_time: str | None = Query(None, description="结束时间 ISO 格式"),
    limit: int = Query(50, le=500),
    offset: int = Query(0),
    es: AsyncElasticsearch | None = Depends(get_es_client),
):
    """查询告警列表：支持多维度筛选"""
    if es is None:
        raise HTTPException(status_code=503, detail="Elasticsearch unavailable")

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

    def _parse(resp: dict):
        hits = resp["hits"]
        raw = hits["hits"]
        total = (
            hits["total"]["value"] if isinstance(hits["total"], dict) else hits["total"]
        )
        return total, [
            AlertSummary(
                event_id=h.get("_source", {}).get("event_id", ""),
                domain=h.get("_source", {}).get("domain", ""),
                score=float(h.get("_source", {}).get("score", 0)),
                family=h.get("_source", {}).get("family"),
                severity=h.get("_source", {}).get("severity", "MEDIUM"),
                timestamp=h.get("_source", {}).get("timestamp", ""),
                src_ip=h.get("_source", {}).get("src_ip", ""),
                is_dga=h.get("_source", {}).get("is_dga", True),
                acknowledged=h.get("_source", {}).get("acknowledged", False),
                pipeline_id=h.get("_source", {}).get("pipeline_id", ""),
            )
            for h in raw
        ]

    try:
        settings = get_settings()
        es_base = settings.es_hosts.split(",")[0].strip()
        url = f"{es_base}/{_events_index_wildcard()}/_search"
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(
                url,
                json={
                    "query": query,
                    "sort": [{"timestamp": "desc"}],
                    "from": offset,
                    "size": limit,
                },
                headers=_ES_V8_HEADERS,
            )
            r.raise_for_status()
            total, alerts = _parse(r.json())
    except Exception:
        raise HTTPException(status_code=503, detail="Elasticsearch unavailable")
    alerts.sort(key=lambda a: a.timestamp or "", reverse=True)
    return AlertListResponse(total=total, alerts=alerts)


# ---------------------------------------------------------------------------
# List alerts grouped by domain
# ---------------------------------------------------------------------------


@router.get(
    "/alerts/grouped",
    response_model=DomainGroupResponse,
    dependencies=[Depends(require_analyst)],
)
async def list_alerts_grouped(
    severity: str | None = Query(None),
    family: str | None = Query(None),
    acknowledged: bool | None = Query(None),
    domain: str | None = Query(None),
    src_ip: str | None = Query(None),
    source: str | None = Query(None),
    pipeline_id: str | None = Query(None),
    score_min: float | None = Query(None),
    score_max: float | None = Query(None),
    start_time: str | None = Query(None),
    end_time: str | None = Query(None),
    size: int = Query(200, le=2000, description="返回的域名分组数"),
    es: AsyncElasticsearch | None = Depends(get_es_client),
):
    """按域名聚合告警：相同域名合并为一条，显示告警次数、源 IP 列表等"""
    if es is None:
        raise HTTPException(status_code=503, detail="Elasticsearch unavailable")

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

    try:
        settings = get_settings()
        es_base = settings.es_hosts.split(",")[0].strip()
        url = f"{es_base}/{_events_index_wildcard()}/_search"
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(url, json=body, headers=_ES_V8_HEADERS)
            r.raise_for_status()
            data = r.json()
    except Exception:
        raise HTTPException(status_code=503, detail="Elasticsearch unavailable")

    aggs = data.get("aggregations", {})
    total_domains = aggs.get("total_unique_domains", {}).get("value", 0)
    buckets = aggs.get("by_domain", {}).get("buckets", [])

    groups: list[DomainGroupItem] = []
    for b in buckets:
        sev_buckets = b.get("max_severity_bucket", {}).get("buckets", [])
        max_sev = "LOW"
        if sev_buckets:
            max_sev = max(
                sev_buckets, key=lambda s: _SEVERITY_PRIORITY.get(s["key"], 0)
            )["key"]

        family_buckets = b.get("family_top", {}).get("buckets", [])
        top_family = family_buckets[0]["key"] if family_buckets else None

        unack = b.get("unacknowledged_count", {}).get("doc_count", 0)

        groups.append(
            DomainGroupItem(
                domain=b["key"],
                alert_count=b["doc_count"],
                unique_src_ips=[
                    ip["key"] for ip in b.get("unique_src_ips", {}).get("buckets", [])
                ],
                unique_src_ip_count=b.get("src_ip_count", {}).get("value", 0),
                max_severity=max_sev,
                max_score=b.get("max_score", {}).get("value", 0.0),
                family=top_family,
                first_seen=b.get("first_seen", {}).get("value_as_string", ""),
                last_seen=b.get("last_seen", {}).get("value_as_string", ""),
                all_acknowledged=(unack == 0),
            )
        )

    groups.sort(
        key=lambda g: (g.alert_count, _SEVERITY_PRIORITY.get(g.max_severity, 0)),
        reverse=True,
    )

    return DomainGroupResponse(total_domains=total_domains, groups=groups)


# ---------------------------------------------------------------------------
# Acknowledge all alerts for given domains
# ---------------------------------------------------------------------------


@router.post("/alerts/acknowledge-by-domain", dependencies=[Depends(require_write)])
async def acknowledge_by_domain(
    req: AckByDomainRequest,
    es: AsyncElasticsearch | None = Depends(get_es_client),
):
    """按域名批量确认告警"""
    if es is None:
        raise HTTPException(status_code=503, detail="Elasticsearch unavailable")
    if not req.domains:
        raise HTTPException(status_code=400, detail="domains list must not be empty")
    if len(req.domains) > 50:
        raise HTTPException(status_code=400, detail="domains list must not exceed 50")

    try:
        settings = get_settings()
        es_base = settings.es_hosts.split(",")[0].strip()
        url = f"{es_base}/{_events_index_wildcard()}/_update_by_query"
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(
                url,
                json={
                    "query": {
                        "bool": {
                            "must": [
                                {"terms": {"domain.keyword": req.domains}},
                                {"term": {"acknowledged": False}},
                            ]
                        }
                    },
                    "script": {"source": "ctx._source.acknowledged = true"},
                },
                headers=_ES_V8_HEADERS,
            )
            r.raise_for_status()
            updated = r.json().get("updated", 0)
    except Exception:
        raise HTTPException(status_code=503, detail="ES unavailable")
    return {"updated": updated}


# ---------------------------------------------------------------------------
# Alert statistics (must be before /alerts/{event_id})
# ---------------------------------------------------------------------------


class AlertStatsResponse(BaseModel):
    total: int = 0
    pending: int = 0
    acknowledged: int = 0
    total_yesterday: int = 0
    by_severity: list[dict] = []


@router.get(
    "/alerts/stats",
    response_model=AlertStatsResponse,
    dependencies=[Depends(require_analyst)],
)
async def alert_stats(
    es: AsyncElasticsearch | None = Depends(get_es_client),
):
    """告警统计：总量、待处理、已确认、昨日总量、严重度分布"""
    if es is None:
        raise HTTPException(status_code=503, detail="Elasticsearch unavailable")

    settings = get_settings()
    es_base = settings.es_hosts.split(",")[0].strip()
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

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(
                f"{es_base}/{wildcard}/_search",
                json=body,
                headers=_ES_V8_HEADERS,
            )
            r.raise_for_status()
            data = r.json()
    except Exception:
        return AlertStatsResponse()

    aggs = data.get("aggregations", {})
    total = data.get("hits", {}).get("total", {})
    total_count = total.get("value", 0) if isinstance(total, dict) else int(total)

    return AlertStatsResponse(
        total=total_count,
        pending=aggs.get("pending", {}).get("doc_count", 0),
        acknowledged=aggs.get("acknowledged_count", {}).get("doc_count", 0),
        total_yesterday=aggs.get("yesterday", {}).get("doc_count", 0),
        by_severity=[
            {"name": b["key"], "value": b["doc_count"]}
            for b in aggs.get("by_severity", {}).get("buckets", [])
        ],
    )


@router.get("/alerts/{event_id}", dependencies=[Depends(require_analyst)])
async def get_alert(
    event_id: str,
    es: AsyncElasticsearch | None = Depends(get_es_client),
):
    """获取告警详情"""
    # Try ES via httpx (wildcard index, ES 8 compatible)
    try:
        settings = get_settings()
        es_base = settings.es_hosts.split(",")[0].strip()
        url = f"{es_base}/{_events_index_wildcard()}/_search"
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(
                url,
                json={"query": {"term": {"event_id.keyword": event_id}}, "size": 1},
                headers=_ES_V8_HEADERS,
            )
            r.raise_for_status()
            hits = r.json()["hits"]["hits"]
            if hits:
                return hits[0]["_source"]
    except Exception:
        raise HTTPException(status_code=503, detail="Elasticsearch unavailable")

    raise HTTPException(status_code=404, detail="Alert not found")


@router.post("/alerts/{event_id}/acknowledge", dependencies=[Depends(require_write)])
async def acknowledge_alert(
    event_id: str,
    es: AsyncElasticsearch | None = Depends(get_es_client),
):
    """确认告警"""
    try:
        settings = get_settings()
        es_base = settings.es_hosts.split(",")[0].strip()
        url = f"{es_base}/{_events_index_wildcard()}/_update_by_query"
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(
                url,
                json={
                    "query": {"term": {"event_id.keyword": event_id}},
                    "script": {"source": "ctx._source.acknowledged = true"},
                },
                headers=_ES_V8_HEADERS,
            )
            r.raise_for_status()
    except Exception:
        raise HTTPException(status_code=503, detail="ES unavailable")
    return {"event_id": event_id, "status": "acknowledged"}
