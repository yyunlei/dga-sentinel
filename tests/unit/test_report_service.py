"""
ReportService 单测：fake ReportRepo，秒级运行，无需 Docker/ES。

覆盖：
  1. 默认 days 参数 → date_range_filter 使用 now-{days}d
  2. 显式 start_date + end_date → 构建 gte/lte 过滤
  3. 仅 start_date → 只有 gte，无 lte
  4. 趋势聚合解析：date/total/dga 字段映射正确
  5. Top 域名解析：rank、domain、count、family 字段
  6. Top 主机解析：rank、src_ip、alerts、unique_domains 字段
  7. 热力图组装：24×7 完整矩阵（168 个元素），计数累加正确
  8. asyncio.gather 确认四个 repo 方法全部被调用
"""
from __future__ import annotations

import pytest

from business.services.report_service import ReportService


# ---------------------------------------------------------------------------
# Fake repo
# ---------------------------------------------------------------------------

class FakeReportRepo:
    """按预设响应模拟 ReportRepo 的四个查询方法。"""

    def __init__(
        self,
        trend_resp: dict | Exception,
        top_domains_resp: dict | Exception,
        top_hosts_resp: dict | Exception,
        heatmap_resp: dict | Exception,
    ) -> None:
        self._trend = trend_resp
        self._top_domains = top_domains_resp
        self._top_hosts = top_hosts_resp
        self._heatmap = heatmap_resp
        self.calls: list[tuple[str, dict]] = []  # (method_name, date_range_filter)

    async def query_trend(self, date_range_filter: dict) -> dict:
        self.calls.append(("trend", date_range_filter))
        if isinstance(self._trend, Exception):
            raise self._trend
        return self._trend

    async def query_top_domains(self, date_range_filter: dict) -> dict:
        self.calls.append(("top_domains", date_range_filter))
        if isinstance(self._top_domains, Exception):
            raise self._top_domains
        return self._top_domains

    async def query_top_hosts(self, date_range_filter: dict) -> dict:
        self.calls.append(("top_hosts", date_range_filter))
        if isinstance(self._top_hosts, Exception):
            raise self._top_hosts
        return self._top_hosts

    async def query_heatmap(self, date_range_filter: dict) -> dict:
        self.calls.append(("heatmap", date_range_filter))
        if isinstance(self._heatmap, Exception):
            raise self._heatmap
        return self._heatmap


# ---------------------------------------------------------------------------
# ES 响应构造辅助函数
# ---------------------------------------------------------------------------

def _trend_response(buckets: list[dict]) -> dict:
    return {"aggregations": {"per_day": {"buckets": buckets}}}


def _top_domains_response(buckets: list[dict]) -> dict:
    return {"aggregations": {"top": {"buckets": buckets}}}


def _top_hosts_response(buckets: list[dict]) -> dict:
    return {"aggregations": {"top": {"buckets": buckets}}}


def _heatmap_response(buckets: list[dict]) -> dict:
    return {"aggregations": {"per_hour": {"buckets": buckets}}}


def _empty_responses() -> tuple[dict, dict, dict, dict]:
    """返回四个全空 ES 响应。"""
    return (
        _trend_response([]),
        _top_domains_response([]),
        _top_hosts_response([]),
        _heatmap_response([]),
    )


def _make_svc(
    trend_resp=None,
    top_domains_resp=None,
    top_hosts_resp=None,
    heatmap_resp=None,
) -> tuple[ReportService, FakeReportRepo]:
    """构造 (ReportService, FakeReportRepo)，未指定的响应默认为空。"""
    tr, td, th, hm = _empty_responses()
    repo = FakeReportRepo(
        trend_resp=trend_resp if trend_resp is not None else tr,
        top_domains_resp=top_domains_resp if top_domains_resp is not None else td,
        top_hosts_resp=top_hosts_resp if top_hosts_resp is not None else th,
        heatmap_resp=heatmap_resp if heatmap_resp is not None else hm,
    )
    return ReportService(repo=repo), repo


# ---------------------------------------------------------------------------
# Test 1: 默认 days 参数 → date_range_filter 使用 now-{days}d
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_default_days_builds_correct_filter():
    """days=30，无显式日期 → filter 应为 {'range': {'timestamp': {'gte': 'now-30d'}}}"""
    svc, repo = _make_svc()
    await svc.get_stats(days=30, start_date=None, end_date=None)

    # 所有方法都收到相同的 date_range_filter
    assert len(repo.calls) == 4
    for _, flt in repo.calls:
        assert flt == {"range": {"timestamp": {"gte": "now-30d"}}}


# ---------------------------------------------------------------------------
# Test 2: 显式 start_date + end_date → 构建 gte/lte 过滤
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_explicit_start_and_end_date_filter():
    """start_date='2024-01-01', end_date='2024-01-31' → filter 含 gte 和 lte"""
    svc, repo = _make_svc()
    await svc.get_stats(days=30, start_date="2024-01-01", end_date="2024-01-31")

    expected_filter = {"range": {"timestamp": {"gte": "2024-01-01", "lte": "2024-01-31"}}}
    for _, flt in repo.calls:
        assert flt == expected_filter


# ---------------------------------------------------------------------------
# Test 3: 仅 start_date → 只有 gte，无 lte
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_only_start_date_no_lte():
    """仅 start_date='2024-06-01'，end_date=None → filter 只有 gte，无 lte"""
    svc, repo = _make_svc()
    await svc.get_stats(days=30, start_date="2024-06-01", end_date=None)

    expected_filter = {"range": {"timestamp": {"gte": "2024-06-01"}}}
    for _, flt in repo.calls:
        assert flt == expected_filter


# ---------------------------------------------------------------------------
# Test 4: 趋势聚合解析
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_trend_parsing():
    """趋势 bucket 正确解析为 date/total/dga 字段。"""
    trend_buckets = [
        {
            "key_as_string": "2024-03-15T00:00:00Z",
            "doc_count": 100,
            "dga": {"doc_count": 40},
        },
        {
            "key_as_string": "2024-03-16T00:00:00+00:00",
            "doc_count": 200,
            "dga": {"doc_count": 80},
        },
    ]
    svc, _ = _make_svc(trend_resp=_trend_response(trend_buckets))
    result = await svc.get_stats(days=30, start_date=None, end_date=None)

    trend = result["trend"]
    assert len(trend) == 2
    assert trend[0] == {"date": "3/15", "total": 100, "dga": 40}
    assert trend[1] == {"date": "3/16", "total": 200, "dga": 80}


# ---------------------------------------------------------------------------
# Test 5: Top 域名解析
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_top_domains_parsing():
    """Top 域名 buckets 解析为含 rank/key/domain/count/family 的列表。"""
    domain_buckets = [
        {"key": "evil.dga.ru", "doc_count": 500},
        {"key": "bad.malware.cn", "doc_count": 300},
    ]
    svc, _ = _make_svc(top_domains_resp=_top_domains_response(domain_buckets))
    result = await svc.get_stats(days=7, start_date=None, end_date=None)

    top_domains = result["topDomains"]
    assert len(top_domains) == 2
    assert top_domains[0] == {"rank": 1, "key": 0, "domain": "evil.dga.ru", "count": 500, "family": ""}
    assert top_domains[1] == {"rank": 2, "key": 1, "domain": "bad.malware.cn", "count": 300, "family": ""}


# ---------------------------------------------------------------------------
# Test 6: Top 主机解析
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_top_hosts_parsing():
    """Top 主机 buckets 解析为含 rank/key/src_ip/alerts/unique_domains 的列表。"""
    host_buckets = [
        {"key": "192.168.1.10", "doc_count": 120, "unique_domains": {"value": 15}},
        {"key": "10.0.0.5", "doc_count": 80, "unique_domains": {"value": 8}},
    ]
    svc, _ = _make_svc(top_hosts_resp=_top_hosts_response(host_buckets))
    result = await svc.get_stats(days=30, start_date=None, end_date=None)

    top_hosts = result["topHosts"]
    assert len(top_hosts) == 2
    assert top_hosts[0] == {"rank": 1, "key": 0, "src_ip": "192.168.1.10", "alerts": 120, "unique_domains": 15}
    assert top_hosts[1] == {"rank": 2, "key": 1, "src_ip": "10.0.0.5", "alerts": 80, "unique_domains": 8}


# ---------------------------------------------------------------------------
# Test 7: 热力图 24×7 完整矩阵
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_heatmap_full_matrix_and_accumulation():
    """热力图应输出 168 个元素（24h × 7d），同一 (hour, weekday) 的计数需累加。"""
    # Monday 2024-01-01 is weekday 0; hour 14 → (14, 0) → count 5
    # Monday 2024-01-01 same hour second bucket → (14, 0) should accumulate → count 5+3=8
    # Tuesday 2024-01-02 hour 9 → (9, 1) → count 10
    heatmap_buckets = [
        {"key_as_string": "2024-01-01T14:00:00+00:00", "doc_count": 5},
        {"key_as_string": "2024-01-01T14:00:00+00:00", "doc_count": 3},  # same slot — should accumulate
        {"key_as_string": "2024-01-02T09:00:00+00:00", "doc_count": 10},
    ]
    svc, _ = _make_svc(heatmap_resp=_heatmap_response(heatmap_buckets))
    result = await svc.get_stats(days=30, start_date=None, end_date=None)

    heatmap = result["heatmap"]
    assert len(heatmap) == 168, "热力图应有 24×7=168 个元素"

    # Find [14, 0, ...] and [9, 1, ...]
    slot_14_0 = next(e for e in heatmap if e[0] == 14 and e[1] == 0)
    slot_9_1 = next(e for e in heatmap if e[0] == 9 and e[1] == 1)
    slot_0_0 = next(e for e in heatmap if e[0] == 0 and e[1] == 0)

    assert slot_14_0[2] == 8, "同一时间槽的计数应累加: 5+3=8"
    assert slot_9_1[2] == 10
    assert slot_0_0[2] == 0, "无数据的时间槽应为 0"


# ---------------------------------------------------------------------------
# Test 8: asyncio.gather — 四个 repo 方法全部被调用
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_all_four_repo_methods_called():
    """get_stats 应通过 asyncio.gather 调用四个 repo 方法各一次。"""
    svc, repo = _make_svc()
    await svc.get_stats(days=14, start_date=None, end_date=None)

    called_methods = [name for name, _ in repo.calls]
    assert len(called_methods) == 4
    assert "trend" in called_methods
    assert "top_domains" in called_methods
    assert "top_hosts" in called_methods
    assert "heatmap" in called_methods
