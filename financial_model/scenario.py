"""Financial Model Engine：把 Driver 转换成公司财务预测
Agent 流程第 9 步（Financial Model）+ 第 10 步（Scenario）。
Revenue = Segment1 Shipment × Share × ASP + Segment2 ... + Other（文档第 21 节）
v2：financial_model（模型头）+ financial_model_line（metric/period/value/formula）
"""
import sys
sys.path.append("/home/admin/stock_agent")

from data.adapters import stock_service  # noqa: F401  (行情数据源)
from data.repositories import graph_repo, forecast_repo
from domain.factor import engine as factor_engine  # noqa


def run_scenarios(symbol, base_eps=None, bull_mult=1.3, bear_mult=0.7,
                  period="2026", persist=True):
    """Bull/Base/Bear 情景：基于当前财务模型 + 行业驱动方向
    Base = 最新 EPS（无则用财务模型数据）；Bull/Bear 按乘数 ± 驱动系数修正
    结果写入 company_forecast（scenario 列）+ financial_model_line（eps 行）。
    """
    from domain.company.profile import profile
    from domain.factor.engine import drivers
    prof = profile(symbol=symbol)
    if "error" in prof:
        return prof
    company_id = prof["company_id"]

    # 取已有 base 情景预测
    existing = forecast_repo.get_company_forecasts(company_id=company_id, metric="eps",
                                                   period=period, scenario="base")
    if base_eps is None and existing:
        base_eps = existing[0].get("value")
    # 基本面兜底：从 stock_fundamental 拿 eps；再兜底 price/pe 估算
    if base_eps is None:
        from data.repositories import mysql_db as db
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
            forecast_repo.upsert_company_forecast(
                company_id, "eps", period, v["eps"], scenario=sc,
                low_value=round(v["eps"] * 0.85, 4), high_value=round(v["eps"] * 1.15, 4),
                confidence=0.7, model_version="intelligence-v1")
    return result
