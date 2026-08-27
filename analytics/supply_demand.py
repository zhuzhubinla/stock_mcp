"""Supply-Demand：供需缺口计算"""
"""Analytics：同比/环比/CAGR/供需缺口/弹性评分
对应文档第 13 节职责边界中的 Analytics 层。
"""
import sys
sys.path.append("/home/admin/stock_agent")


def gap_ratio(demand, production):
    """供需缺口率：缺口占需求比例"""
    if not demand:
        return None
    return round((demand - production) / demand * 100, 2) if production is not None else None


