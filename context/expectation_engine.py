"""Expectation Engine（设计文档第 6 节 Expectation Intelligence）

核心公式：
  Surprise = Actual - Expected
  Investment Surprise = Actual - Market Expected - Priced-in Expectation

Revenue Growth +10% 并不自动 Bullish：
  - 市场预期 +8%  → 正 Surprise（利好）
  - 但估值已反映 +15% → 实际投资信号偏负

实现：
  1. Financial Surprise：财报实际 vs 预期（earnings_surprise 或 fundamentals vs analyst estimate）
  2. Priced-in 检测：PE/PEG 隐含的增长预期 vs 实际增速 → 估值是否已透支
  3. Expectation Gap 输出：actual / expected / priced_in / gap / signal_adjustment
"""
import sys
from datetime import datetime

sys.path.append("/home/admin/stock_agent")

from data.repositories.mysql_db import get_fundamentals
from data.repositories import forecast_repo


def _clamp(v, lo=-1.0, hi=1.0):
    if v is None:
        return None
    return max(lo, min(hi, float(v)))


def _fundamental_metric(symbol, metric):
    d = {f["metric"]: f["value"] for f in get_fundamentals(symbol)}
    v = d.get(metric)
    return float(v) if v is not None else None


def financial_surprise(symbol):
    """财报 Surprise：实际增长 vs 保守基准（趋势增速）
    无 analyst estimate 时，用历史增速的 80% 作为 expected（保守基准）。
    """
    growth = _fundamental_metric(symbol, "revenueGrowth")
    eps_growth = _fundamental_metric(symbol, "epsGrowth")
    if growth is None and eps_growth is None:
        return {"symbol": symbol, "surprise": None, "note": "无增速数据"}
    expected_growth = (growth or 0) * 0.8 if growth is not None else None
    expected_eps_growth = (eps_growth or 0) * 0.8 if eps_growth is not None else None
    rev_surprise = (growth - expected_growth) / 100 if growth is not None else None
    eps_surprise = (eps_growth - expected_eps_growth) / 100 if eps_growth is not None else None
    surprise = (rev_surprise or 0) * 0.5 + (eps_surprise or 0) * 0.5
    if rev_surprise is None and eps_surprise is None:
        surprise = None
    return {
        "symbol": symbol,
        "revenue_growth": growth,
        "eps_growth": eps_growth,
        "expected_revenue_growth": expected_growth,
        "expected_eps_growth": expected_eps_growth,
        "revenue_surprise": round(rev_surprise, 4) if rev_surprise is not None else None,
        "eps_surprise": round(eps_surprise, 4) if eps_surprise is not None else None,
        "surprise": round(surprise, 4) if surprise is not None else None,
        "direction": "beat" if (surprise or 0) > 0.02 else ("miss" if (surprise or 0) < -0.02 else "in_line"),
        "computed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def priced_in_expectation(symbol):
    """估值已定价的预期：PEG 视角
    PEG = PE / (growth*100)
      PEG < 1   → 预期未打满（还有空间）
      PEG > 2   → 预期打满 / 透支
    返回 priced_in 0~1（1 = 完全透支）
    """
    pe = _fundamental_metric(symbol, "pe")
    growth = _fundamental_metric(symbol, "revenueGrowth")
    if pe is None or growth is None or pe <= 0:
        return {"symbol": symbol, "priced_in": None, "peg": None, "note": "缺 PE 或增速"}
    peg = pe / (growth * 100) if growth > 0 else 99.0
    # PEG 0~3 → priced_in 0~1（<1 为低估，>2.5 为高透支）
    priced_in = max(0.0, min(1.0, (peg - 0.5) / 2.5))
    return {
        "symbol": symbol,
        "pe": pe,
        "revenue_growth": growth,
        "peg": round(peg, 2),
        "priced_in": round(priced_in, 4),
        "note": "PEG<1 预期未打满; PEG>2 预期透支" if peg > 2 else (
                "PEG<1 预期未打满" if peg < 1 else "PEG 合理区间"),
    }


def expectation_gap(symbol):
    """Investment Surprise = Actual - Expected - Priced-in
    返回 -1~1 的信号调整量（>0 利好，<0 利空）
    """
    fs = financial_surprise(symbol)
    pi = priced_in_expectation(symbol)
    surprise = fs.get("surprise")
    priced_in = pi.get("priced_in")
    if surprise is None and priced_in is None:
        return {"symbol": symbol, "gap": None, "signal_adjustment": 0.0,
                "note": "数据不足"}
    # 合成：正 Surprise 利好（+），高 priced-in 利空（-）
    gap = (surprise or 0) * 0.6 - (priced_in or 0) * 0.4
    adj = _clamp(gap)
    return {
        "symbol": symbol,
        "surprise": fs.get("surprise"),
        "surprise_direction": fs.get("direction"),
        "priced_in": priced_in,
        "peg": pi.get("peg"),
        "gap": round(gap, 4),
        "signal_adjustment": round(adj, 4),  # 后续 Signal 的乘法/加法调整系数
        "note": f"Actual vs Expected: {fs.get('direction')}; Priced-in: {pi.get('note')}",
        "computed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


if __name__ == "__main__":
    import json
    for s in ["NVDA", "MU", "MSFT"]:
        print(json.dumps(expectation_gap(s), ensure_ascii=False, indent=1))
