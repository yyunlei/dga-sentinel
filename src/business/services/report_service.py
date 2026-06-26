"""
报表统计业务编排 — ReportService。
不依赖 FastAPI；repo 通过构造函数注入，可独立单测。

职责：
  get_stats — 构建日期过滤条件，并发查询 ES 四类聚合（趋势 / Top 域名 / Top 主机 / 热力图），
              解析原始 ES 响应并组装最终响应 dict。
"""
from __future__ import annotations

import asyncio
from datetime import datetime

from common.observability import get_logger

logger = get_logger(__name__)


class ReportService:
    """报表统计业务编排：构建过滤条件 → asyncio.gather 四类 ES 查询 → 解析组装响应。

    不依赖 FastAPI；repo 通过构造函数注入。
    """

    def __init__(self, repo) -> None:
        """
        :param repo: ReportRepo（或实现相同接口的 fake）
        """
        self._repo = repo

    async def get_stats(
        self,
        days: int,
        start_date: str | None,
        end_date: str | None,
    ) -> dict:
        """并发查询四类 ES 聚合，解析并返回报表统计数据。

        :param days:       回溯天数（当 start_date / end_date 均为 None 时生效）
        :param start_date: 显式起始日期字符串（优先于 days）
        :param end_date:   显式结束日期字符串（优先于 days）
        :returns: {"trend": [...], "topDomains": [...], "topHosts": [...], "heatmap": [...]}
        :raises:  任何底层 ES / httpx 异常原样向上抛出，由 api 层处理 HTTP 异常映射。
        """
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

        # 并发请求
        r1, r2, r3, r4 = await asyncio.gather(
            self._repo.query_trend(date_range_filter),
            self._repo.query_top_domains(date_range_filter),
            self._repo.query_top_hosts(date_range_filter),
            self._repo.query_heatmap(date_range_filter),
        )

        # 解析趋势
        trend = []
        for b in r1["aggregations"]["per_day"]["buckets"]:
            ts = datetime.fromisoformat(b["key_as_string"].replace("Z", "+00:00"))
            trend.append({
                "date": f"{ts.month}/{ts.day}",
                "total": b["doc_count"],
                "dga": b["dga"]["doc_count"],
            })

        # 解析 Top 域名
        top_domains = [
            {"rank": i + 1, "key": i, "domain": b["key"], "count": b["doc_count"], "family": ""}
            for i, b in enumerate(r2["aggregations"]["top"]["buckets"])
        ]

        # 解析 Top 主机
        top_hosts = [
            {"rank": i + 1, "key": i, "src_ip": b["key"], "alerts": b["doc_count"],
             "unique_domains": b["unique_domains"]["value"]}
            for i, b in enumerate(r3["aggregations"]["top"]["buckets"])
        ]

        # 解析热力图
        heatmap = []
        hour_day_counts: dict[tuple[int, int], int] = {}
        for b in r4["aggregations"]["per_hour"]["buckets"]:
            ts = datetime.fromisoformat(b["key_as_string"].replace("Z", "+00:00"))
            key = (ts.hour, ts.weekday())
            hour_day_counts[key] = hour_day_counts.get(key, 0) + b["doc_count"]
        for h in range(24):
            for d in range(7):
                heatmap.append([h, d, hour_day_counts.get((h, d), 0)])

        return {"trend": trend, "topDomains": top_domains, "topHosts": top_hosts, "heatmap": heatmap}
