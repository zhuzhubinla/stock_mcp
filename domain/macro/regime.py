"""Macro Regime：宏观四态检测与因子乘数（设计文档 §11 + macro/regime.py）

状态：goldilocks / overheating / recession / stagflation / neutral
V1 用 INDPRO（增长）+ CPI（通胀）的同比与方向启发式判定，
专家先验乘数表：不同 regime 下各因子的影响力缩放。
"""
import sys
import math

sys.path.append("/home/admin/stock_agent")

from data.repositories import macro_repo
from domain.macro.signal import _load_series, _stats

# 各 regime 下因子乘数（未列出 = 1.0）
REGIME_FACTOR_MULTIPLIERS = {
    "goldilocks":   {"GROWTH": 1.2, "FED_POLICY": 1.1, "INFLATION": 0.5,
                     "RATES": 0.7, "RISK": 1.1, "AI_CAPEX": 1.2},
    "overheating":  {"INFLATION": 1.3, "FED_POLICY": 1.3, "RATES": 1.3,
                     "GROWTH": 1.1, "RISK": 1.1, "COMMODITY": 1.2},
    "recession":    {"GROWTH": 1.4, "LABOR": 1.4, "FED_POLICY": 1.3,
                     "LIQUIDITY": 1.2, "RATES": 1.1, "RISK": 0.8},
    "stagflation":  {"COMMODITY": 1.4, "INFLATION": 1.4, "RATES": 1.2,
                     "RISK": 1.3, "FED_POLICY": 1.1, "GROWTH": 0.6},
    "neutral":      {},
}


def regime_factor_multiplier(regime, factor_code):
    return float(REGIME_FACTOR_MULTIPLIERS.get(regime or "neutral", {}).get(factor_code, 1.0))


def _yoy_now(pts):
    """最新同比 % 与 6 期前同比 %（月度序列）"""
    if len(pts) < 19:
        return None, None
    yoy = [(pts[i][1] / pts[i - 12][1] - 1) * 100 for i in range(12, len(pts))]
    return yoy[-1], yoy[-7] if len(yoy) >= 7 else None


def detect_macro_regime(persist=True, as_of=None):
    """检测宏观 regime：增长 vs 通胀 四象限 + 方向"""
    ind = _load_series("industrial_production", as_of=as_of)
    cpi = _load_series("cpi", as_of=as_of)
    growth_yoy, growth_prev = _yoy_now(ind)
    infl_yoy, infl_prev = _yoy_now(cpi)

    if growth_yoy is None or infl_yoy is None:
        regime, conf = "neutral", 0.3
    else:
        g_rising = growth_prev is None or growth_yoy >= growth_prev - 0.2
        i_rising = infl_prev is None or infl_yoy > infl_prev + 0.1
        g_strong = growth_yoy > 0.5
        i_high = infl_yoy > 3.0

        if not g_strong and i_rising and i_high:
            regime, conf = "stagflation", 0.7
        elif g_strong and i_rising and i_high:
            regime, conf = "overheating", 0.7
        elif not g_strong and not i_rising:
            regime, conf = "recession", 0.6
        elif g_strong and not i_rising:
            regime, conf = "goldilocks", 0.65
        else:
            regime, conf = "neutral", 0.5

    detail = {"growth_yoy": round(growth_yoy, 3) if growth_yoy is not None else None,
              "inflation_yoy": round(infl_yoy, 3) if infl_yoy is not None else None,
              "growth_rising": growth_prev is not None and growth_yoy >= growth_prev - 0.2,
              "inflation_rising": infl_prev is not None and infl_yoy > infl_prev + 0.1}
    if persist:
        macro_repo.upsert_macro_regime(
            regime, growth_yoy or 0, infl_yoy or 0,
            bool(detail["growth_rising"]), bool(detail["inflation_rising"]),
            conf, detail=detail)
    return {"regime": regime, "confidence": conf, "detail": detail,
            "growth_yoy": growth_yoy, "inflation_yoy": infl_yoy}
