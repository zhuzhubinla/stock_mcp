"""FCF：自由现金流计算（Detailed Technical Design 第 21 节）
FCF = Operating Cash Flow - Capex；简化：FCF ≈ Net Income + D&A - Capex
"""
import sys
sys.path.append("/home/admin/stock_agent")


def fcf(net_income_value, depreciation=0.0, capex=0.0, working_capital_change=0.0):
    """自由现金流 = 净利润 + 折旧摊销 - 资本开支 ± 营运资本变动"""
    if net_income_value is None:
        return None
    return net_income_value + depreciation - capex - working_capital_change


def fcf_yield(fcf_value, market_cap):
    """自由现金流收益率"""
    if fcf_value is None or not market_cap:
        return None
    return fcf_value / market_cap
