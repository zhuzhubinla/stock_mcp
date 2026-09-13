"""Macro Factor 定义与专家参数（设计文档 §5/§13 + Python 架构 macro/factor.py）

符号约定（消除歧义，文档 §10 评审结论）：
  因子信号 +1 的含义见各因子 direction_note（如 RATES +1 = 收益率上行）。
  Exposure 的 sensitivity 约定：正值 = 因子上行利好该行业。
"""
import sys
sys.path.append("/home/admin/stock_agent")

MODEL_VERSION = "v1"

# 计算 horizon（文档 §13：1D-3D / 1W-4W / 3M-12M → 取代表档）
HORIZONS = ("1d", "1w", "1m", "3m")

# 因子信号数据源：factor → [(indicator_code, 权重, 模式)]
#   mom_yoy : 月频序列，对 12 期同比变化做滚动 z-score（避免 2022 高通胀污染窗口）
#   level_z : 日频序列，对水平值做滚动 z-score（均值回归型变量）
#   weight<0 : 反向（RISK 用 VIX，VIX 升 = 风险偏好降，故 -1）
# 无数据源的因子（LABOR/FED_POLICY/LIQUIDITY/DXY/AI_CAPEX）= 缺省中性 0，
# 经传导边或 scenario 输入激活。
SIGNAL_SPECS = {
    "GROWTH":     [("industrial_production", 0.7, "mom_yoy"),
                   ("consumer_sentiment", 0.3, "mom_yoy")],
    "INFLATION":  [("cpi", 1.0, "mom_yoy")],
    "RATES":      [("us10y_yield", 1.0, "level_z")],
    "RISK":       [("vix", -1.0, "level_z")],
    "COMMODITY":  [("wti_oil", 1.0, "level_z")],
    "FED_POLICY": [],
    "LABOR":      [],
    "LIQUIDITY":  [],
    "DXY":        [],
    "AI_CAPEX":   [],
}

# Horizon 修正（文档 §13 表格 → 数值化；未列出的因子取 1.0）
HORIZON_FACTOR_MULTIPLIERS = {
    # 高 Beta 成长、事件冲击：利率/风险定价最快
    "1d": {"RATES": 1.0, "RISK": 1.0, "FED_POLICY": 0.9, "INFLATION": 0.8,
           "COMMODITY": 0.7, "GROWTH": 0.5, "LABOR": 0.4, "LIQUIDITY": 0.3},
    # 事件驱动：NFP/CPI/FOMC 后 1 周定价
    "1w": {"LABOR": 1.0, "FED_POLICY": 1.0, "RATES": 1.0, "INFLATION": 0.9,
           "COMMODITY": 0.8, "RISK": 0.8, "GROWTH": 0.7, "LIQUIDITY": 0.5},
    # 预期重估：增长/就业/通胀
    "1m": {"GROWTH": 1.0, "LABOR": 1.0, "INFLATION": 0.9, "FED_POLICY": 0.9,
           "RATES": 0.8, "COMMODITY": 0.8, "RISK": 0.7, "LIQUIDITY": 0.8},
    # 基本面传导：经济周期/Fed/流动性/CapEx
    "3m": {"GROWTH": 1.1, "LIQUIDITY": 1.1, "LABOR": 0.9, "FED_POLICY": 1.0,
           "INFLATION": 1.0, "RATES": 0.7, "COMMODITY": 0.9, "RISK": 0.6},
}

# 行业宏观分 → 预期收益%（启发式占位，正分=顺风；待 Phase 8 IC 校准替换）
HORIZON_RETURN_SCALE = {"1d": 1.0, "1w": 2.0, "1m": 3.5, "3m": 7.0}


def horizon_multiplier(horizon, factor_code):
    """文档 §13 Horizon 修正：horizon × factor → 乘数，未配置取 1.0"""
    table = HORIZON_FACTOR_MULTIPLIERS.get(horizon, {})
    return float(table.get(factor_code, 1.0))
