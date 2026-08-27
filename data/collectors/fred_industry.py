"""FRED Industry Collector：美联储 FRED 公开序列 → 行业指标
（Detailed Technical Design 第 23 节：月频行业高频指标同步）
免费无 key：https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}
"""
import sys
import requests
from datetime import datetime

sys.path.append("/home/admin/stock_agent")

from data.repositories import factor_repo, graph_repo, forecast_repo

# 序列配置：FRED series → (indicator_code, indicator_name, unit, frequency, 映射行业)
FRED_SERIES = [
    # 半导体产出指数（NAICS 3341）
    ("IPG3341S", "semiconductor_production_index", "半导体产出指数", "指数", "monthly", "semiconductor"),
    # 半导体出厂价格指数（PPI）
    ("PCU334111334111", "semiconductor_ppi", "半导体出厂价格指数", "指数", "monthly", "semiconductor"),
    # 电子零售销售（消费者电子需求代理）
    ("RSAFS", "electronics_retail_sales", "电子零售销售", "百万美元", "monthly", "edge_ai"),
    # 宏观：工业产出 / CPI / 消费者信心（挂 macro 行业）
    ("INDPRO", "industrial_production", "工业产出", "指数", "monthly", "macro"),
    ("CPIAUCSL", "cpi", "消费者物价指数", "指数", "monthly", "macro"),
    ("UMCSENT", "consumer_sentiment", "消费者信心", "指数", "monthly", "macro"),
]

CACHE = {}


def fetch_fred(series_id):
    """拉取 FRED 序列 CSV → [(date_str, value)]"""
    if series_id in CACHE:
        return CACHE[series_id]
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    rows = []
    for line in r.text.strip().splitlines()[1:]:
        parts = line.split(",")
        if len(parts) != 2:
            continue
        date_s, val_s = parts
        try:
            val = float(val_s)
        except ValueError:
            continue
        rows.append((date_s, val))
    CACHE[series_id] = rows
    return rows


def sync_series(series_id, indicator_code, indicator_name, unit, frequency, industry_code,
                persist=True, max_points=60):
    """同步一条序列到 industry_indicator"""
    industry = graph_repo.get_industry(code=industry_code)
    if not industry:
        return {"series": series_id, "error": f"行业不存在: {industry_code}"}
    rows = fetch_fred(series_id)
    if not rows:
        return {"series": series_id, "error": "无数据"}

    src = forecast_repo.upsert_source(f"FRED:{series_id}", source_type="api",
                                      provider="FRED", base_url="https://fred.stlouisfed.org",
                                      reliability_score=0.9)
    count = 0
    for date_s, val in rows[-max_points:]:
        if persist:
            factor_repo.upsert_indicator(industry["id"], indicator_code, indicator_name,
                                         val, unit=unit, period=date_s[:10],
                                         frequency=frequency, source_id=src)
            count += 1
    return {"series": series_id, "industry": industry_code, "points": count,
            "latest_date": rows[-1][0], "latest_value": rows[-1][1]}


def sync_all(persist=True):
    """同步所有配置的 FRED 序列"""
    results = []
    for series_id, code, name, unit, freq, ind_code in FRED_SERIES:
        try:
            results.append(sync_series(series_id, code, name, unit, freq, ind_code,
                                       persist=persist))
        except Exception as e:
            results.append({"series": series_id, "error": str(e)})
    ok = [r for r in results if "error" not in r]
    print(f"[fred_sync] 完成 {len(ok)}/{len(results)} 条序列")
    return {"results": results, "count": len(results)}


if __name__ == "__main__":
    import json
    print(json.dumps(sync_all(), ensure_ascii=False, indent=1)[:1500])
