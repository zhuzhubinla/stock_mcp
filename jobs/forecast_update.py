"""forecast_update：预测与估值更新（第 23 节：月频出货量/价格/库存、季频模型）
刷新行业指标 → 财务驱动 → 公司预测 → 估值。
"""
import sys
sys.path.append("/home/admin/stock_agent")

from jobs.news_update import load_watchlist
from data.repositories import forecast_repo
from domain.factor.engine import indicators, supply_demand
from financial_model.scenario import run_scenarios
from financial_model.valuation import estimate


def run_forecast_update(symbols=None):
    """重算 watchlist 的情景 EPS 与估值，落库"""
    symbols = symbols or load_watchlist()
    results = []
    for symbol in symbols:
        try:
            scen = run_scenarios(symbol, persist=True)
            val = estimate(symbol, persist=True)
            results.append({"symbol": symbol,
                            "scenarios": scen.get("scenarios"),
                            "price_band": val.get("price_band", {}).get("base")})
        except Exception as e:
            results.append({"symbol": symbol, "error": str(e)})
    print(f"[forecast_update] 完成 {len(results)} 只")
    return {"results": results, "count": len(results)}


def run_industry_snapshot(industry_id=None):
    """行业快照：指标 + 供需 + 预测（月频数据刷新入口）"""
    inds = indicators(industry_id=industry_id)
    sd = supply_demand(industry_id=industry_id)
    forecasts = forecast_repo.get_industry_forecasts(industry_id=industry_id)
    return {"indicators": inds, "supply_demand": sd,
            "forecasts": [{"indicator_code": f["indicator_code"], "period": str(f["period"]),
                           "scenario": f["scenario"], "value": float(f["value"]) if f["value"] is not None else None}
                          for f in forecasts]}


if __name__ == "__main__":
    run_forecast_update()
