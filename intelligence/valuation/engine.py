"""Valuation Engine：PE / PS / DCF / EV-EBITDA / 目标价
Agent 流程第 11 步。基于财务模型情景输出估值区间。
"""
import sys
sys.path.append("/home/admin/stock_agent")

from intelligence.repositories import forecast_repo, graph_repo
from intelligence.financial_model import engine as fm_engine


def estimate(symbol, period="2026E", persist=True):
    """估值：情景 EPS × 行业 PE → 目标价区间
    PE 优先取基本面 pe；无则用默认区间（成长 25-35，稳健 15-25）。
    """
    from intelligence.company.profile import profile
    from intelligence.repositories import mysql_db as db

    prof = profile(symbol=symbol)
    if "error" in prof:
        return prof
    company_id = prof["company_id"]

    pe = None
    for f in db.get_fundamentals(symbol):
        if f["metric"] == "pe" and f["value"]:
            pe = float(f["value"])
            break

    scenarios = fm_engine.run_scenarios(symbol, period=period, persist=persist)
    if "error" in scenarios:
        return scenarios

    # 行业属性粗略决定 PE band
    sector = (prof.get("sector") or "").lower()
    if any(k in sector for k in ("tech", "semiconductor", "software")):
        pe_lo, pe_hi = 25.0, 35.0
    else:
        pe_lo, pe_hi = 15.0, 25.0

    out = {}
    for sc, v in scenarios["scenarios"].items():
        eps = v["eps"]
        lo = round(eps * pe_lo, 2)
        hi = round(eps * pe_hi, 2)
        out[sc] = {"eps": eps, "pe_low": pe_lo, "pe_high": pe_hi,
                   "target_low": lo, "target_high": hi}
        if persist:
            forecast_repo.upsert_valuation(
                company_id, "PE", hi, scenario=sc, target_price=hi,
                as_of=None, model="intelligence-v1")
            forecast_repo.upsert_valuation(
                company_id, "PE_low", lo, scenario=sc, target_price=lo,
                as_of=None, model="intelligence-v1")

    return {"symbol": symbol, "period": period, "current_pe": pe,
            "price_band": out}
