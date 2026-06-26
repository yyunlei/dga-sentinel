#!/usr/bin/env python3
"""
DGA 全链路 Pipeline 真实测试
验证: Gateway评分 → ES写入 → StarRocks写入 → Redis缓存 → Kafka流式 → 告警API
直接对运行中的 Docker 服务发起真实请求，不使用 mock。
"""
from __future__ import annotations

import asyncio
import json
import hashlib
import random
import string
import sys
import time
from datetime import datetime, timezone
from typing import Any, Callable

import requests

# ── 配置 ──────────────────────────────────────────────────────────────
GATEWAY = "http://localhost:8000"
ES_URL = "http://localhost:9200"
REDIS_HOST, REDIS_PORT = "localhost", 6379
STARROCKS_FE, STARROCKS_PORT = "localhost", 9030
KAFKA_BOOTSTRAP = "localhost:9094"

TODAY = datetime.now(timezone.utc).strftime("%Y.%m.%d")
ES_INDEX = f"dga-events-{TODAY}"

# 测试域名
DGA_DOMAINS = [
    "qjkxnvtpmrwzs.com",
    "xkcd8f3m2nq9p.net",
    "a1b2c3d4e5f6g7.org",
    "zyxwvutsrqponm.info",
    "hjkl9876asdf12.xyz",
]
LEGIT_DOMAINS = ["google.com", "github.com", "stackoverflow.com"]
ALL_DOMAINS = DGA_DOMAINS + LEGIT_DOMAINS

# Kafka DNS 日志
KAFKA_TEST_DOMAINS = [
    {"query_name": "qjkxnvtpmrwzs.com", "src_ip": "10.0.0.50", "query_type": "A"},
    {"query_name": "xkcd8f3m2nq9p.net", "src_ip": "10.0.0.51", "query_type": "A"},
]

# ── 工具函数 ───────────────────────────────────────────────────────────
PASS = "\033[92m✓ PASS\033[0m"
FAIL = "\033[91m✗ FAIL\033[0m"
WARN = "\033[93m⚠ WARN\033[0m"
results: list[tuple[str, bool, str]] = []


def report(step: str, ok: bool, detail: str = "") -> None:
    tag = PASS if ok else FAIL
    results.append((step, ok, detail))
    print(f"  {tag}  {step}" + (f"  ({detail})" if detail else ""))


def section(title: str) -> None:
    print(f"\n{'='*60}\n  {title}\n{'='*60}")


def run_async(coro: Any) -> Any:
    """在同步上下文中运行 async 协程"""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def retry(fn: Callable[[], Any], max_attempts: int = 3, delay: float = 2.0, desc: str = "") -> Any:
    """带指数退避的重试"""
    last_err: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except Exception as e:
            last_err = e
            if attempt < max_attempts:
                wait = delay * attempt
                print(f"    Retry {attempt}/{max_attempts} {desc}, {wait:.1f}s...")
                time.sleep(wait)
    raise last_err  # type: ignore[misc]


def generate_random_dga_domain() -> str:
    """生成随机 DGA 域名用于 burst 测试"""
    length = random.randint(10, 20)
    name = "".join(random.choices(string.ascii_lowercase + string.digits, k=length))
    tld = random.choice([".com", ".net", ".org", ".xyz"])
    return name + tld


# ── Step 1: 环境健康检查 ──────────────────────────────────────────────

def check_services() -> bool:
    section("Step 1: 服务健康检查")
    all_ok = True

    # Gateway
    try:
        r = requests.get(f"{GATEWAY}/health", timeout=5)
        ok = r.status_code == 200
        report("Gateway", ok, f"status={r.status_code}")
    except Exception as e:
        report("Gateway", False, str(e)); all_ok = False

    # Scoring Service
    try:
        r = requests.post(f"{GATEWAY}/api/score", json={"domains": ["healthcheck.com"]}, timeout=10)
        ok = r.status_code == 200
        report("Scoring Service", ok, f"status={r.status_code}")
    except Exception as e:
        report("Scoring Service", False, str(e)); all_ok = False

    # Elasticsearch
    try:
        r = requests.get(f"{ES_URL}/_cluster/health", timeout=5)
        ok = r.status_code == 200
        report("Elasticsearch", ok, f"cluster={r.json().get('status','?')}")
    except Exception as e:
        report("Elasticsearch", False, str(e)); all_ok = False

    # Redis
    try:
        import redis as _redis
        rc = _redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
        pong = rc.ping()
        report("Redis", pong, "PONG" if pong else "no response")
        rc.close()
    except Exception as e:
        report("Redis", False, str(e)); all_ok = False

    # Kafka — 直连 aiokafka 检查 topic
    try:
        async def _check_kafka() -> tuple[bool, str]:
            from aiokafka import AIOKafkaConsumer
            consumer = AIOKafkaConsumer(
                "dns-query-logs",
                bootstrap_servers=KAFKA_BOOTSTRAP,
                group_id=f"healthcheck-{int(time.time())}",
                request_timeout_ms=5000,
            )
            await consumer.start()
            try:
                partitions = consumer.partitions_for_topic("dns-query-logs")
                ok = partitions is not None and len(partitions) > 0
                return ok, f"dns-query-logs={'found, partitions=' + str(len(partitions)) if ok else 'MISSING'}"
            finally:
                await consumer.stop()

        ok, detail = run_async(_check_kafka())
        report("Kafka", ok, detail)
    except Exception as e:
        report("Kafka", False, str(e)); all_ok = False

    # StarRocks
    try:
        import pymysql
        conn = pymysql.connect(host=STARROCKS_FE, port=STARROCKS_PORT, user="root", password="", database="dga_analytics")
        cur = conn.cursor()
        cur.execute("SELECT 1")
        report("StarRocks", True, "connected")
        cur.close(); conn.close()
    except Exception as e:
        report("StarRocks", False, str(e))

    return all_ok


# ── Step 2: 清理旧测试数据 ────────────────────────────────────────────

def cleanup_old_data() -> None:
    section("Step 2: 清理旧测试数据")
    all_test_domains = DGA_DOMAINS + LEGIT_DOMAINS + [d["query_name"] for d in KAFKA_TEST_DOMAINS]

    # 清理 ES
    try:
        body = {"query": {"terms": {"domain": all_test_domains}}}
        r = requests.post(f"{ES_URL}/dga-events-*/_delete_by_query", json=body, timeout=10)
        deleted = r.json().get("deleted", 0)
        report("ES 清理", True, f"deleted={deleted}")
    except Exception as e:
        report("ES 清理", False, str(e))

    # 清理 Redis 缓存
    try:
        import redis as _redis
        rc = _redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
        count = 0
        for domain in all_test_domains:
            h = hashlib.sha256(domain.encode()).hexdigest()[:16]
            count += rc.delete(f"score:{h}")
        report("Redis 缓存清理", True, f"deleted={count}")
        rc.close()
    except Exception as e:
        report("Redis 缓存清理", False, str(e))

    time.sleep(1)  # 等待 ES 刷新


# ── Step 3: Gateway 评分链路 ──────────────────────────────────────────

def test_gateway_scoring() -> dict[str, Any]:
    section("Step 3: Gateway 评分链路")
    score_results: dict[str, Any] = {}

    # 3a: DGA 域名评分
    try:
        r = requests.post(f"{GATEWAY}/api/score", json={"domains": DGA_DOMAINS}, timeout=30)
        assert r.status_code == 200, f"status={r.status_code}"
        data = r.json()
        dga_results = data.get("results", [])
        report("DGA 域名评分请求", True, f"trace_id={data.get('trace_id','?')[:12]}, count={len(dga_results)}")

        high_score_count = 0
        for res in dga_results:
            is_high = res["score"] >= 0.7
            if is_high:
                high_score_count += 1
            score_results[res["domain"]] = res
            print(f"    {res['domain']:30s}  score={res['score']:.4f}  is_dga={res['is_dga']}  family={res.get('family','?')}")

        report("DGA 域名高分命中", high_score_count >= 3, f"{high_score_count}/{len(DGA_DOMAINS)} 域名 score>=0.7")
    except Exception as e:
        report("DGA 域名评分", False, str(e))

    # 3b: 正常域名评分
    try:
        r = requests.post(f"{GATEWAY}/api/score", json={"domains": LEGIT_DOMAINS}, timeout=30)
        assert r.status_code == 200
        data = r.json()
        legit_results = data.get("results", [])
        low_count = sum(1 for res in legit_results if res["score"] < 0.5)
        for res in legit_results:
            score_results[res["domain"]] = res
            print(f"    {res['domain']:30s}  score={res['score']:.4f}  is_dga={res['is_dga']}")
        report("正常域名低分", low_count == len(LEGIT_DOMAINS), f"{low_count}/{len(LEGIT_DOMAINS)} 域名 score<0.5")
    except Exception as e:
        report("正常域名评分", False, str(e))

    return score_results


# ── Step 4: 验证 ES 写入 ─────────────────────────────────────────────

def verify_es_write(score_results: dict[str, Any]) -> list[str]:
    section("Step 4: 验证 Elasticsearch 写入")
    time.sleep(2)  # 等待 ES 索引刷新

    # 强制刷新索引
    try:
        requests.post(f"{ES_URL}/dga-events-*/_refresh", timeout=5)
    except Exception:
        pass

    event_ids: list[str] = []
    hit_domains = score_results.keys()
    # 只有 is_dga=True 或 score>=0.7 的才会写入 ES
    expected = [d for d, r in score_results.items() if r.get("is_dga") or r.get("score", 0) >= 0.7]

    try:
        body = {
            "query": {"terms": {"domain": list(hit_domains)}},
            "size": 50,
            "sort": [{"timestamp": "desc"}],
        }
        r = requests.post(f"{ES_URL}/dga-events-*/_search", json=body, timeout=10)
        assert r.status_code == 200, f"ES search status={r.status_code}"
        hits = r.json().get("hits", {}).get("hits", [])
        found_domains = set()
        for hit in hits:
            src = hit["_source"]
            found_domains.add(src["domain"])
            event_ids.append(src["event_id"])
            print(f"    ES doc: {src['domain']:30s}  score={src.get('score',0):.4f}  severity={src.get('severity','?')}  event_id={src['event_id'][:12]}")

        matched = len(set(expected) & found_domains)
        report("ES 文档写入", matched >= len(expected) * 0.6, f"期望={len(expected)}, 找到={matched}")
    except Exception as e:
        report("ES 文档写入", False, str(e))

    return event_ids


# ── Step 5: 验证 Redis 缓存 ──────────────────────────────────────────

def verify_redis_cache() -> None:
    section("Step 5: 验证 Redis 缓存命中")
    try:
        # 再次评分相同域名，应该命中缓存
        r = requests.post(f"{GATEWAY}/api/score", json={"domains": DGA_DOMAINS[:2]}, timeout=15)
        assert r.status_code == 200
        data = r.json()
        cached_count = sum(1 for res in data.get("results", []) if res.get("cached"))
        report("Redis 缓存命中", cached_count >= 1, f"{cached_count}/{len(DGA_DOMAINS[:2])} cached=true")
        for res in data.get("results", []):
            print(f"    {res['domain']:30s}  cached={res.get('cached', False)}")
    except Exception as e:
        report("Redis 缓存命中", False, str(e))

    # 直接检查 Redis key
    try:
        import redis as _redis
        rc = _redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
        found = 0
        for domain in DGA_DOMAINS:
            h = hashlib.sha256(domain.encode()).hexdigest()[:16]
            val = rc.get(f"score:{h}")
            if val:
                found += 1
        report("Redis key 存在", found >= 3, f"{found}/{len(DGA_DOMAINS)} keys found")
        rc.close()
    except Exception as e:
        report("Redis key 检查", False, str(e))


# ── Step 6: 验证 StarRocks 写入 ──────────────────────────────────────

def verify_starrocks() -> None:
    section("Step 6: 验证 StarRocks 写入")
    try:
        import pymysql
        conn = pymysql.connect(host=STARROCKS_FE, port=STARROCKS_PORT, user="root", password="", database="dga_analytics")
        cur = conn.cursor()

        # 查询测试域名
        placeholders = ",".join(["%s"] * len(DGA_DOMAINS))
        sql = f"SELECT domain, score, is_dga, family, severity FROM dga_events WHERE domain IN ({placeholders}) ORDER BY event_time DESC LIMIT 20"
        cur.execute(sql, DGA_DOMAINS)
        rows = cur.fetchall()

        if rows:
            for row in rows:
                print(f"    SR row: domain={row[0]:30s}  score={row[1]:.4f}  is_dga={row[2]}  family={row[3]}  severity={row[4]}")
            report("StarRocks 数据写入", True, f"rows={len(rows)}")
        else:
            report("StarRocks 数据写入", False, "0 rows found")

        # 统计总行数
        cur.execute("SELECT COUNT(*) FROM dga_events")
        total = cur.fetchone()[0]
        print(f"    StarRocks dga_events 总行数: {total}")

        cur.close()
        conn.close()
    except ImportError:
        report("StarRocks 数据写入", False, "pymysql not installed, pip install pymysql")
    except Exception as e:
        report("StarRocks 数据写入", False, str(e))


# ── Step 7: Kafka 全链路 ─────────────────────────────────────────────

async def _produce_kafka_messages(messages: list[dict[str, str]]) -> int:
    """通过 aiokafka 直接生产消息到 dns-query-logs"""
    from aiokafka import AIOKafkaProducer
    producer = AIOKafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
    )
    await producer.start()
    sent = 0
    try:
        for msg in messages:
            await producer.send_and_wait("dns-query-logs", msg)
            sent += 1
    finally:
        await producer.stop()
    return sent


async def _consume_kafka_alerts(timeout_s: float = 15.0) -> list[dict[str, Any]]:
    """从 dga-alerts 消费最近的告警消息"""
    from aiokafka import AIOKafkaConsumer
    consumer = AIOKafkaConsumer(
        "dga-alerts",
        bootstrap_servers=KAFKA_BOOTSTRAP,
        auto_offset_reset="earliest",
        group_id=f"e2e-test-{int(time.time())}",
        value_deserializer=lambda m: json.loads(m.decode()),
    )
    await consumer.start()
    alerts: list[dict[str, Any]] = []
    try:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            batch = await consumer.getmany(timeout_ms=2000)
            for tp, msgs in batch.items():
                for msg in msgs:
                    alerts.append(msg.value)
            if not batch:
                await asyncio.sleep(0.5)
    finally:
        await consumer.stop()
    return alerts


def test_kafka_pipeline() -> None:
    section("Step 7: Kafka 全链路 (dns-query-logs → DAG Engine → dga-alerts)")

    # 7a: 通过 aiokafka 向 dns-query-logs 生产消息
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    messages = [{**d, "timestamp": ts} for d in KAFKA_TEST_DOMAINS]

    try:
        sent = run_async(_produce_kafka_messages(messages))
        for d in KAFKA_TEST_DOMAINS:
            print(f"    Produced: {d['query_name']}  src_ip={d['src_ip']}")
        report("Kafka 生产消息", sent == len(KAFKA_TEST_DOMAINS), f"sent={sent}")
    except Exception as e:
        report("Kafka 生产消息", False, str(e))

    # 7b: 等待 DAG Engine 处理
    print("    等待 DAG Engine 处理 (15s)...")
    time.sleep(15)

    # 7c: 从 dga-alerts 消费
    try:
        alerts = run_async(_consume_kafka_alerts(timeout_s=12.0))
        for a in alerts[-10:]:
            print(f"    Alert: domain={a.get('domain','?')}  score={a.get('score','?')}  severity={a.get('severity','?')}")
        report("Kafka dga-alerts 消费", len(alerts) > 0, f"messages={len(alerts)}")
    except Exception as e:
        report("Kafka dga-alerts 消费", False, str(e))


# ── Step 7b: Burst 流量模拟 ──────────────────────────────────────────

def test_burst_traffic() -> list[str]:
    section("Step 7b: Burst 流量模拟 (随机 DGA → DAG Engine → ES)")

    burst_domains = [generate_random_dga_domain() for _ in range(10)]
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    messages = [
        {
            "query_name": d,
            "src_ip": f"10.99.0.{random.randint(1, 254)}",
            "query_type": random.choice(["A", "AAAA"]),
            "timestamp": ts,
        }
        for d in burst_domains
    ]

    # 注入
    try:
        sent = run_async(_produce_kafka_messages(messages))
        report("Burst 流量注入", sent == len(messages), f"sent={sent}/{len(messages)}")
    except Exception as e:
        report("Burst 流量注入", False, str(e))
        return burst_domains

    # 等待 DAG Engine 处理
    print("    等待 DAG Engine 处理 burst (20s)...")
    time.sleep(20)

    # 验证 ES 写入（带重试）
    def _check_es_burst() -> None:
        requests.post(f"{ES_URL}/dga-events-*/_refresh", timeout=5)
        body = {"query": {"terms": {"domain": burst_domains}}, "size": 50}
        r = requests.post(f"{ES_URL}/dga-events-*/_search", json=body, timeout=10)
        assert r.status_code == 200, f"ES status={r.status_code}"
        hits = r.json().get("hits", {}).get("hits", [])
        found = len(hits)
        for h in hits[:5]:
            src = h["_source"]
            print(f"    Burst ES: {src['domain']:30s}  score={src.get('score',0):.4f}  pipeline={src.get('pipeline_id','?')}")
        assert found > 0, f"0 burst domains found in ES"
        report("Burst 域名 ES 写入", True, f"found={found}/{len(burst_domains)}")

    try:
        retry(_check_es_burst, max_attempts=3, delay=3.0, desc="burst ES 验证")
    except Exception as e:
        report("Burst 域名 ES 写入", False, str(e))

    return burst_domains


# ── Step 8: 验证告警 API ─────────────────────────────────────────────

def verify_alerts_api(event_ids: list[str]) -> None:
    section("Step 8: 验证告警 API")

    # 8a: 列表查询
    try:
        r = requests.get(f"{GATEWAY}/api/alerts", timeout=10)
        assert r.status_code == 200, f"status={r.status_code}"
        data = r.json()
        alerts = data.get("alerts", [])
        report("GET /api/alerts", True, f"total={len(alerts)}")

        # 检查测试域名是否在告警列表中
        alert_domains = {a.get("domain") for a in alerts}
        matched = set(DGA_DOMAINS) & alert_domains
        report("告警包含测试 DGA 域名", len(matched) >= 1, f"matched={list(matched)[:3]}")

        for a in alerts[:5]:
            print(f"    Alert: {a.get('domain','?'):30s}  score={a.get('score',0):.4f}  severity={a.get('severity','?')}  ack={a.get('acknowledged',False)}")
    except Exception as e:
        report("GET /api/alerts", False, str(e))

    # 8b: 单条详情
    if event_ids:
        eid = event_ids[0]
        try:
            r = requests.get(f"{GATEWAY}/api/alerts/{eid}", timeout=10)
            ok = r.status_code == 200
            if ok:
                detail = r.json()
                report("GET /api/alerts/{id}", True, f"domain={detail.get('domain','?')}")
            else:
                report("GET /api/alerts/{id}", False, f"status={r.status_code}")
        except Exception as e:
            report("GET /api/alerts/{id}", False, str(e))
    else:
        report("GET /api/alerts/{id}", False, "no event_ids from ES")

    # 8c: 按严重度过滤
    for sev in ["CRITICAL", "HIGH"]:
        try:
            r = requests.get(f"{GATEWAY}/api/alerts", params={"severity": sev}, timeout=10)
            if r.status_code == 200:
                cnt = len(r.json().get("alerts", []))
                print(f"    severity={sev}: {cnt} alerts")
        except Exception:
            pass

    # 8d: pipeline_id 过滤 — 验证 dga-realtime-v1 告警
    try:
        r = requests.get(
            f"{GATEWAY}/api/alerts",
            params={"pipeline_id": "dga-realtime-v1", "limit": "50"},
            timeout=10,
        )
        assert r.status_code == 200, f"status={r.status_code}"
        data = r.json()
        pipeline_alerts = data.get("alerts", [])
        correct_pid = all(
            a.get("pipeline_id") == "dga-realtime-v1" for a in pipeline_alerts
        )
        report(
            "GET /api/alerts?pipeline_id=dga-realtime-v1",
            len(pipeline_alerts) >= 1 and correct_pid,
            f"count={len(pipeline_alerts)}, all_correct_pid={correct_pid}",
        )
        for a in pipeline_alerts[:3]:
            print(
                f"    pipeline alert: {a.get('domain','?'):30s}  "
                f"pipeline_id={a.get('pipeline_id','?')}  "
                f"score={a.get('score',0):.4f}"
            )
    except Exception as e:
        report("pipeline_id 过滤", False, str(e))


# ── Step 9: 测试报告 ─────────────────────────────────────────────────

def print_report() -> None:
    section("测试报告汇总")
    total = len(results)
    passed = sum(1 for _, ok, _ in results if ok)
    failed = total - passed

    for step, ok, detail in results:
        tag = PASS if ok else FAIL
        print(f"  {tag}  {step}" + (f"  ({detail})" if detail else ""))

    print(f"\n{'='*60}")
    rate = (passed / total * 100) if total else 0
    color = "\033[92m" if failed == 0 else "\033[91m"
    print(f"  {color}总计: {total} 项, 通过: {passed}, 失败: {failed}, 通过率: {rate:.0f}%\033[0m")
    print(f"{'='*60}\n")


# ── Main ──────────────────────────────────────────────────────────────

def main() -> None:
    print("\n" + "=" * 60)
    print("  DGA 全链路 Pipeline 真实测试")
    print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # Step 1
    if not check_services():
        print(f"\n  {WARN} 部分服务不可用，继续测试可能有失败项\n")

    # Step 2
    cleanup_old_data()

    # Step 3
    score_results = test_gateway_scoring()

    # Step 4
    event_ids = verify_es_write(score_results)

    # Step 5
    verify_redis_cache()

    # Step 6
    verify_starrocks()

    # Step 7a
    test_kafka_pipeline()

    # Step 7b
    test_burst_traffic()

    # Step 8
    verify_alerts_api(event_ids)

    # Step 9
    print_report()

    # 退出码
    failed = sum(1 for _, ok, _ in results if not ok)
    sys.exit(1 if failed > 0 else 0)


if __name__ == "__main__":
    main()

