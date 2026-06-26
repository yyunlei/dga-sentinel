"""MCP Tool — 报告生成（查询 ES / StarRocks 真实数据）"""

from __future__ import annotations

import csv
import io
import json
import re
from datetime import datetime, timezone

from elasticsearch import AsyncElasticsearch

from shared.config import get_settings
from shared.observability import get_logger

logger = get_logger(__name__)

_TIME_RE = re.compile(r"^(\d+)([hdwm])$")
_UNIT_MAP = {"h": "h", "d": "d", "w": "w", "m": "M"}


def _to_es_range(time_range: str) -> str:
    """Convert '24h' / '7d' / '30d' to ES date math like 'now-24h'."""
    m = _TIME_RE.match(time_range)
    if not m:
        return "now-24h"
    return f"now-{m.group(1)}{_UNIT_MAP[m.group(2)]}"


class ReportGenerateTool:
    """Generate threat analysis reports in CSV or JSON format."""

    name = "report_generate"
    description = "Generate threat analysis reports in CSV format"

    input_schema: dict = {
        "type": "object",
        "properties": {
            "report_type": {
                "type": "string",
                "enum": ["alert_summary", "threat_intel", "model_performance"],
            },
            "time_range": {"type": "string", "default": "24h"},
            "format": {
                "type": "string",
                "enum": ["csv", "json"],
                "default": "csv",
            },
        },
        "required": ["report_type"],
    }

    async def run(self, **kwargs) -> dict:
        report_type: str = kwargs["report_type"]
        fmt: str = kwargs.get("format", "csv")
        time_range: str = kwargs.get("time_range", "24h")
        try:
            rows = await self._query_data(report_type, time_range)
            now = datetime.now(timezone.utc).isoformat()

            if fmt == "json":
                content = json.dumps(rows, ensure_ascii=False)
            else:
                content = self._to_csv(rows)

            return {
                "report_type": report_type,
                "format": fmt,
                "content": content,
                "generated_at": now,
                "row_count": len(rows),
            }
        except Exception as exc:
            logger.error("report_generate_failed", error=str(exc))
            return {"error": str(exc)}

    # -- data queries --

    async def _query_data(self, report_type: str, time_range: str) -> list[dict]:
        if report_type == "alert_summary":
            return await self._alert_summary(time_range)
        if report_type == "threat_intel":
            return await self._threat_intel(time_range)
        return await self._model_performance()

    async def _alert_summary(self, time_range: str) -> list[dict]:
        """ES aggregation: alert count grouped by severity + family."""
        settings = get_settings()
        es = AsyncElasticsearch(hosts=[settings.es_hosts])
        try:
            resp = await es.search(
                index=f"{settings.es_index_prefix}-*",
                size=0,
                query={"bool": {"filter": [
                    {"range": {"@timestamp": {"gte": _to_es_range(time_range)}}},
                    {"term": {"is_dga": True}},
                ]}},
                aggs={
                    "by_severity": {
                        "terms": {"field": "severity.keyword", "size": 20},
                        "aggs": {"by_family": {"terms": {"field": "family.keyword", "size": 50}}},
                    }
                },
            )
            rows: list[dict] = []
            for sev_bucket in resp["aggregations"]["by_severity"]["buckets"]:
                for fam_bucket in sev_bucket["by_family"]["buckets"]:
                    rows.append({
                        "severity": sev_bucket["key"],
                        "family": fam_bucket["key"],
                        "count": fam_bucket["doc_count"],
                        "time_range": time_range,
                    })
            return rows
        finally:
            await es.close()

    async def _threat_intel(self, time_range: str) -> list[dict]:
        """ES query: top high-score DGA domains in the time range."""
        settings = get_settings()
        es = AsyncElasticsearch(hosts=[settings.es_hosts])
        try:
            resp = await es.search(
                index=f"{settings.es_index_prefix}-*",
                size=100,
                query={"bool": {"filter": [
                    {"range": {"@timestamp": {"gte": _to_es_range(time_range)}}},
                    {"range": {"score": {"gte": 0.7}}},
                    {"term": {"is_dga": True}},
                ]}},
                sort=[{"score": "desc"}],
                _source=["domain", "score", "family", "src_ip", "@timestamp"],
            )
            return [
                {
                    "domain": h["_source"].get("domain", ""),
                    "score": h["_source"].get("score", 0),
                    "family": h["_source"].get("family", "unknown"),
                    "src_ip": h["_source"].get("src_ip", ""),
                    "timestamp": h["_source"].get("@timestamp", ""),
                    "time_range": time_range,
                }
                for h in resp["hits"]["hits"]
            ]
        finally:
            await es.close()

    @staticmethod
    async def _model_performance() -> list[dict]:
        """StarRocks query: latest model metrics."""
        import pymysql

        settings = get_settings()
        conn = pymysql.connect(
            host=settings.starrocks_host,
            port=settings.starrocks_port,
            user=settings.starrocks_user,
            password=settings.starrocks_password,
            database=settings.starrocks_db,
            cursorclass=pymysql.cursors.DictCursor,
        )
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT model_id AS model, version, accuracy, f1, precision_val, recall_val, auc "
                    "FROM model_metrics ORDER BY created_at DESC LIMIT 20"
                )
                return cur.fetchall()
        finally:
            conn.close()

    @staticmethod
    def _to_csv(rows: list[dict]) -> str:
        if not rows:
            return ""
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
        return buf.getvalue()
