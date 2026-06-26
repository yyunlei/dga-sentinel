"""Text2SQL Engine — 自然语言转 SQL 查询"""
from __future__ import annotations
import re
from common.config import get_settings
from common.observability import get_logger
from ai.agents.text2sql.schema_registry import get_schema_context, get_allowed_tables

logger = get_logger(__name__)

FORBIDDEN_KEYWORDS = {
    "DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "CREATE", "TRUNCATE",
    "GRANT", "REVOKE", "EXEC", "EXECUTE", "INTO OUTFILE", "LOAD DATA",
}


class Text2SQLEngine:
    """自然语言 → SQL → 执行 → 解读"""

    def __init__(self, db_type: str = "starrocks"):
        self.db_type = db_type
        self.allowed_tables = get_allowed_tables(db_type)

    async def query(self, question: str) -> dict:
        """完整流程: 问题 → SQL → 执行 → 解读"""
        sql = await self._generate_sql(question)
        if not sql:
            return {"sql": "", "data": [], "explanation": "无法生成 SQL", "error": "generation_failed"}

        error = self._validate_sql(sql)
        if error:
            return {"sql": sql, "data": [], "explanation": "", "error": error}

        try:
            data = await self._execute_sql(sql)
        except Exception as e:
            # 不再把执行失败伪装成「0 条结果」——把真实错误带回 UI
            return {"sql": sql, "data": [], "explanation": f"查询执行失败: {e}", "error": "execution_failed"}
        explanation = await self._explain_result(question, sql, data)
        return {"sql": sql, "data": data, "explanation": explanation}

    async def _generate_sql(self, question: str) -> str:
        settings = get_settings()
        schema_ctx = get_schema_context(self.db_type)
        prompt = (
            f"你是一个 SQL 专家。根据以下表结构，将用户问题转换为 SQL 查询。\n\n"
            f"表结构:\n{schema_ctx}\n\n"
            f"用户问题: {question}\n\n"
            f"要求:\n"
            f"1. 只生成 SELECT 查询\n"
            f"2. 只使用上述表\n"
            f"3. 只输出 SQL，不要解释\n"
        )
        if not settings.deepseek_api_key:
            return self._fallback_sql(question)
        try:
            from langchain_openai import ChatOpenAI
            llm = ChatOpenAI(
                model=settings.deepseek_model,
                api_key=settings.deepseek_api_key,
                base_url=settings.deepseek_base_url,
                temperature=0,
            )
            resp = await llm.ainvoke(prompt)
            sql = resp.content.strip()
            # Extract SQL from markdown code blocks if present
            match = re.search(r"```(?:sql)?\s*(.*?)```", sql, re.DOTALL)
            if match:
                sql = match.group(1).strip()
            return sql
        except Exception as e:
            logger.error("text2sql_generate_error", error=str(e))
            return self._fallback_sql(question)

    def _validate_sql(self, sql: str) -> str | None:
        # 去除 SQL 注释
        cleaned = re.sub(r'/\*.*?\*/', ' ', sql, flags=re.DOTALL)
        cleaned = re.sub(r'--.*$', ' ', cleaned, flags=re.MULTILINE)
        upper = cleaned.upper().strip()
        if not upper.startswith("SELECT"):
            return "Only SELECT queries are allowed"
        # 禁止多语句（分号后还有内容）
        parts = [p.strip() for p in cleaned.split(";") if p.strip()]
        if len(parts) > 1:
            return "Multiple statements are not allowed"
        for kw in FORBIDDEN_KEYWORDS:
            if re.search(r'\b' + kw + r'\b', upper):
                return f"Forbidden keyword: {kw}"
        # Check table whitelist
        has_allowed = False
        for table in self.allowed_tables:
            if table in cleaned.lower():
                has_allowed = True
                break
        if not has_allowed:
            return "Query references unknown tables"
        return None

    async def _execute_sql(self, sql: str) -> list[dict]:
        settings = get_settings()
        try:
            if self.db_type == "starrocks":
                import pymysql
                conn = pymysql.connect(
                    host=settings.starrocks_host,
                    port=settings.starrocks_port,
                    user=settings.starrocks_user,
                    password=settings.starrocks_password,
                    database=settings.starrocks_db,
                )
                try:
                    with conn.cursor(pymysql.cursors.DictCursor) as cur:
                        cur.execute(sql)
                        return cur.fetchall()
                finally:
                    conn.close()
            else:
                import asyncpg
                conn = await asyncpg.connect(settings.pg_dsn)
                try:
                    rows = await conn.fetch(sql)
                    return [dict(r) for r in rows]
                finally:
                    await conn.close()
        except Exception as e:
            logger.error("text2sql_execute_error", error=str(e))
            raise

    async def _explain_result(self, question: str, sql: str, data: list) -> str:
        settings = get_settings()
        if not settings.deepseek_api_key or not data:
            return f"查询返回 {len(data)} 条结果"
        try:
            from langchain_openai import ChatOpenAI
            llm = ChatOpenAI(
                model=settings.deepseek_model,
                api_key=settings.deepseek_api_key,
                base_url=settings.deepseek_base_url,
                temperature=0.3,
            )
            sample = str(data[:5])[:1000]
            prompt = f"用户问题: {question}\nSQL: {sql}\n数据样本: {sample}\n请用 2-3 句话解读查询结果。"
            resp = await llm.ainvoke(prompt)
            return resp.content
        except Exception:
            return f"查询返回 {len(data)} 条结果"

    def _fallback_sql(self, question: str) -> str:
        q = question.lower()
        if "告警" in q and ("趋势" in q or "统计" in q):
            return "SELECT date, family, alert_count FROM alert_summary ORDER BY date DESC LIMIT 30"
        if "模型" in q:
            return "SELECT model_id, version, status, ab_weight FROM model_versions ORDER BY created_at DESC"
        return "SELECT * FROM dga_events ORDER BY detected_at DESC LIMIT 20"