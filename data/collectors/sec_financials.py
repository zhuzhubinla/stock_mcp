"""SEC Financials Collector：从 EDGAR XBRL companyfacts 采集公司真实财报
（Detailed Technical Design 第 23 节：季频财报同步）
数据源：https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json（免费无 key）
指标：Revenues / GrossProfit / OperatingIncomeLoss / NetIncomeLoss /
      EarningsPerShareDiluted / NetCashProvidedByUsedInOperatingActivities
写入：stock_fundamental（真实值）+ company_forecast（actual 情景）+ financial_model_line
"""
import sys
import json
import requests
from datetime import datetime

sys.path.append("/home/admin/stock_agent")

from data.repositories import mysql_db as db, forecast_repo, graph_repo
from config import SEC_USER_AGENT

SEC_HEADERS = {"User-Agent": SEC_USER_AGENT}
TICKER_CIK_URL = "https://www.sec.gov/files/company_tickers.json"

# 需要同步的财务概念 → 规范指标名
METRIC_MAP = {
    "Revenues": "revenue",
    "GrossProfit": "gross_profit",
    "OperatingIncomeLoss": "operating_income",
    "NetIncomeLoss": "net_income",
    "EarningsPerShareDiluted": "eps",
    "NetCashProvidedByUsedInOperatingActivities": "operating_cash_flow",
    "PaymentsToAcquirePropertyPlantAndEquipment": "capex",
}

_cik_cache = None


def _ticker_to_cik():
    """ticker → CIK 映射（全市场）"""
    global _cik_cache
    if _cik_cache is not None:
        return _cik_cache
    r = requests.get(TICKER_CIK_URL, headers=SEC_HEADERS, timeout=30)
    r.raise_for_status()
    data = r.json()
    _cik_cache = {v["ticker"]: str(v["cik_str"]).zfill(10) for v in data.values()}
    return _cik_cache


def get_annual_metrics(symbol):
    """拉取公司年度财务（10-K 口径）：返回 {metric: {year: value}}"""
    cik = _ticker_to_cik().get(symbol.upper())
    if not cik:
        return {"error": f"ticker 不在 SEC 映射表: {symbol}"}
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
    r = requests.get(url, headers=SEC_HEADERS, timeout=30)
    r.raise_for_status()
    facts = r.json().get("facts", {}).get("us-gaap", {})

    out = {}
    for gaap_name, metric in METRIC_MAP.items():
        node = facts.get(gaap_name)
        if not node:
            continue
        by_year = {}
        for unit_rows in node.get("units", {}).values():
            for row in unit_rows:
                if row.get("form") != "10-K" or row.get("fp") != "FY":
                    continue
                end = row.get("end", "")
                year = end[:4] if len(end) >= 4 else None
                if not year:
                    continue
                # 取每年最后一条（全年累计）
                if year not in by_year or row.get("end", "") >= by_year[year].get("end", ""):
                    by_year[year] = {"value": row["val"], "end": row.get("end")}
        out[metric] = {y: v["value"] for y, v in by_year.items()}
    return out


def sync_company(symbol, persist=True, years=("2024", "2025", "2026")):
    """同步一家公司：真实财报 → stock_fundamental + company_forecast + financial_model_line"""
    company = graph_repo.get_company(symbol=symbol.upper())
    if not company:
        return {"symbol": symbol, "error": "公司未注册，先跑 seed"}
    data = get_annual_metrics(symbol)
    if "error" in data:
        return {"symbol": symbol, "error": data["error"]}
    if not data:
        return {"symbol": symbol, "error": "无 10-K 数据"}

    saved = {"fundamental": 0, "forecast": 0, "model_line": 0}
    # 1) stock_fundamental：最新一年真实值
    for metric, by_year in data.items():
        if not by_year:
            continue
        latest_year = max(by_year)
        if persist:
            db.upsert_fundamental(symbol, metric, by_year[latest_year],
                                  period=f"{latest_year}A", source="sec-xbrl")
            saved["fundamental"] += 1

    # 2) company_forecast：各年 actual 情景
    if persist:
        for metric, by_year in data.items():
            for y, v in by_year.items():
                if y not in years:
                    continue
                forecast_repo.upsert_company_forecast(
                    company["id"], metric, y, v, scenario="actual",
                    confidence=1.0, model_version="sec-xbrl")
                saved["forecast"] += 1

    # 3) financial_model_line：写入最新一年作为 base 期
    if persist:
        model_id = forecast_repo.upsert_financial_model(
            company["id"], name=f"{symbol} Financial Model", model_type="bottom_up",
            version="sec-xbrl", base_period=f"{max(data.get('revenue', {}))}-12-31" if data.get("revenue") else None,
            forecast_start="2026-01-01", forecast_end="2027-12-31")
        for metric, by_year in data.items():
            if not by_year:
                continue
            y = max(by_year)
            forecast_repo.upsert_financial_model_line(
                model_id, metric, f"{y}-12-31", by_year[y],
                assumption_type="actual", formula=f"SEC XBRL {metric} FY{y}")
            saved["model_line"] += 1

    summary = {m: {y: v for y, v in by_year.items()} for m, by_year in data.items()}
    return {"symbol": symbol, "saved": saved, "latest": summary}


def sync_watchlist(symbols=None):
    """同步 watchlist 全部公司"""
    from jobs.news_update import load_watchlist
    symbols = symbols or load_watchlist()
    results = []
    for s in symbols:
        try:
            results.append(sync_company(s))
        except Exception as e:
            results.append({"symbol": s, "error": str(e)})
    ok = [r for r in results if "error" not in r]
    print(f"[sec_sync] 完成 {len(ok)}/{len(results)} 家公司")
    return {"results": results, "count": len(results)}


if __name__ == "__main__":
    print(json.dumps(sync_watchlist(), ensure_ascii=False, indent=1)[:2000])
