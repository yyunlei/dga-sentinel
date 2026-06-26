"""
DGA 平台数据种子脚本 — 向 ES/PG/Redis 注入真实数据
用法: python scripts/seed_data.py
"""
from __future__ import annotations

import csv
import json
import os
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import httpx
import asyncpg
import redis
import yaml

# ── 配置（环境变量优先，便于宿主机端口映射变化时无需改代码） ──
SCORING_URL = os.getenv("SCORING_URL", "http://localhost:8001/score")
ES_BASE = os.getenv("ES_BASE", "http://localhost:9200")
PG_DSN = os.getenv("PG_DSN", "postgresql://dga:dga_password@localhost:15432/dga_platform")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:16379/0")
# StarRocks via MySQL protocol (host-direct uses 9030, container uses starrocks-fe:9030)
STARROCKS_HOST = os.getenv("STARROCKS_FE_HOST", "localhost")
STARROCKS_PORT = int(os.getenv("STARROCKS_FE_QUERY_PORT", "9030"))
STARROCKS_USER = os.getenv("STARROCKS_USER", "root")
STARROCKS_DB = os.getenv("STARROCKS_DB", "dga_analytics")
ES_HEADERS = {
    "Content-Type": "application/vnd.elasticsearch+json;compatible-with=8",
    "Accept": "application/vnd.elasticsearch+json;compatible-with=8",
}

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DGA_CSV = PROJECT_ROOT / "DGA-DataSet" / "dga_multi.csv"
PIPELINE_DIR = PROJECT_ROOT / "dag_engine" / "pipelines"

# 50 个固定内网 IP
IP_POOL = [f"192.168.{i // 10}.{100 + i % 10}" for i in range(50)]

BENIGN_DOMAINS = [
    "google.com", "github.com", "stackoverflow.com", "microsoft.com",
    "apple.com", "amazon.com", "cloudflare.com", "wikipedia.org",
    "youtube.com", "twitter.com", "facebook.com", "linkedin.com",
    "reddit.com", "netflix.com", "docker.com", "python.org",
    "npmjs.com", "rust-lang.org", "golang.org", "ubuntu.com",
    "debian.org", "archlinux.org", "fedoraproject.org", "centos.org",
    "nginx.com", "apache.org", "elastic.co", "grafana.com",
    "prometheus.io", "kubernetes.io", "helm.sh", "terraform.io",
    "aws.amazon.com", "azure.microsoft.com", "cloud.google.com",
    "baidu.com", "aliyun.com", "tencent.com", "huawei.com", "jd.com",
    "taobao.com", "weibo.com", "zhihu.com", "bilibili.com", "douyin.com",
    "163.com", "qq.com", "sina.com.cn", "sohu.com", "ifeng.com",
    "cnn.com", "bbc.com", "nytimes.com", "reuters.com", "bloomberg.com",
    "medium.com", "dev.to", "hackernews.com", "techcrunch.com",
    "gitlab.com", "bitbucket.org", "sourceforge.net", "pypi.org",
    "maven.apache.org", "nuget.org", "rubygems.org", "crates.io",
    "fastapi.tiangolo.com", "docs.python.org", "react.dev", "vuejs.org",
    "angular.io", "svelte.dev", "nextjs.org", "vercel.com",
    "heroku.com", "digitalocean.com", "linode.com", "vultr.com",
    "godaddy.com", "namecheap.com", "cloudflare.com", "akamai.com",
    "cdn.jsdelivr.net", "unpkg.com", "cdnjs.cloudflare.com",
    "fonts.googleapis.com", "maps.googleapis.com", "translate.google.com",
    "mail.google.com", "drive.google.com", "docs.google.com",
    "outlook.com", "office.com", "teams.microsoft.com",
    "slack.com", "discord.com", "zoom.us", "webex.com",
]


def _severity(score: float) -> str:
    if score >= 0.9:
        return "CRITICAL"
    if score >= 0.7:
        return "HIGH"
    if score >= 0.5:
        return "MEDIUM"
    return "LOW"


# ── A1: 读取 DGA 域名 + 调用评分服务 → ES ─────────────────────────

def load_dga_domains(n: int = 1500) -> list[tuple[str, str]]:
    """从 dga_multi.csv 读取 (domain, family) 对"""
    rows = []
    with open(DGA_CSV, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append((row["Domain"], row["Botnet_Family"]))
            if len(rows) >= n:
                break
    return rows


def score_domains(domains: list[str], batch_size: int = 50) -> list[dict]:
    """分批调用评分服务，返回评分结果列表"""
    results = []
    client = httpx.Client(timeout=30.0)
    for i in range(0, len(domains), batch_size):
        batch = domains[i : i + batch_size]
        try:
            resp = client.post(SCORING_URL, json={"domains": batch})
            resp.raise_for_status()
            data = resp.json()
            for r in data.get("results", []):
                results.append(r)
            print(f"  scored {min(i + batch_size, len(domains))}/{len(domains)}")
        except Exception as e:
            print(f"  scoring batch {i} failed: {e}, using fallback scores")
            for d in batch:
                results.append({
                    "domain": d, "score": round(random.uniform(0.6, 0.99), 3),
                    "is_dga": True, "family": "unknown",
                    "family_confidence": 0.5, "model_version": "v1.0.0",
                })
    client.close()
    return results


def build_es_docs(scored: list[dict], dga_families: dict[str, str]) -> list[tuple[str, dict]]:
    """构建 ES 文档，时间戳分散到最近 7 天"""
    now = datetime.now(timezone.utc)
    docs = []
    n = len(scored)
    for i, r in enumerate(scored):
        # 分散到 7 天
        day_offset = i * 7 // max(n, 1)
        ts = now - timedelta(days=6 - day_offset, hours=random.randint(0, 23), minutes=random.randint(0, 59))
        domain = r["domain"]
        family = r.get("family") or dga_families.get(domain, "unknown")
        score = float(r.get("score", 0))
        event_id = str(uuid4())
        doc = {
            "event_id": event_id,
            "trace_id": str(uuid4()),
            "timestamp": ts.isoformat().replace("+00:00", "Z"),
            "domain": domain,
            "src_ip": random.choice(IP_POOL),
            "score": round(score, 4),
            "is_dga": bool(r.get("is_dga", score >= 0.5)),
            "family": family if family != "benign" else None,
            "family_confidence": float(r.get("family_confidence", 0) or 0),
            "model_version": r.get("model_version", "v1.0.0"),
            "severity": _severity(score),
            "acknowledged": random.random() > 0.8,
            "tenant_id": "default",
        }
        index_date = ts.strftime("%Y.%m.%d")
        docs.append((f"dga-events-{index_date}", doc))
    return docs


def bulk_index_es(docs: list[tuple[str, dict]]) -> int:
    """ES bulk API 写入，每批 200 条，超时 120s"""
    client = httpx.Client(timeout=120.0)
    # 按索引分组
    by_index: dict[str, list[dict]] = {}
    for idx, doc in docs:
        by_index.setdefault(idx, []).append(doc)

    total = 0
    for idx, batch_docs in by_index.items():
        # 分批写入，每批 200 条
        for chunk_start in range(0, len(batch_docs), 200):
            chunk = batch_docs[chunk_start : chunk_start + 200]
            lines = []
            for doc in chunk:
                lines.append(json.dumps({"index": {"_index": idx}}))
                lines.append(json.dumps(doc))
            body = "\n".join(lines) + "\n"
            try:
                resp = client.post(
                    f"{ES_BASE}/_bulk",
                    content=body.encode(),
                    headers=ES_HEADERS,
                )
                resp.raise_for_status()
                result = resp.json()
                ok_count = sum(1 for item in result.get("items", []) if item.get("index", {}).get("status", 0) < 300)
                total += ok_count
                print(f"  {idx}: {ok_count}/{len(chunk)} indexed (chunk {chunk_start // 200 + 1})")
            except Exception as e:
                print(f"  {idx}: bulk failed: {e}")
    client.close()
    return total


# ── A2-A5: PG 种子数据 ────────────────────────────────────────────

import asyncio

async def seed_pg():
    """向 PG 注入 pipeline、模型版本、操作历史、审计日志"""
    conn = await asyncpg.connect(PG_DSN)
    now = datetime.now(timezone.utc)

    # A2: 4 条真实 Pipeline
    pipelines = [
        ("dga-realtime-v1", "DGA 实时检测流水线", "stream", "running", "dga_realtime.yaml"),
        ("dga-batch-v1", "DGA 批量回放分析", "batch", "stopped", "dga_batch.yaml"),
        ("c2-realtime-v1", "C2 域名实时检测", "stream", "stopped", "c2_realtime.yaml"),
        ("dns-tunnel-v1", "DNS 隧道检测", "stream", "stopped", "dns_tunnel.yaml"),
    ]
    for pid, name, mode, status, yaml_file in pipelines:
        yaml_path = PIPELINE_DIR / yaml_file
        yaml_content = yaml_path.read_text() if yaml_path.exists() else ""
        await conn.execute(
            "INSERT INTO pipeline_configs (pipeline_id, name, mode, yaml_content, status, version, created_at) "
            "VALUES ($1, $2, $3, $4, $5, '1.0.0', $6) "
            "ON CONFLICT (pipeline_id) DO UPDATE SET name=$2, mode=$3, yaml_content=$4, status=$5",
            pid, name, mode, yaml_content, status, now - timedelta(days=7),
        )
    print(f"  PG: 4 pipelines upserted")

    # A3: Pipeline 操作历史 (~15 条)
    ops = [
        ("dga-realtime-v1", "create", "admin", now - timedelta(days=7)),
        ("dga-realtime-v1", "start", "admin", now - timedelta(days=7, hours=-1)),
        ("dga-batch-v1", "create", "admin", now - timedelta(days=6)),
        ("c2-realtime-v1", "create", "admin", now - timedelta(days=6)),
        ("dns-tunnel-v1", "create", "admin", now - timedelta(days=5)),
        ("dga-realtime-v1", "stop", "admin", now - timedelta(days=4)),
        ("dga-realtime-v1", "start", "admin", now - timedelta(days=4, hours=-2)),
        ("dga-batch-v1", "replay", "analyst", now - timedelta(days=3)),
        ("dga-batch-v1", "start", "analyst", now - timedelta(days=3, hours=-1)),
        ("dga-batch-v1", "stop", "system", now - timedelta(days=3, hours=-3)),
        ("c2-realtime-v1", "start", "admin", now - timedelta(days=2)),
        ("c2-realtime-v1", "stop", "admin", now - timedelta(days=2, hours=-4)),
        ("dga-realtime-v1", "stop", "admin", now - timedelta(days=1)),
        ("dga-realtime-v1", "start", "admin", now - timedelta(days=1, hours=-1)),
        ("dns-tunnel-v1", "start", "admin", now - timedelta(hours=6)),
        ("dns-tunnel-v1", "stop", "admin", now - timedelta(hours=2)),
    ]
    for pid, op, operator, ts in ops:
        await conn.execute(
            "INSERT INTO pipeline_operations (pipeline_id, operation, operator, status, detail, created_at) "
            "VALUES ($1, $2, $3, 'success', '{}'::jsonb, $4)",
            pid, op, operator, ts,
        )
    print(f"  PG: {len(ops)} pipeline operations inserted")

    # A4: 模型版本 v1.1.0 staging + 更新 v1.0.0 metrics
    model_seeds = [
        ("binary-xgboost", "v1.1.0", "artifacts/binary/binary_classification_model.pkl",
         {"accuracy": 0.972, "f1": 0.960, "precision": 0.968, "recall": 0.953, "auc": 0.993},
         "staging", 0.0),
        ("multi-cnn-attention", "v1.1.0", "artifacts/multi/multiclass_classification_model.h5",
         {"accuracy": 0.941, "f1": 0.930, "precision": 0.935, "recall": 0.925},
         "staging", 0.0),
    ]
    for mid, ver, path, metrics, status, weight in model_seeds:
        await conn.execute(
            "INSERT INTO model_versions (model_id, version, artifact_path, metrics, status, ab_weight, created_at) "
            "VALUES ($1, $2, $3, $4::jsonb, $5, $6, $7) "
            "ON CONFLICT (model_id, version) DO UPDATE SET metrics=$4::jsonb, status=$5",
            mid, ver, path, json.dumps(metrics), status, weight, now - timedelta(days=3),
        )
    # 更新 v1.0.0 的 metrics 和 deployed_at
    await conn.execute(
        "UPDATE model_versions SET metrics=$1::jsonb, deployed_at=$2 "
        "WHERE model_id='binary-xgboost' AND version='v1.0.0'",
        json.dumps({"accuracy": 0.967, "f1": 0.952, "precision": 0.961, "recall": 0.943, "auc": 0.991}),
        now - timedelta(days=30),
    )
    await conn.execute(
        "UPDATE model_versions SET metrics=$1::jsonb, deployed_at=$2 "
        "WHERE model_id='multi-cnn-attention' AND version='v1.0.0'",
        json.dumps({"accuracy": 0.934, "f1": 0.921, "precision": 0.928, "recall": 0.914}),
        now - timedelta(days=30),
    )
    print(f"  PG: model versions seeded")

    # A5: 审计日志
    audit_entries = [
        ("admin", "model_deploy", "binary-xgboost", {"version": "v1.0.0"}, now - timedelta(days=30)),
        ("admin", "model_deploy", "multi-cnn-attention", {"version": "v1.0.0"}, now - timedelta(days=30)),
        ("admin", "model_rollback", "binary-xgboost", {"from": "v0.9.0", "to": "v1.0.0"}, now - timedelta(days=25)),
        ("analyst", "model_deploy", "binary-xgboost", {"version": "v1.0.0", "note": "re-deploy after rollback"}, now - timedelta(days=20)),
        ("admin", "model_deploy", "multi-cnn-attention", {"version": "v1.0.0", "note": "production promotion"}, now - timedelta(days=15)),
        ("admin", "model_rollback", "multi-cnn-attention", {"from": "v1.0.0-rc1", "to": "v1.0.0"}, now - timedelta(days=10)),
        ("system", "model_deploy", "binary-xgboost", {"version": "v1.0.0", "auto": True}, now - timedelta(days=7)),
        ("admin", "model_offline", "binary-xgboost", {"version": "v0.9.0"}, now - timedelta(days=5)),
        ("analyst", "model_deploy", "multi-cnn-attention", {"version": "v1.0.0"}, now - timedelta(days=3)),
        ("admin", "model_rollback", "binary-xgboost", {"to_version": "v1.0.0"}, now - timedelta(days=1)),
    ]
    for uid, action, resource, detail, ts in audit_entries:
        await conn.execute(
            "INSERT INTO audit_log (user_id, action, resource, detail, created_at) "
            "VALUES ($1, $2, $3, $4::jsonb, $5)",
            uid, action, resource, json.dumps(detail), ts,
        )
    print(f"  PG: {len(audit_entries)} audit log entries inserted")

    await conn.close()


# ── A6: Redis 缓存 ────────────────────────────────────────────────

def seed_redis_cache(es_docs: list[tuple[str, dict]]):
    """预计算 dashboard stats 写入 Redis"""
    r = redis.from_url(REDIS_URL, decode_responses=True)
    now = datetime.now(timezone.utc)
    today_str = now.strftime("%Y.%m.%d")
    today_idx = f"dga-events-{today_str}"

    today_docs = [d for idx, d in es_docs if idx == today_idx]
    total = len(today_docs)
    dga_hits = sum(1 for d in today_docs if d.get("is_dga"))
    hit_rate = round(dga_hits / max(total, 1) * 100, 2)

    # family distribution
    family_counts: dict[str, int] = {}
    for d in today_docs:
        f = d.get("family") or "unknown"
        family_counts[f] = family_counts.get(f, 0) + 1
    family_dist = [{"name": k, "value": v} for k, v in sorted(family_counts.items(), key=lambda x: -x[1])[:10]]

    # qps history (mock realistic pattern based on real count)
    qps_history = []
    for i in range(60):
        h = (now.hour + (i - 59)) % 24
        m = (now.minute + i) % 60
        base_qps = total // 60 + random.randint(-5, 15)
        qps_history.append({
            "time": f"{h:02d}:{m:02d}:00",
            "qps": max(0, base_qps + random.randint(0, 30)),
            "hits": max(0, dga_hits // 60 + random.randint(-2, 5)),
        })

    stats = {
        "total_today": total,
        "dga_hits": dga_hits,
        "hit_rate": hit_rate,
        "p95_latency": round(random.uniform(6, 15), 1),
        "qps_history": qps_history,
        "family_dist": family_dist,
    }
    r.set("dashboard:stats", json.dumps(stats), ex=3600)
    print(f"  Redis: dashboard:stats cached (total={total}, dga={dga_hits})")
    r.close()


# ── main ──────────────────────────────────────────────────────────

def seed_starrocks(es_docs: list[tuple[str, dict]]) -> int:
    """Insert all scored events into StarRocks dga_analytics.dga_events for OLAP analytics.

    Uses pymysql (StarRocks MySQL 9030 protocol). Idempotent via DUPLICATE KEY (event_id, trace_id).
    """
    try:
        import pymysql
    except ImportError:
        print("  pymysql not installed, skipping StarRocks seed")
        return 0

    rows = []
    for _idx_name, doc in es_docs:
        rows.append((
            doc["event_id"],
            doc["trace_id"],
            doc["timestamp"].replace("T", " ").split("+")[0].split(".")[0],  # DATETIME format
            doc["domain"],
            doc.get("src_ip", ""),
            float(doc.get("score", 0)),
            bool(doc.get("is_dga", False)),
            doc.get("family") or "",
            float(doc.get("family_confidence") or 0.0),
            doc.get("model_version", "v1.0.0"),
            doc.get("pipeline_id", "dga-realtime-v1"),
            doc.get("tenant_id", "default"),
            doc.get("severity", "MEDIUM"),
        ))

    conn = pymysql.connect(
        host=STARROCKS_HOST, port=STARROCKS_PORT,
        user=STARROCKS_USER, database=STARROCKS_DB,
        autocommit=True, connect_timeout=10,
    )
    cur = conn.cursor()
    sql = (
        "INSERT INTO dga_events "
        "(event_id, trace_id, event_time, domain, src_ip, score, is_dga, "
        " family, family_confidence, model_version, pipeline_id, tenant_id, severity) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
    )
    inserted = 0
    chunk = 200
    for i in range(0, len(rows), chunk):
        batch = rows[i:i+chunk]
        try:
            cur.executemany(sql, batch)
            inserted += len(batch)
            print(f"  StarRocks: {inserted}/{len(rows)} rows inserted")
        except Exception as e:
            print(f"  StarRocks: chunk {i//chunk} failed: {e}")
    cur.close()
    conn.close()
    return inserted


def main():
    print("=" * 60)
    print("DGA 平台数据种子脚本")
    print("=" * 60)

    # A1: 读取 DGA 域名
    print("\n[A1] 加载 DGA 域名...")
    dga_pairs = load_dga_domains(1500)
    dga_domains = [d for d, _ in dga_pairs]
    dga_families = {d: f for d, f in dga_pairs}
    print(f"  loaded {len(dga_domains)} DGA domains")

    # 加入合法域名
    all_domains = dga_domains + BENIGN_DOMAINS[:300]
    random.shuffle(all_domains)

    print("\n[A1] 调用评分服务...")
    scored = score_domains(all_domains)
    print(f"  scored {len(scored)} domains total")

    print("\n[A1] 构建 ES 文档...")
    es_docs = build_es_docs(scored, dga_families)
    print(f"  built {len(es_docs)} ES documents across 7 days")

    print("\n[A1] 写入 ES...")
    total_indexed = bulk_index_es(es_docs)
    print(f"  total indexed: {total_indexed}")

    # A2-A5: PG 种子
    print("\n[A2-A5] 种子 PG 数据...")
    asyncio.run(seed_pg())

    # A6: Redis 缓存
    print("\n[A6] 预计算 Redis 缓存...")
    seed_redis_cache(es_docs)

    # A7: StarRocks OLAP 表
    print("\n[A7] 写入 StarRocks dga_events...")
    sr_count = seed_starrocks(es_docs)
    print(f"  StarRocks total: {sr_count} rows")

    print("\n" + "=" * 60)
    print("种子数据注入完成!")
    print("=" * 60)


if __name__ == "__main__":
    main()
