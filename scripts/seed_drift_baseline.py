#!/usr/bin/env python3
"""
seed_drift_baseline.py — 一次性种子脚本，给 DriftMonitor 灌真实基线分布。

流程：
  1. 准备 200 个代表性域名（150 benign + 50 DGA-like 合成）
  2. POST 一次 /score 拿到真实模型评分
  3. 用 {score, domain_len} 调 /drift/baseline 设定基线
  4. GET /drift/scores 验证基线生效

为什么不用合成 score：DriftMonitor 算 PSI 时会拿基线和运行窗口对比；
如果基线 score 是合成的（uniform [0,1]），运行时来自模型的真实 score
跟它有天然偏差 → PSI 永远偏离 → 持续误报。所以必须走 /score 拿真分数。

运行方式：
  容器内（推荐，依赖齐全）：
      docker exec dga-sentinel-agent mkdir -p /app/scripts  # 幂等
      docker cp scripts/seed_drift_baseline.py dga-sentinel-agent:/app/scripts/
      docker exec dga-sentinel-agent python /app/scripts/seed_drift_baseline.py

  容器外（uv 环境）:
      SCORING_URL=http://localhost:8001 uv run python scripts/seed_drift_baseline.py
"""

from __future__ import annotations

import asyncio
import os
import random
import string
import sys

import httpx


def _resolve_scoring_url() -> str:
    """优先 SCORING_URL env；其次按 PG_DSN 判定是否容器内；否则本机端口。"""
    if explicit := os.environ.get("SCORING_URL"):
        return explicit
    in_container = os.environ.get("PG_DSN", "").startswith(
        "postgresql://dga:dga_password@postgres"
    )
    return "http://scoring-service:8001" if in_container else "http://localhost:8001"


SCORING_URL = _resolve_scoring_url()


# 150 个常见正常域名（Alexa-style + 工具站点 + 中国互联网）
BENIGN_DOMAINS = [
    "google.com", "youtube.com", "facebook.com", "wikipedia.org",
    "amazon.com", "twitter.com", "instagram.com", "yahoo.com",
    "reddit.com", "github.com", "linkedin.com", "netflix.com",
    "microsoft.com", "office.com", "live.com", "bing.com",
    "apple.com", "icloud.com", "spotify.com", "twitch.tv",
    "stackoverflow.com", "medium.com", "quora.com", "imdb.com",
    "nytimes.com", "bbc.com", "cnn.com", "washingtonpost.com",
    "espn.com", "nba.com", "nfl.com", "fifa.com",
    "khan-academy.org", "coursera.org", "edx.org", "udemy.com",
    "duolingo.com", "ted.com", "khanacademy.org", "udacity.com",
    "dropbox.com", "drive.google.com", "onedrive.live.com", "box.com",
    "slack.com", "discord.com", "zoom.us", "skype.com",
    "wechat.com", "weibo.com", "baidu.com", "qq.com",
    "alibaba.com", "taobao.com", "jd.com", "tmall.com",
    "stripe.com", "paypal.com", "square.com", "venmo.com",
    "salesforce.com", "hubspot.com", "atlassian.com", "trello.com",
    "asana.com", "notion.so", "airtable.com", "monday.com",
    "shopify.com", "wordpress.com", "squarespace.com", "wix.com",
    "amazonaws.com", "azure.com", "googleapis.com", "cloudflare.com",
    "fastly.com", "akamai.com", "digitalocean.com", "linode.com",
    "vultr.com", "hetzner.com", "ovh.com", "godaddy.com",
    "namecheap.com", "name.com", "cloudfront.net", "amazon-adsystem.com",
    "doubleclick.net", "googlesyndication.com", "googletagmanager.com",
    "google-analytics.com", "facebook.net", "fbcdn.net", "cdn-instagram.com",
    "twimg.com", "wp.com", "wordpress.org", "gravatar.com",
    "akamaihd.net", "rackspace.com", "ovh.net", "hetzner.cloud",
    "anthropic.com", "openai.com", "huggingface.co", "kaggle.com",
    "arxiv.org", "ieee.org", "acm.org", "rfc-editor.org",
    "ietf.org", "iana.org", "icann.org", "cve.mitre.org",
    "redhat.com", "ubuntu.com", "debian.org", "centos.org",
    "fedoraproject.org", "archlinux.org", "kernel.org", "python.org",
    "pypi.org", "npmjs.com", "rubygems.org", "crates.io",
    "docker.com", "kubernetes.io", "helm.sh", "terraform.io",
    "ansible.com", "puppet.com", "chef.io", "vagrantup.com",
    "mongodb.com", "redis.io", "postgresql.org", "mysql.com",
    "cassandra.apache.org", "elastic.co", "kafka.apache.org", "rabbitmq.com",
    "grafana.com", "prometheus.io", "datadoghq.com", "newrelic.com",
    "sentry.io", "rollbar.com", "honeycomb.io", "logz.io",
    "djangoproject.com", "rubyonrails.org", "expressjs.com", "nestjs.com",
    "vuejs.org", "reactjs.org", "angular.io", "svelte.dev",
    "go.dev", "rust-lang.org", "swift.org", "ziglang.org",
]


def _generate_dga_like(n: int, seed: int = 42) -> list[str]:
    """生成 n 个伪随机字母数字字符串（模拟 DGA 风格输出）。"""
    rng = random.Random(seed)
    tlds = [".com", ".cc", ".info", ".biz", ".xyz", ".top", ".online"]
    out: list[str] = []
    for _ in range(n):
        length = rng.randint(16, 36)
        sld = "".join(rng.choices(string.ascii_lowercase + string.digits, k=length))
        out.append(sld + rng.choice(tlds))
    return out


async def main() -> int:
    benign = BENIGN_DOMAINS[:150]
    dga_like = _generate_dga_like(50)
    domains = benign + dga_like
    print(f"[seed] {len(domains)} domains ({len(benign)} benign + {len(dga_like)} dga-like)")
    print(f"[seed] scoring URL = {SCORING_URL}")

    async with httpx.AsyncClient(timeout=180.0) as client:
        # 1) 拿真实模型评分
        print("\n[step 1/3] scoring all domains via /score …")
        resp = await client.post(
            f"{SCORING_URL}/score",
            json={"domains": domains, "tenant_id": "default"},
        )
        resp.raise_for_status()
        results = resp.json()["results"]
        print(f"           ✓ scored {len(results)} domains in {resp.elapsed.total_seconds():.1f}s")

        # 2) 打 baseline 包
        baseline = [
            {"score": float(r["score"]), "domain_len": float(len(r["domain"]))}
            for r in results
        ]
        scores_sorted = sorted(s["score"] for s in baseline)
        lens_sorted = sorted(s["domain_len"] for s in baseline)
        print(
            f"           score: min={scores_sorted[0]:.3f} "
            f"med={scores_sorted[len(scores_sorted)//2]:.3f} "
            f"max={scores_sorted[-1]:.3f}"
        )
        print(
            f"           length: min={lens_sorted[0]:.0f} "
            f"med={lens_sorted[len(lens_sorted)//2]:.0f} "
            f"max={lens_sorted[-1]:.0f}"
        )

        # 3) 设定 baseline
        print("\n[step 2/3] POST /drift/baseline …")
        resp = await client.post(
            f"{SCORING_URL}/drift/baseline",
            json={"samples": baseline},
        )
        resp.raise_for_status()
        print(f"           ✓ {resp.json()}")

        # 4) 验证生效
        print("\n[step 3/3] GET /drift/scores …")
        resp = await client.get(f"{SCORING_URL}/drift/scores")
        resp.raise_for_status()
        info = resp.json()
        print(f"           baseline_set = {info['baseline_set']}")
        print(f"           window_size  = {info['window_size']}")
        print(f"           current PSI  = {info['scores']}")

    print("\n✅ Drift baseline seeded successfully")
    print("   → 后续 /score 调用会自动 record 到滑动窗口")
    print("   → 5 分钟后 DriftMonitor 后台 task 会跑首次 check_drift")
    print("   → PSI ≥ 0.25 时 pipeline_operations 收到 drift_alert (pending)")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
