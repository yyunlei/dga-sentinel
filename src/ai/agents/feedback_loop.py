"""
Feedback Aggregator — 关闭反馈闭环

每 ~5 分钟做一次：
  1. 读取 PG `feedback` 表最近 30 天的人工标注
  2. 聚合 (domain) → (FP 数, TP 数)
  3. 规则：
     - FP ≥ 5 且 TP = 0 → 加入 Redis SET `whitelist:auto`
     - TP ≥ 3 且 FP = 0 → 加入 Redis SET `blacklist:auto`
  4. 每次 pass **整集合原子替换**（DEL + SADD pipeline），
     domain 在 30 天窗口外停止获得反馈 → 自动从集合掉出
  5. 把"加入/移除"事件写到 PG `audit_log`，便于追溯

下游 `WhitelistNode` / `BlacklistNode` 已改为同时查
静态配置 + Redis 集合，所以集合更新立即对运行中的 Pipeline 生效。
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from shared.config import get_settings
from shared.observability import get_logger

logger = get_logger(__name__)

POLL_INTERVAL_SEC = 300       # 5 分钟
LOOKBACK_DAYS = 30
FP_PROMOTE_THRESHOLD = 5      # ≥ 5 FP 且 0 TP → whitelist:auto
TP_PROMOTE_THRESHOLD = 3      # ≥ 3 TP 且 0 FP → blacklist:auto

# Per-family 阈值推荐器
FP_RATE_THRESHOLD = 0.20             # FP 率 > 20% 触发推荐
MIN_SAMPLES_PER_FAMILY = 20          # 需要 ≥ 20 个样本（统计有意义）
RECOMMENDATION_COOLDOWN_DAYS = 7     # 同一 family 7 天内只推一次（防刷屏）

WL_KEY = "whitelist:auto"
BL_KEY = "blacklist:auto"


async def _aggregate_once(pg_pool: Any, redis_client: Any) -> dict:
    """单次聚合 + 原子替换；返回本次 diff 的统计。"""
    rows = await pg_pool.fetch(
        f"""
        SELECT domain,
               SUM(CASE WHEN true_label = 'benign' THEN 1 ELSE 0 END) AS fp_count,
               SUM(CASE WHEN true_label = 'dga'    THEN 1 ELSE 0 END) AS tp_count
        FROM feedback
        WHERE created_at > NOW() - INTERVAL '{LOOKBACK_DAYS} days'
          AND domain IS NOT NULL
        GROUP BY domain
        """
    )

    new_wl: list[str] = []
    new_bl: list[str] = []
    for row in rows:
        domain = row["domain"]
        fp = int(row["fp_count"] or 0)
        tp = int(row["tp_count"] or 0)
        if fp >= FP_PROMOTE_THRESHOLD and tp == 0:
            new_wl.append(domain)
        elif tp >= TP_PROMOTE_THRESHOLD and fp == 0:
            new_bl.append(domain)

    new_wl_set = set(new_wl)
    new_bl_set = set(new_bl)

    old_wl = set(await redis_client.smembers(WL_KEY))
    old_bl = set(await redis_client.smembers(BL_KEY))

    added_wl = new_wl_set - old_wl
    removed_wl = old_wl - new_wl_set
    added_bl = new_bl_set - old_bl
    removed_bl = old_bl - new_bl_set

    # 原子替换：删除旧集合 + 写入新集合（单 pipeline 保证读 SISMEMBER 不会读到中间态）
    pipe = redis_client.pipeline()
    pipe.delete(WL_KEY, BL_KEY)
    if new_wl:
        pipe.sadd(WL_KEY, *new_wl)
    if new_bl:
        pipe.sadd(BL_KEY, *new_bl)
    await pipe.execute()

    # 审计日志：只记 diff（避免每 5 分钟刷屏）
    audit_rows = []
    for d in added_wl:
        audit_rows.append((
            "feedback-aggregator", "auto_whitelist_promote", d,
            json.dumps({
                "reason": f"≥{FP_PROMOTE_THRESHOLD} FP & 0 TP in {LOOKBACK_DAYS}d",
            }),
        ))
    for d in removed_wl:
        audit_rows.append((
            "feedback-aggregator", "auto_whitelist_demote", d,
            json.dumps({"reason": "signal aged out of window"}),
        ))
    for d in added_bl:
        audit_rows.append((
            "feedback-aggregator", "auto_blacklist_promote", d,
            json.dumps({
                "reason": f"≥{TP_PROMOTE_THRESHOLD} TP & 0 FP in {LOOKBACK_DAYS}d",
            }),
        ))
    for d in removed_bl:
        audit_rows.append((
            "feedback-aggregator", "auto_blacklist_demote", d,
            json.dumps({"reason": "signal aged out of window"}),
        ))

    if audit_rows:
        await pg_pool.executemany(
            "INSERT INTO audit_log (user_id, action, resource, detail) VALUES ($1, $2, $3, $4::jsonb)",
            audit_rows,
        )

    return {
        "wl_total": len(new_wl_set),
        "bl_total": len(new_bl_set),
        "wl_added": len(added_wl),
        "wl_removed": len(removed_wl),
        "bl_added": len(added_bl),
        "bl_removed": len(removed_bl),
    }


async def _analyze_family_thresholds(pg_pool: Any) -> list[dict]:
    """Per-family FP-rate analysis.

    对每个 family 计算最近 30 天的 FP 率；超过 ``FP_RATE_THRESHOLD`` 且样本量 ≥
    ``MIN_SAMPLES_PER_FAMILY`` 的，写一条 ``threshold_recommendation`` 到
    ``pipeline_operations``（status=pending）。**不自动应用** —— 阈值改动
    需人审批，避免自动闭环把合法流量错误打成误报。

    去重：同一 family 在 ``RECOMMENDATION_COOLDOWN_DAYS`` 天内只推一次。
    """
    rows = await pg_pool.fetch(
        f"""
        SELECT family,
               COUNT(*)::int                                            AS n,
               SUM(CASE WHEN true_label='benign' THEN 1 ELSE 0 END)::int AS fp_count,
               SUM(CASE WHEN true_label='dga'    THEN 1 ELSE 0 END)::int AS tp_count
        FROM feedback
        WHERE created_at > NOW() - INTERVAL '{LOOKBACK_DAYS} days'
          AND family IS NOT NULL
          AND family <> ''
        GROUP BY family
        HAVING COUNT(*) >= {MIN_SAMPLES_PER_FAMILY}
        """
    )

    issued: list[dict] = []
    for row in rows:
        family = row["family"]
        n = int(row["n"])
        fp = int(row["fp_count"])
        tp = int(row["tp_count"])
        fp_rate = (fp / n) if n else 0.0

        if fp_rate <= FP_RATE_THRESHOLD:
            continue

        # 7 天 cooldown：避免同一 family 每 5 分钟一条 pending
        existing = await pg_pool.fetchval(
            f"""
            SELECT id FROM pipeline_operations
            WHERE operation = 'threshold_recommendation'
              AND status = 'pending'
              AND detail->>'family' = $1
              AND created_at > NOW() - INTERVAL '{RECOMMENDATION_COOLDOWN_DAYS} days'
            LIMIT 1
            """,
            family,
        )
        if existing:
            continue

        await pg_pool.execute(
            """
            INSERT INTO pipeline_operations (pipeline_id, operation, operator, status, detail)
            VALUES ($1, $2, $3, $4, $5::jsonb)
            """,
            "default",
            "threshold_recommendation",
            "feedback-aggregator",
            "pending",
            json.dumps({
                "family": family,
                "fp_rate": round(fp_rate, 3),
                "n_samples": n,
                "fp_count": fp,
                "tp_count": tp,
                "lookback_days": LOOKBACK_DAYS,
                "fp_rate_threshold": FP_RATE_THRESHOLD,
                "suggested_action": (
                    "raise per-family detection threshold by 0.05-0.10, "
                    "or extend whitelist:static for known-benign domains in this family"
                ),
                "reason": (
                    f"FP rate {fp_rate:.1%} > {FP_RATE_THRESHOLD:.0%} "
                    f"over {LOOKBACK_DAYS}d (FP={fp} / total={n})"
                ),
            }),
        )
        issued.append({"family": family, "fp_rate": fp_rate, "n": n, "fp": fp})

    return issued


async def start_feedback_aggregator() -> None:
    """长生命周期 task：周期性聚合 feedback，更新 Redis 自动名单。

    PG 不可用时整体跳过；Redis 不可用时整体跳过。两者任一恢复后
    下一轮 pass 会自动接上。
    """
    settings = get_settings()
    pg_pool = None
    redis_client = None

    # 启动重试：PG/Redis 容器健康延迟
    for attempt in range(20):
        try:
            import asyncpg
            import redis.asyncio as aioredis
            pg_pool = await asyncpg.create_pool(
                settings.pg_dsn, min_size=1, max_size=2,
            )
            redis_client = aioredis.from_url(
                settings.redis_url, decode_responses=True,
            )
            await redis_client.ping()
            break
        except Exception as e:
            logger.warning(
                "feedback_loop_init_retry", attempt=attempt, error=str(e),
            )
            if pg_pool:
                await pg_pool.close()
                pg_pool = None
            if redis_client:
                await redis_client.aclose()
                redis_client = None
            await asyncio.sleep(3)
    else:
        logger.error("feedback_loop_init_failed_giving_up")
        return

    logger.info(
        "feedback_aggregator_started",
        interval_sec=POLL_INTERVAL_SEC,
        lookback_days=LOOKBACK_DAYS,
        fp_threshold=FP_PROMOTE_THRESHOLD,
        tp_threshold=TP_PROMOTE_THRESHOLD,
    )

    try:
        while True:
            try:
                stats = await _aggregate_once(pg_pool, redis_client)
                if any(stats[k] for k in ("wl_added", "wl_removed", "bl_added", "bl_removed")):
                    logger.info("feedback_aggregation_diff", **stats)
                else:
                    logger.debug("feedback_aggregation_noop", **stats)

                # Per-family 阈值推荐器（每轮跑，结果落 pipeline_operations.pending）
                fam_recs = await _analyze_family_thresholds(pg_pool)
                if fam_recs:
                    logger.info(
                        "family_threshold_recommendations_issued",
                        count=len(fam_recs),
                        families=[r["family"] for r in fam_recs],
                    )
            except Exception as e:
                logger.error("feedback_aggregation_error", error=str(e))
            await asyncio.sleep(POLL_INTERVAL_SEC)
    except asyncio.CancelledError:
        logger.info("feedback_aggregator_stopping")
    finally:
        if pg_pool:
            await pg_pool.close()
        if redis_client:
            await redis_client.aclose()
