"""Financial Model Engine：把 Driver 转换成公司财务预测
Agent 流程第 9 步（Financial Model）+ 第 10 步（Scenario）。
Revenue = Segment1 Shipment × Share × ASP + Segment2 ... + Other（文档第 11 节）
"""
import sys
sys.path.append("/home/admin/stock_agent")

from services import stock_service
from intelligence.repositories import graph_repo, forecast_repo
from intelligence.factor import engine as factor_engine


def build_revenue_model(symbol):
    """按业务分拆构建营收模型：
    每个 segment 找到对应行业指标（出货量/ASP），
    revenue_segment = indicator_value × share × asp（若有）
    """
    from intelligence.business.decomposer import decompose
    segs = decompose(symbol=symbol).get("segments", [])
    if not segs:
        return {"symbol": symbol, "error": "无业务分拆数据"}

    model = []
    total = 0.0
    for s in segs:
        industry_id = s.get("industry_id")
        seg_rev = None
        if industry_id:
            indicators = factor_engine.indicators(industry_id=industry_id)
            by_name = {}
            for ind in indicators:
                by_name.setdefault(ind["indicator"], []).append(ind)
            shipment = by_name.get("shipment") or by_name.get("出货量")
            asp = by_name.get("asp") or by_name.get("ASP")
            if shipment and asp:
                # 取最新一期
                ship = sorted(shipment, key=lambda x: x["period"] or "")[-1]
                a = sorted(asp, key=lambda x: x["period"] or "")[-1]
                seg_rev = (ship["value"] or 0) * (a["value"] or 0)
        model.append({
            "segment": s["name"], "industry": s.get("industry"),
            "revenue_share": s.get("revenue_share"),
            "estimated_revenue": seg_rev,
            "indicators": [i["indicator"] for i in factor_engine.indicators(industry_id=industry_id)]
                         if industry_id else [],
        })
        if seg_rev:
            total += seg_rev
    return {"symbol": symbol, "segments": model, "total_estimated": round(total, 2),
            "method": "shipment × ASP（分业务）"}


def run_scenarios(symbol, base_eps=None, bull_mult=1.3, bear_mult=0.7,
                  period="2026E", persist=True):
    """Bull/Base/Bear 情景：基于当前财务模型 + 行业驱动方向
    Base = 最新 EPS（无则用财务模型数据）；Bull/Bear 按乘数 ± 驱动系数修正
    """
    from intelligence.company.profile import profile
    from intelligence.factor.engine import drivers
    prof = profile(symbol=symbol)
    if "error" in prof:
        return prof
    company_id = prof["company_id"]

    # 取已有 base 财务模型
    existing = forecast_repo.get_financial_models(company_id=company_id, period=period)
    base_eps = base_eps
    if base_eps is None and existing:
        base_eps = existing[0].get("eps")
    # 基本面兜底：从 stock_fundamental 拿 eps；再兜底 price/pe 估算
    if base_eps is None:
        from database import mysql_db as db
        pe, price = None, None
        for f in db.get_fundamentals(symbol):
            if f["metric"] == "eps" and f["value"]:
                base_eps = float(f["value"])
                break
            if f["metric"] == "pe" and f["value"]:
                pe = float(f["value"])
        if base_eps is None:
            try:
                quote = stock_service.get_quote(symbol)
                price = quote.get("price")
            except Exception:
                price = None
            if price and pe:
                base_eps = round(price / pe, 4)
        # 终极兜底：无 PE 时按行业默认 PE（科技 30）反推
        if base_eps is None:
            try:
                quote = stock_service.get_quote(symbol)
                price = quote.get("price")
            except Exception:
                price = None
            if price:
                sector = (prof.get("sector") or "").lower()
                default_pe = 30.0 if any(k in sector for k in ("tech", "semiconductor", "software")) else 20.0
                base_eps = round(price / default_pe, 4)
    if base_eps is None:
        return {"symbol": symbol, "error": "缺少 EPS 基准（fundamentals/财务模型均无）"}
    base_eps = float(base_eps)

    # 驱动修正：正驱动多 → bull 更高
    drv = drivers(symbol=symbol)
    pos = sum(1 for d in drv if d["impact_direction"] == "positive")
    neg = sum(1 for d in drv if d["impact_direction"] == "negative")
    bias = (pos - neg) * 0.02  # 每个净正向驱动 +2% 弹性

    scenarios = {
        "bull": {"eps": round(base_eps * (bull_mult + bias), 4), "label": "乐观"},
        "base": {"eps": round(base_eps, 4), "label": "中性"},
        "bear": {"eps": round(base_eps * (bear_mult - bias), 4), "label": "悲观"},
    }
    result = {"symbol": symbol, "period": period, "base_eps": base_eps,
              "scenarios": scenarios}
    if persist:
        for sc, v in scenarios.items():
            forecast_repo.upsert_financial_model(
                company_id, sc, period, eps=v["eps"], model="intelligence-v1")
    return result
