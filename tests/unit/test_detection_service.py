"""
DetectionService 单测：fake ScoringClient + fake redis/es，秒级运行，无需 Docker/TF。

覆盖：
  1. 缓存命中 → 跳过 ScoringClient 调用
  2. 缓存未命中 → 调 ScoringClient，结果写入缓存
  3. 混合（部分命中 + 部分未命中）→ 结果正确合并
  4. ES/StarRocks 写入只针对 is_dga 或 score >= 0.7 的结果
"""
from __future__ import annotations

import json
import pytest

from common.schemas import ScoreRequest, ScoreResult
from business.repositories.scoring_client import ScoringClient
from business.services.detection_service import DetectionService


# ---------------------------------------------------------------------------
# Fakes / helpers
# ---------------------------------------------------------------------------

def _make_result(domain: str, score: float, is_dga: bool = True) -> ScoreResult:
    return ScoreResult(
        domain=domain,
        score=score,
        is_dga=is_dga,
        family="qakbot" if is_dga else None,
        family_confidence=0.9 if is_dga else None,
        model_version="v1",
        cached=False,
    )


class FakeScoringClient(ScoringClient):
    """Returns a fixed list of ScoreResults; tracks how many times it was called."""

    def __init__(self, results: list[ScoreResult]) -> None:
        # don't call super().__init__ — no real URL needed
        self._results = results
        self.call_count = 0

    async def score(self, domains: list[str], tenant_id: str) -> list[ScoreResult]:
        self.call_count += 1
        # return only results whose domain is in the requested list
        return [r for r in self._results if r.domain in domains]


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


async def _noop_write_events(rows):
    """StarRocks 写入存根：记录调用但不实际写入。"""
    _noop_write_events.calls.append(rows)

_noop_write_events.calls = []


def _make_service(scoring_client, redis=None, es=None) -> DetectionService:
    return DetectionService(
        scoring_client=scoring_client,
        es=es,
        redis_client=redis,
        write_events_fn=_noop_write_events,
    )


def _make_req(domains: list[str], tenant_id: str = "test") -> ScoreRequest:
    return ScoreRequest(domains=domains, tenant_id=tenant_id)


def _cache_key(domain: str) -> str:
    import hashlib
    h = hashlib.sha256(domain.encode()).hexdigest()[:16]
    return f"score:{h}"


# ---------------------------------------------------------------------------
# Test 1: 全部缓存命中 → 跳过 ScoringClient
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_all_cache_hits_skip_scoring():
    """当所有域名都有缓存时，ScoringClient.score 不应被调用。"""
    domain = "evil.xyz"
    cached_result = _make_result(domain, 0.95)
    cached_data = cached_result.model_dump()
    cached_data["cached"] = True

    redis = FakeRedis({_cache_key(domain): json.dumps(cached_data)})
    scoring_client = FakeScoringClient([])  # 返回空，不应被调用

    svc = _make_service(scoring_client, redis=redis)
    req = _make_req([domain])
    results, latency_ms = await svc.score_domains(req, [domain], trace_id="t1")

    assert scoring_client.call_count == 0, "缓存命中时不应调用 ScoringClient"
    assert len(results) == 1
    assert results[0].domain == domain
    assert latency_ms >= 0


# ---------------------------------------------------------------------------
# Test 2: 全部缓存未命中 → 调 ScoringClient，并写入缓存
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cache_miss_calls_scoring_and_writes_cache():
    """缓存未命中时应调用 ScoringClient，并把结果写入 Redis。"""
    domain = "malware.cc"
    score_result = _make_result(domain, 0.88)

    redis = FakeRedis()  # 空缓存
    scoring_client = FakeScoringClient([score_result])

    svc = _make_service(scoring_client, redis=redis)
    req = _make_req([domain])
    results, latency_ms = await svc.score_domains(req, [domain], trace_id="t2")

    assert scoring_client.call_count == 1, "应调用 ScoringClient 一次"
    assert len(results) == 1
    assert results[0].domain == domain
    assert results[0].score == 0.88

    # 结果应已写入缓存
    assert len(redis.set_calls) == 1
    key, value, ex = redis.set_calls[0]
    assert key == _cache_key(domain)
    assert ex == 300  # TTL 保持 300s
    cached = json.loads(value)
    assert cached["cached"] is True
    assert cached["domain"] == domain


# ---------------------------------------------------------------------------
# Test 3: 混合（部分命中 + 部分未命中）→ 结果正确合并
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_partial_cache_hit_results_merged():
    """一个域名命中缓存，另一个未命中 → 结果应合并为 2 条，顺序为 cached + new。"""
    cached_domain = "cached.dga"
    uncached_domain = "new.dga"

    cached_result = _make_result(cached_domain, 0.91)
    cached_data = cached_result.model_dump()
    cached_data["cached"] = True

    new_result = _make_result(uncached_domain, 0.75)

    redis = FakeRedis({_cache_key(cached_domain): json.dumps(cached_data)})
    scoring_client = FakeScoringClient([new_result])

    svc = _make_service(scoring_client, redis=redis)
    req = _make_req([cached_domain, uncached_domain])
    results, _ = await svc.score_domains(
        req, [cached_domain, uncached_domain], trace_id="t3"
    )

    assert len(results) == 2
    domains_returned = [r.domain for r in results]
    assert cached_domain in domains_returned
    assert uncached_domain in domains_returned

    # cached 在前，new 在后（与原 score.py 行为一致）
    assert results[0].domain == cached_domain
    assert results[1].domain == uncached_domain

    # ScoringClient 只接收未命中的域名
    assert scoring_client.call_count == 1


# ---------------------------------------------------------------------------
# Test 4: 低分域名不写入存储（score < 0.7 且 is_dga=False）
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_low_score_not_stored():
    """score < 0.7 且 is_dga=False 的域名不写入 ES / StarRocks。"""
    domain = "legit.com"
    low_result = _make_result(domain, 0.1, is_dga=False)

    redis = FakeRedis()
    scoring_client = FakeScoringClient([low_result])

    stored_rows: list = []

    async def capture_write(rows):
        stored_rows.extend(rows)

    svc = DetectionService(
        scoring_client=scoring_client,
        es=None,
        redis_client=redis,
        write_events_fn=capture_write,
    )
    req = _make_req([domain])
    results, _ = await svc.score_domains(req, [domain], trace_id="t4")

    assert len(results) == 1
    assert stored_rows == [], "低分且非 DGA 的域名不应写入存储"


# ---------------------------------------------------------------------------
# Test 5: pipeline_id="gateway" 雷点核验
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pipeline_id_is_gateway():
    """ES 事件文档中 pipeline_id 必须为字符串 'gateway'。"""
    domain = "dga-test.ru"
    score_result = _make_result(domain, 0.95)

    redis = FakeRedis()
    scoring_client = FakeScoringClient([score_result])

    stored_rows: list[dict] = []

    async def capture_write(rows):
        stored_rows.extend(rows)

    svc = DetectionService(
        scoring_client=scoring_client,
        es=None,
        redis_client=redis,
        write_events_fn=capture_write,
    )
    req = _make_req([domain])
    await svc.score_domains(req, [domain], trace_id="t5")

    assert len(stored_rows) == 1
    assert stored_rows[0]["pipeline_id"] == "gateway", (
        "pipeline_id 必须为字符串 'gateway'，不能被改变"
    )
