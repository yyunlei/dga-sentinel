"""
AlertService 单测：用 FakeAlertRepo 隔离 ES，秒级运行，无需 Docker/TF。
"""
from __future__ import annotations

import pytest
from business.services.alert_service import AlertService


# ---------------------------------------------------------------------------
# Fake repo
# ---------------------------------------------------------------------------

class FakeAlertRepo:
    """最小可用 fake repo，返回固定数据覆盖 AlertService 所有路径。"""

    async def search_alerts(self, **kw) -> dict:
        return {
            "hits": {
                "hits": [
                    {
                        "_source": {
                            "event_id": "a1",
                            "domain": "evil.xyz",
                            "score": 0.95,
                            "family": "qakbot",
                            "severity": "HIGH",
                            "timestamp": "2024-01-02T10:00:00",
                            "src_ip": "1.2.3.4",
                            "is_dga": True,
                            "acknowledged": False,
                            "pipeline_id": "dag",
                        }
                    },
                    {
                        "_source": {
                            "event_id": "a2",
                            "domain": "bad.top",
                            "score": 0.7,
                            "family": None,
                            "severity": "MEDIUM",
                            "timestamp": "2024-01-01T08:00:00",
                            "src_ip": "5.6.7.8",
                            "is_dga": True,
                            "acknowledged": False,
                            "pipeline_id": "",
                        }
                    },
                ],
                "total": {"value": 2},
            }
        }

    async def search_alerts_grouped(self, **kw) -> dict:
        return {
            "aggregations": {
                "total_unique_domains": {"value": 1},
                "by_domain": {
                    "buckets": [
                        {
                            "key": "evil.xyz",
                            "doc_count": 5,
                            "unique_src_ips": {"buckets": [{"key": "1.2.3.4"}]},
                            "src_ip_count": {"value": 1},
                            "max_severity_bucket": {"buckets": [{"key": "CRITICAL"}, {"key": "HIGH"}]},
                            "max_score": {"value": 0.99},
                            "family_top": {"buckets": [{"key": "qakbot"}]},
                            "first_seen": {"value_as_string": "2024-01-01T00:00:00"},
                            "last_seen": {"value_as_string": "2024-01-02T00:00:00"},
                            "unacknowledged_count": {"doc_count": 3},
                        }
                    ]
                },
            }
        }

    async def acknowledge_by_domain(self, domains: list[str]) -> int:
        return len(domains) * 2

    async def alert_stats(self) -> dict:
        return {
            "hits": {"total": {"value": 100}},
            "aggregations": {
                "pending": {"doc_count": 40},
                "acknowledged_count": {"doc_count": 60},
                "yesterday": {"doc_count": 15},
                "by_severity": {
                    "buckets": [
                        {"key": "HIGH", "doc_count": 30},
                        {"key": "MEDIUM", "doc_count": 70},
                    ]
                },
            },
        }

    async def get_alert(self, event_id: str) -> dict | None:
        if event_id == "a1":
            return {"event_id": "a1", "domain": "evil.xyz", "severity": "HIGH"}
        return None

    async def acknowledge_alert(self, event_id: str) -> None:
        pass  # no-op in fake


class FailingAlertRepo(FakeAlertRepo):
    """alert_stats 故障的 repo，用于测试容错返回空统计。"""

    async def alert_stats(self) -> dict:
        raise RuntimeError("ES down")


# ---------------------------------------------------------------------------
# Tests: list_alerts
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_alerts_returns_all():
    svc = AlertService(repo=FakeAlertRepo())
    total, alerts = await svc.list_alerts()
    assert total == 2
    assert len(alerts) == 2


@pytest.mark.asyncio
async def test_list_alerts_sorted_by_timestamp_desc():
    svc = AlertService(repo=FakeAlertRepo())
    _, alerts = await svc.list_alerts()
    # a1 (2024-01-02) should come before a2 (2024-01-01)
    assert alerts[0]["event_id"] == "a1"
    assert alerts[1]["event_id"] == "a2"


@pytest.mark.asyncio
async def test_list_alerts_fields_present():
    svc = AlertService(repo=FakeAlertRepo())
    _, alerts = await svc.list_alerts()
    required = {"event_id", "domain", "score", "severity", "timestamp", "pipeline_id"}
    assert required.issubset(alerts[0].keys())


# ---------------------------------------------------------------------------
# Tests: get_alert
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_alert_found():
    svc = AlertService(repo=FakeAlertRepo())
    result = await svc.get_alert("a1")
    assert result is not None
    assert result["severity"] == "HIGH"


@pytest.mark.asyncio
async def test_get_alert_missing_returns_none():
    svc = AlertService(repo=FakeAlertRepo())
    assert await svc.get_alert("nonexistent") is None


# ---------------------------------------------------------------------------
# Tests: acknowledge_by_domain
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_acknowledge_by_domain():
    svc = AlertService(repo=FakeAlertRepo())
    updated = await svc.acknowledge_by_domain(["evil.xyz", "bad.top"])
    assert updated == 4  # FakeRepo returns len(domains) * 2


# ---------------------------------------------------------------------------
# Tests: alert_stats
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_alert_stats_normal():
    svc = AlertService(repo=FakeAlertRepo())
    stats = await svc.alert_stats()
    assert stats["total"] == 100
    assert stats["pending"] == 40
    assert stats["acknowledged"] == 60
    assert stats["total_yesterday"] == 15
    assert len(stats["by_severity"]) == 2


@pytest.mark.asyncio
async def test_alert_stats_es_down_returns_empty():
    """ES 异常时 alert_stats 返回全零，而非抛出异常（保持原行为）。"""
    svc = AlertService(repo=FailingAlertRepo())
    stats = await svc.alert_stats()
    assert stats["total"] == 0
    assert stats["pending"] == 0
    assert stats["by_severity"] == []


# ---------------------------------------------------------------------------
# Tests: list_alerts_grouped
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_alerts_grouped_max_severity():
    """CRITICAL 应排在 HIGH 前面，max_sev 应为 CRITICAL。"""
    svc = AlertService(repo=FakeAlertRepo())
    total_domains, groups = await svc.list_alerts_grouped()
    assert total_domains == 1
    assert groups[0]["max_severity"] == "CRITICAL"
    assert groups[0]["domain"] == "evil.xyz"


@pytest.mark.asyncio
async def test_list_alerts_grouped_acknowledged_flag():
    svc = AlertService(repo=FakeAlertRepo())
    _, groups = await svc.list_alerts_grouped()
    # unacknowledged_count=3, so all_acknowledged should be False
    assert groups[0]["all_acknowledged"] is False


# ---------------------------------------------------------------------------
# Tests: acknowledge_alert
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_acknowledge_alert_no_exception():
    svc = AlertService(repo=FakeAlertRepo())
    # Should complete without raising
    await svc.acknowledge_alert("a1")
