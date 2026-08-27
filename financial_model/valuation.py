"""Valuation Engine：PE / PS / EV_EBITDA / DCF / 目标价
Agent 流程第 11 步。基于财务模型情景输出估值区间。
v2：valuation 表 model_type/fair_value/upside/assumption_json。
"""
import sys
sys.path.append("/home/admin/stock_agent")

from data.repositories import forecast_repo, graph_repo
from financial_model.scenario import run_scenarios as _run_scenarios


def estimate(symbol, period="2026", persist=True):
    """估值：情景 EPS × 行业 PE → 目标价区间
    PE 优先取基本面 pe；无则用默认区间（成长 25-35，稳健 15-25）。
    """
    from domain.company.profile import profile
    from data.repositories import mysql_db as db

    prof = profile(symbol=symbol)
    if "error" in prof:
        return prof
    company_id = prof["company_id"]

    pe = None
    for f in db.get_fundamentals(symbol):
        if f["metric"] == "pe" and f["value"]:
            pe = float(f["value"])
            break

    scenarios = _run_scenarios(symbol, period=period, persist=persist)
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
                company_id, "PE", hi, scenario=sc,
                valuation_date=None, upside=round((hi / eps - pe) / (pe or 1), 6) if pe else None,
                assumption_json={"eps": eps, "pe": pe_hi, "method": "PE"},
                model_version="intelligence-v1")
            forecast_repo.upsert_valuation(
                company_id, "PE_low", lo, scenario=sc,
                valuation_date=None, upside=None,
                assumption_json={"eps": eps, "pe": pe_lo, "method": "PE"},
                model_version="intelligence-v1")

    return {"symbol": symbol, "period": period, "current_pe": pe,
            "price_band": out}


def get_valuation_records(symbol, model_type=None):
    """读取已保存的估值记录（含 assumption_json 解析）"""
    rows = forecast_repo.get_valuations(symbol=symbol, model_type=model_type)
    out = []
    for r in rows:
        out.append({
            "id": r["id"], "company": r["company_name"], "symbol": r["stock_symbol"],
            "model_type": r["model_type"], "valuation_date": r["valuation_date"],
            "scenario": r["scenario"], "fair_value": float(r["fair_value"]) if r["fair_value"] is not None else None,
            "upside": float(r["upside"]) if r["upside"] is not None else None,
            "assumptions": r["assumption_json"],
        })
    return {"symbol": symbol, "count": len(out), "valuations": out}
