#!/usr/bin/env python3
"""
e2e 烟雾测试 — 反馈闭环 (Phase 1 + Phase 2)

包含 3 个子测试：
  1. test_whitelist_promotion     —— 6×FP 反馈 → whitelist:auto
  2. test_family_recommender      —— 25×FP 单一 family → pipeline_operations.threshold_recommendation
  3. test_drift_alert             —— 注入基线 + 漂移样本 → pipeline_operations.drift_alert

每个测试独立连接、独立清理、独立 pass/fail。最终汇总返回。

运行方式：
  方式 A · 本机 uv 环境（Linux / Apple Silicon Mac）：
      uv run python scripts/test_feedback_loop.py
  方式 B · Intel Mac 或本机依赖不全（推荐，永远可用）：
      docker exec dga-sentinel-agent mkdir -p /app/scripts
      docker cp scripts/test_feedback_loop.py dga-sentinel-agent:/app/scripts/
      docker exec dga-sentinel-agent python /app/scripts/test_feedback_loop.py

退出码：0 = 全部 PASS，1 = 任一 FAIL
"""

from __future__ import annotations

import asyncio
import os
import random
import sys
import traceback
from pathlib import Path
from uuid import uuid4

# 让脚本能从项目根目录加载 ai.agents 包
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import asyncpg
import httpx
import redis.asyncio as aioredis

# 优先级：PG_DSN_HOST > PG_DSN（容器内）> 默认本机端口
PG_DSN = (
    os.environ.get("PG_DSN_HOST")
    or os.environ.get("PG_DSN")
    or "postgresql://dga:dga_password@localhost:15432/dga_platform"
)
REDIS_URL = (
    os.environ.get("REDIS_URL_HOST")
    or os.environ.get("REDIS_URL")
    or "redis://localhost:16379/0"
)
SCORING_URL = (
    os.environ.get("SCORING_URL_HOST")
    or os.environ.get("SCORING_URL")
    or "http://scoring-service:8001"
    if os.environ.get("PG_DSN", "").startswith("postgresql://dga:dga_password@postgres")
    else "http://localhost:8001"
)


# ──────────────────────────────────────────────────────
# Test 1 — Whitelist promotion via FP feedbacks
# ──────────────────────────────────────────────────────


async def test_whitelist_promotion(pg_pool, redis_client) -> bool:
    print("\n┌─ Test 1: WHITELIST PROMOTION (6×FP → whitelist:auto) " + "─" * 8)
    domain = f"fbtest-{uuid4().hex[:8]}.example"
    try:
        await _cleanup_domain(pg_pool, redis_client, domain, fb_annotator="e2e-test")

        async with pg_pool.acquire() as c:
            for i in range(6):
                await c.execute(
                    "INSERT INTO feedback (event_id, domain, true_label, predicted_label, score, annotator) "
                    "VALUES ($1, $2, 'benign', 'dga', 0.95, 'e2e-test')",
                    f"e2e-{domain}-{i}", domain,
                )
        pre = await redis_client.sismember("whitelist:auto", domain)
        assert not pre, "domain unexpectedly already in whitelist:auto"

        from ai.agents.feedback_loop import _aggregate_once
        stats = await _aggregate_once(pg_pool, redis_client)

        post = await redis_client.sismember("whitelist:auto", domain)
        async with pg_pool.acquire() as c:
            audit = await c.fetchrow(
                "SELECT action FROM audit_log WHERE resource = $1 ORDER BY id DESC LIMIT 1",
                domain,
            )

        passed = bool(post) and audit and audit["action"] == "auto_whitelist_promote"
        print(f"│ stats: {stats}")
        print(f"│ SISMEMBER whitelist:auto = {post}")
        print(f"│ audit_log.action = {audit['action'] if audit else None}")
        print(f"└─ {'✅ PASS' if passed else '❌ FAIL'}")
        return bool(passed)
    finally:
        await _cleanup_domain(pg_pool, redis_client, domain, fb_annotator="e2e-test")


# ──────────────────────────────────────────────────────
# Test 2 — Per-family threshold recommendation
# ──────────────────────────────────────────────────────


async def test_family_recommender(pg_pool) -> bool:
    print("\n┌─ Test 2: FAMILY THRESHOLD RECOMMENDER (25×FP → pipeline_operations) " + "─")
    family = f"fam-{uuid4().hex[:6]}"
    annotator = f"e2e-fam-{uuid4().hex[:4]}"
    try:
        async with pg_pool.acquire() as c:
            for i in range(25):
                await c.execute(
                    "INSERT INTO feedback (event_id, domain, true_label, predicted_label, score, family, annotator) "
                    "VALUES ($1, $2, 'benign', 'dga', 0.93, $3, $4)",
                    f"fam-test-{i}", f"fam-test-{i}.example", family, annotator,
                )

        from ai.agents.feedback_loop import _analyze_family_thresholds
        issued = await _analyze_family_thresholds(pg_pool)

        async with pg_pool.acquire() as c:
            row = await c.fetchrow(
                """
                SELECT operation, status, detail::text AS detail
                FROM pipeline_operations
                WHERE operation = 'threshold_recommendation'
                  AND detail->>'family' = $1
                ORDER BY id DESC LIMIT 1
                """,
                family,
            )

        passed = (
            any(r["family"] == family for r in issued)
            and row is not None
            and row["status"] == "pending"
        )
        print(f"│ issued: {issued}")
        print(f"│ pipeline_operations: {row['detail'][:140] if row else None}")
        print(f"└─ {'✅ PASS' if passed else '❌ FAIL'}")
        return bool(passed)
    finally:
        async with pg_pool.acquire() as c:
            await c.execute("DELETE FROM feedback WHERE annotator = $1", annotator)
            await c.execute(
                "DELETE FROM pipeline_operations "
                "WHERE operation = 'threshold_recommendation' AND detail->>'family' = $1",
                family,
            )


# ──────────────────────────────────────────────────────
# Test 3 — Drift alert via /drift HTTP API
# ──────────────────────────────────────────────────────


async def test_drift_alert(pg_pool) -> bool:
    print(f"\n┌─ Test 3: DRIFT ALERT  (synthetic baseline → drift → persist) ────")
    print(f"│ scoring URL = {SCORING_URL}")

    # 注：drift_alert 持久化不带 family 标签，所以清理用全局清理
    feature_marker = "score"  # baseline + drifted 都用 score 这个 feature
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            # 0) 重置：清掉之前的 drift_alert（避免 cooldown 影响）
            async with pg_pool.acquire() as c:
                await c.execute(
                    "DELETE FROM pipeline_operations WHERE operation = 'drift_alert' AND created_at > NOW() - INTERVAL '6 hours'"
                )

            # 1) 设置基线分布：score 在 [0.0, 0.3] 之间
            random.seed(42)
            baseline = [
                {"score": random.uniform(0.0, 0.3), "domain_len": random.uniform(8.0, 20.0)}
                for _ in range(200)
            ]
            r1 = await client.post(f"{SCORING_URL}/drift/baseline", json={"samples": baseline})
            r1.raise_for_status()

            # 2) 注入显著漂移样本：score 在 [0.7, 1.0]
            drifted = [
                {"score": random.uniform(0.7, 1.0), "domain_len": random.uniform(40.0, 80.0)}
                for _ in range(200)
            ]
            r2 = await client.post(f"{SCORING_URL}/drift/record", json={"samples": drifted})
            r2.raise_for_status()
            print(f"│ baseline n=200, drifted n=200, window={r2.json()['window_size']}")

            # 3) 触发 check + persist
            r3 = await client.post(f"{SCORING_URL}/drift/persist")
            r3.raise_for_status()
            payload = r3.json()
            print(f"│ scores: {payload['scores']}")
            print(f"│ alerts_written: {payload['alerts_written']}")

        # 4) 验证 PG 写入
        async with pg_pool.acquire() as c:
            row = await c.fetchrow(
                """
                SELECT operation, status, detail::text AS detail
                FROM pipeline_operations
                WHERE operation = 'drift_alert'
                  AND detail->>'feature' = $1
                ORDER BY id DESC LIMIT 1
                """,
                feature_marker,
            )

        any_score_above = any(
            v >= 0.25 for v in payload["scores"].values()
        )
        passed = (
            payload["alerts_written"] >= 1
            and any_score_above
            and row is not None
        )
        print(f"│ pipeline_operations: {row['detail'][:140] if row else None}")
        print(f"└─ {'✅ PASS' if passed else '❌ FAIL'}")
        return bool(passed)
    finally:
        async with pg_pool.acquire() as c:
            await c.execute(
                "DELETE FROM pipeline_operations WHERE operation = 'drift_alert' AND created_at > NOW() - INTERVAL '6 hours'"
            )


# ──────────────────────────────────────────────────────
# Helpers + main
# ──────────────────────────────────────────────────────


async def _cleanup_domain(pg_pool, redis_client, domain: str, fb_annotator: str) -> None:
    try:
        async with pg_pool.acquire() as c:
            await c.execute(
                "DELETE FROM feedback WHERE domain = $1 AND annotator = $2",
                domain, fb_annotator,
            )
            await c.execute("DELETE FROM audit_log WHERE resource = $1", domain)
        await redis_client.srem("whitelist:auto", domain)
        await redis_client.srem("blacklist:auto", domain)
    except Exception as e:  # noqa: BLE001
        print(f"   cleanup warning: {e}")


async def main() -> int:
    print(f"[setup] PG       = {PG_DSN}")
    print(f"[setup] redis    = {REDIS_URL}")
    print(f"[setup] scoring  = {SCORING_URL}")

    try:
        pg_pool = await asyncpg.create_pool(PG_DSN, min_size=1, max_size=3)
        r = aioredis.from_url(REDIS_URL, decode_responses=True)
        await r.ping()
    except Exception as e:  # noqa: BLE001
        print(f"\n❌ FAIL [connect]: {e}")
        return 1

    results: dict[str, bool] = {}
    try:
        try:
            results["whitelist"] = await test_whitelist_promotion(pg_pool, r)
        except Exception:
            traceback.print_exc()
            results["whitelist"] = False

        try:
            results["family"] = await test_family_recommender(pg_pool)
        except Exception:
            traceback.print_exc()
            results["family"] = False

        try:
            results["drift"] = await test_drift_alert(pg_pool)
        except Exception:
            traceback.print_exc()
            results["drift"] = False
    finally:
        await pg_pool.close()
        await r.aclose()

    print("\n" + "═" * 62)
    print(" Summary")
    print("═" * 62)
    for name, ok in results.items():
        print(f"   {name:<12} {'✅ PASS' if ok else '❌ FAIL'}")
    print("═" * 62)

    if all(results.values()):
        print("\n✅ ALL TESTS PASSED")
        return 0
    failed = [k for k, v in results.items() if not v]
    print(f"\n❌ FAILED: {failed}")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
