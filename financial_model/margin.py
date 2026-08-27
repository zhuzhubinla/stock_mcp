"""Margin：毛利率/营业利润率计算（Detailed Technical Design 第 21 节）
Gross Profit = Revenue × Gross Margin
Operating Profit = Gross Profit - Operating Expense
"""
import sys
sys.path.append("/home/admin/stock_agent")


def gross_profit(revenue, gross_margin):
    """毛利 = 营收 × 毛利率"""
    if revenue is None or gross_margin is None:
        return None
    return revenue * gross_margin


def operating_profit(gross_profit_value, opex):
    """营业利润 = 毛利 - 运营费用"""
    if gross_profit_value is None or opex is None:
        return None
    return gross_profit_value - opex


def operating_margin(operating_profit_value, revenue):
    """营业利润率"""
    if operating_profit_value is None or not revenue:
        return None
    return operating_profit_value / revenue


def net_margin(net_income, revenue):
    """净利率"""
    if net_income is None or not revenue:
        return None
    return net_income / revenue


def segment_margin_chain(segment_revenue, segment_gross_margin, segment_opex=None):
    """单业务段：营收 → 毛利 → 营业利润 链条（分业务建模，再汇总到公司层）"""
    gp = gross_profit(segment_revenue, segment_gross_margin)
    op = operating_profit(gp, segment_opex) if segment_opex is not None else gp
    return {"revenue": segment_revenue, 
            "gross_profit": gp,
            "operating_profit": op,
            "gross_margin": segment_gross_margin}
