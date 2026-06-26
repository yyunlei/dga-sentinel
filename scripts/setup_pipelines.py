#!/usr/bin/env python3
"""
清理旧 Pipeline 并创建真实场景 Pipeline，然后运行全链路测试。
用法: python scripts/setup_pipelines.py
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone

import requests

GATEWAY = "http://localhost:8000"
PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"

results: list[tuple[str, bool, str]] = []


def report(step: str, ok: bool, detail: str = "") -> None:
    results.append((step, ok, detail))
    tag = PASS if ok else FAIL
    print(f"  {tag}  {step}" + (f"  ({detail})" if detail else ""))


def section(title: str) -> None:
    print(f"\n{'='*60}\n  {title}\n{'='*60}")


# ── Pipeline YAML 定义 ──────────────────────────────────────────

PIPELINES = [
    {
        "name": "DGA 全链路检测 (实时)",
        "mode": "stream",
        "yaml": """nodes:
  - id: kafka_ingest
    type: kafka_consumer
    config:
      topic: dns-query-logs
      group_id: dga-realtime-v1
      auto_offset_reset: latest
  - id: dns_parse
    type: dns_parser
    config:
      fields: [query_name, query_type, src_ip, timestamp]
  - id: feature_extract
    type: feature_extractor
    config:
      extractors: [lexical, entropy]
  - id: dga_scoring
    type: scoring_service
    config:
      endpoint: "http://scoring-service:8001"
      protocol: http
      timeout_ms: 3000
      model_id: binary-xgboost
      threshold: 0.7
  - id: whitelist_filter
    type: whitelist
    config:
      source: static
      static: [google.com, microsoft.com, apple.com, amazon.com, github.com, cloudflare.com]
  - id: threshold_filter
    type: threshold
    config:
      min_score: 0.7
  - id: severity_tagger
    type: severity_tag
    config:
      critical_threshold: 0.95
      high_threshold: 0.85
      medium_threshold: 0.7
  - id: output_sink
    type: multi_sink
    config:
      routes: ["es:always", "kafka:is_dga", "starrocks:always"]
      es_index: dga-events
      kafka_topic: dga-alerts
      starrocks_table: dga_events
connections:
  - source: kafka_ingest
    target: dns_parse
  - source: dns_parse
    target: feature_extract
  - source: feature_extract
    target: dga_scoring
  - source: dga_scoring
    target: whitelist_filter
  - source: whitelist_filter
    target: threshold_filter
  - source: threshold_filter
    target: severity_tagger
  - source: severity_tagger
    target: output_sink""",
    },
    {
        "name": "C2 域名实时检测",
        "mode": "stream",
        "yaml": """nodes:
  - id: kafka_ingest
    type: kafka_consumer
    config:
      topic: dns-query-logs
      group_id: c2-detector-v1
      auto_offset_reset: latest
  - id: dns_parse
    type: dns_parser
    config:
      fields: [query_name, query_type, src_ip, timestamp]
  - id: feature_extract
    type: feature_extractor
    config:
      extractors: [entropy, lexical, ngram]
      window_size: 120s
  - id: c2_scoring
    type: scoring_service
    config:
      endpoint: "http://scoring-service:8001"
      protocol: http
      timeout_ms: 3000
      model_id: binary-xgboost
      threshold: 0.6
  - id: whitelist_filter
    type: whitelist
    config:
      source: redis
      redis_key: whitelist:domains
  - id: threshold_filter
    type: threshold
    config:
      min_score: 0.6
  - id: output_sink
    type: multi_sink
    config:
      routes: ["es:always", "kafka:is_dga"]
      es_index: c2-events
      kafka_topic: c2-alerts
connections:
  - source: kafka_ingest
    target: dns_parse
  - source: dns_parse
    target: feature_extract
  - source: feature_extract
    target: c2_scoring
  - source: c2_scoring
    target: whitelist_filter
  - source: whitelist_filter
    target: threshold_filter
  - source: threshold_filter
    target: output_sink""",
    },
    {
        "name": "DNS 隧道检测",
        "mode": "stream",
        "yaml": """nodes:
  - id: kafka_ingest
    type: kafka_consumer
    config:
      topic: dns-query-logs
      group_id: dns-tunnel-v1
      auto_offset_reset: latest
  - id: dns_parse
    type: dns_parser
    config:
      fields: [query_name, query_type, src_ip, timestamp, response_size]
  - id: feature_extract
    type: feature_extractor
    config:
      extractors: [entropy, lexical, ngram]
      window_size: 300s
  - id: tunnel_scoring
    type: scoring_service
    config:
      endpoint: "http://scoring-service:8001"
      protocol: http
      timeout_ms: 3000
      model_id: binary-xgboost
      threshold: 0.65
  - id: whitelist_filter
    type: whitelist
    config:
      source: redis
      redis_key: whitelist:domains
  - id: threshold_filter
    type: threshold
    config:
      min_score: 0.65
  - id: output_sink
    type: multi_sink
    config:
      routes: ["es:always", "kafka:is_dga"]
      es_index: dns-tunnel-events
      kafka_topic: dns-tunnel-alerts
connections:
  - source: kafka_ingest
    target: dns_parse
  - source: dns_parse
    target: feature_extract
  - source: feature_extract
    target: tunnel_scoring
  - source: tunnel_scoring
    target: whitelist_filter
  - source: whitelist_filter
    target: threshold_filter
  - source: threshold_filter
    target: output_sink""",
    },
    {
        "name": "威胁情报联动告警",
        "mode": "stream",
        "yaml": """nodes:
  - id: kafka_ingest
    type: kafka_consumer
    config:
      topic: dns-query-logs
      group_id: threat-intel-v1
      auto_offset_reset: latest
  - id: dns_parse
    type: dns_parser
    config:
      fields: [query_name, query_type, src_ip, timestamp]
  - id: feature_extract
    type: feature_extractor
    config:
      extractors: [lexical, entropy]
  - id: dga_scoring
    type: scoring_service
    config:
      endpoint: "http://scoring-service:8001"
      protocol: http
      timeout_ms: 3000
      model_id: binary-xgboost
      threshold: 0.7
  - id: threat_enrich
    type: threat_intel_enrich
    config:
      providers: [virustotal, threatfox]
      cache_ttl: 3600
      timeout_ms: 5000
      fail_open: true
  - id: geoip
    type: geoip_lookup
    config:
      ip_field: src_ip
      database: maxmind
      output_fields: [country, city, asn]
  - id: risk_score
    type: risk_aggregate
    config:
      dga_score_weight: 0.4
      threat_intel_weight: 0.3
      geoip_risk_weight: 0.3
      aggregation_method: weighted_sum
  - id: severity_tagger
    type: severity_tag
    config:
      critical_threshold: 0.95
      high_threshold: 0.85
      medium_threshold: 0.7
  - id: output_sink
    type: fan_out
    config:
      channels: [es, kafka, starrocks]
      es_index: threat-intel-events
      kafka_topic: threat-intel-alerts
      starrocks_table: dga_events
      fail_strategy: continue
connections:
  - source: kafka_ingest
    target: dns_parse
  - source: dns_parse
    target: feature_extract
  - source: feature_extract
    target: dga_scoring
  - source: dga_scoring
    target: threat_enrich
  - source: threat_enrich
    target: geoip
  - source: geoip
    target: risk_score
  - source: risk_score
    target: severity_tagger
  - source: severity_tagger
    target: output_sink""",
    },
    {
        "name": "DGA 批量回溯分析",
        "mode": "batch",
        "yaml": """nodes:
  - id: file_ingest
    type: file_reader
    config:
      directory: /data/dns-logs/
      pattern: "*.jsonl"
      format: jsonl
      batch_size: 1000
  - id: dns_parse
    type: dns_parser
    config:
      fields: [query_name, query_type, src_ip, timestamp]
  - id: feature_extract
    type: feature_extractor
    config:
      extractors: [lexical, entropy]
  - id: dga_scoring
    type: scoring_service
    config:
      endpoint: "http://scoring-service:8001"
      protocol: http
      timeout_ms: 5000
      model_id: binary-xgboost
      threshold: 0.7
      batch_size: 64
  - id: family_classify
    type: family_classify
    config:
      endpoint: "http://scoring-service:8001"
      model_id: multi-cnn-attention
      top_k: 3
      min_confidence: 0.3
      only_dga: true
  - id: threshold_filter
    type: threshold
    config:
      min_score: 0.7
  - id: output_sink
    type: multi_sink
    config:
      routes: ["es:always", "starrocks:always"]
      es_index: dga-events
      starrocks_table: dga_events
connections:
  - source: file_ingest
    target: dns_parse
  - source: dns_parse
    target: feature_extract
  - source: feature_extract
    target: dga_scoring
  - source: dga_scoring
    target: family_classify
  - source: family_classify
    target: threshold_filter
  - source: threshold_filter
    target: output_sink""",
    },
]


# ── Step 1: 删除所有旧 Pipeline ─────────────────────────────────

def delete_all_pipelines() -> None:
    section("Step 1: 删除所有旧 Pipeline")
    try:
        r = requests.get(f"{GATEWAY}/api/dag/pipelines", timeout=10)
        r.raise_for_status()
        existing = r.json().get("pipelines", [])
        if not existing:
            report("无旧 Pipeline 需要删除", True)
            return
        for p in existing:
            pid = p["pipeline_id"]
            name = p["name"]
            # 先停止 running 的
            if p.get("status") == "running":
                try:
                    requests.post(
                        f"{GATEWAY}/api/dag/pipelines/{pid}/stop", timeout=5,
                    )
                    time.sleep(0.5)
                except Exception:
                    pass
            try:
                dr = requests.delete(
                    f"{GATEWAY}/api/dag/pipelines/{pid}", timeout=10,
                )
                ok = dr.status_code == 200
                report(f"删除 [{name}]", ok, f"id={pid[:8]}")
            except Exception as e:
                report(f"删除 [{name}]", False, str(e))
    except Exception as e:
        report("获取 Pipeline 列表", False, str(e))


# ── Step 2: 创建真实场景 Pipeline ────────────────────────────────

def create_pipelines() -> list[dict]:
    section("Step 2: 创建真实场景 Pipeline")
    created: list[dict] = []
    for p in PIPELINES:
        try:
            r = requests.post(
                f"{GATEWAY}/api/dag/pipelines",
                json={
                    "name": p["name"],
                    "mode": p["mode"],
                    "yaml_content": p["yaml"].strip(),
                },
                timeout=10,
            )
            r.raise_for_status()
            data = r.json()
            created.append(data)
            report(
                f"创建 [{p['name']}]",
                True,
                f"id={data['pipeline_id'][:8]}, mode={p['mode']}",
            )
        except Exception as e:
            report(f"创建 [{p['name']}]", False, str(e))
    return created


# ── Step 3: 启动 stream 类型 Pipeline ────────────────────────────

def start_stream_pipelines(created: list[dict]) -> None:
    section("Step 3: 启动 Stream Pipeline")
    for p in created:
        if p.get("mode") != "stream":
            print(f"  跳过 batch pipeline: {p['name']}")
            continue
        pid = p["pipeline_id"]
        try:
            r = requests.post(
                f"{GATEWAY}/api/dag/pipelines/{pid}/start", timeout=10,
            )
            ok = r.status_code == 200
            report(f"启动 [{p['name']}]", ok)
        except Exception as e:
            report(f"启动 [{p['name']}]", False, str(e))


# ── Step 4: 验证 Pipeline 列表 ──────────────────────────────────

def verify_pipelines() -> None:
    section("Step 4: 验证 Pipeline 列表")
    try:
        r = requests.get(f"{GATEWAY}/api/dag/pipelines", timeout=10)
        r.raise_for_status()
        plist = r.json().get("pipelines", [])
        report(f"Pipeline 总数", len(plist) == len(PIPELINES), f"期望={len(PIPELINES)}, 实际={len(plist)}")
        for p in plist:
            status_icon = "🟢" if p["status"] == "running" else "🔴" if p["status"] == "stopped" else "⚪"
            print(f"    {status_icon} {p['name']:30s}  mode={p['mode']:8s}  status={p['status']:10s}  v{p['version']}")
    except Exception as e:
        report("获取 Pipeline 列表", False, str(e))


# ── Step 5: 评分链路测试 ────────────────────────────────────────

DGA_DOMAINS = [
    "qjkxnvtpmrwzs.com", "xkcd8f3m2nq9p.net", "a1b2c3d4e5f6g7.org",
    "zyxwvutsrqponm.info", "hjkl9876asdf12.xyz",
]
LEGIT_DOMAINS = ["google.com", "github.com", "stackoverflow.com"]


def test_scoring() -> None:
    section("Step 5: 评分链路测试")
    # DGA 域名
    try:
        r = requests.post(
            f"{GATEWAY}/api/score",
            json={"domains": DGA_DOMAINS},
            timeout=30,
        )
        assert r.status_code == 200, f"status={r.status_code}"
        data = r.json()
        res_list = data.get("results", [])
        high = sum(1 for x in res_list if x["score"] >= 0.7)
        for x in res_list:
            print(f"    {x['domain']:30s}  score={x['score']:.4f}  is_dga={x['is_dga']}")
        report("DGA 域名高分命中", high >= 3, f"{high}/{len(DGA_DOMAINS)} score>=0.7")
    except Exception as e:
        report("DGA 域名评分", False, str(e))

    # 正常域名
    try:
        r = requests.post(
            f"{GATEWAY}/api/score",
            json={"domains": LEGIT_DOMAINS},
            timeout=30,
        )
        assert r.status_code == 200
        data = r.json()
        res_list = data.get("results", [])
        low = sum(1 for x in res_list if x["score"] < 0.5)
        for x in res_list:
            print(f"    {x['domain']:30s}  score={x['score']:.4f}  is_dga={x['is_dga']}")
        report("正常域名低分", low == len(LEGIT_DOMAINS), f"{low}/{len(LEGIT_DOMAINS)} score<0.5")
    except Exception as e:
        report("正常域名评分", False, str(e))


# ── Step 6: 验证告警写入 ────────────────────────────────────────

def verify_alerts() -> None:
    section("Step 6: 验证告警写入")
    time.sleep(3)
    try:
        r = requests.get(f"{GATEWAY}/api/alerts", timeout=10)
        assert r.status_code == 200
        alerts = r.json().get("alerts", [])
        report("告警 API 可用", True, f"total={len(alerts)}")
        dga_matched = [a for a in alerts if a.get("domain") in DGA_DOMAINS]
        report("告警包含测试 DGA 域名", len(dga_matched) >= 1, f"matched={len(dga_matched)}")
        for a in alerts[:5]:
            print(f"    {a.get('domain','?'):30s}  score={a.get('score',0):.4f}  severity={a.get('severity','?')}")
    except Exception as e:
        report("告警 API", False, str(e))


# ── 报告 ────────────────────────────────────────────────────────

def print_report() -> None:
    section("测试报告")
    total = len(results)
    passed = sum(1 for _, ok, _ in results if ok)
    failed = total - passed
    for step, ok, detail in results:
        tag = PASS if ok else FAIL
        print(f"  {tag}  {step}" + (f"  ({detail})" if detail else ""))
    print(f"\n{'='*60}")
    rate = (passed / total * 100) if total else 0
    color = "\033[92m" if failed == 0 else "\033[91m"
    print(f"  {color}总计: {total}, 通过: {passed}, 失败: {failed}, 通过率: {rate:.0f}%\033[0m")
    print(f"{'='*60}\n")


# ── Main ────────────────────────────────────────────────────────

def main() -> None:
    print(f"\n{'='*60}")
    print("  DGA Pipeline 初始化 & 全链路测试")
    print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")

    # 检查 Gateway 可用
    try:
        r = requests.get(f"{GATEWAY}/health", timeout=5)
        assert r.status_code == 200
        print(f"\n  Gateway 可用 ✓")
    except Exception:
        print(f"\n  Gateway 不可用，请先启动 docker-compose")
        sys.exit(1)

    delete_all_pipelines()
    created = create_pipelines()
    start_stream_pipelines(created)
    time.sleep(2)
    verify_pipelines()
    test_scoring()
    verify_alerts()
    print_report()

    failed = sum(1 for _, ok, _ in results if not ok)
    sys.exit(1 if failed > 0 else 0)


if __name__ == "__main__":
    main()
