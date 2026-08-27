"""industry_sync：真实行业数据源同步编排（替换种子数据）
数据源：
- SEC EDGAR XBRL：公司真实财报（营收/毛利/净利/EPS/现金流）→ stock_fundamental + company_forecast + financial_model_line
- FRED：半导体产出/PPI/电子零售/宏观序列 → industry_indicator
- Nasdaq API：真实基本面（已有 stock_service 兜底）
"""
import sys
sys.path.append("/home/admin/stock_agent")

from data.collectors import sec_financials, fred_industry


def run_industry_sync(symbols=None):
    """完整同步：SEC 财务 + FRED 行业指标"""
    sec = sec_financials.sync_watchlist(symbols=symbols)
    fred = fred_industry.sync_all(persist=True)
    return {
        "sec_financials": {"ok": sum(1 for r in sec.get("results", []) if "error" not in r),
                           "total": sec.get("count", 0)},
        "fred_series": {"ok": sum(1 for r in fred.get("results", []) if "error" not in r),
                        "total": fred.get("count", 0)},
    }


if __name__ == "__main__":
    print(run_industry_sync())
