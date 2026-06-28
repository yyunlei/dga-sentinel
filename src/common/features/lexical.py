"""
词法特征提取器 — 从 predict.py bin_predict 类重构而来
提取域名的统计特征：长度、字符比例、最长子串等
"""

from __future__ import annotations

import re
import math
from collections import Counter

import numpy as np
import pandas as pd

# 22 个词法特征列（顺序固定，训练与推理共享）
LEXICAL_COLUMNS = [
    "N", "LCc", "LCv", "LCn",
    "L_tld", "Rc_tld", "Rv_tld", "Rn_tld", "Rl_tld", "Rs_tld",
    "L_sld", "Rc_sld", "Rv_sld", "Rn_sld", "Rl_sld", "Rs_sld",
    "L_sub", "Rc_sub", "Rv_sub", "Rn_sub", "Rl_sub", "Rs_sub",
]


def count_char_features(domain: str) -> tuple[int, float, float, float, float, float]:
    """计算域名字符级特征"""
    L = len(domain)
    if L == 0:
        return 0, 0.0, 0.0, 0.0, 0.0, 0.0

    consonant_count = sum(1 for c in domain if c in "bcdfghjklmnpqrstvwxyz")
    vowel_count = sum(1 for c in domain if c in "aeiou")
    letter_count = sum(1 for c in domain if c.isalpha())
    number_count = sum(1 for c in domain if c.isdigit())
    symbolic_count = sum(1 for c in domain if not c.isalnum())

    return (
        L,
        consonant_count / L,  # Rc
        vowel_count / L,      # Rv
        number_count / L,     # Rn
        letter_count / L,     # Rl
        symbolic_count / L,   # Rs
    )


def extract_lexical_features(domain: str) -> dict[str, float]:
    """
    提取完整的词法特征向量（22 维，与原 bin_predict.calc_custom_features 一致）
    """
    parts = domain.split(".")
    subdomain = ".".join(parts[:-2]) if len(parts) >= 3 else ""
    sld = parts[-2] if len(parts) >= 2 else parts[0]
    tld = parts[-1] if len(parts) >= 2 else ""

    N = 3 if subdomain else 2

    # 最长连续子串
    consonants = re.findall(r"[^aeiou\d\s\W]+", domain)
    LCc = max((len(c) for c in consonants), default=0)
    numbers = re.findall(r"\d+", domain)
    LCn = max((len(n) for n in numbers), default=0)
    vowels = re.findall(r"[aeiou]+", domain)
    LCv = max((len(v) for v in vowels), default=0)

    L_tld, Rc_tld, Rv_tld, Rn_tld, Rl_tld, Rs_tld = count_char_features(tld)
    L_sld, Rc_sld, Rv_sld, Rn_sld, Rl_sld, Rs_sld = count_char_features(sld)
    if subdomain:
        L_sub, Rc_sub, Rv_sub, Rn_sub, Rl_sub, Rs_sub = count_char_features(subdomain)
    else:
        L_sub = Rc_sub = Rv_sub = Rn_sub = Rl_sub = Rs_sub = 0.0

    return {
        "N": N, "LCc": LCc, "LCv": LCv, "LCn": LCn,
        "L_tld": L_tld, "Rc_tld": Rc_tld, "Rv_tld": Rv_tld,
        "Rn_tld": Rn_tld, "Rl_tld": Rl_tld, "Rs_tld": Rs_tld,
        "L_sld": L_sld, "Rc_sld": Rc_sld, "Rv_sld": Rv_sld,
        "Rn_sld": Rn_sld, "Rl_sld": Rl_sld, "Rs_sld": Rs_sld,
        "L_sub": L_sub, "Rc_sub": Rc_sub, "Rv_sub": Rv_sub,
        "Rn_sub": Rn_sub, "Rl_sub": Rl_sub, "Rs_sub": Rs_sub,
    }
