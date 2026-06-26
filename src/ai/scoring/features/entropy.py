"""
熵特征提取器 — Shannon 熵 + 字符分布统计
"""

from __future__ import annotations

import math
from collections import Counter


def shannon_entropy(domain: str) -> float:
    """计算域名的 Shannon 信息熵"""
    if not domain:
        return 0.0
    freq = Counter(domain)
    length = len(domain)
    return -sum(
        (count / length) * math.log2(count / length)
        for count in freq.values()
    )


def char_class_entropy(domain: str) -> float:
    """计算字符类别（字母/数字/符号）的熵"""
    if not domain:
        return 0.0
    classes = []
    for c in domain:
        if c.isalpha():
            classes.append("alpha")
        elif c.isdigit():
            classes.append("digit")
        else:
            classes.append("symbol")
    freq = Counter(classes)
    length = len(classes)
    return -sum(
        (count / length) * math.log2(count / length)
        for count in freq.values()
    )


def extract_entropy_features(domain: str) -> dict[str, float]:
    """提取熵相关特征"""
    # 去掉 TLD 部分，只计算 SLD 的熵
    parts = domain.split(".")
    sld = parts[-2] if len(parts) >= 2 else parts[0]

    return {
        "entropy_full": shannon_entropy(domain),
        "entropy_sld": shannon_entropy(sld),
        "char_class_entropy": char_class_entropy(sld),
        "unique_char_ratio": len(set(sld)) / max(len(sld), 1),
    }
