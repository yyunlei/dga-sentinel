"""
运营推荐业务逻辑。
不依赖 FastAPI，只依赖 OperationsRepo。可独立单测。
"""
from __future__ import annotations

import json


def _row_to_item(r: dict) -> dict:
    detail = r["detail"]
    if isinstance(detail, str):
        try:
            detail = json.loads(detail)
        except Exception:  # noqa: BLE001
            detail = {"raw": detail}
    return {
        "id": r["id"],
        "pipeline_id": r["pipeline_id"],
        "operation": r["operation"],
        "operator": r["operator"],
        "status": r["status"],
        "detail": detail or {},
        "created_at": r["created_at"].isoformat() if r["created_at"] else "",
    }


class OperationsService:
    """运营推荐业务编排：查询、状态流转、审计日志。不做 HTTP。"""

    def __init__(self, repo) -> None:
        self._repo = repo

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    async def list_pending(
        self, op_type: str | None, limit: int
    ) -> dict:
        """返回 pending 推荐列表（items + total）。"""
        rows = await self._repo.fetch_pending(op_type, limit)
        items = [_row_to_item(dict(r)) for r in rows]
        return {"items": items, "total": len(items)}

    async def list_recent(self, limit: int) -> dict:
        """返回近期全部 operation（items + total）。"""
        rows = await self._repo.fetch_recent(limit)
        items = [_row_to_item(dict(r)) for r in rows]
        return {"items": items, "total": len(items)}

    async def get_stats(self) -> dict:
        """聚合计数：by_status、by_operation_pending、pending_total。"""
        by_status_rows = await self._repo.fetch_by_status_counts()
        by_op_pending_rows = await self._repo.fetch_pending_by_operation_counts()
        status_map = {r["status"]: r["n"] for r in by_status_rows}
        return {
            "by_status": status_map,
            "by_operation_pending": {r["operation"]: r["n"] for r in by_op_pending_rows},
            "pending_total": status_map.get("pending", 0),
        }

    # ------------------------------------------------------------------
    # 状态流转
    # ------------------------------------------------------------------

    async def transition(
        self,
        op_id: int,
        new_status: str,
        actor: dict,
    ) -> dict:
        """
        将指定 operation 从 pending 转换到 new_status。
        返回 {"id", "status", "by"}；
        rec 不存在时返回 {"_error": 404, "detail": ...}；
        已非 pending 时返回 {"_error": 409, "detail": ...}。
        """
        rec = await self._repo.fetchrow_by_id(op_id)
        if not rec:
            return {"_error": 404, "detail": f"Operation {op_id} not found"}
        if rec["status"] != "pending":
            return {"_error": 409, "detail": f"Operation {op_id} is already {rec['status']}"}

        await self._repo.update_status(op_id, new_status)
        user_id = actor.get("sub") or actor.get("username") or "analyst"
        await self._repo.write_audit_log(
            user_id,
            f"operation_{new_status}",
            str(op_id),
            json.dumps({"new_status": new_status, "by": user_id}),
        )
        return {"id": op_id, "status": new_status, "by": user_id}
