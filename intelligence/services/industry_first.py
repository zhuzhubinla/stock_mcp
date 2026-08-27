"""Industry-First：行业选股（文档第 15 节）
Industry → Factors → Forecast → Companies → Ranking
"""
import sys
sys.path.append("/home/admin/stock_agent")

from intelligence.industry.mapper import map_industry, industry_tree
from intelligence.factor.engine import industry_factors, indicators, supply_demand
from intelligence.repositories import forecast_repo
from intelligence.analytics.calc import elasticity_score


def list_industries():
    return industry_tree()


def analyze(industry_id=None, code=None, name=None, top_n=10):
    """行业全景 + 受益公司排名（按 暴露度 × 弹性）"""
    industry = None
    from intelligence.repositories import graph_repo
    industry = graph_repo.get_industry(industry_id=industry_id, code=code, name=name)
    if not industry:
        return {"error": f"行业不存在: {code or name or industry_id}"}

    # 1. 行业因子
    factors = industry_factors(industry_id=industry["id"])
    # 2. 行业指标
    inds = indicators(industry_id=industry["id"])
    # 3. 供需
    sd = supply_demand(industry_id=industry["id"])
    # 4. 行业预测
    forecasts = forecast_repo.get_industry_forecasts(industry_id=industry["id"])
    # 5. 受益公司
    comps = map_industry(industry_id=industry["id"])["companies"]

    # 弹性粗估：用行业指标最新值的同比作为统一弹性代理
    elastic = {}
    for c in comps:
        elastic[c["symbol"]] = round((c["exposure"] or 0) * 100, 1)
    ranked = sorted(comps, key=lambda x: elastic.get(x["symbol"], 0), reverse=True)[:top_n]
    for c in ranked:
        c["elasticity"] = elastic.get(c["symbol"])

    return {
        "industry": industry["name"], "code": industry["code"],
        "industry_id": industry["id"],
        "factors": factors,
        "indicators": inds,
        "supply_demand": sd,
        "forecasts": [{"indicator": f["indicator_name"], "period": f["period"],
                       "value": float(f["value"]) if f["value"] is not None else None,
                       "confidence": float(f["confidence"]) if f["confidence"] is not None else None}
                      for f in forecasts],
        "companies": ranked,
        "company_count": len(comps),
    }
