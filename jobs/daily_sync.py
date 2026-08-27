"""Intelligence Graph 定时任务：每日全链路研报生成
- 08:45 跑 watchlist 的 Stock-First 全链路 + LLM 研报摘要
- 60min 刷新一次行业指标驱动的弹性排名（可选）
"""
import sys
sys.path.append("/home/admin/stock_agent")

from jobs.news_update import load_watchlist
from app.use_cases import stock_first, factor_first
from ai.analyst import summarize


def run_daily_intelligence_report(symbols=None):
    """对 watchlist 每只股票跑 Stock-First + 研报摘要，落库 stock_analysis"""
    from data.repositories import mysql_db as db
    symbols = symbols or load_watchlist()
    results = []
    for symbol in symbols:
        try:
            sf = stock_first.analyze(symbol, with_valuation=True, persist=True)
            report = summarize(stock_first_result=sf, symbol=symbol)
            db.save_analysis(symbol, report, analysis_type="intelligence", model="intelligence-v1")
            results.append({"symbol": symbol, "report": report.get("report", "")[:80],
                            "error": None})
        except Exception as e:
            results.append({"symbol": symbol, "report": None, "error": str(e)})
    print(f"[daily_sync] 完成 {len(results)} 只，失败 "
          f"{sum(1 for r in results if r['error'])}")
    return {"results": results, "count": len(results)}


def run_daily_factor_scan():
    """因子扫描：DRAM 合约价 / AI 眼镜出货量 / 云资本开支 的受益排名"""
    out = {}
    for ind_name in ("dram_contract_price", "shipment", "capex"):
        try:
            r = factor_first.analyze_indicator(indicator_name=ind_name)
            if "error" not in r:
                out[ind_name] = [{"symbol": x["symbol"], "metric": x["impact_metric"],
                                  "impact_pct": x.get("metric_impact_pct")}
                                 for x in r["ranking"][:5]]
        except Exception as e:
            out[ind_name] = {"error": str(e)}
    print(f"[daily_sync] 因子扫描完成: {list(out.keys())}")
    return out


if __name__ == "__main__":
    run_daily_intelligence_report()
