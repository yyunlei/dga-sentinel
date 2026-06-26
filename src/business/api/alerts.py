"""
告警路由 — /alerts /incidents
HTTP 层：解析请求 → 调 AlertService → 包装响应/异常。
不包含 ES 查询逻辑，不包含业务规则。
"""
from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from elasticsearch import AsyncElasticsearch

from business.repositories.es_repo import AlertRepo
from business.infra.connections import get_es_client, get_es_http
from business.services.alert_service import AlertService
from business.middleware.rbac import require_analyst, require_write
from common.config import get_settings

router = APIRouter()


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


class AlertStatsResponse(BaseModel):
    total: int = 0
    pending: int = 0
    acknowledged: int = 0
    total_yesterday: int = 0
    by_severity: list[dict] = []


# ---------------------------------------------------------------------------
# Service factory
# ---------------------------------------------------------------------------


def _service(
    es: AsyncElasticsearch | None = Depends(get_es_client),
    http: httpx.AsyncClient | None = Depends(get_es_http),
) -> AlertService:
    """DI 工厂：注入 AlertRepo（共享 httpx 连接池）→ AlertService。"""
    if es is None or http is None:
        raise HTTPException(status_code=503, detail="Elasticsearch unavailable")
    es_base = get_settings().es_hosts.split(",")[0].strip()
    return AlertService(repo=AlertRepo(es=es, http=http, es_base=es_base))


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
    svc: AlertService = Depends(_service),
):
    """查询告警列表：支持多维度筛选"""
    try:
        total, alerts = await svc.list_alerts(
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
            limit=limit,
            offset=offset,
        )
    except Exception:
        raise HTTPException(status_code=503, detail="Elasticsearch unavailable")
    return AlertListResponse(
        total=total,
        alerts=[AlertSummary(**a) for a in alerts],
    )


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
    svc: AlertService = Depends(_service),
):
    """按域名聚合告警：相同域名合并为一条，显示告警次数、源 IP 列表等"""
    try:
        total_domains, groups = await svc.list_alerts_grouped(
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
            size=size,
        )
    except Exception:
        raise HTTPException(status_code=503, detail="Elasticsearch unavailable")
    return DomainGroupResponse(
        total_domains=total_domains,
        groups=[DomainGroupItem(**g) for g in groups],
    )


# ---------------------------------------------------------------------------
# Acknowledge all alerts for given domains
# ---------------------------------------------------------------------------


@router.post("/alerts/acknowledge-by-domain", dependencies=[Depends(require_write)])
async def acknowledge_by_domain(
    req: AckByDomainRequest,
    svc: AlertService = Depends(_service),
):
    """按域名批量确认告警"""
    if not req.domains:
        raise HTTPException(status_code=400, detail="domains list must not be empty")
    if len(req.domains) > 50:
        raise HTTPException(status_code=400, detail="domains list must not exceed 50")
    try:
        updated = await svc.acknowledge_by_domain(req.domains)
    except Exception:
        raise HTTPException(status_code=503, detail="ES unavailable")
    return {"updated": updated}


# ---------------------------------------------------------------------------
# Alert statistics (must be before /alerts/{event_id})
# ---------------------------------------------------------------------------


@router.get(
    "/alerts/stats",
    response_model=AlertStatsResponse,
    dependencies=[Depends(require_analyst)],
)
async def alert_stats(
    svc: AlertService = Depends(_service),
):
    """告警统计：总量、待处理、已确认、昨日总量、严重度分布"""
    stats = await svc.alert_stats()
    return AlertStatsResponse(**stats)


# ---------------------------------------------------------------------------
# Single alert detail
# ---------------------------------------------------------------------------


@router.get("/alerts/{event_id}", dependencies=[Depends(require_analyst)])
async def get_alert(
    event_id: str,
    svc: AlertService = Depends(_service),
):
    """获取告警详情"""
    try:
        result = await svc.get_alert(event_id)
    except Exception:
        raise HTTPException(status_code=503, detail="Elasticsearch unavailable")
    if result is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    return result


# ---------------------------------------------------------------------------
# Acknowledge single alert
# ---------------------------------------------------------------------------


@router.post("/alerts/{event_id}/acknowledge", dependencies=[Depends(require_write)])
async def acknowledge_alert(
    event_id: str,
    svc: AlertService = Depends(_service),
):
    """确认告警"""
    try:
        await svc.acknowledge_alert(event_id)
    except Exception:
        raise HTTPException(status_code=503, detail="ES unavailable")
    return {"event_id": event_id, "status": "acknowledged"}
