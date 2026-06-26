"""
运营推荐数据层 — 封装所有 pipeline_operations + audit_log PG 操作。
业务规则不在此处。构造注入 pg pool。
"""
from __future__ import annotations

import json

import asyncpg


class OperationsRepo:
    def __init__(self, pg: asyncpg.Pool | None) -> None:
        self._pg = pg

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    async def fetch_pending(
        self, op_type: str | None, limit: int
    ) -> list[asyncpg.Record]:
        """列出 pending 状态推荐，可按 operation 类型过滤，按 id 倒序。"""
        if op_type:
            return await self._pg.fetch(
                """
                SELECT id, pipeline_id, operation, operator, status, detail, created_at
                FROM pipeline_operations
                WHERE status = 'pending' AND operation = $1
                ORDER BY id DESC LIMIT $2
                """,
                op_type, limit,
            )
        return await self._pg.fetch(
            """
            SELECT id, pipeline_id, operation, operator, status, detail, created_at
            FROM pipeline_operations
            WHERE status = 'pending'
            ORDER BY id DESC LIMIT $1
            """,
            limit,
        )

    async def fetch_recent(self, limit: int) -> list[asyncpg.Record]:
        """列出近期所有状态的 operation，按 id 倒序。"""
        return await self._pg.fetch(
            """
            SELECT id, pipeline_id, operation, operator, status, detail, created_at
            FROM pipeline_operations
            ORDER BY id DESC LIMIT $1
            """,
            limit,
        )

    async def fetch_by_status_counts(self) -> list[asyncpg.Record]:
        """按 status 聚合计数。"""
        return await self._pg.fetch(
            "SELECT status, COUNT(*)::int AS n FROM pipeline_operations GROUP BY status"
        )

    async def fetch_pending_by_operation_counts(self) -> list[asyncpg.Record]:
        """pending 状态按 operation 类型聚合计数。"""
        return await self._pg.fetch(
            "SELECT operation, COUNT(*)::int AS n FROM pipeline_operations "
            "WHERE status = 'pending' GROUP BY operation"
        )

    async def fetchrow_by_id(self, op_id: int) -> asyncpg.Record | None:
        """按 id 查询单条记录（仅 id + status）。"""
        return await self._pg.fetchrow(
            "SELECT id, status FROM pipeline_operations WHERE id = $1",
            op_id,
        )

    # ------------------------------------------------------------------
    # 状态变更
    # ------------------------------------------------------------------

    async def update_status(self, op_id: int, new_status: str) -> None:
        """将指定记录的 status 更新为 new_status。"""
        await self._pg.execute(
            "UPDATE pipeline_operations SET status = $1 WHERE id = $2",
            new_status, op_id,
        )

    async def write_audit_log(
        self,
        user_id: str,
        action: str,
        resource: str,
        detail: str,
    ) -> None:
        """写入 audit_log。"""
        await self._pg.execute(
            """
            INSERT INTO audit_log (user_id, action, resource, detail)
            VALUES ($1, $2, $3, $4::jsonb)
            """,
            user_id,
            action,
            resource,
            detail,
        )
