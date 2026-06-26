"""
OperationsService 单测：fake repo，秒级运行，无需 Docker/PG。

覆盖：
  1. list_pending — 透传 repo 行（无 op_type 过滤）
  2. list_pending — 透传 repo 行（有 op_type 过滤）
  3. list_recent  — 透传 repo 行，字段正确转换
  4. get_stats    — 正确组装 by_status / by_operation_pending / pending_total
  5. transition acknowledge — 成功路径：状态转换 + 审计写入
  6. transition dismiss     — 成功路径：状态转换 + 审计写入
  7. transition — 记录不存在，返回 404 错误 dict
  8. transition — 已非 pending，返回 409 错误 dict
"""
from __future__ import annotations

import datetime

import pytest

from business.services.operations_service import OperationsService


# ---------------------------------------------------------------------------
# Fake repo
# ---------------------------------------------------------------------------

class _FakeRecord(dict):
    """模拟 asyncpg.Record（支持 dict() 转换，created_at 为 datetime）。"""
    pass


def _make_record(**kwargs) -> _FakeRecord:
    r = _FakeRecord(kwargs)
    return r


class FakeOperationsRepo:
    """记录所有调用，返回可控结果。"""

    def __init__(self) -> None:
        self.calls: dict[str, list] = {}
        self._pending_rows: list[dict] = []
        self._recent_rows: list[dict] = []
        self._status_counts: list[dict] = []
        self._op_pending_counts: list[dict] = []
        self._fetchrow_result: dict | None = None

    def _record(self, method: str, *args) -> None:
        self.calls.setdefault(method, []).append(args)

    async def fetch_pending(self, op_type, limit):
        self._record("fetch_pending", op_type, limit)
        return self._pending_rows

    async def fetch_recent(self, limit):
        self._record("fetch_recent", limit)
        return self._recent_rows

    async def fetch_by_status_counts(self):
        self._record("fetch_by_status_counts")
        return self._status_counts

    async def fetch_pending_by_operation_counts(self):
        self._record("fetch_pending_by_operation_counts")
        return self._op_pending_counts

    async def fetchrow_by_id(self, op_id):
        self._record("fetchrow_by_id", op_id)
        return self._fetchrow_result

    async def update_status(self, op_id, new_status):
        self._record("update_status", op_id, new_status)

    async def write_audit_log(self, user_id, action, resource, detail):
        self._record("write_audit_log", user_id, action, resource, detail)


def _make_service(repo=None):
    if repo is None:
        repo = FakeOperationsRepo()
    return OperationsService(repo=repo), repo


_SAMPLE_ROW = {
    "id": 1,
    "pipeline_id": "pipe-a",
    "operation": "retrain",
    "operator": "system",
    "status": "pending",
    "detail": '{"reason": "drift"}',
    "created_at": datetime.datetime(2025, 1, 1, 12, 0, 0),
}


# ---------------------------------------------------------------------------
# Test 1: list_pending — 无 op_type
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_pending_no_filter():
    """list_pending 无过滤时透传 repo 行，字段正确转换。"""
    svc, repo = _make_service()
    repo._pending_rows = [_make_record(**_SAMPLE_ROW)]

    result = await svc.list_pending(op_type=None, limit=50)

    assert result["total"] == 1
    assert len(result["items"]) == 1
    item = result["items"][0]
    assert item["id"] == 1
    assert item["pipeline_id"] == "pipe-a"
    assert item["operation"] == "retrain"
    assert isinstance(item["detail"], dict)
    assert item["detail"] == {"reason": "drift"}
    assert item["created_at"] == "2025-01-01T12:00:00"
    # repo 被调用时 op_type=None 被透传
    assert repo.calls["fetch_pending"][0] == (None, 50)


# ---------------------------------------------------------------------------
# Test 2: list_pending — 有 op_type 过滤
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_pending_with_op_type_filter():
    """list_pending 有 op_type 时透传过滤参数给 repo。"""
    svc, repo = _make_service()
    repo._pending_rows = []

    result = await svc.list_pending(op_type="retrain", limit=10)

    assert result == {"items": [], "total": 0}
    assert repo.calls["fetch_pending"][0] == ("retrain", 10)


# ---------------------------------------------------------------------------
# Test 3: list_recent — 字段转换
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_recent_converts_fields():
    """list_recent 透传 repo 行，detail 从 JSON 字符串解析，created_at 转 isoformat。"""
    svc, repo = _make_service()
    repo._recent_rows = [_make_record(**_SAMPLE_ROW)]

    result = await svc.list_recent(limit=100)

    assert result["total"] == 1
    item = result["items"][0]
    assert item["detail"] == {"reason": "drift"}
    assert item["created_at"] == "2025-01-01T12:00:00"
    assert repo.calls["fetch_recent"][0] == (100,)


# ---------------------------------------------------------------------------
# Test 4: get_stats — 正确组装
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_stats_assembles_correctly():
    """get_stats 应正确聚合 by_status、by_operation_pending 和 pending_total。"""
    svc, repo = _make_service()
    repo._status_counts = [
        _make_record(status="pending", n=5),
        _make_record(status="acknowledged", n=3),
    ]
    repo._op_pending_counts = [
        _make_record(operation="retrain", n=4),
        _make_record(operation="adjust_threshold", n=1),
    ]

    result = await svc.get_stats()

    assert result["by_status"] == {"pending": 5, "acknowledged": 3}
    assert result["by_operation_pending"] == {"retrain": 4, "adjust_threshold": 1}
    assert result["pending_total"] == 5


# ---------------------------------------------------------------------------
# Test 5: transition acknowledge — 成功路径
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_transition_acknowledge_success():
    """acknowledge 成功时返回 {id, status, by} 并调用 update_status + write_audit_log。"""
    svc, repo = _make_service()
    repo._fetchrow_result = _make_record(id=7, status="pending")

    result = await svc.transition(7, "acknowledged", {"sub": "analyst01"})

    assert result == {"id": 7, "status": "acknowledged", "by": "analyst01"}
    assert repo.calls["update_status"][0] == (7, "acknowledged")
    assert "write_audit_log" in repo.calls
    audit_args = repo.calls["write_audit_log"][0]
    assert audit_args[0] == "analyst01"
    assert audit_args[1] == "operation_acknowledged"
    assert audit_args[2] == "7"


# ---------------------------------------------------------------------------
# Test 6: transition dismiss — 成功路径
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_transition_dismiss_success():
    """dismiss 成功时返回 {id, status, by} 并写审计日志。"""
    svc, repo = _make_service()
    repo._fetchrow_result = _make_record(id=3, status="pending")

    result = await svc.transition(3, "dismissed", {"username": "analyst02"})

    assert result["status"] == "dismissed"
    assert result["by"] == "analyst02"
    assert repo.calls["update_status"][0] == (3, "dismissed")


# ---------------------------------------------------------------------------
# Test 7: transition — 记录不存在，返回 404 错误 dict
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_transition_not_found_returns_error_dict():
    """op_id 不存在时，返回 _error=404 的 dict，不调用 update_status。"""
    svc, repo = _make_service()
    repo._fetchrow_result = None

    result = await svc.transition(99, "acknowledged", {"sub": "analyst"})

    assert result["_error"] == 404
    assert "99" in result["detail"]
    assert "update_status" not in repo.calls
    assert "write_audit_log" not in repo.calls


# ---------------------------------------------------------------------------
# Test 8: transition — 已非 pending，返回 409 错误 dict
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_transition_already_not_pending_returns_409():
    """已 acknowledged 的记录再次 acknowledge 时返回 _error=409。"""
    svc, repo = _make_service()
    repo._fetchrow_result = _make_record(id=5, status="acknowledged")

    result = await svc.transition(5, "acknowledged", {"sub": "analyst"})

    assert result["_error"] == 409
    assert "acknowledged" in result["detail"]
    assert "update_status" not in repo.calls
