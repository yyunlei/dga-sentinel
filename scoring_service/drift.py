"""
数据漂移检测 — 监控特征分布变化 + 告警通知 (Phase 2)
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from typing import Any

from shared.observability import get_logger

logger = get_logger(__name__)

# 漂移分级阈值（Population Stability Index）
DRIFT_THRESHOLD_WARN = 0.10   # 轻微漂移
DRIFT_THRESHOLD_ALERT = 0.25  # 显著漂移 → 告警 + 写 PG

# 同一 feature 的告警冷却期（避免每次 check_drift 都写一条 PG）
DRIFT_PG_COOLDOWN_HOURS = 6

# Prometheus 漂移指标（延迟导入避免循环）
_drift_gauge = None
_feedback_counter = None
_drift_crossings = None


def _get_drift_gauge():
    global _drift_gauge
    if _drift_gauge is None:
        from prometheus_client import Gauge
        _drift_gauge = Gauge(
            "dga_data_drift_score",
            "Feature distribution drift score (PSI)",
            ["feature_name"],
        )
    return _drift_gauge


def _get_drift_crossings_counter():
    """每次 PSI 越过 ALERT 阈值时计数 +1，用于 Grafana / Alertmanager 路由。"""
    global _drift_crossings
    if _drift_crossings is None:
        from prometheus_client import Counter
        _drift_crossings = Counter(
            "dga_data_drift_crossings_total",
            "Count of times a feature's PSI crossed the alert threshold",
            ["feature_name"],
        )
    return _drift_crossings


def _get_feedback_counter():
    global _feedback_counter
    if _feedback_counter is None:
        from prometheus_client import Counter
        _feedback_counter = Counter(
            "dga_feedback_total",
            "Annotation feedback count",
            ["label"],
        )
    return _feedback_counter


class DriftMonitor:
    """
    特征分布漂移检测器
    维护滑动窗口内的特征统计，与基线对比计算 PSI
    """

    def __init__(self, window_size: int = 1000):
        self.window_size = window_size
        self._window: list[dict[str, float]] = []
        self._baseline: dict[str, list[float]] | None = None

    def set_baseline(self, samples: list[dict[str, float]]) -> None:
        """设置特征分布基线"""
        self._baseline = defaultdict(list)
        for s in samples:
            for k, v in s.items():
                self._baseline[k].append(v)
        logger.info("drift_baseline_set", n_samples=len(samples))

    def record(self, features: dict[str, float]) -> None:
        """记录一条特征到滑动窗口"""
        self._window.append(features)
        if len(self._window) > self.window_size:
            self._window = self._window[-self.window_size:]

    def check_drift(self) -> dict[str, float]:
        """
        计算当前窗口 vs 基线的 PSI（Population Stability Index）。

        分级:
          PSI < 0.10            → 无漂移
          0.10 ≤ PSI < 0.25     → 轻微漂移（仅记录 gauge）
          PSI ≥ 0.25            → 显著漂移：log warning + 计数器 +1

        指标:
          dga_data_drift_score{feature_name}        Gauge（每次写）
          dga_data_drift_crossings_total{feature_name}  Counter（仅 ALERT 越界时 +1）
        """
        if not self._baseline or len(self._window) < 100:
            return {}

        drift_scores: dict[str, float] = {}
        gauge = _get_drift_gauge()
        crossings = _get_drift_crossings_counter()

        for feature_name, baseline_values in self._baseline.items():
            current_values = [s.get(feature_name, 0.0) for s in self._window]
            psi = self._compute_psi(baseline_values, current_values)
            drift_scores[feature_name] = psi
            gauge.labels(feature_name=feature_name).set(psi)

            if psi >= DRIFT_THRESHOLD_ALERT:
                crossings.labels(feature_name=feature_name).inc()
                logger.warning(
                    "data_drift_alert",
                    feature=feature_name,
                    psi=round(psi, 4),
                    threshold=DRIFT_THRESHOLD_ALERT,
                    severity="ALERT",
                    suggested_action="review baseline; consider retraining or rebaseline",
                )
            elif psi >= DRIFT_THRESHOLD_WARN:
                logger.info(
                    "data_drift_warn",
                    feature=feature_name,
                    psi=round(psi, 4),
                    severity="WARN",
                )

        return drift_scores

    async def persist_drift_alerts(
        self,
        pg_pool: Any,
        scores: dict[str, float] | None = None,
    ) -> int:
        """对 PSI ≥ ALERT 阈值的 feature，把告警事件写入 ``pipeline_operations``。

        - operation = ``drift_alert``，status = ``pending``
        - 同一 feature 在 ``DRIFT_PG_COOLDOWN_HOURS`` 内只写一条（防刷屏）
        - 推荐人接 dispatch retraining job 或 rebaseline

        Args:
            pg_pool: asyncpg.Pool / Connection
            scores: 可选；若 None 则自动调 ``check_drift()`` 取最新分数

        Returns:
            实际写入的事件数（可能 < 越界数，因为 cooldown 去重）
        """
        if scores is None:
            scores = self.check_drift()
        if not scores:
            return 0

        written = 0
        for feature_name, psi in scores.items():
            if psi < DRIFT_THRESHOLD_ALERT:
                continue
            existing = await pg_pool.fetchval(
                f"""
                SELECT id FROM pipeline_operations
                WHERE operation = 'drift_alert'
                  AND status = 'pending'
                  AND detail->>'feature' = $1
                  AND created_at > NOW() - INTERVAL '{DRIFT_PG_COOLDOWN_HOURS} hours'
                LIMIT 1
                """,
                feature_name,
            )
            if existing:
                continue

            await pg_pool.execute(
                """
                INSERT INTO pipeline_operations (pipeline_id, operation, operator, status, detail)
                VALUES ($1, $2, $3, $4, $5::jsonb)
                """,
                "default",
                "drift_alert",
                "drift-monitor",
                "pending",
                json.dumps({
                    "feature": feature_name,
                    "psi": round(psi, 4),
                    "threshold": DRIFT_THRESHOLD_ALERT,
                    "window_size": len(self._window),
                    "suggested_action": (
                        "trigger retraining pipeline OR rebaseline if drift is "
                        "expected (e.g. new domain TLD distribution)"
                    ),
                }),
            )
            written += 1
        return written

    @staticmethod
    def _compute_psi(expected: list[float], actual: list[float], bins: int = 10) -> float:
        """计算 PSI"""
        if not expected or not actual:
            return 0.0

        min_val = min(min(expected), min(actual))
        max_val = max(max(expected), max(actual))

        if max_val == min_val:
            return 0.0

        bin_edges = [min_val + i * (max_val - min_val) / bins for i in range(bins + 1)]

        def _bin_counts(values: list[float]) -> list[float]:
            counts = [0] * bins
            for v in values:
                idx = min(int((v - min_val) / (max_val - min_val) * bins), bins - 1)
                counts[idx] += 1
            total = len(values)
            return [(c / total) if total > 0 else 1e-6 for c in counts]

        expected_pct = _bin_counts(expected)
        actual_pct = _bin_counts(actual)

        psi = 0.0
        for e, a in zip(expected_pct, actual_pct):
            e = max(e, 1e-6)
            a = max(a, 1e-6)
            psi += (a - e) * math.log(a / e)

        return psi
