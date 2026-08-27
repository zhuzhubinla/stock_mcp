"""Earnings：净利润/EPS 计算（Detailed Technical Design 第 21 节）
Net Income = Operating Profit + Non-operating Items - Tax
EPS = Net Income / Diluted Shares
"""
import sys
sys.path.append("/home/admin/stock_agent")


def net_income(operating_profit_value, non_operating=0.0, tax=0.0):
    """净利润 = 营业利润 + 营业外收支 - 税"""
    if operating_profit_value is None:
        return None
    return operating_profit_value + non_operating - tax


def eps(net_income_value, diluted_shares):
    """EPS = 净利润 / 摊薄股数"""
    if net_income_value is None or not diluted_shares:
        return None
    return net_income_value / diluted_shares


def eps_chain(operating_profit_value, diluted_shares, non_operating=0.0, tax=0.0):
    """营业利润 → 净利润 → EPS 全链"""
    ni = net_income(operating_profit_value, non_operating, tax)
    return {"net_income": ni, "eps": eps(ni, diluted_shares)}
