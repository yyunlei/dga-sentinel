"""MCP Tool — 模型信息查询"""
from __future__ import annotations
import asyncpg
from common.config import get_settings
from common.observability import get_logger

logger = get_logger(__name__)


class ModelInfoTool:
    """查询模型版本、性能指标、A/B 测试状态"""
    name = "model_info"
    description = "查询 DGA 检测模型的版本、状态和性能指标"
    input_schema = {
        "type": "object",
        "properties": {
            "model_id": {"type": "string", "description": "Specific model ID (optional)"},
            "status": {"type": "string", "enum": ["production", "staging", "archived"], "description": "Filter by status"},
        },
    }

    async def run(self, **kwargs) -> dict:
        settings = get_settings()
        model_id = kwargs.get("model_id", "")
        status = kwargs.get("status", "")
        try:
            conn = await asyncpg.connect(settings.pg_dsn)
            try:
                sql = "SELECT * FROM model_versions"
                params = []
                conditions = []
                if model_id:
                    conditions.append(f"model_id = ${len(params)+1}")
                    params.append(model_id)
                if status:
                    conditions.append(f"status = ${len(params)+1}")
                    params.append(status)
                if conditions:
                    sql += " WHERE " + " AND ".join(conditions)
                sql += " ORDER BY created_at DESC LIMIT 20"
                rows = await conn.fetch(sql, *params)
                models = [dict(r) for r in rows]
                for m in models:
                    for k, v in m.items():
                        if hasattr(v, 'isoformat'):
                            m[k] = v.isoformat()
                return {"models": models, "count": len(models)}
            finally:
                await conn.close()
        except Exception as e:
            logger.error("model_info_error", error=str(e))
            return {"models": [], "count": 0, "error": str(e)}
