"""
RealtimeService 单测：fake DashboardRepo + fake Redis，秒级运行，无需 Docker/ES。

覆盖：
  1. Redis 缓存命中 → 跳过 repo 调用
  2. 今日索引有数据 → 无 fallback（仅 1 次 count_aggs 调用）
  3. 今日索引 404 → fallback 到 24h（24h 有数据，不再继续）
  4. 今日索引 404 + 24h 为 0 → fallback 到 30d
  5. 今日索引存在但 total=0 → 直接 fallback 到 30d（不经 24h）
  6. QPS 空桶过滤：doc_count=0 的 bucket 不进入 qps_history
"""
from __future__ import annotations

import json
import pytest

from business.repositories.es_repo import IndexNotFoundError
from business.services.realtime_service import RealtimeService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_es_count_response(
    total: int,
    dga_hits: int = 0,
    family_buckets: list[dict] | None = None,
) -> dict:
    """构造 dashboard_count_aggs 的 ES 返回结构。"""
    return {
        "hits": {"total": {"value": total, "relation": "eq"}, "hits": []},
        "aggregations": {
            "dga_hits": {"doc_count": dga_hits},
            "family_dist": {"buckets": family_buckets or []},
        },
    }


class FakeDashboardRepo:
    """按调用顺序消费预设响应（dict → 返回，Exception → 抛出）的 DashboardRepo fake。"""

    def __init__(
        self,
        count_responses: list,
        qps_responses: list | None = None,
    ) -> None:
        self._count_responses = list(count_responses)
        self._qps_responses = list(qps_responses or [])
        self.count_calls: list[tuple[str, dict]] = []   # (target, query)
        self.qps_calls: list[tuple[str, str]] = []      # (interval, granularity)

    async def dashboard_count_aggs(self, target: str, query: dict) -> dict:
        self.count_calls.append((target, query))
        if not self._count_responses:
            return _make_es_count_response(0)
        resp = self._count_responses.pop(0)
        if isinstance(resp, Exception):
            raise resp
        return resp

    async def qps_buckets(self, interval: str, granularity: str) -> list[dict]:
        self.qps_calls.append((interval, granularity))
        if not self._qps_responses:
            return []
        resp = self._qps_responses.pop(0)
        if isinstance(resp, Exception):
            raise resp
        return resp

    async def recent_dga_alerts(self, limit: int = 30) -> list[dict]:
        return []


class FakeRedis:
    """In-memory fake Redis with get/set."""

    def __init__(self, initial: dict[str, str] | None = None) -> None:
        self._store: dict[str, str] = dict(initial or {})
        self.set_calls: list[tuple] = []

    async def get(self, key: str) -> str | None:
        return self._store.get(key)

    async def set(self, key: str, value: str, ex: int = 0) -> None:
        self._store[key] = value
        self.set_calls.append((key, value, ex))


def _make_svc(repo, redis=None) -> RealtimeService:
    """构造 RealtimeService，settings=None（跳过 Prometheus 查询）。"""
    return RealtimeService(repo=repo, redis=redis, settings=None)


# ---------------------------------------------------------------------------
# Test 1: Redis 缓存命中 → 跳过 repo 调用
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_redis_cache_hit_skips_repo():
    """缓存有效时，DashboardRepo 的任何方法都不应被调用。"""
    cached_stats = {
        "total_today": 99, "dga_hits": 50, "hit_rate": 50.5,
        "p95_latency": 12.0, "qps_history": [], "family_dist": [],
        "recent_alerts": [],
    }
    redis = FakeRedis({"dashboard:stats": json.dumps(cached_stats)})
    repo = FakeDashboardRepo([])

    svc = _make_svc(repo, redis=redis)
    result = await svc.get_dashboard_stats()

    assert result["total_today"] == 99
    assert repo.count_calls == [], "缓存命中时不应调用 repo"


# ---------------------------------------------------------------------------
# Test 2: 今日索引有数据 → 无 fallback
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_today_has_data_no_fallback():
    """今日索引返回 total=150，只需 1 次 count_aggs 调用，不走 24h/30d。"""
    today_response = _make_es_count_response(total=150, dga_hits=75)
    repo = FakeDashboardRepo([today_response])

    svc = _make_svc(repo, redis=FakeRedis())
    result = await svc.get_dashboard_stats()

    assert result["total_today"] == 150
    assert result["dga_hits"] == 75
    assert result["hit_rate"] == 50.0
    assert len(repo.count_calls) == 1, "今日有数据时只应查询 1 次"
    # 确认第一次查询是 today index（match_all）
    _, first_query = repo.count_calls[0]
    assert first_query == {"match_all": {}}


# ---------------------------------------------------------------------------
# Test 3: 今日索引 404 → fallback 到 24h（24h 有数据）
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_today_404_fallback_to_24h():
    """今日索引不存在(404)，fallback 到 24h，24h 有数据，不再继续到 30d。"""
    h24_response = _make_es_count_response(total=50, dga_hits=20)
    repo = FakeDashboardRepo([
        IndexNotFoundError("dga-events-2099.01.01"),  # today → 404
        h24_response,                                  # 24h
    ])

    svc = _make_svc(repo, redis=FakeRedis())
    result = await svc.get_dashboard_stats()

    assert result["total_today"] == 50
    assert result["dga_hits"] == 20
    assert len(repo.count_calls) == 2, "today(404) + 24h = 2 次调用"

    # 第二次查询是 24h wildcard
    _, second_query = repo.count_calls[1]
    assert second_query == {"range": {"timestamp": {"gte": "now-24h"}}}


# ---------------------------------------------------------------------------
# Test 4: 今日索引 404 + 24h 为 0 → fallback 到 30d
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_today_404_24h_empty_fallback_to_30d():
    """今日索引 404，24h 返回 0 docs，继续 fallback 到 30d。"""
    d30_response = _make_es_count_response(total=80, dga_hits=40)
    repo = FakeDashboardRepo([
        IndexNotFoundError("dga-events-2099.01.01"),  # today → 404
        _make_es_count_response(total=0, dga_hits=0),  # 24h → 0
        d30_response,                                   # 30d
    ])

    svc = _make_svc(repo, redis=FakeRedis())
    result = await svc.get_dashboard_stats()

    assert result["total_today"] == 80
    assert result["dga_hits"] == 40
    assert len(repo.count_calls) == 3, "today(404) + 24h(0) + 30d = 3 次调用"

    # 第三次查询是 30d
    _, third_query = repo.count_calls[2]
    assert third_query == {"range": {"timestamp": {"gte": "now-30d"}}}


# ---------------------------------------------------------------------------
# Test 5: 今日索引存在但 total=0 → 直接 fallback 到 30d（不经 24h）
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_today_exists_but_empty_goes_directly_to_30d():
    """今日索引存在且返回 total=0（非 404），直接 fallback 到 30d，不经过 24h。"""
    d30_response = _make_es_count_response(total=60, dga_hits=30)
    repo = FakeDashboardRepo([
        _make_es_count_response(total=0, dga_hits=0),  # today exists, 0 docs
        d30_response,                                    # 30d
    ])

    svc = _make_svc(repo, redis=FakeRedis())
    result = await svc.get_dashboard_stats()

    assert result["total_today"] == 60
    assert len(repo.count_calls) == 2, "today(0) + 30d = 2 次调用（跳过 24h）"

    # 确认没有 24h 查询（第一次是 match_all，第二次是 30d range）
    _, first_query = repo.count_calls[0]
    _, second_query = repo.count_calls[1]
    assert first_query == {"match_all": {}}
    assert second_query == {"range": {"timestamp": {"gte": "now-30d"}}}


# ---------------------------------------------------------------------------
# Test 6: QPS 空桶过滤 —— doc_count=0 的 bucket 不进入 qps_history
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_qps_empty_bucket_filtered_out():
    """QPS buckets 中 doc_count=0 的 bucket 不应出现在 qps_history 中。"""
    buckets_with_empties = [
        # empty bucket — should be filtered
        {
            "key_as_string": "2024-01-01T00:00:00Z",
            "doc_count": 0,
            "hits": {"doc_count": 0},
        },
        # non-empty bucket — should appear in result
        {
            "key_as_string": "2024-01-01T01:00:00+00:00",
            "doc_count": 5,
            "hits": {"doc_count": 3},
        },
        # another empty — should be filtered
        {
            "key_as_string": "2024-01-01T02:00:00Z",
            "doc_count": 0,
            "hits": {"doc_count": 0},
        },
    ]

    today_response = _make_es_count_response(total=10, dga_hits=5)
    # Only 60m/1min bucket list; rest return empty → loop breaks on first non-empty window
    repo = FakeDashboardRepo(
        count_responses=[today_response],
        qps_responses=[buckets_with_empties],  # 60m window returns buckets above
    )

    svc = _make_svc(repo, redis=FakeRedis())
    result = await svc.get_dashboard_stats()

    qps = result["qps_history"]
    assert len(qps) == 1, "只有 1 个 doc_count>0 的 bucket 应出现"
    assert qps[0]["qps"] == 5
    assert qps[0]["hits"] == 3


# ---------------------------------------------------------------------------
# Test 7: 结果写入 Redis 缓存（TTL=30s）
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_result_written_to_cache():
    """ES 查询成功后，结果应写入 Redis，key='dashboard:stats'，TTL=30。"""
    today_response = _make_es_count_response(total=10, dga_hits=3)
    repo = FakeDashboardRepo([today_response])
    redis = FakeRedis()

    svc = _make_svc(repo, redis=redis)
    await svc.get_dashboard_stats()

    assert len(redis.set_calls) == 1
    key, value, ex = redis.set_calls[0]
    assert key == "dashboard:stats"
    assert ex == 30
    stored = json.loads(value)
    assert stored["total_today"] == 10
    assert stored["dga_hits"] == 3
