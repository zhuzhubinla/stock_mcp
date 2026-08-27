"""Driver Engine：行业因子/指标 → 公司财务驱动映射
Agent 流程第 7 步。核心：把行业变化转换为可解释的公司财务变化，
而不是简单 industry_growth × company_revenue（文档第 10 节）。
v2：factor.impact_direction / indicator.indicator_code / supply_demand.supply_demand_gap
"""
import sys
sys.path.append("/home/admin/stock_agent")

from data.repositories import graph_repo, factor_repo


def industry_factors(industry_id=None, factor_type=None):
    """行业驱动因子列表"""
    rows = factor_repo.get_industry_factors(industry_id=industry_id, factor_type=factor_type)
    return [{
        "factor_id": r["id"], "factor": r["name"], "type": r["factor_type"],
        "impact_direction": r["impact_direction"], "description": r["description"],
        "importance": float(r["importance"]) if r["importance"] is not None else None,
        "unit": r["unit"],
        "industry": r["industry_name"], "industry_id": r["industry_id"],
    } for r in rows]


def indicators(industry_id=None, indicator_code=None, symbol=None, indicator_name=None):
    """行业指标（出货量/渗透率/ASP/产能/库存）"""
    rows = factor_repo.get_indicators(industry_id=industry_id,
                                      indicator_code=indicator_code, symbol=symbol,
                                      indicator_name=indicator_name)
    return [{
        "indicator_id": r["id"], "indicator": r["indicator_name"],
        "indicator_code": r["indicator_code"],
        "value": float(r["value"]) if r["value"] is not None else None,
        "unit": r["unit"], "period": str(r["period"]) if r["period"] else None,
        "industry": r["industry_name"], "industry_id": r["industry_id"],
    } for r in rows]


def supply_demand(industry_id=None):
    """供需：产能/产量/需求/库存/利用率/缺口"""
    rows = factor_repo.get_supply_demand(industry_id=industry_id)
    return [{
        "period": str(r["period"]) if r["period"] else None,
        "capacity": float(r["capacity"]) if r["capacity"] is not None else None,
        "production": float(r["production"]) if r["production"] is not None else None,
        "demand": float(r["demand"]) if r["demand"] is not None else None,
        "inventory": float(r["inventory"]) if r["inventory"] is not None else None,
        "utilization_rate": float(r["utilization_rate"]) if r["utilization_rate"] is not None else None,
        "supply_demand_gap": float(r["supply_demand_gap"]) if r["supply_demand_gap"] is not None else None,
        "unit": r["unit"],
        "industry": r["industry_name"],
    } for r in rows]


def drivers(symbol=None, company_id=None, impact_metric=None):
    """公司财务驱动（financial_driver 表）"""
    rows = factor_repo.get_financial_drivers(symbol=symbol, company_id=company_id,
                                             impact_metric=impact_metric)
    return [{
        "driver_id": r["id"], "company": r["company_name"], "symbol": r["stock_symbol"],
        "segment": r.get("segment_name"), "driver_type": r["impact_metric"],
        "driver": r["driver_name"], "impact_metric": r["impact_metric"],
        "impact_direction": r["impact_direction"],
        "coefficient": float(r["impact_coefficient"]) if r["impact_coefficient"] is not None else None,
        "elasticity": float(r["elasticity"]) if r["elasticity"] is not None else None,
        "base_value": float(r["base_value"]) if r["base_value"] is not None else None,
        "forecast_value": float(r["forecast_value"]) if r["forecast_value"] is not None else None,
        "confidence": float(r["confidence"]) if r["confidence"] is not None else None,
        "source_indicator": r.get("source_indicator"),
        "indicator_code": r.get("indicator_code"),
    } for r in rows]


def run_indicator_impact(indicator_id, new_value=None):
    """指标变动 → 关联公司财务影响（Factor-First 核心）
    按 impact_coefficient 计算：impact_pct = (new/base - 1) * coefficient
    new_value 缺省时取指标最新一期值。
    """
    rows = factor_repo.get_driver_by_indicator(indicator_id)
    if not rows:
        return {"indicator_id": indicator_id, "impacts": [], "count": 0}
    # 指标最新值（new_value 缺省时用）
    from data.repositories import factor_repo as _fr
    if new_value is None:
        inds = _fr.get_indicators(industry_id=None, indicator_code=None)
        latest = None
        for r in inds:
            if r["id"] == indicator_id:
                latest = r
        if latest is not None and latest.get("value") is not None:
            new_value = float(latest["value"])
    out = []
    for r in rows:
        base = r["base_value"]
        growth = None
        if new_value is not None and base:
            growth = (float(new_value) - float(base)) / float(base)
        impact = None
        if growth is not None and r["impact_coefficient"] is not None:
            impact = growth * float(r["impact_coefficient"])
        out.append({
            "driver_id": r["id"], "company": r["company_name"], "symbol": r["stock_symbol"],
            "segment": r.get("segment_name"), "driver": r["driver_name"],
            "impact_metric": r["impact_metric"],
            "impact_direction": r["impact_direction"],
            "indicator_growth_pct": round(growth * 100, 2) if growth is not None else None,
            "metric_impact_pct": round(impact * 100, 2) if impact is not None else None,
        })
    return {"indicator_id": indicator_id, "impacts": out, "count": len(out)}
