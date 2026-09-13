"""Macro Event：事件分级与因子相关性（设计文档 §12 + macro/event.py）

Event 修正：Normal=1.0 / Important=1.5 / Major=2.0，作用于相关因子。
"""
import sys

sys.path.append("/home/admin/stock_agent")

EVENT_LEVELS = {"normal": 1.0, "important": 1.5, "major": 2.0}

# 事件关键词 → 相关因子（事件日提高这些因子的传导权重）
EVENT_FACTOR_RELEVANCE = [
    (("nfp", "nonfarm", "payroll", "job", "unemployment", "claims", "labor"),
     ["LABOR", "FED_POLICY", "RATES"]),
    (("cpi", "pce", "inflation", "ppi", "deflator"),
     ["INFLATION", "FED_POLICY", "RATES"]),
    (("fomc", "fed", "powell", "rate cut", "rate hike"),
     ["FED_POLICY", "RATES"]),
    (("oil", "opec", "wti", "brent", "energy price"),
     ["COMMODITY", "INFLATION"]),
    (("gdp", "pmi", "retail sales", "growth"),
     ["GROWTH", "RATES"]),
    (("vix", "volatility", "credit spread", "risk-off"),
     ["RISK"]),
]


def event_level_multiplier(level):
    """事件级别乘数（默认 normal=1.0）"""
    return float(EVENT_LEVELS.get((level or "normal").lower(), 1.0))


def relevant_factors(event_key):
    """事件关键词命中的因子列表"""
    key = (event_key or "").lower()
    hits = []
    for kws, factors in EVENT_FACTOR_RELEVANCE:
        if any(k in key for k in kws):
            hits.extend(factors)
    return hits


def event_factor_multipliers(event_key=None, level="normal"):
    """{factor_code: 乘数}：相关因子 × 级别乘数，无关因子 1.0"""
    mul = event_level_multiplier(level)
    rel = relevant_factors(event_key)
    if mul == 1.0 or not rel:
        return {f: mul for f in rel}  # 无关因子走 1.0 默认
    return {f: mul for f in rel}
