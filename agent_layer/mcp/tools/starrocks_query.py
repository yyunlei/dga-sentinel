"""MCP Tool — StarRocks OLAP 查询"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from shared.config import get_settings
from shared.observability import get_logger

logger = get_logger(__name__)

_READ_ONLY_RE = re.compile(r"^\s*(SELECT|SHOW|DESCRIBE|DESC|EXPLAIN)\b", re.IGNORECASE)


class StarRocksQueryTool:
    """Execute SQL queries on StarRocks OLAP database."""

    name = "starrocks_query"
    description = "Execute SQL queries on StarRocks OLAP database"

    input_schema: dict = {
        "type": "object",
        "properties": {
            "sql": {"type": "string", "description": "SQL query to execute"},
            "db_type": {
                "type": "string",
                "enum": ["starrocks"],
                "default": "starrocks",
            },
        },
        "required": ["sql"],
    }

    async def run(self, **kwargs) -> dict:
        sql: str = kwargs["sql"]
        try:
            if not _READ_ONLY_RE.match(sql):
                return {"error": "Only read-only queries (SELECT/SHOW/DESCRIBE/EXPLAIN) are allowed"}

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
                    cur.execute(sql)
                    rows = cur.fetchall()
                    columns = [desc[0] for desc in cur.description] if cur.description else []
            finally:
                conn.close()

            return {
                "columns": columns,
                "rows": rows,
                "row_count": len(rows),
                "executed_at": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as exc:
            logger.error("starrocks_query_failed", error=str(exc))
            return {"error": str(exc)}
