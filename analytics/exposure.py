"""Exposure：暴露度 × 弹性评分"""
"""Analytics：同比/环比/CAGR/供需缺口/弹性评分
对应文档第 13 节职责边界中的 Analytics 层。
"""
import sys
sys.path.append("/home/admin/stock_agent")


def elasticity_score(impacts):
    """
    弹性评分：对 Factor-First 的驱动影响排序
    按 metric_impact_pct 绝对值加权（revenue 权1.0 / eps 权1.5）
    """
    scored = []
    for im in impacts:
        pct = im.get("metric_impact_pct")
        if pct is None:
            continue
        metric = im.get("impact_metric") or "revenue"
        w = 1.5 if metric in ("eps", "fcf") else 1.0
        scored.append({**im, "elasticity": round(abs(pct) * w, 2)})
    return sorted(scored, key=lambda x: x["elasticity"], reverse=True)


def exposure_weighted_rank(companies, exposures=None):
    """
    按 暴露度 × 弹性 综合排名
    """
    if exposures is None:
        return companies
    ranked = []
    for c in companies:
        exp = exposures.get(c["symbol"], 1.0)
        ranked.append({**c,
                       "exposure": exp,
                       "composite": round((c.get("elasticity") or 0) * exp, 2)})
    return sorted(ranked, key=lambda x: x["composite"], reverse=True)
