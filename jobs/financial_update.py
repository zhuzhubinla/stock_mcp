"""financial_update：财务数据更新（第 23 节：季频财报、业务 Segment、收入利润模型）
从基本面数据源刷新公司财务指标，并重建 Revenue/EPS 模型。
"""
import sys
sys.path.append("/home/admin/stock_agent")

from jobs.news_update import load_watchlist
from data.adapters import stock_service
from data.repositories import forecast_repo
from financial_model.revenue import build_revenue_model
from financial_model.scenario import run_scenarios


def run_financial_update(symbols=None):
    """刷新基本面 + 重建财务模型 + 情景 EPS"""
    symbols = symbols or load_watchlist()
    results = []
    for symbol in symbols:
        try:
            fundamentals = stock_service.get_fundamentals(symbol, force_refresh=False)
            rev = build_revenue_model(symbol, persist=True)
            scen = run_scenarios(symbol, persist=True)
            results.append({"symbol": symbol, "fundamentals": len(fundamentals.get("metrics", [])),
                            "revenue_model": rev.get("total_estimated"),
                            "scenarios": scen.get("scenarios")})
        except Exception as e:
            results.append({"symbol": symbol, "error": str(e)})
    print(f"[financial_update] 完成 {len(results)} 只")
    return {"results": results, "count": len(results)}


if __name__ == "__main__":
    run_financial_update()
