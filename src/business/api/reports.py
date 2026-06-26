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
    from business.repositories.es_repo import ReportRepo
    from business.services.report_service import ReportService

    settings = get_settings()
    es_base = settings.es_hosts.split(",")[0].strip()
    repo = ReportRepo(es_base=es_base)
    svc = ReportService(repo=repo)

    try:
        return await svc.get_stats(days=days, start_date=start_date, end_date=end_date)
    except Exception as e:
        logger.warning("reports_es_fallback", error=str(e))
        raise HTTPException(status_code=503, detail="Report data unavailable")
