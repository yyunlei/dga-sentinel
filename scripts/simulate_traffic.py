#!/usr/bin/env python3
"""
DGA DNS 查询日志流量模拟器
通过 aiokafka 直连 Kafka，持续生成混合 DGA/正常域名的 DNS 查询日志，
驱动 DAG Engine 实时检测 Pipeline。

用法:
  python scripts/simulate_traffic.py                        # 默认参数，无限运行
  python scripts/simulate_traffic.py --duration 60          # 运行 60 秒
  python scripts/simulate_traffic.py --batch-size 20 --interval 1 --dga-ratio 0.5
  python scripts/simulate_traffic.py --business http://localhost:8000  # 同时调用 Gateway 评分
"""
from __future__ import annotations

import argparse
import asyncio
import json
import random
import signal
import string
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

# ---------------------------------------------------------------------------
# Domain pools & generators
# ---------------------------------------------------------------------------

DGA_TLDS = [".com", ".net", ".org", ".info", ".xyz", ".top", ".club", ".biz", ".pw", ".eu"]

LEGIT_POOL = [
    "google.com", "github.com", "stackoverflow.com", "microsoft.com",
    "apple.com", "amazon.com", "cloudflare.com", "wikipedia.org",
    "youtube.com", "twitter.com", "linkedin.com", "reddit.com",
    "baidu.com", "taobao.com", "qq.com", "weibo.com",
    "netflix.com", "spotify.com", "zoom.us", "slack.com",
    "docker.com", "npmjs.com", "pypi.org", "golang.org",
    "ubuntu.com", "debian.org", "archlinux.org", "fedoraproject.org",
    "elastic.co", "grafana.com", "prometheus.io", "kafka.apache.org",
]

# 源 IP 池 — 4 个子网，每子网 50 个 IP
SRC_IP_SUBNETS = ["192.168.1", "10.0.0", "172.16.5", "10.10.20"]
SRC_IPS = [f"{subnet}.{i}" for subnet in SRC_IP_SUBNETS for i in range(10, 60)]

QUERY_TYPES = ["A", "AAAA", "MX", "TXT"]
QUERY_TYPE_WEIGHTS = [0.70, 0.15, 0.10, 0.05]


def generate_random_dga() -> str:
    """生成随机 DGA 域名：8-25 位字母数字 + 随机 TLD"""
    length = random.randint(8, 25)
    name = "".join(random.choices(string.ascii_lowercase + string.digits, k=length))
    return name + random.choice(DGA_TLDS)


def _hex_str(n: int) -> str:
    return "".join(random.choices("0123456789abcdef", k=n))


def _alpha_str(n: int) -> str:
    return "".join(random.choices(string.ascii_lowercase, k=n))


def _alnum_str(n: int) -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))


def _consonant_str(n: int) -> str:
    consonants = "bcdfghjklmnpqrstvwxyz"
    return "".join(random.choices(consonants, k=n))


DGA_FAMILY_GENERATORS: dict[str, Any] = {
    "qakbot": lambda: _hex_str(random.randint(12, 16)) + random.choice([".com", ".net"]),
    "necurs": lambda: _consonant_str(random.randint(15, 21)) + random.choice([".pw", ".top", ".club"]),
    "conficker": lambda: _alpha_str(random.randint(8, 12)) + random.choice([".info", ".org", ".net"]),
    "suppobox": lambda: _alnum_str(random.randint(10, 18)) + ".com",
    "ramnit": lambda: _alpha_str(random.randint(12, 20)) + random.choice([".eu", ".com"]),
}


def generate_family_dga(family: str) -> str:
    """按 DGA 家族模式生成域名"""
    gen = DGA_FAMILY_GENERATORS.get(family)
    if gen:
        return gen()
    return generate_random_dga()


def pick_legit_domain() -> str:
    return random.choice(LEGIT_POOL)


def build_message(domain: str, src_ip: str, query_type: str) -> dict[str, str]:
    """构建 DNS 查询日志消息，匹配 DNSParserNode 期望格式"""
    return {
        "query_name": domain,
        "src_ip": src_ip,
        "query_type": query_type,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TrafficConfig:
    batch_size: int = 10
    interval: float = 2.0
    dga_ratio: float = 0.3
    bootstrap_servers: str = "localhost:9094"
    topic: str = "dns-query-logs"
    duration: int = 0           # 0 = 无限
    burst_probability: float = 0.1
    burst_multiplier: int = 5
    gateway_url: str = ""       # 可选：同时调用 Gateway 评分


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

@dataclass
class Stats:
    total_sent: int = 0
    total_dga: int = 0
    total_legit: int = 0
    total_errors: int = 0
    rounds: int = 0
    start_time: float = field(default_factory=time.monotonic)
    _last_report: float = field(default_factory=time.monotonic)

    def log_round(self, dga: int, legit: int, errors: int, is_burst: bool) -> None:
        self.total_dga += dga
        self.total_legit += legit
        self.total_errors += errors
        self.total_sent += dga + legit
        self.rounds += 1
        now_str = datetime.now().strftime("%H:%M:%S")
        burst_tag = " [BURST]" if is_burst else ""
        print(
            f"  [{now_str}] Round {self.rounds}{burst_tag}: "
            f"sent={dga + legit} (dga={dga}, legit={legit}) "
            f"errors={errors} | cumulative={self.total_sent}",
            flush=True,
        )
        self._periodic_summary()

    def _periodic_summary(self) -> None:
        now = time.monotonic()
        if now - self._last_report < 30:
            return
        self._last_report = now
        elapsed = now - self.start_time
        rate = self.total_sent / elapsed if elapsed > 0 else 0
        print(
            f"\n  --- 统计 ({elapsed:.0f}s) ---  "
            f"总计={self.total_sent}  DGA={self.total_dga}  "
            f"正常={self.total_legit}  错误={self.total_errors}  "
            f"速率={rate:.1f} msg/s\n",
            flush=True,
        )

    def final_report(self) -> None:
        elapsed = time.monotonic() - self.start_time
        rate = self.total_sent / elapsed if elapsed > 0 else 0
        print(f"\n{'=' * 55}")
        print(f"  模拟结束")
        print(f"  轮次: {self.rounds}  耗时: {elapsed:.1f}s")
        print(f"  总计: {self.total_sent}  DGA: {self.total_dga}  正常: {self.total_legit}")
        print(f"  错误: {self.total_errors}  速率: {rate:.1f} msg/s")
        print(f"{'=' * 55}\n")


# ---------------------------------------------------------------------------
# Shutdown signal
# ---------------------------------------------------------------------------

_shutdown = asyncio.Event()


def _handle_signal(sig: int, _frame: Any) -> None:
    print(f"\n  收到 {signal.Signals(sig).name}，正在停止...")
    _shutdown.set()


# ---------------------------------------------------------------------------
# Optional business scoring
# ---------------------------------------------------------------------------

async def _score_via_gateway(gateway_url: str, domains: list[str]) -> None:
    """可选：同时通过 Gateway 评分（写入 ES + StarRocks + Redis）"""
    if not gateway_url:
        return
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(f"{gateway_url}/api/score", json={"domains": domains})
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

async def run_simulator(config: TrafficConfig) -> None:
    from aiokafka import AIOKafkaProducer

    producer = AIOKafkaProducer(
        bootstrap_servers=config.bootstrap_servers,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
    )
    await producer.start()
    stats = Stats()

    families = list(DGA_FAMILY_GENERATORS.keys())

    print(f"\n  Kafka producer 已连接: {config.bootstrap_servers}")
    print(f"  Topic: {config.topic}  批次: {config.batch_size}  间隔: {config.interval}s")
    print(f"  DGA 占比: {config.dga_ratio:.0%}  Burst 概率: {config.burst_probability:.0%}\n")

    try:
        while not _shutdown.is_set():
            # 判断是否 burst
            is_burst = random.random() < config.burst_probability
            batch = config.batch_size * config.burst_multiplier if is_burst else config.batch_size

            dga_count = max(1, int(batch * config.dga_ratio))
            legit_count = batch - dga_count

            messages: list[dict[str, str]] = []
            gateway_domains: list[str] = []

            # 生成 DGA 域名
            for _ in range(dga_count):
                if random.random() < 0.7:
                    domain = generate_random_dga()
                else:
                    domain = generate_family_dga(random.choice(families))
                src_ip = random.choice(SRC_IPS)
                qtype = random.choices(QUERY_TYPES, weights=QUERY_TYPE_WEIGHTS, k=1)[0]
                messages.append(build_message(domain, src_ip, qtype))
                gateway_domains.append(domain)

            # 生成正常域名
            for _ in range(legit_count):
                domain = pick_legit_domain()
                src_ip = random.choice(SRC_IPS)
                qtype = random.choices(QUERY_TYPES, weights=QUERY_TYPE_WEIGHTS, k=1)[0]
                messages.append(build_message(domain, src_ip, qtype))
                gateway_domains.append(domain)

            random.shuffle(messages)

            # 发送到 Kafka
            errors = 0
            for msg in messages:
                try:
                    await producer.send_and_wait(config.topic, msg)
                except Exception:
                    errors += 1

            stats.log_round(dga_count, legit_count, errors, is_burst)

            # 可选 Gateway 评分
            if config.gateway_url:
                await _score_via_gateway(config.gateway_url, gateway_domains[:20])

            # 检查时长限制
            if config.duration > 0:
                elapsed = time.monotonic() - stats.start_time
                if elapsed >= config.duration:
                    break

            # 带抖动的间隔
            jitter = config.interval * random.uniform(0.7, 1.3)
            try:
                await asyncio.wait_for(_shutdown.wait(), timeout=jitter)
                break  # shutdown signaled
            except asyncio.TimeoutError:
                pass
    finally:
        stats.final_report()
        await producer.stop()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> TrafficConfig:
    p = argparse.ArgumentParser(
        description="DGA DNS 查询日志流量模拟器 — 直连 Kafka 持续生成 DNS 日志",
    )
    p.add_argument("--batch-size", type=int, default=10, help="每轮发送域名数 (default: 10)")
    p.add_argument("--interval", type=float, default=2.0, help="轮次间隔秒数 (default: 2.0)")
    p.add_argument("--dga-ratio", type=float, default=0.3, help="DGA 域名占比 0.0-1.0 (default: 0.3)")
    p.add_argument("--bootstrap-servers", default="localhost:9094", help="Kafka bootstrap (default: localhost:9094)")
    p.add_argument("--topic", default="dns-query-logs", help="Kafka topic (default: dns-query-logs)")
    p.add_argument("--duration", type=int, default=0, help="运行时长秒数, 0=无限 (default: 0)")
    p.add_argument("--burst-prob", type=float, default=0.1, help="Burst 概率 (default: 0.1)")
    p.add_argument("--burst-mult", type=int, default=5, help="Burst 倍数 (default: 5)")
    p.add_argument("--business", default="", help="可选 Gateway URL, 同时评分 (e.g. http://localhost:8000)")
    args = p.parse_args()
    return TrafficConfig(
        batch_size=args.batch_size,
        interval=args.interval,
        dga_ratio=args.dga_ratio,
        bootstrap_servers=args.bootstrap_servers,
        topic=args.topic,
        duration=args.duration,
        burst_probability=args.burst_prob,
        burst_multiplier=args.burst_mult,
        gateway_url=args.gateway,
    )


def main() -> None:
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    config = parse_args()
    dur = f"{config.duration}s" if config.duration > 0 else "无限"

    print("=" * 55)
    print("  DGA DNS 查询日志流量模拟器")
    print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  运行时长: {dur}  按 Ctrl+C 停止")
    print("=" * 55)

    asyncio.run(run_simulator(config))


if __name__ == "__main__":
    main()
