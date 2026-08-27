"""Backtest：历史回测框架（Detailed Technical Design Phase 9）
验证 Driver → Financial → Stock 的预测有效性。
方法：对历史每个时点，用当时的指标值 + 财务驱动系数预测 EPS/营收，
与真实财务数据对比，评估预测误差；再对比预测方向与股价实际涨跌。
"""
import sys
from datetime import datetime

sys.path.append("/home/admin/stock_agent")

from data.repositories import factor_repo
from data.repositories.mysql_db import get_conn


def _run_driver_predictions(symbol, indicator_code, metric, periods):
    """用 financial_driver（base_value + impact_coefficient）预测各期指标值"""
    from data.repositories import factor_repo as fr
    from data.repositories import graph_repo
    comp = graph_repo.get_company(symbol=symbol)
    if not comp:
        return {"error": f"company not found: {symbol}"}
    rows = fr.get_financial_drivers(symbol=symbol, impact_metric=metric)
    predictions = []
    for p in periods:
        inds = fr.get_indicators(symbol=symbol, indicator_code=indicator_code)
        # 找该期指标
        row = next((r for r in inds if str(r["period"]).startswith(p[:4])), None)
        if not row:
            continue
        for d in rows:
            base = d["base_value"]
            if base is None or not d["impact_coefficient"]:
                continue
            growth = (float(row["value"]) - float(base)) / float(base)
            impact = growth * float(d["impact_coefficient"])
            predictions.append({
                "period": p, "driver": d["driver_name"],
                "indicator_value": float(row["value"]), "base_value": float(base),
                "growth_pct": round(growth * 100, 2),
                "predicted_impact_pct": round(impact * 100, 2),
                "impact_direction": d["impact_direction"],
            })
    return {"symbol": symbol, "metric": metric, "predictions": predictions,
            "count": len(predictions)}


def _backtest_direction(symbol, days=120):
    """方向有效性：驱动预测方向 vs 股价实际涨跌方向
    对每个驱动，取指标当期 vs base 的变动方向；对比区间股价涨跌方向。
    """
    from data.adapters import stock_service
    from data.repositories import factor_repo as fr
    rows = fr.get_financial_drivers(symbol=symbol)
    hist = stock_service.get_history(symbol, days=days)
    bars = hist.get("bars", [])
    if len(bars) < 20:
        return {"symbol": symbol, "error": "历史数据不足"}
    start_price = bars[0]["close"]
    end_price = bars[-1]["close"]
    actual_dir = 1 if end_price >= start_price else -1
    actual_return = (end_price - start_price) / start_price * 100 if start_price else 0

    results = []
    for d in rows:
        base = d["base_value"]
        ind_id = d.get("indicator_id")
        if base is None or not ind_id:
            continue
        inds = fr.get_indicators(industry_id=None, indicator_code=None)
        ind_row = next((r for r in inds if r["id"] == ind_id), None)
        if not ind_row or ind_row["value"] is None:
            continue
        growth = (float(ind_row["value"]) - float(base)) / float(base)
        predicted_dir = 1 if growth * (1 if d["impact_direction"] == "positive" else -1) > 0 else -1
        results.append({
            "driver": d["driver_name"], "impact_metric": d["impact_metric"],
            "indicator_growth_pct": round(growth * 100, 2),
            "predicted_dir": predicted_dir,
            "actual_dir": actual_dir,
            "hit": predicted_dir == actual_dir,
        })
    hits = sum(1 for r in results if r["hit"])
    return {"symbol": symbol, "days": days, "actual_return_pct": round(actual_return, 2),
            "drivers": results, "hit_rate": round(hits / len(results), 2) if results else None,
            "count": len(results)}


def backtest(symbols=None, days=120):
    """跑回测：方向有效性为主，附驱动预测明细"""
    from jobs.news_update import load_watchlist
    symbols = symbols or load_watchlist()
    out = []
    for symbol in symbols:
        try:
            out.append(_backtest_direction(symbol, days=days))
        except Exception as e:
            out.append({"symbol": symbol, "error": str(e)})
    ok = [r for r in out if "error" not in r]
    avg_hit = sum(r["hit_rate"] or 0 for r in ok) / len(ok) if ok else None
    return {"results": out, "avg_hit_rate": avg_hit, "count": len(out)}


def backtest_metric(symbol, indicator_code="dram_contract_price", metric="revenue",
                    periods=("2024", "2025", "2026")):
    """按指标分期预测财务影响（回测指标 → 财务映射）"""
    return _run_driver_predictions(symbol, indicator_code, metric, periods)


if __name__ == "__main__":
    print(backtest())
