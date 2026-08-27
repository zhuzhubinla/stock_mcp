"""Factor-First：事件/因子驱动选股（文档第 15 节）
Factor → Industry → Companies → Financial Impact → Stock Ranking
"""
import sys
sys.path.append("/home/admin/stock_agent")

from intelligence.repositories import factor_repo
from intelligence.factor.engine import run_indicator_impact
from intelligence.industry.mapper import map_industry
from intelligence.analytics.calc import elasticity_score


def analyze_indicator(indicator_id=None, indicator_name=None, industry_id=None,
                      new_value=None):
    """指标变化 → 行业公司财务影响 → 弹性排名
    indicator_id 优先；否则按 indicator_name + industry_id 定位。
    """
    if not indicator_id:
        rows = factor_repo.get_indicators(industry_id=industry_id,
                                          indicator_name=indicator_name)
        if not rows:
            return {"error": f"指标不存在: {indicator_name} industry={industry_id}"}
        latest = sorted(rows, key=lambda r: r["period"] or "")[-1]
        indicator_id = latest["id"]

    # 1. 指标基本信息
    inds = factor_repo.get_indicators(industry_id=industry_id,
                                      indicator_name=indicator_name)
    # 2. 驱动影响（financial_driver 关联）
    result = run_indicator_impact(indicator_id, new_value=new_value)
    if not result["impacts"]:
        return {"error": "该指标未配置财务驱动映射（financial_driver）", "indicator_id": indicator_id}

    # 3. 弹性评分 + 排名
    ranked = elasticity_score(result["impacts"])
    return {
        "indicator_id": indicator_id,
        "indicator_name": inds[0]["indicator_name"] if inds else indicator_name,
        "new_value": new_value,
        "impacts": result["impacts"],
        "ranking": ranked,
        "count": len(ranked),
    }


def analyze_factor(factor_name, industry_id=None):
    """行业因子 → 关联指标 → 驱动影响"""
    rows = factor_repo.get_industry_factors(industry_id=industry_id)
    factors = [r for r in rows if r["name"] == factor_name]
    if not factors:
        return {"error": f"因子不存在: {factor_name}"}
    f = factors[0]
    inds = factor_repo.get_indicators(industry_id=f["industry_id"])
    return {
        "factor": f["name"], "type": f["factor_type"], "direction": f["direction"],
        "description": f["description"], "industry": f["industry_name"],
        "related_indicators": [{"id": i["id"], "name": i["indicator_name"],
                                "period": i["period"], "value": float(i["value"]) if i["value"] is not None else None}
                               for i in inds],
    }


def top_beneficiaries(indicator_id, new_value=None, top_n=10):
    """因子变化 → 受益/受损公司 Top N"""
    result = analyze_indicator(indicator_id, new_value=new_value)
    if "error" in result:
        return result
    return {"indicator": result["indicator_name"], "top": result["ranking"][:top_n],
            "count": result["count"]}
