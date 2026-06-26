"""
告警中心业务逻辑。
不依赖 FastAPI，只依赖 AlertRepo。可独立单测。
"""
from __future__ import annotations

_SEVERITY_PRIORITY: dict[str, int] = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}


class AlertService:
    """告警中心业务编排：parse ES 响应 → 领域数据结构，不做 HTTP。"""

    def __init__(self, repo) -> None:
        self._repo = repo

    # ------------------------------------------------------------------
    # 告警列表
    # ------------------------------------------------------------------

    async def list_alerts(
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
    ) -> tuple[int, list[dict]]:
        """返回 (total, list[dict])，调用方再构造 AlertSummary。"""
        resp = await self._repo.search_alerts(
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
        hits = resp["hits"]
        raw = hits["hits"]
        total = (
            hits["total"]["value"]
            if isinstance(hits["total"], dict)
            else hits["total"]
        )
        alerts = [
            {
                "event_id": h.get("_source", {}).get("event_id", ""),
                "domain": h.get("_source", {}).get("domain", ""),
                "score": float(h.get("_source", {}).get("score", 0)),
                "family": h.get("_source", {}).get("family"),
                "severity": h.get("_source", {}).get("severity", "MEDIUM"),
                "timestamp": h.get("_source", {}).get("timestamp", ""),
                "src_ip": h.get("_source", {}).get("src_ip", ""),
                "is_dga": h.get("_source", {}).get("is_dga", True),
                "acknowledged": h.get("_source", {}).get("acknowledged", False),
                "pipeline_id": h.get("_source", {}).get("pipeline_id", ""),
            }
            for h in raw
        ]
        alerts.sort(key=lambda a: a.get("timestamp", ""), reverse=True)
        return total, alerts

    # ------------------------------------------------------------------
    # 按域名分组
    # ------------------------------------------------------------------

    async def list_alerts_grouped(
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
    ) -> tuple[int, list[dict]]:
        """返回 (total_domains, list[group_dict])，调用方再构造 DomainGroupItem。"""
        resp = await self._repo.search_alerts_grouped(
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
        aggs = resp.get("aggregations", {})
        total_domains = aggs.get("total_unique_domains", {}).get("value", 0)
        buckets = aggs.get("by_domain", {}).get("buckets", [])

        groups: list[dict] = []
        for b in buckets:
            sev_buckets = b.get("max_severity_bucket", {}).get("buckets", [])
            max_sev = "LOW"
            if sev_buckets:
                max_sev = max(
                    sev_buckets,
                    key=lambda s: _SEVERITY_PRIORITY.get(s["key"], 0),
                )["key"]

            family_buckets = b.get("family_top", {}).get("buckets", [])
            top_family = family_buckets[0]["key"] if family_buckets else None

            unack = b.get("unacknowledged_count", {}).get("doc_count", 0)

            groups.append(
                {
                    "domain": b["key"],
                    "alert_count": b["doc_count"],
                    "unique_src_ips": [
                        ip["key"]
                        for ip in b.get("unique_src_ips", {}).get("buckets", [])
                    ],
                    "unique_src_ip_count": b.get("src_ip_count", {}).get("value", 0),
                    "max_severity": max_sev,
                    "max_score": b.get("max_score", {}).get("value", 0.0),
                    "family": top_family,
                    "first_seen": b.get("first_seen", {}).get("value_as_string", ""),
                    "last_seen": b.get("last_seen", {}).get("value_as_string", ""),
                    "all_acknowledged": (unack == 0),
                }
            )

        groups.sort(
            key=lambda g: (
                g["alert_count"],
                _SEVERITY_PRIORITY.get(g["max_severity"], 0),
            ),
            reverse=True,
        )
        return total_domains, groups

    # ------------------------------------------------------------------
    # 按域名批量确认
    # ------------------------------------------------------------------

    async def acknowledge_by_domain(self, domains: list[str]) -> int:
        """返回实际更新的文档数。"""
        return await self._repo.acknowledge_by_domain(domains)

    # ------------------------------------------------------------------
    # 统计
    # ------------------------------------------------------------------

    async def alert_stats(self) -> dict:
        """返回统计字段 dict；ES 不可用时返回全零默认值（保持原行为）。"""
        try:
            resp = await self._repo.alert_stats()
        except Exception:
            return {
                "total": 0,
                "pending": 0,
                "acknowledged": 0,
                "total_yesterday": 0,
                "by_severity": [],
            }

        aggs = resp.get("aggregations", {})
        total = resp.get("hits", {}).get("total", {})
        total_count = (
            total.get("value", 0) if isinstance(total, dict) else int(total)
        )
        return {
            "total": total_count,
            "pending": aggs.get("pending", {}).get("doc_count", 0),
            "acknowledged": aggs.get("acknowledged_count", {}).get("doc_count", 0),
            "total_yesterday": aggs.get("yesterday", {}).get("doc_count", 0),
            "by_severity": [
                {"name": b["key"], "value": b["doc_count"]}
                for b in aggs.get("by_severity", {}).get("buckets", [])
            ],
        }

    # ------------------------------------------------------------------
    # 单条告警
    # ------------------------------------------------------------------

    async def get_alert(self, event_id: str) -> dict | None:
        """返回 _source dict 或 None。"""
        return await self._repo.get_alert(event_id)

    # ------------------------------------------------------------------
    # 确认单条告警
    # ------------------------------------------------------------------

    async def acknowledge_alert(self, event_id: str) -> None:
        """标记单条告警为已确认。"""
        await self._repo.acknowledge_alert(event_id)
