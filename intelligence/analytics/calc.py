"""Analytics：同比/环比/CAGR/供需缺口/弹性评分
对应文档第 13 节职责边界中的 Analytics 层。
"""
import sys
sys.path.append("/home/admin/stock_agent")


def yoy(series, key="value", period_key="period"):
    """同比：按 period 字符串（如 2025Q1）推算上年同期"""
    rows = sorted(series, key=lambda r: r.get(period_key) or "")
    out = []
    lookup = {r.get(period_key): r for r in rows}
    for r in rows:
        p = r.get(period_key)
        prev = _prev_period(p)
        base = lookup.get(prev)
        cur = r.get(key)
        if cur is not None and base and base.get(key):
            out.append({
                "period": p, "value": cur, "prev_period": prev,
                "prev_value": base[key],
                "yoy_pct": round((cur - base[key]) / base[key] * 100, 2),
            })
        else:
            out.append({"period": p, "value": cur, "prev_period": prev,
                        "prev_value": base[key] if base else None, "yoy_pct": None})
    return out


def _prev_period(p):
    """'2025Q1' → '2024Q1'；'2025' → '2024'；'2025-01' → '2024-01'"""
    if not p:
        return None
    if p.endswith("Q") or len(p) == 6 and p[4] == "Q":
        try:
            y, q = int(p[:4]), int(p[5])
            return f"{y-1}Q{q}"
        except ValueError:
            return None
    if len(p) == 4 and p.isdigit():
        return str(int(p) - 1)
    if len(p) == 7 and p[4] == "-":
        try:
            y, m = int(p[:4]), int(p[5:7])
            return f"{y-1}-{m:02d}"
        except ValueError:
            return None
    return None


def cagr(start_value, end_value, periods):
    """复合增长率；periods 为年数或期数"""
    if not start_value or not end_value or start_value <= 0 or periods <= 0:
        return None
    return round(((end_value / start_value) ** (1 / periods) - 1) * 100, 2)


def gap_ratio(demand, production):
    """供需缺口率：缺口占需求比例"""
    if not demand:
        return None
    return round((demand - production) / demand * 100, 2) if production is not None else None


def elasticity_score(impacts):
    """弹性评分：对 Factor-First 的驱动影响排序
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
    """按 暴露度 × 弹性 综合排名"""
    if exposures is None:
        return companies
    ranked = []
    for c in companies:
        exp = exposures.get(c["symbol"], 1.0)
        ranked.append({**c, "exposure": exp,
                       "composite": round((c.get("elasticity") or 0) * exp, 2)})
    return sorted(ranked, key=lambda x: x["composite"], reverse=True)
