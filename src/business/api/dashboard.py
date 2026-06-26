"""
Dashboard 路由 — /dashboard/stats
提供仪表盘统计数据（检测量、命中率、QPS 历史、家族分布）
优先从 Redis 缓存读取，fallback 到 ES 聚合查询

业务编排已迁移至 business.services.realtime_service.RealtimeService：
  - Redis 缓存(30s TTL) → ES 多级 fallback → 空统计
  - 多级窗口 fallback：今日索引(404→24h) → total==0 时再扩至 30d
  - QPS 四级 fallback、P95 latency、家族分布、recent_alerts
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from business.repositories.pg_repo import get_redis_client
from business.repositories.es_repo import DashboardRepo
from business.services.realtime_service import RealtimeService
from business.middleware.rbac import require_analyst
from common.config import get_settings

router = APIRouter()


class DashboardStats(BaseModel):
    total_today: int
    dga_hits: int
    hit_rate: float
    p95_latency: float
    qps_history: list[dict]
    family_dist: list[dict]
    recent_alerts: list[dict] = []


@router.get("/dashboard/stats", dependencies=[Depends(require_analyst)])
async def get_dashboard_stats(redis=Depends(get_redis_client)):
    """获取仪表盘统计数据：Redis 缓存 → ES 聚合"""
    settings = get_settings()
    es_base = settings.es_hosts.split(",")[0].strip()
    repo = DashboardRepo(es_base=es_base)
    svc = RealtimeService(repo=repo, redis=redis, settings=settings)
    return await svc.get_dashboard_stats()
